"""Dependencies shared by the ``/v1`` routes.

Use the ``Annotated`` aliases in route signatures::

    from app.api.deps import AppSettings, DbSession

    @router.get("/teams")
    def list_teams(db: DbSession) -> list[TeamOut]: ...

Route handlers are plain ``def`` (FastAPI runs them in its thread pool) and the session is the
sync SQLAlchemy ``Session``. The session does not commit by itself: the service that changes
data calls ``db.commit()``; anything left uncommitted is rolled back when the request ends.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    """The settings the app was created with (``create_app(settings)``)."""
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    """One database session per request, closed (and rolled back if uncommitted) at the end."""
    factory: sessionmaker[Session] | None = request.app.state.sessionmaker
    if factory is None:
        raise RuntimeError("FLOORWARS_DATABASE_URL is not set")
    with factory() as session:
        yield session


AppSettings = Annotated[Settings, Depends(get_app_settings)]
DbSession = Annotated[Session, Depends(get_db)]
