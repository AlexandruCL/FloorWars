"""The game-event feed (plan 7.2.1): ``GET /v1/me/events`` and the WebSocket replay.

``event_json`` is the only place that turns a ``game_event`` row into the contract's ``WsEvent``
JSON; a ``building_flipped`` row gives exactly what ``leaderboards.flip_message`` published.
``events_after`` is the only place that decides who sees an event: every event of every season
the user has joined (a ``team_membership`` row for the event's ``season_id``; Ionut, 2026-11-19).
The socket hub applies the same rule to live messages with ``visible``.
"""

import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GameEvent, Team, TeamMembership

# Highest game_event id (bigint): a larger ``since`` is a 422, not a database error.
MAX_EVENT_ID = 2**63 - 1
MAX_LIMIT = 100


@dataclass(frozen=True, slots=True)
class EventPage:
    items: list[dict[str, object]]
    last_event_id: int
    has_more: bool


def visible(season_id: int | None, joined: Collection[int]) -> bool:
    """The visibility rule for one event, given the user's joined season ids."""
    return season_id is not None and season_id in joined


def event_json(row: GameEvent, codes: Mapping[int, str]) -> dict[str, object]:
    """``WsEvent`` JSON of one row; ``codes`` maps team id to team code."""
    if row.kind == "building_flipped":
        return {
            "type": "building_flipped",
            "event_id": row.id,
            "building_id": row.building_id,
            "from_team": None if row.from_team is None else codes[row.from_team],
            "to_team": codes[cast(int, row.to_team)],  # always set on a flip
            "at": row.created_at.astimezone(UTC).isoformat(),
        }
    # season_state: nothing writes one before the Week 5 pause switch; its payload carries
    # ``paused`` (bool) and ``ends_at`` (ISO 8601 date-time).
    return {
        "type": "season_state",
        "event_id": row.id,
        "paused": row.payload["paused"],
        "ends_at": row.payload["ends_at"],
    }


def joined_seasons(db: Session, user_id: uuid.UUID) -> set[int]:
    return set(
        db.execute(
            select(TeamMembership.season_id).where(TeamMembership.user_id == user_id)
        ).scalars()
    )


def events_after(db: Session, user_id: uuid.UUID, since: int, limit: int) -> EventPage:
    """The user's visible events with ``id > since``, ascending, at most ``limit``.

    Known window: ids are assigned at insert, so a lower id can commit after a higher one; a poll
    whose ``since`` already passed it never sees it (the socket delivers it live).
    """
    # TODO(week 5): xid8 + pg_snapshot_xmin filter on the feed
    joined = select(TeamMembership.season_id).where(TeamMembership.user_id == user_id)
    rows = list(
        db.execute(
            select(GameEvent)
            .where(GameEvent.id > since, GameEvent.season_id.in_(joined))
            .order_by(GameEvent.id)
            .limit(limit + 1)
        ).scalars()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    team_ids = {t for r in rows for t in (r.from_team, r.to_team) if t is not None}
    codes: dict[int, str] = {}
    if team_ids:
        codes = dict(db.execute(select(Team.id, Team.code).where(Team.id.in_(team_ids))).all())
    return EventPage(
        items=[event_json(r, codes) for r in rows],
        last_event_id=rows[-1].id if rows else since,
        has_more=has_more,
    )
