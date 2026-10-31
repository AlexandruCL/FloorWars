"""Refresh retry window, mail failures and sign-up defaults (PostGIS and Valkey)."""

import re
import threading
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import otp
from app.mail import FakeMailSender, MailError
from tests.helpers import device, last_code, new_email, sign_in


def _refresh(client: TestClient, token: str) -> Any:
    return client.post("/v1/auth/refresh", json={"refresh_token": token})


def _rows(client: TestClient, sql: str, **params: object) -> list[tuple[Any, ...]]:
    with client.app.state.sessionmaker() as db:
        return [tuple(r) for r in db.execute(text(sql), params).all()]


# Refresh grace window.


def test_retry_within_grace_window_keeps_family(client: TestClient) -> None:
    pair = sign_in(client, new_email())
    rotated = _refresh(client, pair["refresh_token"])
    assert rotated.status_code == 200
    # The client lost the response and retries with the old token: refused, family kept.
    retry = _refresh(client, pair["refresh_token"])
    assert retry.status_code == 401
    assert _refresh(client, rotated.json()["refresh_token"]).status_code == 200


def test_reuse_after_grace_window_revokes_family(make_app: Callable[..., TestClient]) -> None:
    client = make_app(refresh_reuse_grace_s=0)
    pair = sign_in(client, new_email())
    rotated = _refresh(client, pair["refresh_token"])
    assert rotated.status_code == 200
    assert _refresh(client, pair["refresh_token"]).status_code == 401
    assert _refresh(client, rotated.json()["refresh_token"]).status_code == 401
    assert _rows(client, "SELECT count(*) FROM refresh_token WHERE revoked_at IS NULL") == [(0,)]


def test_parallel_refreshes_leave_a_working_family(client: TestClient) -> None:
    pair = sign_in(client, new_email())
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def worker() -> None:
        barrier.wait()
        results.append(_refresh(client, pair["refresh_token"]))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 401]
    winner = next(r for r in results if r.status_code == 200)
    assert _refresh(client, winner.json()["refresh_token"]).status_code == 200


# Mail failures.


class FailingMail(FakeMailSender):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def send_otp(self, to: str, code: str, ttl_s: int) -> None:
        if self.fail:
            raise MailError("down")
        super().send_otp(to, code, ttl_s)


def test_mail_failure_keeps_previous_code_active(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mail = FailingMail()
    client.app.state.mail_sender = mail
    codes = iter(["111111", "222222"])
    monkeypatch.setattr(otp, "new_code", lambda: next(codes))
    email = new_email()

    assert client.post("/v1/auth/otp", json={"email": email}).status_code == 202
    mail.fail = True
    response = client.post("/v1/auth/otp", json={"email": email})
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"

    rows = _rows(
        client,
        "SELECT consumed_at IS NULL FROM otp_challenge WHERE email = :e ORDER BY created_at",
        e=email,
    )
    assert rows == [(True,), (False,)]  # first still active, the unsent one retired
    ok = client.post(
        "/v1/auth/verify",
        json={
            "email": email,
            "code": "111111",
            "device": device(),
            "accept_terms": True,
            "confirm_adult": True,
        },
    )
    assert ok.status_code == 200
    # The unsent code never works.
    assert [m.code for m in mail.outbox] == ["111111"]


def test_mail_failure_without_previous_code(client: TestClient) -> None:
    mail = FailingMail()
    mail.fail = True
    client.app.state.mail_sender = mail
    email = new_email()
    assert client.post("/v1/auth/otp", json={"email": email}).status_code == 503
    rows = _rows(client, "SELECT consumed_at IS NULL FROM otp_challenge WHERE email = :e", e=email)
    assert rows == [(False,)]


# Sign-up defaults.


def test_new_user_gets_neutral_display_name(client: TestClient) -> None:
    email = new_email()
    sign_in(client, email)
    (name,) = _rows(client, 'SELECT display_name FROM "user" WHERE email = :e', e=email)[0]
    assert re.fullmatch(r"Player-[0-9a-f]{4}", name)
    assert email.split("@")[0] not in name


def test_last_code_helper_still_matches_outbox(client: TestClient) -> None:
    email = new_email()
    client.post("/v1/auth/otp", json={"email": email})
    assert re.fullmatch(r"[0-9]{6}", last_code(client.app, email))
