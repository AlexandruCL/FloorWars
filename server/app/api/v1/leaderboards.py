"""``GET /v1/leaderboards``: individual, team and building boards for a season.

Served from the Valkey sorted sets of ``app.leaderboards``. When Valkey is not configured or
fails, the board is computed from ``climb_segment`` (season totals). When a key is missing and the
database holds points for that board, the season is rebuilt once and the key read again; without
points the board is empty and nothing is rebuilt.

``scope=building`` ranks the **teams** in that building for the season (spec section 8).

Problem types (404): ``season-not-found``, ``building-not-found``, ``no-active-season``.
"""

import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import leaderboards as lb
from app.api.deps import CurrentUser, DbSession
from app.api.problems import ProblemError, problem_doc
from app.api.v1.teams import MAX_ID
from app.db.models import Building, Season
from app.teams import service as teams_service
from app.valkey import ValkeyClient, ValkeyError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["leaderboards"])

Scope = Literal["individual", "team", "building"]


class LeaderboardEntryOut(BaseModel):
    rank: int
    id: str
    name: str
    points: int


class LeaderboardOut(BaseModel):
    scope: Scope
    season_id: int
    building_id: int | None
    entries: list[LeaderboardEntryOut]


_DB_BOARDS = {
    "individual": text(
        "SELECT user_id::text AS member, sum(points)::bigint AS points FROM climb_segment "
        "WHERE season_id = :s AND status = 'verified' GROUP BY user_id HAVING sum(points) > 0 "
        "ORDER BY points DESC, member LIMIT :n"
    ),
    "team": text(
        "SELECT team_id::text AS member, sum(points)::bigint AS points FROM climb_segment "
        "WHERE season_id = :s AND status = 'verified' GROUP BY team_id HAVING sum(points) > 0 "
        "ORDER BY points DESC, member LIMIT :n"
    ),
    "building": text(
        "SELECT team_id::text AS member, sum(points)::bigint AS points FROM climb_segment "
        "WHERE season_id = :s AND building_id = :b AND status = 'verified' "
        "GROUP BY team_id HAVING sum(points) > 0 ORDER BY points DESC, member LIMIT :n"
    ),
}
_SEASON_HAS_POINTS = text(
    "SELECT EXISTS (SELECT 1 FROM climb_segment "
    "WHERE season_id = :s AND status = 'verified' AND points > 0)"
)
_BUILDING_HAS_POINTS = text(
    "SELECT EXISTS (SELECT 1 FROM climb_segment "
    "WHERE season_id = :s AND building_id = :b AND status = 'verified' AND points > 0)"
)


def _has_points(db: Session, season_id: int, building_id: int | None) -> bool:
    if building_id is None:
        return bool(db.execute(_SEASON_HAS_POINTS, {"s": season_id}).scalar_one())
    params = {"s": season_id, "b": building_id}
    return bool(db.execute(_BUILDING_HAS_POINTS, params).scalar_one())


def _from_database(
    db: Session, scope: Scope, season_id: int, building_id: int | None, limit: int
) -> list[tuple[str, int]]:
    params = {"s": season_id, "b": building_id, "n": limit}
    if scope != "building":
        params.pop("b")
    return [(r.member, r.points) for r in db.execute(_DB_BOARDS[scope], params)]


def _from_valkey(
    vk: ValkeyClient, db: Session, scope: Scope, season_id: int, building_id: int | None, limit: int
) -> list[tuple[str, int]] | None:
    if scope == "individual":
        key = lb.users_key(season_id)
    elif scope == "team":
        key = lb.teams_key(season_id)
    else:
        if building_id is None:
            raise ValueError("building_id is required for the building board")
        key = lb.building_key(season_id, building_id)
    entries = lb.top(vk, key, limit)
    if entries is None:  # never built or evicted: rebuild the season once, then read again
        if not _has_points(db, season_id, building_id):  # a rebuild would not create the key
            return []
        lb.rebuild(db, vk, season_id)
        entries = lb.top(vk, key, limit)
    return entries


def _names(db: Session, scope: Scope, members: list[str]) -> dict[str, str]:
    if not members:
        return {}
    if scope == "individual":
        ids = [uuid.UUID(m) for m in members]
        rows = db.execute(
            text('SELECT id::text AS k, display_name AS v FROM "user" WHERE id = ANY(:ids)'),
            {"ids": ids},
        )
    else:
        rows = db.execute(
            text("SELECT id::text AS k, code AS v FROM team WHERE id = ANY(:ids)"),
            {"ids": [int(m) for m in members]},
        )
    return {r.k: r.v for r in rows}


@router.get(
    "/leaderboards",
    response_model=LeaderboardOut,
    responses={
        401: problem_doc("Missing or invalid access token."),
        404: problem_doc(
            "Unknown season (``season-not-found``) or building (``building-not-found``), or no "
            "season is active and ``season_id`` was not given (``no-active-season``)."
        ),
        422: problem_doc("Bad query, or ``scope=building`` without ``building_id``."),
    },
    operation_id="getLeaderboard",
)
def get_leaderboard(
    request: Request,
    _user: CurrentUser,
    db: DbSession,
    scope: Scope,
    season_id: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
    building_id: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LeaderboardOut:
    """The best ``limit`` users or teams by points of verified segments."""
    if scope == "building" and building_id is None:
        raise ProblemError(422, detail="building_id is required when scope is building.")
    if scope != "building":
        building_id = None
    if season_id is None:
        season_id = teams_service.active_season(db).id
    elif db.get(Season, season_id) is None:
        raise ProblemError(
            404, detail="No such season.", type_=teams_service.TYPE_PREFIX + "season-not-found"
        )
    if building_id is not None and db.get(Building, building_id) is None:
        raise ProblemError(
            404, detail="No such building.", type_=teams_service.TYPE_PREFIX + "building-not-found"
        )

    vk: ValkeyClient | None = getattr(request.app.state, "valkey", None)
    entries: list[tuple[str, int]] | None = None
    if vk is not None:
        try:
            entries = _from_valkey(vk, db, scope, season_id, building_id, limit)
        except ValkeyError:
            logger.warning("leaderboard served from the database: valkey failed")
    if entries is None:
        entries = _from_database(db, scope, season_id, building_id, limit)

    names = _names(db, scope, [m for m, _ in entries])
    entries.sort(key=lambda e: (-e[1], names.get(e[0], e[0])))
    return LeaderboardOut(
        scope=scope,
        season_id=season_id,
        building_id=building_id,
        entries=[
            LeaderboardEntryOut(
                rank=i,
                id=names.get(m, m) if scope != "individual" else m,
                name=names.get(m, m),
                points=p,
            )
            for i, (m, p) in enumerate(entries, start=1)
        ],
    )
