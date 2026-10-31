"""All SQL of the auth feature, as small functions over the sync ``Session``.

No commits here: the service decides transaction boundaries. Functions that lock use
``SELECT ... FOR UPDATE``, so the lock lasts until the service commits or rolls back.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Device, OtpChallenge, RefreshToken, User

# Challenges older than this are deleted (codes live 10 minutes; a day is plenty for support).
CHALLENGE_RETENTION = timedelta(days=1)

# One-time codes.


def add_pending_challenge(
    db: Session, email: str, code_hash: bytes, salt: bytes, expires_at: datetime, now: datetime
) -> uuid.UUID:
    """Store a new challenge as *retired* (``consumed_at`` set) until its mail is accepted.

    The e-mail's current active challenge stays usable meanwhile; ``activate_challenge`` swaps
    them once the mail backend accepted the new code.
    """
    challenge = OtpChallenge(
        email=email, code_hash=code_hash, salt=salt, expires_at=expires_at, consumed_at=now
    )
    db.add(challenge)
    db.flush()
    return challenge.id


def activate_challenge(db: Session, email: str, challenge_id: uuid.UUID, now: datetime) -> None:
    """Retire the e-mail's active challenge (superseded) and make ``challenge_id`` the active one.

    Raises ``IntegrityError`` (unique active challenge per e-mail) if a concurrent request
    activated its own challenge in between; the caller retries.
    """
    db.execute(
        update(OtpChallenge)
        .where(OtpChallenge.email == email, OtpChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    db.execute(update(OtpChallenge).where(OtpChallenge.id == challenge_id).values(consumed_at=None))


def delete_old_challenges(db: Session, email: str, before: datetime) -> None:
    """Drop the e-mail's retired challenges created before ``before`` (data minimisation)."""
    db.execute(
        delete(OtpChallenge).where(
            OtpChallenge.email == email,
            OtpChallenge.consumed_at.is_not(None),
            OtpChallenge.created_at < before,
        )
    )


def lock_active_challenge(db: Session, email: str) -> OtpChallenge | None:
    """The e-mail's active challenge, row-locked for the rest of the transaction."""
    return db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.email == email, OtpChallenge.consumed_at.is_(None))
        .with_for_update()
    ).one_or_none()


# Users and devices.


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).one_or_none()


def add_user(db: Session, email: str, display_name: str, now: datetime) -> User:
    user = User(email=email, display_name=display_name, terms_accepted_at=now, age_confirmed_at=now)
    db.add(user)
    db.flush()
    return user


def upsert_device(
    db: Session,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    model: str,
    has_barometer: bool,
    now: datetime,
) -> None:
    """Register or refresh the device ``(user_id, device_id)``; other users' rows are untouched."""
    values = {"model": model, "has_barometer": has_barometer, "last_seen_at": now}
    stmt = insert(Device).values(user_id=user_id, id=device_id, **values)
    db.execute(stmt.on_conflict_do_update(index_elements=[Device.user_id, Device.id], set_=values))


# Refresh tokens.


def add_refresh_token(
    db: Session,
    user_id: uuid.UUID,
    token_hash: bytes,
    family_id: uuid.UUID,
    expires_at: datetime,
) -> None:
    db.add(
        RefreshToken(
            user_id=user_id, token_hash=token_hash, family_id=family_id, expires_at=expires_at
        )
    )
    db.flush()


def lock_refresh_token(db: Session, token_hash: bytes) -> RefreshToken | None:
    return db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    ).one_or_none()


def revoke_family(db: Session, family_id: uuid.UUID) -> int:
    """Revoke every still-valid token of the family; returns how many were revoked."""
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    return int(getattr(result, "rowcount", 0) or 0)


# Maintenance.


def purge_expired(db: Session, now: datetime) -> tuple[int, int]:
    """Delete stale auth rows; returns ``(challenges, refresh_tokens)`` deleted. No commit.

    - challenges created more than ``CHALLENGE_RETENTION`` ago (used, retired or expired);
    - refresh tokens of families whose every token is past ``expires_at``. Revoked tokens of a
      family that still has a live token are kept, so presenting them is still detected as reuse.

    TODO(week 5, plan 7.6): run daily from Celery beat (one transaction, then commit).
    """
    challenges = db.execute(
        delete(OtpChallenge)
        .where(OtpChallenge.created_at < now - CHALLENGE_RETENTION)
        .execution_options(synchronize_session=False)
    )
    expired_families = (
        select(RefreshToken.family_id)
        .group_by(RefreshToken.family_id)
        .having(func.max(RefreshToken.expires_at) < now)
    )
    tokens = db.execute(
        delete(RefreshToken)
        .where(RefreshToken.family_id.in_(expired_families))
        .execution_options(synchronize_session=False)
    )
    return (
        int(getattr(challenges, "rowcount", 0) or 0),
        int(getattr(tokens, "rowcount", 0) or 0),
    )
