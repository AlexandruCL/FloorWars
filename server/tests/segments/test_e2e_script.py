"""The ``--upload`` flow of ``tools/e2e/e2e_check.py`` against the real app, in process.

The script's HTTP helper is swapped for the FastAPI ``TestClient``, so the requests the script
builds run through the real routes, rules and database.
"""

import sys
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import World, make_world, utcnow

E2E_DIR = Path(__file__).resolve().parents[3] / "tools" / "e2e"
sys.path.insert(0, str(E2E_DIR))
import e2e_check  # noqa: E402  (tools/e2e is not a package)

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")


@pytest.fixture(autouse=True)
def _leave_database_empty(clean: None) -> Iterator[None]:
    """``tests/test_migrations.py`` assumes an empty database."""
    yield
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text('TRUNCATE team, season, building, "user" RESTART IDENTITY CASCADE'))
    finally:
        engine.dispose()


@pytest.fixture
def world(make_app: Callable[..., TestClient]) -> World:
    return make_world(make_app())


def _route_through(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def call(
        method: str,
        base: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        sent = dict(headers or {})
        if token:
            sent["Authorization"] = f"Bearer {token}"
        response = client.request(method, f"/v1{path}", json=body, headers=sent)
        return response.status_code, response.json() if response.content else None

    monkeypatch.setattr(e2e_check, "call", call)


def test_upload_flow_passes_against_the_real_app(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    climber = world.climber()
    _route_through(world.client, monkeypatch)
    # The world's check-in opened two hours ago; the script starts the climb just before now.
    checkin = {
        "id": str(climber.checkin_id),
        "building_id": climber.building_id,
        "valid_from": (utcnow() - timedelta(minutes=1)).isoformat(),
    }
    token = climber.headers["Authorization"].removeprefix("Bearer ")

    assert e2e_check.upload_checks("http://test/v1", token, str(climber.device_id), checkin)

    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert token not in out
