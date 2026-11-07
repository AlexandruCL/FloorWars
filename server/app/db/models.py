"""SQLAlchemy models (plan section 5.1).

Must match the migrations in ``migrations/versions/`` exactly; ``alembic check`` enforces that.
See ``docs/er_review.md`` for the decisions behind nullability, PK types and delete rules.
"""

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geography, Geometry, WKBElement
from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    cast,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import (
    BYTEA,
    CITEXT,
    JSONB,
    TSTZRANGE,
    UUID,
    ExcludeConstraint,
    Range,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import OTP_MAX_ATTEMPTS
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
        # Retention purge and per-e-mail cleanup (``created_at`` ranges).
        Index("ix_otp_challenge_email_created_at", "email", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(CITEXT())
    code_hash: Mapped[bytes] = mapped_column(BYTEA())
    salt: Mapped[bytes] = mapped_column(BYTEA())
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


# Check-in (0003_checkin).

CHECKIN_METHODS = ("qr", "geofence")


class Checkin(Base):
    """A check-in at a building, valid for ``valid_during`` (plan 3.2; 90 minutes by default).

    The exclusion constraint keeps the check-ins of one user from overlapping, so a user has at
    most one active check-in. The position of a geofence check-in is never stored (plan 8).
    """

    __tablename__ = "checkin"
    __table_args__ = (
        CheckConstraint("method IN ('qr', 'geofence')", name="method"),
        CheckConstraint("NOT isempty(valid_during)", name="valid_during_not_empty"),
        ExcludeConstraint(
            ("user_id", "="),
            ("valid_during", "&&"),
            name="excl_checkin_user_overlap",
            using="gist",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    building_id: Mapped[int] = mapped_column(ForeignKey("building.id"), index=True)
    method: Mapped[str] = mapped_column(Text)
    valid_during: Mapped[Range[datetime]] = mapped_column(TSTZRANGE())
    created_at: Mapped[datetime] = _created_at()


# Plain ``geography`` (no subtype, no SRID), so the cast is exactly ``footprint::geography``; the
# geofence query uses the same expression, which is what lets it use the index below.
GEOGRAPHY = Geography(geometry_type=None, srid=-1)
BUILDING_FOOTPRINT_GEOG = cast(Building.footprint, GEOGRAPHY)

# Functional GiST index for the geofence lookup (0003_checkin). Declared outside ``Building`` so
# that model stays unchanged; it attaches to the building table all the same.
Index("ix_building_footprint_geog", BUILDING_FOOTPRINT_GEOG, postgresql_using="gist")


# Segments, scores and claims (0004_segments).


class ClimbSegment(Base):
    """One uploaded climb, verified or rejected. Partitioned by month on ``started_at``.

    The partitions (``climb_segment_YYYYMM``) are not models: see ``app/segments/partitions.py``.
    A partitioned table's primary key must include the partition key, so a resend is recognised
    by ``segment_receipt``, not by this key.
    """

    __tablename__ = "climb_segment"
    __table_args__ = (
        CheckConstraint("status IN ('verified', 'rejected')", name="status"),
        CheckConstraint("steps_scored BETWEEN 0 AND 2000", name="steps_scored_range"),
        CheckConstraint("points >= 0", name="points_not_negative"),
        CheckConstraint(
            "status = 'rejected' OR (steps BETWEEN 1 AND 2000 "
            "AND ascent_m BETWEEN 2.0 AND 120.0 AND stair_prob BETWEEN 0 AND 1)",
            name="verified_bounds",
        ),
        CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)", name="reject_reason_if_rejected"
        ),
        # The owner query: verified segments of one building, newest first.
        Index(
            "ix_climb_segment_building_id_started_at",
            "building_id",
            text("started_at DESC"),
            postgresql_where=text("status = 'verified'"),
        ),
        Index("ix_climb_segment_user_id_started_at", "user_id", text("started_at DESC")),
        Index("ix_climb_segment_season_id_team_id", "season_id", "team_id"),
        {"postgresql_partition_by": "RANGE (started_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    season_id: Mapped[int] = mapped_column(ForeignKey("season.id"))
    checkin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checkin.id"))
    building_id: Mapped[int] = mapped_column(ForeignKey("building.id"))
    status: Mapped[str] = mapped_column(Text)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[int] = mapped_column(Integer)
    steps_scored: Mapped[int] = mapped_column(SmallInteger)
    points: Mapped[int] = mapped_column(Integer)
    ascent_m: Mapped[float] = mapped_column(REAL)
    duration_s: Mapped[float] = mapped_column(REAL)
    vert_speed_mps: Mapped[float] = mapped_column(REAL)
    stair_prob: Mapped[float] = mapped_column(REAL)
    classifier_version: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = _created_at()


class SegmentReceipt(Base):
    """The answer given for ``(device_id, id)``: decides resends, also for unstored rejections."""

    __tablename__ = "segment_receipt"

    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text)
    reject_reason: Mapped[str | None] = mapped_column(Text)
    steps_scored: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()


class FraudFlag(Base):
    """A rejection worth reviewing. No FK to ``climb_segment``: a partition drop must not block."""

    __tablename__ = "fraud_flag"
    __table_args__ = (
        Index(
            "ix_fraud_flag_created_at",
            "created_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    segment_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    rule: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamBuildingScore(Base):
    """Season totals (standings history, leaderboards); ownership uses the rolling window."""

    __tablename__ = "team_building_score"
    __table_args__ = (CheckConstraint("points >= 0", name="points_not_negative"),)

    season_id: Mapped[int] = mapped_column(ForeignKey("season.id"), primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("building.id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    steps: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class BuildingClaim(Base):
    """The owner of a building in a season; the row every claim transaction locks."""

    __tablename__ = "building_claim"

    season_id: Mapped[int] = mapped_column(ForeignKey("season.id"), primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("building.id"), primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))  # NULL = unowned
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GameEvent(Base):
    """An event written inside the transaction that caused it (plan 7.2.1)."""

    __tablename__ = "game_event"
    __table_args__ = (
        CheckConstraint("kind IN ('building_flipped', 'season_state')", name="kind"),
        Index("ix_game_event_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    season_id: Mapped[int | None] = mapped_column(Integer)
    building_id: Mapped[int | None] = mapped_column(Integer)
    from_team: Mapped[int | None] = mapped_column(Integer)
    to_team: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = _created_at()
