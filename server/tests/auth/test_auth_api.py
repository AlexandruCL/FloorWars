"""Auth endpoints end to end against PostGIS and Valkey (skipped when they are not configured)."""

import json
import logging
import os
import time
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.auth import otp
from app.auth.tokens import AccessTokens, b64url_decode, b64url_encode
from app.config import ConfigError, Settings
from app.main import create_app
from tests.helpers import (
    TEST_JWT_KEY,
    auth_headers,
    device,
    insert_user,
    last_code,
    new_email,
    sign_in,
)

PROBLEM_JSON = "application/problem+json"


def _sql(client: TestClient, statement: str, **params: object) -> None:
    with client.app.state.sessionmaker() as db:
        db.execute(text(statement), params)
        db.commit()


def _scalar(client: TestClient, statement: str, **params: object) -> object:
    with client.app.state.sessionmaker() as db:
        return db.execute(text(statement), params).scalar_one()


def _verify(client: TestClient, email: str, code: str, **extra: object) -> object:
    body = {"email": email, "code": code, "device": device(), **extra}
    return client.post("/v1/auth/verify", json=body)


def _whoami(client: TestClient, access_token: str) -> object:
    return client.get("/test/whoami", headers={"Authorization": f"Bearer {access_token}"})


def _wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


# Full flow.


def test_full_flow(client: TestClient) -> None:
    email = new_email()
    device_id = uuid.uuid4()

    response = client.post("/v1/auth/otp", json={"email": email.upper()})
    assert response.status_code == 202
    assert response.content == b""

    code = last_code(client.app, email)
    response = client.post(
        "/v1/auth/verify",
        json={
            "email": email,
            "code": code,
            "device": device(device_id),
            "accept_terms": True,
            "confirm_adult": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    pair = response.json()
    assert pair["token_type"] == "Bearer"  # noqa: S105
    assert pair["expires_in"] == 900
    assert pair["refresh_expires_in"] == 30 * 24 * 3600

    me = _whoami(client, pair["access_token"])
    assert me.status_code == 200
    assert me.json()["email"] == email

    assert _scalar(client, "SELECT count(*) FROM device WHERE id = :d", d=device_id) == 1
    assert (
        _scalar(
            client,
            'SELECT terms_accepted_at IS NOT NULL AND age_confirmed_at IS NOT NULL FROM "user" '
            "WHERE email = :e",
            e=email,
        )
        is True
    )
    # The challenge is consumed: the same code cannot be used twice.
    assert _verify(client, email, code).status_code == 401

    response = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["refresh_token"] != pair["refresh_token"]
    assert _whoami(client, rotated["access_token"]).status_code == 200


def test_existing_user_signs_in_without_confirmations(client: TestClient) -> None:
    email = new_email()
    with client.app.state.sessionmaker() as db:
        insert_user(db, email)
    client.post("/v1/auth/otp", json={"email": email})
    response = _verify(client, email, last_code(client.app, email))
    assert response.status_code == 200


def test_protected_route_needs_token(client: TestClient) -> None:
    response = client.get("/test/whoami")
    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_headers_helper(client: TestClient) -> None:
    with client.app.state.sessionmaker() as db:
        user_id = insert_user(db, new_email())
    response = client.get("/test/whoami", headers=auth_headers(client.app, user_id))
    assert response.json()["id"] == str(user_id)


# OTP abuse.


def test_wrong_domain_is_403(client: TestClient) -> None:
    response = client.post("/v1/auth/otp", json={"email": "someone@gmail.com"})
    assert response.status_code == 403
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"] == "urn:floorwars:problem:email-domain-not-allowed"


def test_subdomain_is_not_allowed(client: TestClient) -> None:
    response = client.post("/v1/auth/otp", json={"email": "a@evil.student.upt.ro"})
    assert response.status_code == 403


def test_sixth_attempt_is_429(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    code = last_code(client.app, email)
    for _ in range(5):
        assert _verify(client, email, _wrong(code)).status_code == 401
    # Even the right code is refused now.
    response = _verify(client, email, code, accept_terms=True, confirm_adult=True)
    assert response.status_code == 429
    assert _scalar(client, "SELECT attempts FROM otp_challenge WHERE email = :e", e=email) == 5


def test_expired_code_is_401(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    _sql(client, "UPDATE otp_challenge SET expires_at = now() - interval '1 second'")
    code = last_code(client.app, email)
    response = _verify(client, email, code, accept_terms=True, confirm_adult=True)
    assert response.status_code == 401


def test_new_request_supersedes_old_code(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    old = last_code(client.app, email)
    client.post("/v1/auth/otp", json={"email": email})
    new = last_code(client.app, email)
    if old != new:
        assert _verify(client, email, old).status_code == 401
    ok = _verify(client, email, new, accept_terms=True, confirm_adult=True)
    assert ok.status_code == 200


def test_code_is_stored_hashed(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    code = last_code(client.app, email)
    with client.app.state.sessionmaker() as db:
        code_hash, salt = db.execute(
            text("SELECT code_hash, salt FROM otp_challenge WHERE email = :e"), {"e": email}
        ).one()
    assert len(salt) == 16
    assert code_hash == otp.hash_code(salt, code)
    assert code.encode() not in code_hash


@pytest.mark.parametrize(
    ("accept_terms", "confirm_adult"), [(False, False), (True, False), (False, True)]
)
def test_new_account_without_confirmations_is_403(
    client: TestClient, accept_terms: bool, confirm_adult: bool
) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    code = last_code(client.app, email)
    response = _verify(client, email, code, accept_terms=accept_terms, confirm_adult=confirm_adult)
    assert response.status_code == 403
    assert response.json()["type"] == "urn:floorwars:problem:terms-required"
    assert _scalar(client, 'SELECT count(*) FROM "user" WHERE email = :e', e=email) == 0
    # The challenge stays usable: the app can resend with both confirmations.
    ok = _verify(client, email, code, accept_terms=True, confirm_adult=True)
    assert ok.status_code == 200


def test_validation_error_is_problem_without_input(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/verify",
        json={"email": new_email(), "code": "12345x", "device": device(), "extra": 1},
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    assert "12345x" not in response.text
    assert {tuple(e["loc"]) for e in response.json()["errors"]} >= {
        ("body", "code"),
        ("body", "extra"),
    }


def test_rate_limit_per_email_is_429(client: TestClient) -> None:
    email = new_email()
    for _ in range(5):
        assert client.post("/v1/auth/otp", json={"email": email}).status_code == 202
    response = client.post("/v1/auth/otp", json={"email": email})
    assert response.status_code == 429
    assert response.headers["content-type"] == PROBLEM_JSON
    assert int(response.headers["retry-after"]) >= 1


def test_rate_limit_per_ip_is_429(make_app: Callable[..., TestClient]) -> None:
    client = make_app(otp_rate_per_ip_per_hour=2)
    assert client.post("/v1/auth/otp", json={"email": new_email()}).status_code == 202
    assert client.post("/v1/auth/otp", json={"email": new_email()}).status_code == 202
    response = client.post("/v1/auth/otp", json={"email": new_email()})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


def test_otp_without_valkey_is_503(make_app: Callable[..., TestClient]) -> None:
    client = make_app(valkey_url=None)
    assert client.post("/v1/auth/otp", json={"email": new_email()}).status_code == 503


def test_otp_with_unreachable_valkey_is_503(make_app: Callable[..., TestClient]) -> None:
    client = make_app(valkey_url="redis://127.0.0.1:1/0")
    response = client.post("/v1/auth/otp", json={"email": new_email()})
    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON


# Refresh tokens.


def test_refresh_reuse_revokes_family(client: TestClient) -> None:
    first = sign_in(client, new_email())
    second = client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200
    newer = second.json()["refresh_token"]

    # Reusing the rotated token is theft: 401 and the whole family is revoked ...
    reuse = client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    assert reuse.headers["content-type"] == PROBLEM_JSON
    # ... so the newer token fails too.
    assert client.post("/v1/auth/refresh", json={"refresh_token": newer}).status_code == 401
    assert _scalar(client, "SELECT count(*) FROM refresh_token WHERE revoked_at IS NULL") == 0


def test_refresh_unknown_and_expired_are_401(client: TestClient) -> None:
    unknown = client.post("/v1/auth/refresh", json={"refresh_token": "nope"})
    assert unknown.status_code == 401
    pair = sign_in(client, new_email())
    _sql(client, "UPDATE refresh_token SET expires_at = now() - interval '1 second'")
    expired = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert expired.status_code == 401


def test_refresh_token_stored_hashed(client: TestClient) -> None:
    pair = sign_in(client, new_email())
    raw = pair["refresh_token"]
    assert len(b64url_decode(raw)) == 32
    with client.app.state.sessionmaker() as db:
        hashes = db.execute(text("SELECT token_hash FROM refresh_token")).scalars().all()
    assert raw.encode() not in hashes
    assert all(len(h) == 32 for h in hashes)


# Forged access tokens.


def _user_token(client: TestClient) -> str:
    return str(sign_in(client, new_email())["access_token"])


def test_forged_signature_is_401(client: TestClient) -> None:
    header, claims, signature = _user_token(client).split(".")
    payload = json.loads(b64url_decode(claims))
    payload["sub"] = str(uuid.uuid4())
    forged = f"{header}.{b64url_encode(json.dumps(payload).encode())}.{signature}"
    assert _whoami(client, forged).status_code == 401


def test_alg_none_is_401(client: TestClient) -> None:
    _, claims, _ = _user_token(client).split(".")
    header = b64url_encode(b'{"alg":"none","typ":"JWT"}')
    assert _whoami(client, f"{header}.{claims}.").status_code == 401


def test_wrong_audience_is_401(client: TestClient) -> None:
    user_id = uuid.UUID(_whoami(client, _user_token(client)).json()["id"])
    other = AccessTokens(bytes.fromhex(TEST_JWT_KEY), "another-api", 900).issue(user_id)
    assert _whoami(client, other).status_code == 401


def test_expired_access_token_is_401(client: TestClient) -> None:
    user_id = uuid.UUID(_whoami(client, _user_token(client)).json()["id"])
    past = AccessTokens(
        bytes.fromhex(TEST_JWT_KEY), "floorwars-api", 900, clock=lambda: time.time() - 901
    )
    assert _whoami(client, past.issue(user_id)).status_code == 401


# Secrets stay out of logs.


def test_code_and_tokens_never_logged(
    make_app: Callable[..., TestClient],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(otp, "new_code", lambda: "424242")
    client = make_app(mail_backend="log", log_level="DEBUG")
    email = new_email()
    assert client.post("/v1/auth/otp", json={"email": email}).status_code == 202
    _verify(client, email, "000000")  # a wrong attempt is logged nowhere with its code
    response = _verify(client, email, "424242", accept_terms=True, confirm_adult=True)
    assert response.status_code == 200
    pair = response.json()
    client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})

    logs = caplog.text + capsys.readouterr().out
    assert f"otp mail sent to {email}" in logs
    for secret in ("424242", "000000", pair["access_token"], pair["refresh_token"], TEST_JWT_KEY):
        assert secret not in logs


# Startup checks.


ACS = {
    "mail_from": "DoNotReply@example.azurecomm.net",
    "acs_endpoint": "https://example.communication.azure.com",
    "acs_access_key": "Zmxvb3J3YXJzLXRlc3Qta2V5LW5vdC1hLXNlY3JldCE=",  # dummy
}


def test_prod_without_acs_refuses_to_start() -> None:
    with pytest.raises(ConfigError, match="MAIL_BACKEND=acs") as exc:
        create_app(Settings(env="prod", mail_backend="log", jwt_signing_key=TEST_JWT_KEY))
    assert TEST_JWT_KEY not in str(exc.value)
    partial = {k: v for k, v in ACS.items() if k != "acs_access_key"}
    with pytest.raises(ConfigError, match="FLOORWARS_ACS_ACCESS_KEY"):
        create_app(
            Settings(env="prod", mail_backend="acs", jwt_signing_key=TEST_JWT_KEY, **partial)
        )
    with pytest.raises(ConfigError, match="FLOORWARS_JWT_SIGNING_KEY"):
        create_app(Settings(env="prod", mail_backend="acs", **ACS))
    with pytest.raises(ConfigError, match="fake"):
        create_app(Settings(env="staging", mail_backend="fake", jwt_signing_key=TEST_JWT_KEY))
    # Complete production settings start.
    create_app(Settings(env="prod", mail_backend="acs", jwt_signing_key=TEST_JWT_KEY, **ACS))


def test_settings_load_with_only_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The migration container gets only floorwars_database_url (and the environment name)."""
    for name in list(os.environ):
        if name.upper().startswith("FLOORWARS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("FLOORWARS_ENV", "prod")
    monkeypatch.setenv("FLOORWARS_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/floorwars")
    settings = Settings()
    assert settings.database_url is not None
    assert settings.jwt_signing_key is None
    assert settings.qr_hmac_key is None


def test_malformed_keys_rejected_without_echo() -> None:
    with pytest.raises(ValidationError, match="64 hex") as exc:
        Settings(jwt_signing_key="ab" * 31)
    assert "ab" * 31 not in str(exc.value)
