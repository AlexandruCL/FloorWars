"""A repeat is answered from ``segment_receipt`` and changes nothing else."""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import World, climb, make_world, scalar

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")


@pytest.fixture(autouse=True)
def _leave_database_empty(clean: None) -> Iterator[None]:
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


def _counts(world: World) -> tuple[int, ...]:
    return tuple(
        scalar(world.client, f"SELECT count(*) FROM {table}")  # noqa: S608
        for table in ("climb_segment", "segment_receipt", "fraud_flag", "game_event")
    )


def test_a_resend_is_accepted_without_points_or_effects(world: World) -> None:
    user = world.climber()
    item = climb()
    first = user.ok(item, key="k1")
    assert first["accepted"] == [{"id": item["id"], "steps_scored": 60, "points": 60}]
    before = _counts(world)
    again = user.ok(item, key="k1")
    assert again == {
        "accepted": [{"id": item["id"], "steps_scored": 60}],
        "rejected": [],
        "flips": [],
    }
    assert _counts(world) == before
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


def test_duplicates_are_decided_by_segment_not_by_key(world: World) -> None:
    user = world.climber()
    item = climb()
    user.ok(item, key="k1")
    assert "points" not in user.ok(item, key="k2")["accepted"][0]
    # The same key with a new segment is not a repeat.
    assert user.ok(climb(minutes_ago=2), key="k1")["accepted"][0]["points"] == 60


def test_a_rejected_duplicate_keeps_its_reason(world: World) -> None:
    user = world.climber()
    item = climb(vert_speed_mps=5.0)
    assert user.ok(item)["rejected"] == [{"id": item["id"], "reason": "speed"}]
    before = _counts(world)
    assert user.ok(item)["rejected"] == [{"id": item["id"], "reason": "speed"}]
    assert _counts(world) == before


def test_a_rejected_duplicate_stays_rejected_after_the_values_change(world: World) -> None:
    """The answer comes from the receipt, so a resend cannot turn a rejection into points."""
    user = world.climber()
    item = climb(checkin_id=str(uuid.uuid4()))
    assert user.ok(item)["rejected"][0]["reason"] == "no_checkin"
    fixed = {k: v for k, v in item.items() if k != "checkin_id"}
    assert user.ok(fixed)["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM team_building_score") == 0


def test_the_same_id_twice_in_one_batch_scores_once(world: World) -> None:
    user = world.climber()
    item = climb()
    result = user.ok(item, item)
    assert result["accepted"] == [
        {"id": item["id"], "steps_scored": 60, "points": 60},
        {"id": item["id"], "steps_scored": 60},
    ]
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


def test_a_mixed_resend_only_adds_the_new_item(world: World) -> None:
    user = world.climber()
    old, new = climb(minutes_ago=5), climb(minutes_ago=1)
    user.ok(old)
    result = user.ok(old, new)
    assert result["accepted"] == [
        {"id": old["id"], "steps_scored": 60},
        {"id": new["id"], "steps_scored": 60, "points": 60},
    ]
    assert scalar(world.client, "SELECT points FROM team_building_score") == 120
