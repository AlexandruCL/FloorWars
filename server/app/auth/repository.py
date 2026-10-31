"""All SQL of the auth feature, as small functions over the sync ``Session``.

No commits here: the service decides transaction boundaries. Functions that lock use
``SELECT ... FOR UPDATE``, so the lock lasts until the service commits or rolls back.
"""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import OtpChallenge

# One-time codes.


def supersede_active_challenge(db: Session, email: str, now: datetime) -> None:
    """Retire the e-mail's unused challenge, if any (a new request replaces it)."""
    db.execute(
        update(OtpChallenge)
        .where(OtpChallenge.email == email, OtpChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
    )


def delete_old_challenges(db: Session, email: str, before: datetime) -> None:
    """Drop the e-mail's retired challenges created before ``before`` (data minimisation)."""
    db.execute(
        delete(OtpChallenge).where(
            OtpChallenge.email == email,
            OtpChallenge.consumed_at.is_not(None),
            OtpChallenge.created_at < before,
        )
    )


def add_challenge(
    db: Session, email: str, code_hash: bytes, salt: bytes, expires_at: datetime
) -> None:
    db.add(OtpChallenge(email=email, code_hash=code_hash, salt=salt, expires_at=expires_at))
    db.flush()


def lock_active_challenge(db: Session, email: str) -> OtpChallenge | None:
    """The e-mail's active challenge, row-locked for the rest of the transaction."""
    return db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.email == email, OtpChallenge.consumed_at.is_(None))
        .with_for_update()
    ).one_or_none()


# Users and devices.


# Refresh tokens.
