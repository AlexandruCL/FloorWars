"""Buildings routes: ``GET /v1/buildings`` and ``GET /v1/buildings/{id}/standings``."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.problems import ProblemError, problem_doc
from app.api.v1.teams import MAX_ID, TeamOut
from app.db.models import Building, BuildingClaim, Team
from app.segments import claim
from app.teams import service as teams_service

router = APIRouter(tags=["buildings"])

WINDOW = timedelta(days=7)


class BuildingOut(BaseModel):
    id: int
    name: str


class TeamStandingOut(BaseModel):
    team_id: int
    code: str
    color_hex: str
    points: int


class BuildingStandingsOut(BaseModel):
    building_id: int
    season_id: int
    owner: TeamOut | None
    claimed_at: datetime | None
    window_start: datetime
    teams: list[TeamStandingOut]


@router.get(
    "/buildings",
    response_model=list[BuildingOut],
    responses={401: problem_doc("Missing or invalid access token.")},
    operation_id="listBuildings",
)
def list_buildings(_user: CurrentUser, db: DbSession) -> list[BuildingOut]:
    """All claimable buildings, ordered by name."""
    rows = db.execute(select(Building.id, Building.name).order_by(Building.name, Building.id))
    return [BuildingOut(id=r.id, name=r.name) for r in rows]


@router.get(
    "/buildings/{id}/standings",
    response_model=BuildingStandingsOut,
    responses={
        401: problem_doc("Missing or invalid access token."),
        404: problem_doc("Unknown building (``building-not-found``) or no active season."),
    },
    operation_id="getBuildingStandings",
)
def get_building_standings(
    id: Annotated[int, Path(ge=1, le=MAX_ID)], _user: CurrentUser, db: DbSession
) -> BuildingStandingsOut:
    """Owner of a building and every team's points in it over the rolling 7 days."""
    if db.get(Building, id) is None:
        raise ProblemError(
            404,
            detail="No such building.",
            type_=teams_service.TYPE_PREFIX + "building-not-found",
        )
    season = teams_service.active_season(db)
    now = datetime.now(UTC)
    points = {p.team_id: p.points for p in claim.rolling_points(db, season.id, id, now)}
    standings = sorted(
        (
            TeamStandingOut(
                team_id=t.id, code=t.code, color_hex=t.color_hex, points=points.get(t.id, 0)
            )
            for t in db.scalars(select(Team))
        ),
        key=lambda s: (-s.points, s.code),
    )
    row = db.execute(
        select(Team, BuildingClaim.claimed_at)
        .join(BuildingClaim, BuildingClaim.team_id == Team.id)
        .where(BuildingClaim.season_id == season.id, BuildingClaim.building_id == id)
    ).first()
    owner = TeamOut(id=row[0].id, code=row[0].code, color_hex=row[0].color_hex) if row else None
    return BuildingStandingsOut(
        building_id=id,
        season_id=season.id,
        owner=owner,
        claimed_at=row[1] if row else None,
        window_start=now - WINDOW,
        teams=standings,
    )
