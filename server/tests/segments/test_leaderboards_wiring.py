"""An upload through the route reaches the Valkey leaderboards, and never depends on them."""

import json
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import leaderboards
from app.valkey import ValkeyError
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


def _state(world: World) -> Any:
    return cast(Any, world.client.app).state


def _score(world: World, key: str, member: object) -> float | None:
    raw = _state(world).valkey.execute("ZSCORE", key, str(member))
    return None if raw is None else float(raw)


class _Recorder:
    """Stands in for ``app.state.valkey``; the rate limiter keeps its own client."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[Any, ...]] = []

    def execute(self, *args: Any) -> None:
        if self.failure:
            raise self.failure
        self.calls.append(args)


def test_an_upload_updates_all_three_boards(world: World) -> None:
    user = world.climber("AC")
    user.ok(climb())
    season, team = world.season_id, world.team_ids["AC"]
    assert _score(world, leaderboards.users_key(season), user.user_id) == 60
    assert _score(world, leaderboards.teams_key(season), team) == 60
    assert _score(world, leaderboards.building_key(season, world.building_id), team) == 60


def test_a_resend_and_a_rejection_do_not_touch_the_boards(world: World) -> None:
    user = world.climber("AC")
    item = climb(minutes_ago=5)
    user.ok(item)
    user.ok(item)
    user.ok(climb(vert_speed_mps=5.0))
    key = leaderboards.users_key(world.season_id)
    assert _score(world, key, user.user_id) == 60


def test_incremental_boards_equal_a_rebuild(world: World) -> None:
    ac, etc = world.climber("AC"), world.climber("ETC")
    ac.ok(climb(minutes_ago=5))
    etc.ok(climb(minutes_ago=4), climb(minutes_ago=2))
    keys = [
        (leaderboards.users_key(world.season_id), ac.user_id),
        (leaderboards.users_key(world.season_id), etc.user_id),
        (leaderboards.teams_key(world.season_id), world.team_ids["ETC"]),
        (leaderboards.building_key(world.season_id, world.building_id), world.team_ids["AC"]),
    ]
    incremental = [_score(world, key, member) for key, member in keys]
    assert incremental == [60, 120, 120, 60]
    with _state(world).sessionmaker() as db:
        leaderboards.rebuild(db, _state(world).valkey, world.season_id)
    assert [_score(world, key, member) for key, member in keys] == incremental


def test_a_flip_is_published_with_team_codes(world: World) -> None:
    recorder = _Recorder()
    _state(world).valkey = recorder
    result = world.climber("AC").ok(climb())
    published = [call for call in recorder.calls if call[0] == "PUBLISH"]
    assert len(published) == 1
    assert published[0][1] == leaderboards.EVENTS_CHANNEL
    event = json.loads(published[0][2])
    assert event["type"] == "building_flipped"
    assert (event["building_id"], event["from_team"], event["to_team"]) == (
        world.building_id,
        None,
        "AC",
    )
    assert event["at"] == result["flips"][0]["at"].replace("Z", "+00:00")
    assert event["event_id"] == scalar(world.client, "SELECT id FROM game_event")


def test_valkey_down_after_the_commit_keeps_the_upload(world: World) -> None:
    _state(world).valkey = _Recorder(ValkeyError("down"))
    user = world.climber("AC")
    item = climb()
    result = user.ok(item)
    assert result["accepted"] == [{"id": item["id"], "steps_scored": 60, "points": 60}]
    assert len(result["flips"]) == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


def test_no_valkey_client_uses_the_no_op(world: World) -> None:
    _state(world).valkey = None
    assert world.climber("AC").ok(climb())["accepted"][0]["points"] == 60
