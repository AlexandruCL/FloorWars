"""All SQL of the auth feature, as small functions over the sync ``Session``.

No commits here: the service decides transaction boundaries. Functions that lock use
``SELECT ... FOR UPDATE``, so the lock lasts until the service commits or rolls back.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Device, OtpChallenge, RefreshToken, User

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


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).one_or_none()


def add_user(db: Session, email: str, display_name: str, now: datetime) -> User:
    user = User(email=email, display_name=display_name, terms_accepted_at=now, age_confirmed_at=now)
    db.add(user)
    db.flush()
    return user


def lock_device_owner(db: Session, device_id: uuid.UUID) -> uuid.UUID | None:
    """Current owner of the device (row-locked), or None for a new device."""
    return db.scalars(
        select(Device.user_id).where(Device.id == device_id).with_for_update()
    ).one_or_none()


def upsert_device(
    db: Session,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    model: str,
    has_barometer: bool,
    now: datetime,
) -> None:
    """Register the device for ``user_id`` (moving it if another user had it)."""
    values = {"user_id": user_id, "model": model, "has_barometer": has_barometer}
    stmt = insert(Device).values(id=device_id, last_seen_at=now, **values)
    db.execute(
        stmt.on_conflict_do_update(index_elements=[Device.id], set_={**values, "last_seen_at": now})
    )


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
