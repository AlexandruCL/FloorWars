"""Security hardening: client buckets, limit order, devices per user, e-mail rules, log hygiene."""

import logging
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.problems import ProblemError
from app.auth import otp, repository, service
from app.auth.ratelimit import Decision, client_bucket
from app.auth.schemas import DeviceInfo, OtpVerifyRequest
from tests.helpers import device, new_email, settings_for_tests, sign_in

# Client buckets.


@pytest.mark.parametrize(
    ("ip", "bucket"),
    [
        ("192.0.2.7", "192.0.2.7"),
        ("192.0.2.8", "192.0.2.8"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
        ("::ffff:192.0.2.9", "192.0.2.9"),
        ("testclient", "testclient"),
    ],
)
def test_client_bucket(ip: str, bucket: str) -> None:
    assert client_bucket(ip) == bucket


# Limit order and placement (no database: the limits come first).


class RecordingLimiter:
    def __init__(self, deny: str | None = None) -> None:
        self.deny = deny
        self.hits: list[tuple[str, str]] = []

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        self.hits.append((name, subject))
        if name == self.deny:
            return Decision(allowed=False, retry_after_s=42)
        return Decision(allowed=True, retry_after_s=0)


NO_DB: Any = None  # any database access would fail with AttributeError


def test_otp_checks_ip_bucket_before_email_bucket() -> None:
    limiter = RecordingLimiter(deny="otp:ip")
    with pytest.raises(ProblemError) as exc:
        service.request_otp(NO_DB, settings_for_tests(), limiter, NO_DB, new_email(), "2001:db8::5")
    assert exc.value.problem.status == 429
    assert exc.value.headers["Retry-After"] == "42"
    assert limiter.hits == [("otp:ip", "2001:db8::/64")]


def _verify_body() -> OtpVerifyRequest:
    return OtpVerifyRequest(
        email=new_email(),
        code="123456",
        device=DeviceInfo(id=uuid.uuid4(), model="x", has_barometer=True),
    )


def test_verify_ip_limit_before_any_database_work() -> None:
    limiter = RecordingLimiter(deny="verify:ip")
    with pytest.raises(ProblemError) as exc:
        service.verify_otp(NO_DB, settings_for_tests(), NO_DB, limiter, _verify_body(), "192.0.2.1")
    assert exc.value.problem.status == 429
    assert "Retry-After" in exc.value.headers


def test_refresh_ip_limit_before_any_database_work() -> None:
    limiter = RecordingLimiter(deny="refresh:ip")
    with pytest.raises(ProblemError) as exc:
        service.refresh(NO_DB, settings_for_tests(), NO_DB, limiter, "token", "192.0.2.1")
    assert exc.value.problem.status == 429


def test_verify_and_refresh_fail_closed_without_limiter() -> None:
    with pytest.raises(ProblemError) as exc:
        service.verify_otp(NO_DB, settings_for_tests(), NO_DB, None, _verify_body(), "192.0.2.1")
    assert exc.value.problem.status == 503
    with pytest.raises(ProblemError) as exc:
        service.refresh(NO_DB, settings_for_tests(), NO_DB, None, "token", "192.0.2.1")
    assert exc.value.problem.status == 503


def test_verify_ip_limit_is_429_over_http(make_app: Callable[..., TestClient]) -> None:
    client = make_app(verify_rate_per_ip_per_hour=2)
    body = {"email": new_email(), "code": "000000", "device": device()}
    assert client.post("/v1/auth/verify", json=body).status_code == 401
    assert client.post("/v1/auth/verify", json=body).status_code == 401
    response = client.post("/v1/auth/verify", json=body)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


def test_refresh_ip_limit_is_429_over_http(make_app: Callable[..., TestClient]) -> None:
    client = make_app(refresh_rate_per_ip_per_hour=1)
    assert client.post("/v1/auth/refresh", json={"refresh_token": "x"}).status_code == 401
    response = client.post("/v1/auth/refresh", json={"refresh_token": "x"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


# E-mail rules.


@pytest.mark.parametrize("email", ["ana+game@student.upt.ro", "+@student.upt.ro"])
def test_plus_addressing_is_422(client: TestClient, email: str) -> None:
    response = client.post("/v1/auth/otp", json={"email": email})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = {"email": email, "code": "123456", "device": device()}
    assert client.post("/v1/auth/verify", json=body).status_code == 422


# Devices.


def test_same_device_id_for_two_users_gives_two_rows(client: TestClient) -> None:
    shared = uuid.uuid4()
    first, second = new_email(), new_email()
    sign_in(client, first, device={"id": str(shared), "model": "A", "has_barometer": True})
    sign_in(client, second, device={"id": str(shared), "model": "B", "has_barometer": False})
    # The first user signs in again on the same phone: only their row changes.
    sign_in(client, first, device={"id": str(shared), "model": "A2", "has_barometer": True})
    with client.app.state.sessionmaker() as db:
        rows = db.execute(
            text(
                'SELECT u.email, d.model, d.has_barometer FROM device d JOIN "user" u '
                "ON u.id = d.user_id WHERE d.id = :d ORDER BY d.model"
            ),
            {"d": shared},
        ).all()
    assert [tuple(r) for r in rows] == [(first, "A2", True), (second, "B", False)]


# Log hygiene on database errors.


def test_database_error_logs_no_bound_values(
    make_app: Callable[..., TestClient],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    salt = b"S" * 16
    monkeypatch.setattr(otp, "new_salt", lambda: salt)
    monkeypatch.setattr(otp, "new_code", lambda: "135791")

    def failing_add(db: Session, email: str, code_hash: bytes, salt: bytes, *_: Any) -> None:
        # attempts = 9 violates the CHECK: a database error with bound parameters.
        db.execute(
            text(
                "INSERT INTO otp_challenge (email, code_hash, salt, attempts, expires_at) "
                "VALUES (:e, :h, :s, 9, now())"
            ),
            {"e": email, "h": code_hash, "s": salt},
        )

    monkeypatch.setattr(repository, "add_challenge", failing_add)
    caplog.set_level(logging.DEBUG)
    client = make_app(log_level="DEBUG")
    client_no_raise = TestClient(client.app, raise_server_exceptions=False)
    email = new_email()
    response = client_no_raise.post("/v1/auth/otp", json={"email": email})
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"

    logs = caplog.text + capsys.readouterr().out
    assert "ck_otp_challenge_attempts_range" in logs  # the error itself is logged
    code_hash = otp.hash_code(salt, "135791")
    for secret in (email, "SSSSSSSSSSSSSSSS", code_hash.hex(), repr(code_hash), "135791"):
        assert secret not in logs
