"""All SQL of the segment batch, as small functions over the sync ``Session``.

No commits here: the service owns the transaction. ``lock_user`` takes a row lock that lasts until
the service commits or rolls back, which serialises the batches of one user. Every function runs
on the caller's connection, so it sees the earlier items of the same transaction.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    ColumnElement,
    Interval,
    and_,
    exists,
    func,
    insert,
    literal,
    literal_column,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    Checkin,
    ClimbSegment,
    Device,
    FraudFlag,
    Season,
    SegmentReceipt,
    TeamBuildingScore,
    TeamMembership,
    User,
)
from app.segments.models import STATUS_VERIFIED, ItemContext, Receipt, SegmentRow
from app.segments.rules import DURATION_MAX_S, OVERLAP_TOLERANCE

# Far above a normal batch (about 1 s), and below the 30 s wait for a pooled connection, so batches
# queued on one user cannot starve other users of connections.
LOCK_TIMEOUT_MS = 5000


def lock_user(db: Session, user_id: uuid.UUID) -> bool:
    """``SELECT ... FROM "user" WHERE id = :id FOR UPDATE``. False if the user is gone.

    Waits at most ``LOCK_TIMEOUT_MS``; beyond it PostgreSQL raises ``lock_not_available``, which
    ``app.api.problems`` answers with 503 and ``Retry-After``. Only this wait is limited: later
    locks of the transaction (claim and score rows, shared with other users) keep the previous
    setting.
    """
    previous = db.scalar(select(func.current_setting("lock_timeout")))
    db.execute(select(func.set_config("lock_timeout", f"{LOCK_TIMEOUT_MS}ms", True)))
    found = db.scalars(select(User.id).where(User.id == user_id).with_for_update()).first()
    db.execute(select(func.set_config("lock_timeout", previous, True)))
    return found is not None


def device_belongs(db: Session, user_id: uuid.UUID, device_id: uuid.UUID) -> bool:
    return bool(
        db.scalar(select(exists().where(Device.user_id == user_id, Device.id == device_id)))
    )


def get_receipt(db: Session, device_id: uuid.UUID, segment_id: uuid.UUID) -> Receipt | None:
    """The stored answer for ``(device_id, segment_id)``, whichever user it belongs to.

    A device id is unique per user only, so the caller compares ``Receipt.user_id``.
    """
    row = db.execute(
        select(
            SegmentReceipt.user_id,
            SegmentReceipt.status,
            SegmentReceipt.reject_reason,
            SegmentReceipt.steps_scored,
        ).where(SegmentReceipt.device_id == device_id, SegmentReceipt.id == segment_id)
    ).first()
    if row is None:
        return None
    return Receipt(
        device_id=device_id,
        id=segment_id,
        user_id=row.user_id,
        status=row.status,
        reject_reason=row.reject_reason,
        steps_scored=row.steps_scored,
    )


def insert_receipt(
    db: Session,
    device_id: uuid.UUID,
    segment_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
    reject_reason: str | None,
    steps_scored: int,
) -> None:
    """Record the answer. ``ON CONFLICT DO NOTHING``: an existing receipt is never changed."""
    db.execute(
        pg_insert(SegmentReceipt)
        .values(
            device_id=device_id,
            id=segment_id,
            user_id=user_id,
            status=status,
            reject_reason=reject_reason,
            steps_scored=steps_scored,
        )
        .on_conflict_do_nothing(index_elements=[SegmentReceipt.device_id, SegmentReceipt.id])
    )


def load_context(
    db: Session, user_id: uuid.UUID, checkin_id: uuid.UUID, started_at: datetime
) -> ItemContext:
    """The check-in, the season containing ``started_at`` and the user's team in it.

    One query, one row: the anchor keeps the row when any of the outer joins finds nothing. The
    exclusion constraint on ``season.active_during`` allows at most one matching season.
    """
    anchor = select(literal(1).label("one")).subquery("anchor")
    row = db.execute(
        select(
            Checkin.user_id,
            Checkin.building_id,
            Checkin.valid_during,
            Season.id.label("season_id"),
            TeamMembership.team_id,
        )
        .select_from(anchor)
        .outerjoin(Checkin, Checkin.id == checkin_id)
        .outerjoin(Season, Season.active_during.contains(started_at))
        .outerjoin(
            TeamMembership,
            and_(TeamMembership.user_id == user_id, TeamMembership.season_id == Season.id),
        )
    ).one()
    return ItemContext(
        checkin_user_id=row.user_id,
        checkin_building_id=row.building_id,
        checkin_valid_during=row.valid_during,
        season_id=row.season_id,
        team_id=row.team_id,
    )


def _verified_steps(db: Session, user_id: uuid.UUID, *range_: ColumnElement[bool]) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(ClimbSegment.steps_scored), 0)).where(
            ClimbSegment.user_id == user_id,
            ClimbSegment.status == STATUS_VERIFIED,
            *range_,
        )
    )
    return int(total or 0)


def verified_steps_around(db: Session, user_id: uuid.UUID, at: datetime, window: timedelta) -> int:
    """Verified steps of the user with ``started_at`` in ``(at - window, at + window)``.

    Both sides count, so uploading the newest climb first cannot bypass a limit.
    """
    return _verified_steps(
        db, user_id, ClimbSegment.started_at > at - window, ClimbSegment.started_at < at + window
    )


def verified_steps_before(db: Session, user_id: uuid.UUID, at: datetime, window: timedelta) -> int:
    """Verified steps of the user with ``started_at`` in ``(at - window, at)``."""
    return _verified_steps(
        db, user_id, ClimbSegment.started_at > at - window, ClimbSegment.started_at < at
    )


def verified_steps_in_hour(db: Session, user_id: uuid.UUID, at: datetime) -> int:
    """Verified steps of the user with ``started_at`` in the same UTC clock hour as ``at``.

    A fixed hour holds the same climbs whatever the upload order, so the points of that hour do not
    depend on it (apart from rounding per climb).
    """
    start = at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return _verified_steps(
        db,
        user_id,
        ClimbSegment.started_at >= start,
        ClimbSegment.started_at < start + timedelta(hours=1),
    )


def segment_exists(db: Session, id: uuid.UUID, started_at: datetime) -> bool:
    """Whether ``(id, started_at)`` is stored, for any user and with any status."""
    return bool(
        db.scalar(
            select(exists().where(ClimbSegment.id == id, ClimbSegment.started_at == started_at))
        )
    )


def overlaps_verified(
    db: Session,
    user_id: uuid.UUID,
    started_at: datetime,
    duration_s: float,
    *,
    device_id: uuid.UUID | None = None,
) -> bool:
    """Whether ``[started_at, started_at + duration_s)`` overlaps a verified segment of the user,
    only among those of ``device_id`` when given.

    Segments that only touch at an end do not overlap (``rules.OVERLAP_TOLERANCE``). A verified
    segment lasts at most ``rules.DURATION_MAX_S``, which bounds the range of ``started_at`` read.
    Lowering that constant hides longer climbs already stored, until they leave the upload range.
    """
    end = started_at + timedelta(seconds=duration_s)
    stored_end = ClimbSegment.started_at + ClimbSegment.duration_s * literal_column(
        "interval '1 second'", Interval
    )
    return bool(
        db.scalar(
            select(
                exists().where(
                    ClimbSegment.user_id == user_id,
                    ClimbSegment.status == STATUS_VERIFIED,
                    ClimbSegment.started_at > started_at - timedelta(seconds=DURATION_MAX_S),
                    ClimbSegment.started_at < end - OVERLAP_TOLERANCE,
                    stored_end > started_at + OVERLAP_TOLERANCE,
                    *([] if device_id is None else [ClimbSegment.device_id == device_id]),
                )
            )
        )
    )


def insert_segment(db: Session, row: SegmentRow) -> bool:
    """Insert one row; False if ``(id, started_at)`` already exists (nothing is changed then).

    ``segment_exists`` catches a resend earlier, so this only happens when a concurrent upload
    stores the same segment first. ``received_at`` is left to the database default.
    """
    stmt = (
        pg_insert(ClimbSegment)
        .values(
            id=row.id,
            device_id=row.device_id,
            user_id=row.user_id,
            team_id=row.team_id,
            season_id=row.season_id,
            checkin_id=row.checkin_id,
            building_id=row.building_id,
            status=row.status,
            reject_reason=row.reject_reason,
            steps=row.steps,
            steps_scored=row.steps_scored,
            points=row.points,
            ascent_m=row.ascent_m,
            duration_s=row.duration_s,
            vert_speed_mps=row.vert_speed_mps,
            stair_prob=row.stair_prob,
            classifier_version=row.classifier_version,
            started_at=row.started_at,
        )
        .on_conflict_do_nothing(index_elements=[ClimbSegment.id, ClimbSegment.started_at])
        .returning(ClimbSegment.id)
    )
    return db.execute(stmt).first() is not None


def add_fraud_flag(
    db: Session, segment_id: uuid.UUID, started_at: datetime, user_id: uuid.UUID, rule: str
) -> None:
    db.execute(
        insert(FraudFlag).values(
            segment_id=segment_id, segment_started_at=started_at, user_id=user_id, rule=rule
        )
    )


def add_score(
    db: Session, season_id: int, building_id: int, team_id: int, points: int, steps: int
) -> None:
    """Add to the team's season totals in the building, creating the row if needed."""
    stmt = pg_insert(TeamBuildingScore).values(
        season_id=season_id, building_id=building_id, team_id=team_id, points=points, steps=steps
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                TeamBuildingScore.season_id,
                TeamBuildingScore.building_id,
                TeamBuildingScore.team_id,
            ],
            set_={
                "points": TeamBuildingScore.points + stmt.excluded.points,
                "steps": TeamBuildingScore.steps + stmt.excluded.steps,
            },
        )
    )
