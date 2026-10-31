"""The auth routes against ``contracts/openapi.yaml``, plus edge cases of the HTTP surface."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import repository
from app.config import Settings
from app.main import create_app
from tests.helpers import device, last_code, new_email, sign_in

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
AUTH_PATHS = ("/auth/otp", "/auth/verify", "/auth/refresh")
# Documented by the server ahead of the contract (contract PR pending, done by the lead): 503 on
# all three paths, and 429 on /auth/refresh (per-IP limit, security review 2026-10-31). Once the
# contract has them, the check below still passes; then these can be emptied.
SERVER_EXTRAS = {
    "/auth/otp": {"503"},
    "/auth/verify": {"503"},
    "/auth/refresh": {"429", "503"},
}


def _responses(operation: dict[str, Any]) -> set[str]:
    return {str(code) for code in operation["responses"]}


def test_auth_routes_match_contract() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    app = create_app(Settings(env="dev", log_level="WARNING"))
    served = app.openapi()
    for path in AUTH_PATHS:
        expected = contract["paths"][path]
        actual = served["paths"][f"/v1{path}"]
        assert set(actual) == set(expected), path
        for method, operation in expected.items():
            codes = _responses(actual[method])
            assert codes - SERVER_EXTRAS[path] == _responses(operation) - SERVER_EXTRAS[path], (
                path,
                method,
            )
            assert _responses(operation) <= codes, (path, method)
            assert actual[method]["operationId"] == operation["operationId"]
    # Every problem response points at the one shared component.
    problem = served["components"]["schemas"]["Problem"]
    assert problem["properties"]["status"]["minimum"] == 100
    refs = {
        content["schema"].get("$ref")
        for path in AUTH_PATHS
        for operation in served["paths"][f"/v1{path}"].values()
        for code, response in operation["responses"].items()
        if code not in ("200", "202")
        for content in response.get("content", {}).values()
    }
    assert refs == {"#/components/schemas/Problem"}


def test_protected_routes_use_the_contract_security_scheme(client: TestClient) -> None:
    served = client.app.openapi()
    assert set(served["components"]["securitySchemes"]) == {"bearerAuth"}
    assert served["paths"]["/test/whoami"]["get"]["security"] == [{"bearerAuth": []}]


# Validation and headers.


@pytest.mark.parametrize(
    "body", [{}, {"email": 5}, {"email": "a@student.upt.ro", "extra": 1}, {"email": "nope"}]
)
def test_otp_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/v1/auth/otp", json=body)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    "body", [{}, {"refresh_token": 5}, {"refresh_token": ""}, {"refresh_token": "x" * 129}]
)
def test_refresh_422(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/v1/auth/refresh", json=body)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_refresh_response_is_not_cached(client: TestClient) -> None:
    pair = sign_in(client, new_email())
    response = client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


# Concurrency.


def test_parallel_wrong_guesses_stop_at_five(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    code = last_code(client.app, email)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    n = 10
    barrier = threading.Barrier(n)
    statuses: list[int] = []

    def guess() -> None:
        barrier.wait()
        body = {"email": email, "code": wrong, "device": device()}
        statuses.append(client.post("/v1/auth/verify", json=body).status_code)

    threads = [threading.Thread(target=guess) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [401] * 5 + [429] * 5
    with client.app.state.sessionmaker() as db:
        attempts = db.execute(
            text("SELECT attempts FROM otp_challenge WHERE email = :e"), {"e": email}
        ).scalar_one()
    assert attempts == 5


def _competing_activation(client: TestClient, email: str, failures: int) -> Callable[..., None]:
    """Wrap activate_challenge: the first ``failures`` calls lose a race with another request."""
    real = repository.activate_challenge
    calls = {"n": 0}

    def activate(db: Session, email_: str, challenge_id: Any, now: Any) -> None:
        calls["n"] += 1
        if calls["n"] <= failures:
            with client.app.state.sessionmaker() as other:
                other.execute(
                    text(
                        "UPDATE otp_challenge SET consumed_at = now() "
                        "WHERE email = :e AND consumed_at IS NULL"
                    ),
                    {"e": email_},
                )
                other.execute(
                    text(
                        "INSERT INTO otp_challenge (email, code_hash, salt, expires_at) "
                        "VALUES (:e, :h, :s, now() + interval '10 minutes')"
                    ),
                    {"e": email_, "h": bytes(32), "s": bytes(16)},
                )
                other.commit()
            raise IntegrityError("activate", {}, Exception("ix_otp_challenge_email"))
        real(db, email_, challenge_id, now)

    return activate


def test_activation_retries_once_after_integrity_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = new_email()
    monkeypatch.setattr(repository, "activate_challenge", _competing_activation(client, email, 1))
    assert client.post("/v1/auth/otp", json={"email": email}).status_code == 202
    with client.app.state.sessionmaker() as db:
        active = db.execute(
            text("SELECT count(*) FROM otp_challenge WHERE email = :e AND consumed_at IS NULL"),
            {"e": email},
        ).scalar_one()
    assert active == 1
    # The surviving active challenge is ours: the mailed code works.
    body = {
        "email": email,
        "code": last_code(client.app, email),
        "device": device(),
        "accept_terms": True,
        "confirm_adult": True,
    }
    assert client.post("/v1/auth/verify", json=body).status_code == 200


def test_activation_gives_up_after_second_integrity_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = new_email()
    monkeypatch.setattr(repository, "activate_challenge", _competing_activation(client, email, 2))
    quiet = TestClient(client.app, raise_server_exceptions=False)
    response = quiet.post("/v1/auth/otp", json={"email": email})
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
