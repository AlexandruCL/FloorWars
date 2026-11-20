"""``GET /v1/me/events``: the notification feed (plan 7.2.1), the same one the socket replays.

Every event of every season the user has joined, oldest first (``app.events.feed``). There is
no server-side notification rate limit: the phone notifies at most once per building per 10
minutes, and a server drop would also hide flips from the live standings (Ionut, 2026-11-20).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.api.problems import problem_doc
from app.events.feed import MAX_EVENT_ID, MAX_LIMIT, events_after

router = APIRouter(tags=["me"])


class GameEventPageOut(BaseModel):
    items: list[dict[str, Any]]
    last_event_id: int
    has_more: bool


@router.get(
    "/me/events",
    response_model=GameEventPageOut,
    responses={
        401: problem_doc("Missing, invalid or expired access token."),
        422: problem_doc("since or limit out of range."),
    },
    operation_id="listMyEvents",
)
def list_my_events(
    user: CurrentUser,
    db: DbSession,
    since: Annotated[int, Query(ge=0, le=MAX_EVENT_ID)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> GameEventPageOut:
    """Game events after ``since``, ascending ``event_id``."""
    page = events_after(db, user.id, since, limit)
    return GameEventPageOut(
        items=page.items, last_event_id=page.last_event_id, has_more=page.has_more
    )
