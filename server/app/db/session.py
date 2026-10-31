"""Engine and session factory built from settings.

Nothing connects at import time; the engine is created on first use.

Sync on purpose (decision 2026-10-31): route handlers are plain ``def`` functions, which FastAPI
runs in its thread pool, and database access lives in small repository functions (for example
``app/auth/repository.py``), so a later switch to ``create_async_engine`` touches one layer.
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def database_url() -> str:
    """Return the configured database URL or fail loudly if it is unset."""
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("FLOORWARS_DATABASE_URL is not set")
    return url.get_secret_value()


def make_engine(url: str) -> Engine:
    """Engine for the API.

    ``pool_pre_ping`` replaces connections dropped by a database restart. ``hide_parameters``
    keeps bound values (e-mails, code hashes, salts, token hashes) out of exception messages and
    therefore out of logs. The pool is sized for the thread pool that runs the handlers.
    """
    return create_engine(
        url, pool_pre_ping=True, hide_parameters=True, pool_size=10, max_overflow=10
    )


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    """Session factory. Sessions do not autocommit: services call ``session.commit()``."""
    return sessionmaker(engine, expire_on_commit=False)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine(database_url())


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return make_sessionmaker(get_engine())
