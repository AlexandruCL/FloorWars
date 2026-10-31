"""Teams routes: ``GET /v1/teams``, ``GET /v1/seasons/active``, ``POST /v1/seasons/{id}/join``.

Thin handlers: the rules are in ``app.teams.service``.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbSession
from app.api.problems import problem_doc
from app.teams import service

router = APIRouter(tags=["teams"])


class TeamOut(BaseModel):
    id: int
    code: str
    color_hex: str


class SeasonOut(BaseModel):
    id: int
    starts_at: datetime
    ends_at: datetime


class JoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: Annotated[int, Field(ge=1, strict=True)]


class TeamMembershipOut(BaseModel):
    season_id: int
    team_id: int


@router.get("/teams", response_model=list[TeamOut], operation_id="listTeams")
def list_teams(db: DbSession) -> list[TeamOut]:
    """All teams (faculties), ordered by code."""
    return [TeamOut(id=t.id, code=t.code, color_hex=t.color_hex) for t in service.list_teams(db)]


@router.get(
    "/seasons/active",
    response_model=SeasonOut,
    responses={404: problem_doc("No season is active right now (``no-active-season``).")},
    operation_id="getActiveSeason",
)
def get_active_season(db: DbSession) -> SeasonOut:
    """The season that is running now."""
    season = service.active_season(db)
    rng = season.active_during
    if rng.lower is None or rng.upper is None:
        raise RuntimeError("season range must be bounded")
    return SeasonOut(id=season.id, starts_at=rng.lower, ends_at=rng.upper)


@router.post(
    "/seasons/{id}/join",
    status_code=201,
    response_model=TeamMembershipOut,
    responses={
        401: problem_doc("Missing or invalid access token."),
        404: problem_doc("Unknown season (``season-not-found``)."),
        409: problem_doc("``already-joined`` or ``season-not-active``."),
        422: problem_doc("Body does not match the schema, or unknown team (``team-not-found``)."),
    },
    operation_id="joinSeason",
)
def join_season(
    id: Annotated[int, Path(ge=1)], body: JoinRequest, user: CurrentUser, db: DbSession
) -> TeamMembershipOut:
    """Pick a team for the season; one team per user per season."""
    service.join_season(db, user.id, id, body.team_id)
    return TeamMembershipOut(season_id=id, team_id=body.team_id)
