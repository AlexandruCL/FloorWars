"""SQLAlchemy models (plan section 5.1).

Must match the migrations in ``migrations/versions/`` exactly; ``alembic check`` enforces that.
See ``docs/er_review.md`` for the decisions behind nullability, PK types and delete rules.
"""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, CITEXT, TSTZRANGE, UUID, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

GEN_UUID = text("gen_random_uuid()")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    # Reserved word in PostgreSQL; SQLAlchemy quotes it as "user".
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT(), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    # Set at sign-up from OtpVerifyRequest.accept_terms / confirm_adult (0002_auth). NULL only
    # for rows created before 0002; the API never creates a user without them.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    age_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Base):
    """A phone of a user. The id comes from the app; it is unique per user only.

    Composite primary key ``(user_id, id)`` (0002_auth): the same device id signed in by two
    users gives two rows, so one user can never take over another user's device row.
    """

    __tablename__ = "device"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID
    )
    model: Mapped[str] = mapped_column(Text)
    has_barometer: Mapped[bool] = mapped_column(Boolean)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class Team(Base):
    __tablename__ = "team"
    __table_args__ = (CheckConstraint("color_hex ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    color_hex: Mapped[str] = mapped_column(Text)


class Season(Base):
    __tablename__ = "season"
    __table_args__ = (
        CheckConstraint("NOT isempty(active_during)", name="active_during_not_empty"),
        ExcludeConstraint(("active_during", "&&"), name="excl_season_active_during", using="gist"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    active_during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE())


class TeamMembership(Base):
    __tablename__ = "team_membership"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    season_id: Mapped[int] = mapped_column(ForeignKey("season.id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    created_at: Mapped[datetime] = _created_at()


class Building(Base):
    __tablename__ = "building"
    __table_args__ = (Index("ix_building_footprint", "footprint", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # No floor count or height columns: the game does not need building floor data.
    footprint: Mapped[WKBElement] = mapped_column(
        Geometry("POLYGON", srid=4326, spatial_index=False)
    )


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[bytes] = mapped_column(BYTEA(), unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the token was rotated (0002_auth). Presenting it again within the reuse grace
    # window is a client retry, not theft; ``revoked_at`` alone also covers family revocation.
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Highest value of otp_challenge.attempts (plan 7.9: five attempts per code). The CHECK below and
# the Settings bound on ``otp_max_attempts`` both use it.
OTP_MAX_ATTEMPTS = 5


class OtpChallenge(Base):
    """A sign-in code sent by e-mail (plan 7.9). Only ``sha256(salt || code)`` is stored.

    At most one *active* (``consumed_at IS NULL``) challenge per e-mail: a new request sets
    ``consumed_at`` on the previous one (superseded), a successful verify sets it too.
    """

    __tablename__ = "otp_challenge"
    __table_args__ = (
        CheckConstraint(f"attempts BETWEEN 0 AND {OTP_MAX_ATTEMPTS}", name="attempts_range"),
        Index(
            "ix_otp_challenge_email",
            "email",
            unique=True,
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT())
    code_hash: Mapped[bytes] = mapped_column(BYTEA())
    salt: Mapped[bytes] = mapped_column(BYTEA())
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
