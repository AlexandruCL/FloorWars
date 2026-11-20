"""``GET /v1/me/season-stats``: totals, rank and team buildings of one user in one season."""

import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import leaderboards as lb
from app.landing.service import user_scan_points
from app.me.landmarks import progress
from app.valkey import ValkeyClient, ValkeyError

logger = logging.getLogger(__name__)

_TOTALS = text(
    "SELECT coalesce(sum(steps_scored), 0)::bigint AS steps, "
    "coalesce(sum(ascent_m::float8), 0) AS ascent, coalesce(sum(points), 0)::bigint AS points "
    "FROM climb_segment WHERE user_id = :u AND season_id = :s AND status = 'verified'"
)
_RANK = text(
    f"SELECT count(*) + 1 FROM (SELECT 1 FROM {lb.POINTS_SOURCE} "  # noqa: S608
    "WHERE season_id = :s GROUP BY user_id HAVING sum(points) > :p) t"
)
_OWNED = text("SELECT count(*) FROM building_claim WHERE season_id = :s AND team_id = :t")
_TEAM = text("SELECT team_id FROM team_membership WHERE user_id = :u AND season_id = :s")


def _rank_valkey(vk: ValkeyClient, db: Session, season_id: int, user_id: uuid.UUID) -> int | None:
    if not lb.is_built(vk, season_id) and not lb.rebuild(db, vk, season_id):
        return None
    key = lb.users_key(season_id)
    score = vk.execute("ZSCORE", key, str(user_id))
    if score is None:
        return None
    higher = vk.execute("ZCOUNT", key, f"({int(float(score))}", "+inf")
    return int(higher) + 1


def rank(
    db: Session, vk: ValkeyClient | None, season_id: int, user_id: uuid.UUID, points: int
) -> int | None:
    """Competition rank (ties share it) on the individual board; None without points."""
    if points <= 0:
        return None
    if vk is not None:
        try:
            found = _rank_valkey(vk, db, season_id, user_id)
        except ValkeyError:
            logger.warning("rank served from the database: valkey failed")
        else:
            if found is not None:
                return found
    return int(db.execute(_RANK, {"s": season_id, "p": points}).scalar_one())


def stats(
    db: Session, vk: ValkeyClient | None, user_id: uuid.UUID, season_id: int
) -> dict[str, object]:
    row = db.execute(_TOTALS, {"u": user_id, "s": season_id}).one()
    points = int(row.points) + user_scan_points(db, user_id, season_id)
    team_id = db.execute(_TEAM, {"u": user_id, "s": season_id}).scalar_one_or_none()
    owned = 0
    if team_id is not None:
        owned = int(db.execute(_OWNED, {"s": season_id, "t": team_id}).scalar_one())
    ascent = round(float(row.ascent), 2)
    return {
        "season_id": season_id,
        "team_id": team_id,
        "steps_verified": int(row.steps),
        "ascent_m": ascent,
        "points": points,
        "rank": rank(db, vk, season_id, user_id, points),
        "buildings_owned_by_team": owned,
        "landmarks": progress(ascent),
    }
