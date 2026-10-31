"""Team and season rules: list teams, find the active season, join a season."""

import uuid

from sqlalchemy.orm import Session

from app.api.problems import ProblemError, conflict
from app.db.models import Season, Team
from app.teams import repository

TYPE_PREFIX = "urn:floorwars:problem:"


def list_teams(db: Session) -> list[Team]:
    return repository.list_teams(db)


def active_season(db: Session) -> Season:
    season = repository.active_season(db)
    if season is None:
        raise ProblemError(
            404, detail="No season is active right now.", type_=TYPE_PREFIX + "no-active-season"
        )
    return season


def join_season(db: Session, user_id: uuid.UUID, season_id: int, team_id: int) -> None:
    if repository.get_season(db, season_id) is None:
        raise ProblemError(404, detail="No such season.", type_=TYPE_PREFIX + "season-not-found")
    if repository.get_team(db, team_id) is None:
        raise ProblemError(422, detail="No such team.", type_=TYPE_PREFIX + "team-not-found")
    if not repository.is_active(db, season_id):
        raise conflict("The season is not running now.", type_=TYPE_PREFIX + "season-not-active")
    if not repository.add_membership(db, user_id, season_id, team_id):
        raise conflict(
            "You already joined a team for this season.", type_=TYPE_PREFIX + "already-joined"
        )
