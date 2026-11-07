"""The claim transaction: points of a segment and the owner of a building.

``recompute_owner`` runs last in the batch transaction and locks the building's claim row until
the commit, so claims on one building are serialised. PostgreSQL's default READ COMMITTED matters
here: the owner query takes a fresh snapshot after the lock is granted, so it sees every segment
of the transaction that held the lock before. The last transaction to commit therefore always
decides on all the segments.
"""

import math
from datetime import datetime

from sqlalchemy import insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import BuildingClaim, GameEvent, Team
from app.segments.models import Flip, TeamPoints
from app.segments.rules import (
    FULL_POINT_STEPS_PER_HOUR,
    OWNERSHIP_WINDOW,
    REDUCED_POINT_PER_STEP,
)

EVENT_BUILDING_FLIPPED = "building_flipped"

# Verified points per team in the window, best first. ``status = 'verified'`` is written as a
# literal so the planner can match the partial index; ``started_at`` has no upper bound because a
# segment may start up to 5 minutes in the future and must count at once.
#
# ``reached_at`` is when the team's running total first equalled its final total: a segment worth
# 0 points after that moment does not make the team later. ``ORDER BY started_at, id`` gives every
# segment its own running total, also when two share a ``started_at``.
ROLLING_POINTS_SQL = text(
    """
    WITH counted AS (
        SELECT team_id,
               started_at,
               sum(points) OVER (PARTITION BY team_id ORDER BY started_at, id) AS running,
               sum(points) OVER (PARTITION BY team_id) AS total
        FROM climb_segment
        WHERE building_id = :building_id
          AND status = 'verified'
          AND season_id = :season_id
          AND started_at >= :window_start
    )
    SELECT counted.team_id,
           team.code,
           counted.total::int AS points,
           min(counted.started_at) FILTER (WHERE counted.running = counted.total) AS reached_at
    FROM counted
    JOIN team ON team.id = counted.team_id
    WHERE counted.total > 0
    GROUP BY counted.team_id, team.code, counted.total
    ORDER BY points DESC, reached_at ASC, counted.team_id ASC
    """
)


def points_for(steps: int, prior_steps: int) -> int:
    """Points of a verified segment, given the user's other verified steps within an hour of it,
    on either side."""
    full = max(0, min(steps, FULL_POINT_STEPS_PER_HOUR - prior_steps))
    return math.floor(full + (steps - full) * REDUCED_POINT_PER_STEP)


def rolling_points(
    db: Session, season_id: int, building_id: int, now: datetime
) -> list[TeamPoints]:
    """Teams with points in the building over the rolling window, in winning order.

    Winning order: most points, then who reached that total first. Teams without points are left
    out; the current owner's advantage in a tie is applied by ``recompute_owner``.
    """
    rows = db.execute(
        ROLLING_POINTS_SQL,
        {
            "season_id": season_id,
            "building_id": building_id,
            "window_start": now - OWNERSHIP_WINDOW,
        },
    )
    return [TeamPoints(r.team_id, r.code, r.points, r.reached_at) for r in rows]


def _winner(standings: list[TeamPoints], owner_id: int | None) -> TeamPoints | None:
    """The team that should own the building; ``None`` when nobody has points."""
    if not standings:
        return None
    best = standings[0]
    for team in standings:
        if team.points == best.points and team.team_id == owner_id:
            return team  # a flip needs strictly more points than the owner
    return best


def recompute_owner(db: Session, season_id: int, building_id: int, now: datetime) -> Flip | None:
    """Apply the 7-day and tie rules to the building, inside the caller's transaction.

    Creates the claim row first, so the first two climbs in a building cannot race, then locks it
    until the caller commits. A change of owner also writes its ``game_event`` row. Without points
    in the window the owner stays: only a team with more points can take a building.
    """
    db.execute(
        pg_insert(BuildingClaim)
        .values(season_id=season_id, building_id=building_id)
        .on_conflict_do_nothing(index_elements=[BuildingClaim.season_id, BuildingClaim.building_id])
    )
    owner_id = db.execute(
        select(BuildingClaim.team_id)
        .where(BuildingClaim.season_id == season_id, BuildingClaim.building_id == building_id)
        .with_for_update()
    ).scalar_one()

    winner = _winner(rolling_points(db, season_id, building_id, now), owner_id)
    if winner is None or winner.team_id == owner_id:
        return None

    db.execute(
        update(BuildingClaim)
        .where(BuildingClaim.season_id == season_id, BuildingClaim.building_id == building_id)
        .values(team_id=winner.team_id, claimed_at=now)
    )
    event_id = db.execute(
        insert(GameEvent)
        .values(
            kind=EVENT_BUILDING_FLIPPED,
            season_id=season_id,
            building_id=building_id,
            from_team=owner_id,
            to_team=winner.team_id,
        )
        .returning(GameEvent.id)
    ).scalar_one()
    from_code = None
    if owner_id is not None:
        from_code = db.execute(select(Team.code).where(Team.id == owner_id)).scalar_one()
    return Flip(
        building_id=building_id,
        season_id=season_id,
        from_team_id=owner_id,
        to_team_id=winner.team_id,
        from_code=from_code,
        to_code=winner.code,
        at=now,
        event_id=event_id,
    )
