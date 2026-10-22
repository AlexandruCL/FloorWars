"""Async engine and session factory built from settings.

Nothing connects at import time; the engine is created on first use.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def database_url() -> str:
    """Return the configured database URL or fail loudly if it is unset."""
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("FLOORWARS_DATABASE_URL is not set")
    return url.get_secret_value()


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
