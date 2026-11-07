"""The claim transaction: points of a segment and the owner of a building."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.segments.models import Flip, TeamPoints


def points_for(steps: int, prior_steps: int) -> int:
    raise NotImplementedError


def rolling_points(
    db: Session, season_id: int, building_id: int, now: datetime
) -> list[TeamPoints]:
    raise NotImplementedError


def recompute_owner(db: Session, season_id: int, building_id: int, now: datetime) -> Flip | None:
    raise NotImplementedError
