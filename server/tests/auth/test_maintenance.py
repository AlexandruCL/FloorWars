"""Retention purge and signing-key rotation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.auth import repository
from app.auth.tokens import AccessTokens, build_access_tokens, public_key_hex
from app.config import Settings
from tests.helpers import insert_user, new_email

# Purge.


def _challenge(db: object, email: str, created: datetime) -> None:
    db.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO otp_challenge (email, code_hash, salt, expires_at, consumed_at, "
            "created_at) VALUES (:e, :h, :s, :x, :c, :t)"
        ),
        {
            "e": email,
            "h": bytes(32),
            "s": bytes(16),
            "x": created + timedelta(minutes=10),
            "c": created,
            "t": created,
        },
    )


def _token(
    db: object, user_id: uuid.UUID, family: uuid.UUID, expires: datetime, revoked: bool
) -> None:
    db.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO refresh_token (user_id, token_hash, family_id, expires_at, revoked_at) "
            "VALUES (:u, :h, :f, :x, :r)"
        ),
        {
            "u": user_id,
            "h": uuid.uuid4().bytes * 2,
            "f": family,
            "x": expires,
            "r": expires if revoked else None,
        },
    )


def test_purge_expired(client: TestClient) -> None:
    now = datetime.now(UTC)
    with client.app.state.sessionmaker() as db:
        user_id = insert_user(db, new_email())
        _challenge(db, "old@student.upt.ro", now - timedelta(days=2))
        _challenge(db, "new@student.upt.ro", now - timedelta(hours=2))
        dead, alive = uuid.uuid4(), uuid.uuid4()
        # Every token of `dead` has expired: the family goes.
        _token(db, user_id, dead, now - timedelta(days=3), revoked=True)
        _token(db, user_id, dead, now - timedelta(days=1), revoked=False)
        # `alive` still has a live token: its expired, revoked ancestor stays for reuse detection.
        _token(db, user_id, alive, now - timedelta(days=1), revoked=True)
        _token(db, user_id, alive, now + timedelta(days=29), revoked=False)
        db.commit()

        assert repository.purge_expired(db, now) == (1, 2)
        db.commit()

        emails = db.execute(text("SELECT email FROM otp_challenge")).scalars().all()
        families = db.execute(text("SELECT family_id FROM refresh_token")).scalars().all()
    assert emails == ["new@student.upt.ro"]
    assert sorted(map(str, families)) == [str(alive), str(alive)]


# Key rotation.

OLD_SEED = bytes(range(32))
NEW_SEED = bytes(range(1, 33))
USER = uuid.UUID("00000000-0000-4000-8000-000000000002")


def test_token_signed_with_previous_key_still_verifies() -> None:
    old_token = AccessTokens(OLD_SEED, "floorwars-api", 900).issue(USER)
    settings = Settings(
        env="dev",
        jwt_signing_key=NEW_SEED.hex(),  # type: ignore[arg-type]
        jwt_previous_public_keys=public_key_hex(OLD_SEED),  # type: ignore[arg-type]
    )
    tokens = build_access_tokens(settings)
    assert tokens.verify(old_token).user_id == USER
    # New tokens carry the new kid and verify too.
    assert tokens.verify(tokens.issue(USER)).user_id == USER
    # Without the previous key the old token is refused.
    without = build_access_tokens(Settings(env="dev", jwt_signing_key=NEW_SEED.hex()))  # type: ignore[arg-type]
    with pytest.raises(Exception, match="kid"):
        without.verify(old_token)


def test_previous_public_keys_parsing() -> None:
    a, b = public_key_hex(OLD_SEED), public_key_hex(NEW_SEED)
    settings = Settings(jwt_previous_public_keys=f" {a.upper()} ,{b},")  # type: ignore[arg-type]
    assert settings.jwt_previous_public_keys == (a, b)
    with pytest.raises(ValidationError, match="64 hex"):
        Settings(jwt_previous_public_keys="abcd")  # type: ignore[arg-type]
