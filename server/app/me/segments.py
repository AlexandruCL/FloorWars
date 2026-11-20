"""``GET /v1/me/segments``: keyset pagination on ``(started_at, id)``, newest first."""

import base64
import binascii
import uuid
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.api.problems import ProblemError
from app.db.models import ClimbSegment


def encode_cursor(started_at: datetime, segment_id: uuid.UUID) -> str:
    raw = f"{started_at.isoformat()}|{segment_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        at, _, sid = raw.partition("|")
        started_at = datetime.fromisoformat(at)
        if started_at.tzinfo is None:
            raise ValueError("naive cursor time")
        return started_at, uuid.UUID(sid)
    except (ValueError, binascii.Error):
        raise ProblemError(422, detail="Invalid cursor.") from None


def page(
    db: Session, user_id: uuid.UUID, limit: int, cursor: str | None
) -> tuple[list[ClimbSegment], str | None]:
    """At most ``limit`` rows of the user and the cursor of the next page (None on the last)."""
    query = select(ClimbSegment).where(ClimbSegment.user_id == user_id)
    if cursor is not None:
        started_at, segment_id = decode_cursor(cursor)
        query = query.where(
            tuple_(ClimbSegment.started_at, ClimbSegment.id) < (started_at, segment_id)
        )
    query = query.order_by(ClimbSegment.started_at.desc(), ClimbSegment.id.desc()).limit(limit + 1)
    rows = list(db.scalars(query))
    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    return rows, encode_cursor(rows[-1].started_at, rows[-1].id)
