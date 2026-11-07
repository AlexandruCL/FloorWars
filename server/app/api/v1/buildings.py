"""Buildings routes: ``GET /v1/buildings`` (standings are added in a later commit)."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.problems import problem_doc
from app.db.models import Building

router = APIRouter(tags=["buildings"])


class BuildingOut(BaseModel):
    id: int
    name: str


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
