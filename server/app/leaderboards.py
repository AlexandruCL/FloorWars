"""Valkey leaderboards and the live-event channel (Week 3 spec section 7).

Keys (score = season points, always an integer):

- ``fw:lb:s{season}:users``: member = user id
- ``fw:lb:s{season}:teams``: member = team id
- ``fw:lb:s{season}:b{building}:teams``: member = team id

Events are published on the channel ``fw:events`` as JSON.

Everything here is best effort for the caller: Valkey errors are raised as ``ValkeyError`` and
the caller decides (the claim path logs and carries on, the read path falls back to the database).
``rebuild`` recomputes every key of a season from ``climb_segment`` and is idempotent, so a drift
caused by a failed incremental update is repaired by running it again.
"""

import json
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.valkey import ValkeyClient, ValkeyError

EVENTS_CHANNEL = "fw:events"


class Commands(Protocol):
    """The part of ``ValkeyClient`` used here (a fake with ``execute`` is enough in tests)."""

    def execute(self, *args: str | int) -> Any: ...


class FlipLike(Protocol):
    """The fields of ``app.segments.models.Flip`` that the event carries."""

    @property
    def building_id(self) -> int: ...
    @property
    def event_id(self) -> int: ...
    @property
    def from_code(self) -> str | None: ...
    @property
    def to_code(self) -> str: ...
    @property
    def at(self) -> datetime: ...


def users_key(season_id: int) -> str:
    return f"fw:lb:s{season_id}:users"


def teams_key(season_id: int) -> str:
    return f"fw:lb:s{season_id}:teams"


def building_key(season_id: int, building_id: int) -> str:
    return f"fw:lb:s{season_id}:b{building_id}:teams"


def record_verified(
    vk: Commands, season_id: int, user_id: object, team_id: int, building_id: int, points: int
) -> None:
    """Add ``points`` of one verified segment to the three boards. ``points <= 0`` is ignored."""
    if points <= 0:
        return
    vk.execute("ZINCRBY", users_key(season_id), points, str(user_id))
    vk.execute("ZINCRBY", teams_key(season_id), points, str(team_id))
    vk.execute("ZINCRBY", building_key(season_id, building_id), points, str(team_id))


def flip_message(flip: FlipLike) -> str:
    """The JSON text of a ``building_flipped`` event (team codes, not ids)."""
    return json.dumps(
        {
            "type": "building_flipped",
            "event_id": flip.event_id,
            "building_id": flip.building_id,
            "from_team": flip.from_code,
            "to_team": flip.to_code,
            "at": flip.at.isoformat(),
        },
        separators=(",", ":"),
    )


def publish_flip(vk: Commands, flip: FlipLike) -> None:
    vk.execute("PUBLISH", EVENTS_CHANNEL, flip_message(flip))


def top(vk: Commands, key: str, limit: int) -> list[tuple[str, int]] | None:
    """The best ``limit`` members of ``key`` with their points, best first.

    Ties are ordered by member (descending, as Valkey does for equal scores); callers that need
    a stable order re-sort. ``None`` when the key does not exist (never built, or evicted).
    """
    reply = vk.execute("ZREVRANGE", key, 0, limit - 1, "WITHSCORES")
    if not isinstance(reply, list):
        raise ValkeyError("unexpected reply to ZREVRANGE")
    if not reply:
        return None if int(vk.execute("EXISTS", key)) == 0 else []
    out: list[tuple[str, int]] = []
    for i in range(0, len(reply) - 1, 2):
        member, score = reply[i], reply[i + 1]
        if isinstance(member, bytes):
            member = member.decode()
        out.append((str(member), int(float(score))))
    return out


_USER_TOTALS = text(
    "SELECT user_id::text AS member, sum(points)::bigint AS points FROM climb_segment "
    "WHERE season_id = :s AND status = 'verified' GROUP BY user_id HAVING sum(points) > 0"
)
_TEAM_TOTALS = text(
    "SELECT team_id::text AS member, sum(points)::bigint AS points FROM climb_segment "
    "WHERE season_id = :s AND status = 'verified' GROUP BY team_id HAVING sum(points) > 0"
)
_BUILDING_TOTALS = text(
    "SELECT building_id, team_id::text AS member, sum(points)::bigint AS points "
    "FROM climb_segment WHERE season_id = :s AND status = 'verified' "
    "GROUP BY building_id, team_id HAVING sum(points) > 0"
)


def _replace(vk: Commands, key: str, scores: dict[str, int]) -> None:
    """Swap ``key`` for ``scores`` atomically enough: build aside, then RENAME over it."""
    if not scores:
        vk.execute("DEL", key)
        return
    tmp = f"{key}:rebuild"
    vk.execute("DEL", tmp)
    for i in range(0, len(scores), 500):
        chunk = list(scores.items())[i : i + 500]
        args: list[str | int] = []
        for member, points in chunk:
            args += [points, member]
        vk.execute("ZADD", tmp, *args)
    vk.execute("RENAME", tmp, key)


def rebuild(db: Session, vk: Commands, season_id: int) -> None:
    """Recompute the three board families of a season from verified segments (season totals)."""
    params = {"s": season_id}
    users = {r.member: r.points for r in db.execute(_USER_TOTALS, params)}
    teams = {r.member: r.points for r in db.execute(_TEAM_TOTALS, params)}
    buildings: dict[int, dict[str, int]] = {}
    for r in db.execute(_BUILDING_TOTALS, params):
        buildings.setdefault(r.building_id, {})[r.member] = r.points
    _replace(vk, users_key(season_id), users)
    _replace(vk, teams_key(season_id), teams)
    for building_id, scores in buildings.items():
        _replace(vk, building_key(season_id, building_id), scores)


__all__ = [
    "EVENTS_CHANNEL",
    "Commands",
    "ValkeyClient",
    "building_key",
    "flip_message",
    "publish_flip",
    "rebuild",
    "record_verified",
    "teams_key",
    "top",
    "users_key",
]
