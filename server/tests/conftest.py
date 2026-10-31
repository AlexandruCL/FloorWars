"""Shared fixtures for database tests (PostGIS, optional Valkey). Helpers: ``tests/helpers.py``.

- ``migrated`` (session): migrates ``FLOORWARS_TEST_DATABASE_URL`` to head; skips the test when
  the variable is unset.
- ``clean``: empties every application table (``TRUNCATE ... RESTART IDENTITY CASCADE``, so new
  tables of later migrations are included) and flushes ``FLOORWARS_TEST_VALKEY_URL`` if set.
- ``make_app``: factory ``make_app(**settings_overrides)`` returning a started ``TestClient`` on a
  clean database, with ``settings_for_tests`` (dev, fake mail, fixed signing key). The app has
  one extra protected route, ``GET /test/whoami``, for auth tests.
- ``client``: ``make_app()`` with the defaults.

Both URLs must point at throwaway services. Test order does not matter: ``test_migrations.py``
leaves the database at head.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.deps import CurrentUser
from app.main import create_app
from app.valkey import ValkeyClient
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL, settings_for_tests

SERVER_DIR = Path(__file__).resolve().parents[1]
# Not ours (PostGIS) or migration bookkeeping: never truncated.
KEEP_TABLES = ("alembic_version", "spatial_ref_sys")


def alembic_config() -> Config:
    """Alembic config pointing at the test database, without touching logging."""
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DB_URL
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated() -> None:
    if not TEST_DB_URL:
        pytest.skip("FLOORWARS_TEST_DATABASE_URL not set")
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def clean(migrated: None) -> None:
    assert TEST_DB_URL
    # A test module may have migrated the database in between (test_migrations.py).
    command.upgrade(alembic_config(), "head")
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            tables = conn.execute(
                text(
                    "SELECT quote_ident(tablename) FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> ALL(:keep)"
                ),
                {"keep": list(KEEP_TABLES)},
            ).scalars()
            names = ", ".join(tables)
            if names:
                # Names come from pg_tables through quote_ident.
                conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()
    if TEST_VALKEY_URL:
        valkey = ValkeyClient(TEST_VALKEY_URL)
        try:
            valkey.execute("FLUSHDB")
        finally:
            valkey.close()


def _add_protected_route(app: FastAPI) -> None:
    def whoami(user: CurrentUser) -> dict[str, str]:
        return {"id": str(user.id), "email": user.email}

    app.add_api_route("/test/whoami", whoami, methods=["GET"])


@pytest.fixture
def make_app(clean: None) -> Iterator[Callable[..., TestClient]]:
    """Factory: ``make_app(**settings_overrides)`` returns a started ``TestClient``."""
    clients: list[TestClient] = []

    def factory(**overrides: Any) -> TestClient:
        app = create_app(settings_for_tests(**overrides))
        _add_protected_route(app)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_app: Callable[..., TestClient]) -> TestClient:
    return make_app()
