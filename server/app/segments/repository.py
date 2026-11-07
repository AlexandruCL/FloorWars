"""All SQL of the segment batch, as small functions over the sync ``Session``.

No commits here: the service owns the transaction.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.segments.models import ItemContext, Receipt, SegmentRow


def lock_user(db: Session, user_id: uuid.UUID) -> bool:
    raise NotImplementedError


def device_belongs(db: Session, user_id: uuid.UUID, device_id: uuid.UUID) -> bool:
    raise NotImplementedError


def get_receipt(db: Session, device_id: uuid.UUID, segment_id: uuid.UUID) -> Receipt | None:
    raise NotImplementedError


def insert_receipt(
    db: Session,
    device_id: uuid.UUID,
    segment_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
    reject_reason: str | None,
    steps_scored: int,
) -> None:
    raise NotImplementedError


def load_context(
    db: Session, user_id: uuid.UUID, checkin_id: uuid.UUID, started_at: datetime
) -> ItemContext:
    raise NotImplementedError


def verified_steps_between(db: Session, user_id: uuid.UUID, start: datetime, end: datetime) -> int:
    raise NotImplementedError


def insert_segment(db: Session, row: SegmentRow) -> None:
    raise NotImplementedError


def add_fraud_flag(
    db: Session, segment_id: uuid.UUID, started_at: datetime, user_id: uuid.UUID, rule: str
) -> None:
    raise NotImplementedError


def add_score(
    db: Session, season_id: int, building_id: int, team_id: int, points: int, steps: int
) -> None:
    raise NotImplementedError
