"""Upload order earns nothing, one person climbs once at a time, a resend never counts as a climb.

Timestamps are fixed once per test: ``api_world.climb(minutes_ago=...)`` reads the clock per call,
and that drift would shrink the gaps the replays depend on.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range

from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import Climber, World, climb, make_world, scalar, utcnow

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")

# A real check-in lasts 90 minutes; both replays fit inside one.
CHECKIN = timedelta(minutes=90)
# 3 steps/s is the cadence limit: the most steps a climb of the longest duration can hold.
LONG_CLIMB: dict[str, Any] = {
    "steps": 540,
    "ascent_m": 90.0,
    "duration_s": 180.0,
    "vert_speed_mps": 0.5,
}
# More than half of the 600 per 10 minutes: counting this climb twice would exceed the rate limit.
BIG_CLIMB: dict[str, Any] = {
    "steps": 360,
    "ascent_m": 60.0,
    "duration_s": 150.0,
    "vert_speed_mps": 0.4,
}


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


def _at(when: datetime, **overrides: Any) -> dict[str, Any]:
    return climb(started_at=when.isoformat(), **overrides)


def _checked_in(world: World, now: datetime) -> Climber:
    return world.climber(valid_during=Range(now - CHECKIN, now))


def _replay(user: Climber, items: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, str]]:
    """Upload each item on its own: points per accepted id, reason per rejected id."""
    accepted: dict[str, int] = {}
    rejected: dict[str, str] = {}
    for item in items:
        result = user.ok(item, key=item["id"])
        accepted.update({a["id"]: a["points"] for a in result["accepted"]})
        rejected.update({r["id"]: r["reason"] for r in result["rejected"]})
    return accepted, rejected


def _second_device(world: World, user: Climber) -> uuid.UUID:
    device = uuid.uuid4()
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text(
                "INSERT INTO device (user_id, id, model, has_barometer) "
                "VALUES (:u, :d, 'test', true)"
            ),
            {"u": user.user_id, "d": device},
        )
        db.commit()
    return device


def _reject_reason(world: World, item: dict[str, Any]) -> Any:
    return scalar(
        world.client,
        "SELECT reject_reason FROM climb_segment WHERE id = CAST(:id AS uuid)",
        id=item["id"],
    )


# Replays: newest first, one upload per climb.


def test_replaying_short_climbs_newest_first_gets_the_hourly_halving(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    # Exactly the upload bucket (60 per hour). No climb sees 10 others closer than 10 minutes, so
    # none hits the rate limit: the first 5 reach 300 steps at full points, the other 55 are halved.
    items = [_at(now - timedelta(minutes=1 + i)) for i in range(60)]
    accepted, rejected = _replay(user, items)
    assert rejected == {}
    assert [accepted[item["id"]] for item in items] == [60] * 5 + [30] * 55
    assert sum(accepted.values()) == 1950
    assert scalar(world.client, "SELECT points FROM team_building_score") == 1950
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 3600


def test_replaying_long_climbs_newest_first_hits_the_rate_limit(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    # Each climb ends where the next newer one starts, so they touch and do not overlap. One climb
    # fits per 10 minute window: every 4th passes (12 minutes apart), the first with 300 full
    # points and 240 halved (420), the others all halved (270).
    items = [_at(now - timedelta(minutes=4 + 3 * i), **LONG_CLIMB) for i in range(20)]
    accepted, rejected = _replay(user, items)
    passed = items[::4]
    assert [accepted[item["id"]] for item in passed] == [420, 270, 270, 270, 270]
    assert sum(accepted.values()) == 1500
    assert len(accepted) == 5
    assert len(rejected) == 15
    assert set(rejected.values()) == {"rate_limit"}
    assert scalar(world.client, "SELECT points FROM team_building_score") == 1500
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 2700
    flags = "SELECT count(*) FROM fraud_flag WHERE rule = 'rate_limit'"
    assert scalar(world.client, flags) == 15


# Overlap.


def test_the_same_climb_under_a_new_id_is_an_overlap(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    first = _at(now - timedelta(minutes=10))
    copy = {**first, "id": str(uuid.uuid4())}
    user.ok(first)
    result = user.ok(copy)
    assert result == {
        "accepted": [],
        "rejected": [{"id": copy["id"], "reason": "overlap"}],
        "flips": [],
    }
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 1
    assert scalar(world.client, "SELECT rule FROM fraud_flag") == "overlap"
    assert _reject_reason(world, copy) == "overlap"
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 2
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


@pytest.mark.parametrize(
    ("offset_s", "overrides"),
    [
        pytest.param(29.0, {}, id="starts 1 s before the end"),
        pytest.param(-29.0, {}, id="ends 1 s after the start"),
        pytest.param(5.0, {"duration_s": 20.0, "vert_speed_mps": 0.6}, id="inside"),
        pytest.param(-10.0, {"duration_s": 100.0, "vert_speed_mps": 0.12}, id="around"),
    ],
)
def test_any_shared_time_is_an_overlap(
    world: World, offset_s: float, overrides: dict[str, Any]
) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    start = now - timedelta(minutes=10)
    user.ok(_at(start))  # 30 s
    result = user.ok(_at(start + timedelta(seconds=offset_s), **overrides))
    assert [r["reason"] for r in result["rejected"]] == ["overlap"]


@pytest.mark.parametrize("offset_s", [30.0, -30.0], ids=["starts at its end", "ends at its start"])
def test_climbs_that_only_touch_do_not_overlap(world: World, offset_s: float) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    start = now - timedelta(minutes=10)
    user.ok(_at(start))  # 30 s
    touching = _at(start + timedelta(seconds=offset_s))
    assert [a["id"] for a in user.ok(touching)["accepted"]] == [touching["id"]]


def test_an_overlap_inside_one_batch_rejects_the_later_climb(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    start = now - timedelta(minutes=10)
    earlier, later = _at(start), _at(start + timedelta(seconds=10))
    result = user.ok(later, earlier)  # handled by started_at, whatever the request order
    assert [a["id"] for a in result["accepted"]] == [earlier["id"]]
    assert result["rejected"] == [{"id": later["id"], "reason": "overlap"}]
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


def test_a_rejected_row_does_not_block_a_later_climb(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    start = now - timedelta(minutes=10)
    flat = _at(start, steps=500)
    assert [r["reason"] for r in user.ok(flat)["rejected"]] == ["pressure_steps_mismatch"]
    assert _reject_reason(world, flat) == "pressure_steps_mismatch"
    retry = _at(start)
    assert [a["id"] for a in user.ok(retry)["accepted"]] == [retry["id"]]


def test_a_row_rejected_for_overlap_does_not_block_a_later_climb(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    start = now - timedelta(minutes=10)
    user.ok(_at(start))  # 30 s
    # Rejected, and covers the 10 s after the end of the first climb.
    assert [r["reason"] for r in user.ok(_at(start + timedelta(seconds=10)))["rejected"]] == [
        "overlap"
    ]
    after = _at(start + timedelta(seconds=30))
    assert [a["id"] for a in user.ok(after)["accepted"]] == [after["id"]]


def test_the_same_time_for_another_user_is_no_overlap(world: World) -> None:
    now = utcnow()
    start = now - timedelta(minutes=10)
    _checked_in(world, now).ok(_at(start))
    item = _at(start)
    assert [a["id"] for a in _checked_in(world, now).ok(item)["accepted"]] == [item["id"]]


# A resend from a second device (no receipt there yet) is not a new climb.


def test_a_big_climb_resent_from_a_second_device_changes_nothing(world: World) -> None:
    now = utcnow()
    user = _checked_in(world, now)
    item = _at(now - timedelta(minutes=10), **BIG_CLIMB)
    assert user.ok(item)["accepted"][0]["points"] == 330  # 300 full, 60 halved
    second = _second_device(world, user)
    result = user.ok(item, device_id=str(second))
    assert result == {
        "accepted": [],
        "rejected": [{"id": item["id"], "reason": "no_checkin"}],
        "flips": [],
    }
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 330
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 360
    receipt = "SELECT reject_reason FROM segment_receipt WHERE device_id = CAST(:d AS uuid)"
    assert scalar(world.client, receipt, d=str(second)) == "no_checkin"


def test_a_big_climb_sent_by_another_user_changes_nothing(world: World) -> None:
    now = utcnow()
    item = _at(now - timedelta(minutes=10), **BIG_CLIMB)
    assert _checked_in(world, now).ok(item)["accepted"][0]["points"] == 330
    result = _checked_in(world, now).ok(item)
    assert result == {
        "accepted": [],
        "rejected": [{"id": item["id"], "reason": "no_checkin"}],
        "flips": [],
    }
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 330
