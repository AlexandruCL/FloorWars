"""Helpers for tests that need a signed-in user. Other features' tests may import these.

Example (any test with a ``create_app`` app whose database is migrated)::

    from tests.auth.helpers import auth_headers, insert_user

    with app.state.sessionmaker() as db:
        user_id = insert_user(db, "ana@student.upt.ro")
    response = client.get("/v1/teams", headers=auth_headers(app, user_id))
"""

import os
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.mail import FakeMailSender

TEST_DB_URL = os.environ.get("FLOORWARS_TEST_DATABASE_URL")
TEST_VALKEY_URL = os.environ.get("FLOORWARS_TEST_VALKEY_URL")
# Dummy key for tests only (never used anywhere else).
TEST_JWT_KEY = "11" * 32


def settings_for_tests(**overrides: Any) -> Settings:
    """Dev settings on the test database and Valkey, fake mail and a fixed signing key."""
    values: dict[str, Any] = {
        "env": "dev",
        "log_level": "WARNING",
        "database_url": TEST_DB_URL,
        "valkey_url": TEST_VALKEY_URL,
        "mail_backend": "fake",
        "jwt_signing_key": TEST_JWT_KEY,
        **overrides,
    }
    return Settings(**values)


def new_email() -> str:
    return f"s{uuid.uuid4().hex[:12]}@student.upt.ro"


def auth_headers(app: FastAPI, user_id: uuid.UUID) -> dict[str, str]:
    """``Authorization`` header with a valid access token for ``user_id``."""
    token = app.state.access_tokens.issue(user_id)
    return {"Authorization": f"Bearer {token}"}


def insert_user(db: Session, email: str) -> uuid.UUID:
    """Create a user directly in the database (committed) and return its id."""
    user_id = db.execute(
        text(
            'INSERT INTO "user" (email, display_name, terms_accepted_at, age_confirmed_at) '
            "VALUES (:e, :d, now(), now()) RETURNING id"
        ),
        {"e": email, "d": email.split("@", 1)[0]},
    ).scalar_one()
    db.commit()
    assert isinstance(user_id, uuid.UUID)
    return user_id


def last_code(app: FastAPI, email: str) -> str:
    """The last code the fake mail backend sent to ``email``."""
    sender = app.state.mail_sender
    assert isinstance(sender, FakeMailSender)
    codes = [m.code for m in sender.outbox if m.to == email]
    assert codes, f"no code sent to {email}"
    return codes[-1]


def device(device_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {"id": str(device_id or uuid.uuid4()), "model": "test Pixel 9", "has_barometer": True}


def sign_in(client: TestClient, email: str, **extra: Any) -> dict[str, Any]:
    """Run the OTP flow through the API and return the token pair (new accounts accepted)."""
    assert client.post("/v1/auth/otp", json={"email": email}).status_code == 202
    body = {
        "email": email,
        "code": last_code(client.app, email),
        "device": device(),
        "accept_terms": True,
        "confirm_adult": True,
        **extra,
    }
    response = client.post("/v1/auth/verify", json=body)
    assert response.status_code == 200, response.text
    pair: dict[str, Any] = response.json()
    return pair
