"""Engine and session factory built from settings.

Nothing connects at import time; the engine is created on first use.

Sync for now: SQLAlchemy's asyncio extension needs ``greenlet`` (``sqlalchemy[asyncio]``),
which is not a declared dependency yet. Switch to ``create_async_engine`` once it is.
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


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)
