"""Plausibility rules of an uploaded segment (Week 3 spec sections 3 and 4). Pure functions.

``check_item`` runs the rules in their fixed order and returns the first failure. The database
values it needs arrive as arguments, loaded by the caller. ``check_bounds`` is the first group on
its own: the caller runs it before any query, because a ``started_at`` far outside the accepted
range is not safe for date arithmetic.
"""

import math
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, Literal

from app.segments.models import ItemContext

if TYPE_CHECKING:
    from app.segments.schemas import Segment

BATCH_MAX: Final = 100
STARTED_AT_MAX_AGE: Final = timedelta(days=7)
STARTED_AT_FUTURE_SKEW: Final = timedelta(minutes=5)
ASCENT_MIN_M: Final = 2.0
ASCENT_MAX_M: Final = 120.0
STEPS_MIN: Final = 1
STEPS_MAX: Final = 2000
DURATION_MIN_S: Final = 5.0
DURATION_MAX_S: Final = 180.0
STAIR_PROB_MIN: Final = 0.0
STAIR_PROB_MAX: Final = 1.0
SPEED_MIN_MPS: Final = 0.1
SPEED_MAX_MPS: Final = 0.9
SPEED_TOLERANCE: Final = 0.2
STEPS_PER_M_MIN: Final = 4.0
STEPS_PER_M_MAX: Final = 8.0
CADENCE_MAX_STEPS_PER_S: Final = 3.0
VERIFIED_STEPS_PER_10_MIN: Final = 600
RATE_WINDOW: Final = timedelta(minutes=10)
# Climbs that only touch at an end do not overlap: a stored ``real`` duration is rounded.
OVERLAP_TOLERANCE: Final = timedelta(milliseconds=1)
UPLOADS_PER_HOUR: Final = 60
FULL_POINT_STEPS_PER_HOUR: Final = 300
REDUCED_POINT_PER_STEP: Final = 0.5
POINTS_WINDOW: Final = timedelta(hours=1)
OWNERSHIP_WINDOW: Final = timedelta(days=7)

RejectReason = Literal[
    "pressure_steps_mismatch",
    "ascent_range",
    "steps_range",
    "stair_prob_range",
    "speed",
    "cadence",
    "duration",
    "overlap",
    "rate_limit",
    "no_checkin",
    "building_mismatch",
    "started_at_range",
    "season_inactive",
    "no_team",
]

# State problems, not cheating: no fraud_flag row.
NOT_FRAUD: Final[frozenset[RejectReason]] = frozenset(
    {"started_at_range", "no_checkin", "season_inactive", "no_team"}
)
# Rules 1 to 4: the item may lack a usable team, season, building or check-in, or hold values the
# table cannot store, so it is recorded only in segment_receipt.
RECEIPT_ONLY: Final[frozenset[RejectReason]] = frozenset(
    {
        "started_at_range",
        "steps_range",
        "ascent_range",
        "duration",
        "stair_prob_range",
        "no_checkin",
        "building_mismatch",
        "season_inactive",
        "no_team",
    }
)


def _within(value: float, low: float, high: float) -> bool:
    """False for NaN as well, since every comparison with NaN is false."""
    return low <= value <= high


def check_bounds(item: "Segment", now: datetime) -> RejectReason | None:
    """Rules 1 and 2. No database, safe for any parsed value."""
    if item.started_at < now - STARTED_AT_MAX_AGE or item.started_at > now + STARTED_AT_FUTURE_SKEW:
        return "started_at_range"
    if not _within(item.steps, STEPS_MIN, STEPS_MAX):
        return "steps_range"
    if not _within(item.ascent_m, ASCENT_MIN_M, ASCENT_MAX_M):
        return "ascent_range"
    if not _within(item.duration_s, DURATION_MIN_S, DURATION_MAX_S):
        return "duration"
    if not _within(item.stair_prob, STAIR_PROB_MIN, STAIR_PROB_MAX):
        return "stair_prob_range"
    return None


def _check_state(item: "Segment", ctx: ItemContext, user_id: uuid.UUID) -> RejectReason | None:
    """Rules 3 and 4. Only ``started_at`` must be inside the check-in: a climb that starts in it
    and ends after it still counts."""
    if (
        ctx.checkin_user_id != user_id
        or ctx.checkin_valid_during is None
        or not ctx.checkin_valid_during.contains(item.started_at)
    ):
        return "no_checkin"
    if item.building_id != ctx.checkin_building_id:
        return "building_mismatch"
    if ctx.season_id is None:
        return "season_inactive"
    if ctx.team_id is None:
        return "no_team"
    return None


def _check_physics(item: "Segment") -> RejectReason | None:
    """Rules 5 to 7. ``check_bounds`` has passed, so the divisors are positive and finite."""
    speed = item.vert_speed_mps
    measured = item.ascent_m / item.duration_s
    if not _within(speed, SPEED_MIN_MPS, SPEED_MAX_MPS) or (
        abs(speed - measured) > SPEED_TOLERANCE * measured
    ):
        return "speed"
    if not _within(item.steps / item.ascent_m, STEPS_PER_M_MIN, STEPS_PER_M_MAX):
        return "pressure_steps_mismatch"
    if item.steps / item.duration_s > CADENCE_MAX_STEPS_PER_S:
        return "cadence"
    return None


def check_item(
    item: "Segment",
    ctx: ItemContext,
    *,
    user_id: uuid.UUID,
    now: datetime,
    recent_verified_steps: int,
    overlaps_verified: bool = False,
) -> RejectReason | None:
    """The first failed rule, or None for a verified segment.

    ``recent_verified_steps``: the user's verified steps with ``started_at`` in
    ``(started_at - 10 min, started_at + 10 min)``. ``overlaps_verified``: whether the climb shares
    time with a verified segment of the user. The default is for callers judging a climb alone.
    """
    reason = check_bounds(item, now) or _check_state(item, ctx, user_id) or _check_physics(item)
    if reason is not None:
        return reason
    if overlaps_verified:
        return "overlap"
    if recent_verified_steps + item.steps > VERIFIED_STEPS_PER_10_MIN:
        return "rate_limit"
    return None


def storable_real(value: float) -> float:
    """``value`` as a PostgreSQL ``real`` accepts it: a finite float8 outside its range makes the
    cast fail, which would lose the whole batch. Any stored row can hold such a value: a rejected
    one a huge or tiny speed, a verified one a tiny ``stair_prob`` (it passes the 0 to 1 rule)."""
    if not math.isfinite(value):
        return value
    if abs(value) > 3.4e38:
        return math.copysign(math.inf, value)
    if abs(value) < 1e-37:
        return 0.0
    return value
