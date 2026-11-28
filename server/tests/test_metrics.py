"""``/metrics``: format, counters that move, and no user data in any name or label."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import create_engine, text

from app.metrics import REGISTRY
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import World, climb, make_world

ALLOWED_LABELS = {"route", "method", "status", "reason", "rule", "le"}


def value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


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


def test_metrics_text_parses_and_is_not_public_json(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    families = {f.name: f for f in text_string_to_metric_families(response.text)}
    assert "floorwars_http_requests" in families
    assert "floorwars_websocket_connections" in families


def test_every_name_has_the_prefix_and_no_label_can_hold_user_data(client: TestClient) -> None:
    client.get("/healthz")
    families = list(text_string_to_metric_families(client.get("/metrics").text))

    for family in families:
        if family.name.startswith(("python_", "process_")):
            continue
        assert family.name.startswith("floorwars_")
        for sample in family.samples:
            assert set(sample.labels) <= ALLOWED_LABELS


def test_requests_are_counted_per_route_template_not_raw_path(client: TestClient) -> None:
    before = value("floorwars_http_requests_total", route="/healthz", method="GET", status="200")

    client.get("/healthz")
    client.get("/v1/no-such-path-9f3a")

    after = value("floorwars_http_requests_total", route="/healthz", method="GET", status="200")
    assert after == before + 1
    assert value("floorwars_http_requests_total", route="unmatched", method="GET", status="404")
    assert "no-such-path-9f3a" not in client.get("/metrics").text


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_counters_move_on_an_accepted_and_a_rejected_upload(world: World) -> None:
    user = world.climber("AC")
    acc = value("floorwars_segments_accepted_total")
    rej = value("floorwars_segments_rejected_total", reason="steps_range")
    lat = value("floorwars_detection_latency_seconds_count")

    body: dict[str, Any] = user.ok(climb(), climb(steps=5000))

    assert len(body["accepted"]) == 1 and len(body["rejected"]) == 1
    assert value("floorwars_segments_accepted_total") == acc + 1
    assert value("floorwars_segments_rejected_total", reason="steps_range") == rej + 1
    assert value("floorwars_detection_latency_seconds_count") == lat + 1
    text = world.client.get("/metrics").text
    assert str(user.user_id) not in text and str(user.device_id) not in text


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_active_users_counts_distinct_users_not_labels(world: World) -> None:
    for _ in range(2):
        world.climber("AC").ok(climb())

    world.client.get("/metrics")

    assert value("floorwars_active_users") == 2


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_websocket_gauge_follows_open_sockets(world: World) -> None:
    user = world.climber("AC")
    base = value("floorwars_websocket_connections")

    with world.client.websocket_connect("/v1/ws", headers=user.headers):
        assert value("floorwars_websocket_connections") == base + 1

    assert value("floorwars_websocket_connections") == base
