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
from tests.segments.api_world import Climber, World, climb, make_world, scalar

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


def _build(world: World) -> None:
    with _state(world).sessionmaker() as db:
        assert leaderboards.rebuild(db, _state(world).valkey, world.season_id)


def _team_board(world: World, user: Climber) -> list[tuple[str, int]]:
    response = world.client.get("/v1/leaderboards", params={"scope": "team"}, headers=user.headers)
    assert response.status_code == 200, response.text
    return [(e["name"], e["points"]) for e in response.json()["entries"]]


class _FailingScripts:
    """The real client, but every ``EVAL`` (the board update) fails."""

    def __init__(self, real: Any) -> None:
        self.real = real

    def execute(self, *args: Any) -> Any:
        if args[0] == "EVAL":
            raise ValkeyError("injected")
        return self.real.execute(*args)


def test_an_upload_updates_all_three_boards(world: World) -> None:
    _build(world)
    user = world.climber("AC")
    user.ok(climb())
    season, team = world.season_id, world.team_ids["AC"]
    assert _score(world, leaderboards.users_key(season), user.user_id) == 60
    assert _score(world, leaderboards.teams_key(season), team) == 60
    assert _score(world, leaderboards.building_key(season, world.building_id), team) == 60


def test_a_resend_and_a_rejection_do_not_touch_the_boards(world: World) -> None:
    _build(world)
    user = world.climber("AC")
    item = climb(minutes_ago=5)
    user.ok(item)
    user.ok(item)
    user.ok(climb(vert_speed_mps=5.0))
    key = leaderboards.users_key(world.season_id)
    assert _score(world, key, user.user_id) == 60


def test_an_upload_skips_a_season_that_is_not_built(world: World) -> None:
    world.climber("AC").ok(climb())
    assert _state(world).valkey.execute("EXISTS", leaderboards.users_key(world.season_id)) == 0


def test_wiped_valkey_then_an_upload_never_serves_a_partial_board(world: World) -> None:
    _build(world)
    ac, etc = world.climber("AC"), world.climber("ETC")
    ac.ok(climb(minutes_ago=5))
    _state(world).valkey.execute("FLUSHDB")  # Valkey lost its data
    etc.ok(climb(minutes_ago=2))
    assert _team_board(world, ac) == [("AC", 60), ("ETC", 60)]


def test_a_failed_update_is_repaired_by_the_next_read(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    _build(world)
    ac, etc = world.climber("AC"), world.climber("ETC")
    ac.ok(climb(minutes_ago=5))
    real = _state(world).valkey
    _state(world).valkey = _FailingScripts(real)
    assert etc.ok(climb(minutes_ago=2))["accepted"][0]["points"] == 60
    assert any(r.message == "leaderboard update failed" for r in caplog.records)
    assert real.execute("EXISTS", leaderboards.built_key(world.season_id)) == 0
    _state(world).valkey = real
    assert _team_board(world, ac) == [("AC", 60), ("ETC", 60)]
    assert real.execute("EXISTS", leaderboards.built_key(world.season_id)) == 1


@pytest.mark.parametrize("upload_at", ["before_snapshot", "after_snapshot"])
def test_a_rebuild_racing_an_upload_keeps_correct_totals(
    world: World, monkeypatch: pytest.MonkeyPatch, upload_at: str
) -> None:
    ac, etc = world.climber("AC"), world.climber("ETC")
    ac.ok(climb(minutes_ago=5))
    hook = "_rebuild_keys" if upload_at == "before_snapshot" else "_replace"
    real = getattr(leaderboards, hook)
    raced: list[bool] = []

    def racing(*args: Any) -> None:
        if not raced:  # one upload, committed and notified while the rebuild holds the lock
            raced.append(True)
            etc.ok(climb(minutes_ago=2))
        real(*args)

    monkeypatch.setattr(leaderboards, hook, racing)
    with _state(world).sessionmaker() as db:
        assert not leaderboards.rebuild(db, _state(world).valkey, world.season_id)
    monkeypatch.setattr(leaderboards, hook, real)
    vk = _state(world).valkey
    assert vk.execute("EXISTS", leaderboards.lock_key(world.season_id)) == 0
    assert vk.execute("EXISTS", leaderboards.built_key(world.season_id)) == 0
    assert _team_board(world, ac) == [("AC", 60), ("ETC", 60)]  # rebuilt by the read
    assert vk.execute("EXISTS", leaderboards.built_key(world.season_id)) == 1


def test_incremental_boards_equal_a_rebuild(world: World) -> None:
    _build(world)
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
