"""Valkey leaderboards and the live-event channel (Week 3 spec section 7).

Keys (score = season points, always an integer):

- ``fw:lb:s{season}:users``: member = user id
- ``fw:lb:s{season}:teams``: member = team id
- ``fw:lb:s{season}:b{building}:teams``: member = team id
- ``fw:lb:s{season}:built``: set by ``rebuild`` (expires after ``BUILT_TTL_S``). Missing means
  "needs rebuild": reads rebuild first, uploads skip the season.
- ``fw:lb:s{season}:lock``: held by a running rebuild (``SET NX``, random token).

Events are published on the channel ``fw:events`` as JSON.

Everything here is best effort for the caller: Valkey errors are raised as ``ValkeyError`` and
the caller decides (the claim path logs and carries on, the read path falls back to the database).
``rebuild`` recomputes every key of a season from ``climb_segment`` and is idempotent, so a drift
caused by a failed incremental update is repaired by running it again.
"""

import json
import secrets
import time
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.valkey import ValkeyClient, ValkeyError

EVENTS_CHANNEL = "fw:events"
# Expiry of the built marker: an hourly rebuild bounds the drift of an update that failed while
# Valkey was unreachable (the marker could not be deleted then).
BUILT_TTL_S = 3600
# Rebuild lock expiry: far above a rebuild's duration, short enough that a crashed rebuild only
# sends reads to the database for a while.
LOCK_TTL_MS = 30_000


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


def built_key(season_id: int) -> str:
    return f"fw:lb:s{season_id}:built"


def is_built(vk: Commands, season_id: int) -> bool:
    return int(vk.execute("EXISTS", built_key(season_id))) == 1


def lock_key(season_id: int) -> str:
    return f"fw:lb:s{season_id}:lock"


# KEYS: lock, built. A running rebuild is marked dirty (as in ``_RECORD``), so it cannot set the
# marker again over an update that failed during it.
_STALE = """
redis.call('DEL', KEYS[2])
if redis.call('EXISTS', KEYS[1]) == 1 then redis.call('APPEND', KEYS[1], ':dirty') end
"""


def mark_stale(vk: Commands, season_id: int) -> None:
    """The next read rebuilds the season."""
    vk.execute("EVAL", _STALE, 2, lock_key(season_id), built_key(season_id))


# KEYS: lock, built, users, teams, building. ARGV: points, user, team. Atomic: all three or none.
# During a rebuild the update is skipped and the lock marked dirty: whether the rebuild's snapshot
# holds this segment is unknown, so the rebuild must not set the marker (the next read rebuilds).
_RECORD = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  redis.call('APPEND', KEYS[1], ':dirty')
  return 0
end
if redis.call('EXISTS', KEYS[2]) == 0 then return 0 end
redis.call('ZINCRBY', KEYS[3], ARGV[1], ARGV[2])
redis.call('ZINCRBY', KEYS[4], ARGV[1], ARGV[3])
redis.call('ZINCRBY', KEYS[5], ARGV[1], ARGV[3])
return 1
"""

# KEYS: lock, built. ARGV: token, marker expiry (0: the rebuild failed). Releases the lock only if
# this rebuild still owns it; sets the marker only if no upload overlapped (lock not dirty). A lost
# lock (expired, maybe taken by another rebuild) means unknown keys: drop the marker.
_FINISH = """
local v = redis.call('GET', KEYS[1])
if not v or string.sub(v, 1, #ARGV[1]) ~= ARGV[1] then
  redis.call('DEL', KEYS[2])
  return 0
end
redis.call('DEL', KEYS[1])
if v == ARGV[1] and ARGV[2] ~= '0' then
  redis.call('SET', KEYS[2], '1', 'EX', ARGV[2], 'NX')
  return 1
end
redis.call('DEL', KEYS[2])
return 0
"""


def record_verified(
    vk: Commands, season_id: int, user_id: object, team_id: int, building_id: int, points: int
) -> bool:
    """Add ``points`` of one verified segment to the three boards, in one atomic script.

    Skipped (False) when ``points <= 0`` or the season is not built: the rebuild will count it.
    On an error the caller marks the season stale (``mark_stale``).
    """
    if points <= 0:
        return False
    keys = (lock_key(season_id), built_key(season_id), users_key(season_id), teams_key(season_id))
    return bool(
        vk.execute(
            "EVAL",
            _RECORD,
            5,
            *keys,
            building_key(season_id, building_id),
            points,
            str(user_id),
            str(team_id),
        )
    )


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
_BUILDING_IDS = text("SELECT id FROM building")


def _check_deadline(deadline: float) -> None:
    """A ValkeyError, so the rebuild's ``finally`` releases the lock and a read falls back to the
    database. A season that always needs more than half the lock expiry never converges: its
    reads stay on the database."""
    if time.monotonic() > deadline:
        raise ValkeyError("leaderboard rebuild took over half the lock expiry")


def _replace(vk: Commands, key: str, scores: dict[str, int], token: str, deadline: float) -> None:
    """Swap ``key`` for ``scores`` atomically enough: build aside, then RENAME over it."""
    if not scores:
        vk.execute("DEL", key)
        return
    tmp = f"{key}:rebuild:{token}"  # per rebuild: one that lost its lock cannot mix into another
    try:
        for i in range(0, len(scores), 500):
            _check_deadline(deadline)
            chunk = list(scores.items())[i : i + 500]
            args: list[str | int] = []
            for member, points in chunk:
                args += [points, member]
            vk.execute("ZADD", tmp, *args)
        vk.execute("RENAME", tmp, key)
    finally:
        vk.execute("DEL", tmp)  # no-op after the RENAME; drops a half-written key


def rebuild(db: Session, vk: Commands, season_id: int) -> bool:
    """Recompute the three board families of a season from verified segments (season totals),
    then set the built marker. True when the season is marked built; False when another rebuild
    holds the lock or an upload overlapped this one (the marker stays missing)."""
    token = secrets.token_hex(16)
    if not vk.execute("SET", lock_key(season_id), token, "NX", "PX", LOCK_TTL_MS):
        return False
    # Stop at half the lock expiry, while the lock is still ours.
    deadline = time.monotonic() + LOCK_TTL_MS / 2000
    ok = False
    try:
        # Another reader rebuilt it while we waited for the lock: only release (the finish below).
        if not is_built(vk, season_id):
            _rebuild_keys(db, vk, season_id, token, deadline)
        ok = True
    finally:
        expiry = BUILT_TTL_S if ok else 0
        built = vk.execute(
            "EVAL", _FINISH, 2, lock_key(season_id), built_key(season_id), token, expiry
        )
    return bool(built)


def _rebuild_keys(db: Session, vk: Commands, season_id: int, token: str, deadline: float) -> None:
    params = {"s": season_id}
    users = {r.member: r.points for r in db.execute(_USER_TOTALS, params)}
    teams = {r.member: r.points for r in db.execute(_TEAM_TOTALS, params)}
    buildings: dict[int, dict[str, int]] = {b: {} for b in db.execute(_BUILDING_IDS).scalars()}
    for r in db.execute(_BUILDING_TOTALS, params):
        buildings.setdefault(r.building_id, {})[r.member] = r.points
    boards = [(users_key(season_id), users), (teams_key(season_id), teams)]
    # Every building, so stale keys go too.
    boards += [(building_key(season_id, b), scores) for b, scores in buildings.items()]
    for key, scores in boards:
        _check_deadline(deadline)
        _replace(vk, key, scores, token, deadline)


__all__ = [
    "EVENTS_CHANNEL",
    "Commands",
    "ValkeyClient",
    "building_key",
    "built_key",
    "flip_message",
    "is_built",
    "lock_key",
    "mark_stale",
    "publish_flip",
    "rebuild",
    "record_verified",
    "teams_key",
    "top",
    "users_key",
]
