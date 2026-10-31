"""Fixtures for the auth integration tests (real PostGIS and Valkey).

Tests that use ``make_app`` / ``client`` skip (in the ``migrated`` fixture) unless both
``FLOORWARS_TEST_DATABASE_URL`` and ``FLOORWARS_TEST_VALKEY_URL`` are set. Both must point at
throwaway services: the database is migrated to head and its auth tables are truncated, and the
Valkey database is flushed.
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
from tests.auth.helpers import TEST_DB_URL, TEST_VALKEY_URL, settings_for_tests

SERVER_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def migrated() -> None:
    if not (TEST_DB_URL and TEST_VALKEY_URL):
        pytest.skip("FLOORWARS_TEST_DATABASE_URL and FLOORWARS_TEST_VALKEY_URL not set")
    cfg = Config(str(SERVER_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DB_URL
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def clean(migrated: None) -> None:
    assert TEST_DB_URL and TEST_VALKEY_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            # Cascades to device, refresh_token and team_membership.
            conn.execute(text('TRUNCATE "user", otp_challenge CASCADE'))
    finally:
        engine.dispose()
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
