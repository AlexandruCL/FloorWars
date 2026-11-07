"""Plain data passed between the segment service, its repository and the claim transaction.

Frozen dataclasses with no database or framework behaviour, so ``rules.check_item`` stays pure
and tests can build them by hand. The tables are in ``app/db/models.py``.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import Range

STATUS_VERIFIED = "verified"
STATUS_REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Receipt:
    """The stored answer for ``(device_id, id)``; a resend is answered from it."""

    device_id: uuid.UUID
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    reject_reason: str | None
    steps_scored: int


@dataclass(frozen=True, slots=True)
class ItemContext:
    """What the rules need from the database for one item.

    The ``checkin_*`` fields are all ``None`` when ``checkin_id`` is unknown. They describe the
    check-in whoever owns it: the rule compares ``checkin_user_id`` with the signed-in user.
    ``checkin_valid_during.contains(started_at)`` applies the stored bounds (``[)`` in practice).
    ``season_id`` is the season containing ``started_at``; ``team_id`` is the user's team in it.
    """

    checkin_user_id: uuid.UUID | None
    checkin_building_id: int | None
    checkin_valid_during: Range[datetime] | None
    season_id: int | None
    team_id: int | None


@dataclass(frozen=True, slots=True)
class SegmentRow:
    """One ``climb_segment`` row. ``received_at`` is set by the database."""

    id: uuid.UUID
    device_id: uuid.UUID
    user_id: uuid.UUID
    team_id: int
    season_id: int
    checkin_id: uuid.UUID
    building_id: int
    status: str
    reject_reason: str | None
    steps: int
    steps_scored: int
    points: int
    ascent_m: float
    duration_s: float
    vert_speed_mps: float
    stair_prob: float
    classifier_version: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class TeamPoints:
    """A team's points in a building over the rolling window.

    ``reached_at`` is when the team's running total first equalled ``points``. The earliest
    ``reached_at`` wins a tie when the current owner is not among the top teams.
    """

    team_id: int
    code: str
    points: int
    reached_at: datetime


@dataclass(frozen=True, slots=True)
class Flip:
    """A change of owner, already written to ``game_event`` (``event_id``) in the transaction.

    ``from_team_id`` and ``from_code`` are ``None`` when the building had no owner.
    """

    building_id: int
    season_id: int
    from_team_id: int | None
    to_team_id: int
    from_code: str | None
    to_code: str
    at: datetime
    event_id: int
