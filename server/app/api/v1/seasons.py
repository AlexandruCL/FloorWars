"""``GET /v1/seasons``: every season, newest ``starts_at`` first ."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.api.problems import problem_doc
from app.api.v1.teams import SeasonOut
from app.db.models import Season

router = APIRouter(tags=["teams"])


@router.get(
    "/seasons",
    response_model=list[SeasonOut],
    responses={401: problem_doc("Missing or invalid access token.")},
    operation_id="listSeasons",
)
def list_seasons(_user: CurrentUser, db: DbSession) -> list[SeasonOut]:
    """Every season, newest ``starts_at`` first."""
    seasons = db.scalars(
        select(Season).order_by(func.lower(Season.active_during).desc(), Season.id.desc())
    )
    out = []
    for season in seasons:
        rng = season.active_during
        if rng.lower is None or rng.upper is None:
            raise RuntimeError("season range must be bounded")
        out.append(SeasonOut(id=season.id, starts_at=rng.lower, ends_at=rng.upper))
    return out
