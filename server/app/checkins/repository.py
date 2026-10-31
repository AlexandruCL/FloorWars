"""All SQL of the check-in feature, as small functions over the sync ``Session``.

No commits here: the service decides the transaction. ``lock_user`` takes a row lock that lasts
until the service commits or rolls back, which serialises the check-ins of one user.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, cast, exists, func, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.db.models import BUILDING_FOOTPRINT_GEOG, GEOGRAPHY, Building, Checkin, User


def lock_user(db: Session, user_id: uuid.UUID) -> bool:
    """``SELECT ... FROM "user" WHERE id = :uid FOR UPDATE``. False if the user is gone."""
    return (
        db.scalars(select(User.id).where(User.id == user_id).with_for_update()).first() is not None
    )


def db_clock(db: Session) -> datetime:
    """The database's current time (``clock_timestamp()``, not the transaction start).

    Read after ``lock_user``: a check-in that waited for the lock must start after the one that
    held it, or ending that one would give it an upper bound before its lower bound.
    """
    now: datetime = db.execute(select(func.clock_timestamp())).scalar_one()
    return now


def end_active_checkin(db: Session, user_id: uuid.UUID, now: datetime) -> int:
    """End the user's check-in that is valid at ``now`` by setting its upper bound to ``now``.

    Returns the number of rows ended (0 or 1; the exclusion constraint allows at most one).
    """
    result = db.execute(
        update(Checkin)
        .where(Checkin.user_id == user_id, Checkin.valid_during.contains(now))
        .values(valid_during=func.tstzrange(func.lower(Checkin.valid_during), now, "[)"))
    )
    return int(getattr(result, "rowcount", 0) or 0)


def add_checkin(
    db: Session,
    user_id: uuid.UUID,
    building_id: int,
    method: str,
    valid_from: datetime,
    valid_until: datetime,
) -> Checkin:
    """Insert a check-in valid for ``[valid_from, valid_until)``; flushed, so ``id`` is set."""
    row = Checkin(
        user_id=user_id,
        building_id=building_id,
        method=method,
        valid_during=Range(valid_from, valid_until, bounds="[)"),
    )
    db.add(row)
    db.flush()
    return row


def building_exists(db: Session, building_id: int) -> bool:
    return bool(db.scalar(select(exists().where(Building.id == building_id))))


def nearest_building_stmt(latitude: float, longitude: float, radius_m: float) -> Select[int]:
    """The geofence query: id of the building nearest to the point, at most ``radius_m`` away.

    Distances are in metres on the geography type. ``footprint::geography`` is exactly the
    expression of ``ix_building_footprint_geog``, so ``ST_DWithin`` uses that GiST index.
    """
    point = cast(func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326), GEOGRAPHY)
    return (
        select(Building.id)
        .where(func.ST_DWithin(BUILDING_FOOTPRINT_GEOG, point, radius_m))
        .order_by(func.ST_Distance(BUILDING_FOOTPRINT_GEOG, point), Building.id)
        .limit(1)
    )


def nearest_building_id(
    db: Session, latitude: float, longitude: float, radius_m: float
) -> int | None:
    return db.scalars(nearest_building_stmt(latitude, longitude, radius_m)).first()
