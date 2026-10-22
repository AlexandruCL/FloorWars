"""SQLAlchemy models for the baseline schema (plan section 5.1).

Must match ``migrations/versions/0001_baseline.py`` exactly; ``alembic check`` enforces that.
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


class Device(Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
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
