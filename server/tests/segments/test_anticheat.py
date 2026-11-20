"""Anti-cheat v2 (W4-5): flag-only rules on newly verified segments. A flagged segment keeps
``verified`` and its points, and the answer carries no new reason."""

from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range

from app.auth.ratelimit import Decision
from app.segments import rules, service
from app.segments.schemas import SegmentBatch, SegmentBatchResult
from app.valkey import ValkeyError
from tests.checkins.conftest import CENTRE_LAT, CENTRE_LON, insert_building
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import TSTZRANGE_SQL, Climber, World, climb_at, make_world, utcnow

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


def _upload(
    world: World,
    user: Climber,
    *items: dict[str, Any],
    now: datetime | None = None,
    limiter: Any = None,
) -> SegmentBatchResult:
    """``service.upload_batch`` directly, for a ``now`` in the past or a fake limiter."""
    segs = [
        {"checkin_id": str(user.checkin_id), "building_id": user.building_id, **i} for i in items
    ]
    batch = SegmentBatch.model_validate({"device_id": str(user.device_id), "segments": segs})
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return service.upload_batch(db, user.user_id, batch, now=now, limiter=limiter)


def _flags(world: World) -> dict[str, set[str]]:
    """Rules per segment id. Asserts at most one flag per segment and rule."""
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        rows = db.execute(text("SELECT segment_id::text, rule FROM fraud_flag")).all()
    counts = Counter((row[0], row[1]) for row in rows)
    assert all(n == 1 for n in counts.values()), counts
    out: dict[str, set[str]] = {}
    for segment_id, rule in counts:
        out.setdefault(segment_id, set()).add(rule)
    return out


def _verified(world: World, item: dict[str, Any]) -> tuple[str, int]:
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.execute(
            text("SELECT status, points FROM climb_segment WHERE id = :i"), {"i": item["id"]}
        ).one()
    return row[0], row[1]


# identical_segment


@pytest.mark.parametrize(
    ("change", "flagged"),
    [
        ({}, True),
        ({"ascent_m": 12.009}, True),
        ({"ascent_m": 11.991}, True),
        ({"ascent_m": 12.011}, False),
        ({"ascent_m": 11.989}, False),
        ({"duration_s": 30.09}, True),
        ({"duration_s": 29.91}, True),
        ({"duration_s": 30.11}, False),
        ({"duration_s": 29.89}, False),
        ({"steps": 61}, False),
    ],
)
def test_identical_segment_tolerances(world: World, change: dict[str, Any], flagged: bool) -> None:
    user = world.climber()
    start = utcnow() - timedelta(minutes=60)
    first, second = climb_at(start), climb_at(start + timedelta(minutes=5), **change)
    user.ok(first)
    result = user.ok(second)
    assert result["rejected"] == []  # no new reason: flag only
    assert [a["id"] for a in result["accepted"]] == [second["id"]]
    assert _flags(world) == ({second["id"]: {"identical_segment"}} if flagged else {})
    assert _verified(world, second) == ("verified", second["steps"])


@pytest.mark.parametrize("older_first", [True, False], ids=["older first", "newer first"])
@pytest.mark.parametrize(("minutes", "flagged"), [(-1, True), (1, False)])
def test_identical_segment_window_on_both_sides(
    world: World, older_first: bool, minutes: int, flagged: bool
) -> None:
    now = utcnow()
    user = world.climber(valid_during=Range(now - timedelta(days=8), now + timedelta(hours=1)))
    newer_at = now - timedelta(hours=1)
    older_at = newer_at - rules.IDENTICAL_WINDOW + timedelta(minutes=-minutes)
    older, newer = climb_at(older_at), climb_at(newer_at)
    # The older climb is uploaded with a clock just after it, so it is inside the 7-day range.
    uploads = [(older, older_at + timedelta(minutes=5)), (newer, now)]
    for item, clock in uploads if older_first else uploads[::-1]:
        assert len(_upload(world, user, item, now=clock).accepted) == 1
    second = newer if older_first else older
    assert _flags(world) == ({second["id"]: {"identical_segment"}} if flagged else {})


def test_identical_segments_in_one_batch_flag_all_but_the_first(world: World) -> None:
    user = world.climber()
    start = utcnow() - timedelta(minutes=60)
    items = [climb_at(start + timedelta(minutes=5 * i)) for i in range(3)]
    result = user.ok(*items[::-1])
    assert len(result["accepted"]) == 3
    assert _flags(world) == {i["id"]: {"identical_segment"} for i in items[1:]}


def test_identical_segment_of_another_user_is_not_flagged(world: World) -> None:
    one, two = world.climber(), world.climber()
    start = utcnow() - timedelta(minutes=60)
    one.ok(climb_at(start))
    two.ok(climb_at(start + timedelta(minutes=5)))
    assert _flags(world) == {}


# impossible_sequence


def _two_checkins(
    world: World, now: datetime, split: datetime, until: datetime | None = None
) -> tuple[Climber, int, str, float]:
    """A user checked in at the world's building until ``split``, then at a building about
    1.1 km north until ``until`` (check-ins of one user cannot overlap): the user, that building,
    its check-in and the walk between the two in seconds."""
    user = world.climber(valid_during=Range(now - timedelta(hours=3), split))
    building = insert_building(world.client, CENTRE_LAT + 0.01, CENTRE_LON)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        checkin = db.execute(
            text(
                "INSERT INTO checkin (user_id, building_id, method, valid_during) "  # noqa: S608
                f"VALUES (:u, :b, 'qr', {TSTZRANGE_SQL}) RETURNING id::text"
            ),
            {
                "u": user.user_id,
                "b": building,
                "lo": split,
                "hi": until or now + timedelta(hours=1),
            },
        ).scalar_one()
        metres = db.execute(
            text(
                "SELECT ST_Distance(a.footprint::geography, b.footprint::geography) "
                "FROM building a, building b WHERE a.id = :a AND b.id = :b"
            ),
            {"a": world.building_id, "b": building},
        ).scalar_one()
        db.commit()
    assert 1000 < metres < 1200
    return user, building, checkin, metres / rules.MAX_WALK_SPEED_MPS


@pytest.mark.parametrize(
    "later_first", [False, True], ids=["earlier uploaded first", "later uploaded first"]
)
@pytest.mark.parametrize(("slack_s", "flagged"), [(-1.0, True), (1.0, False)])
def test_impossible_sequence_on_both_sides(
    world: World, later_first: bool, slack_s: float, flagged: bool
) -> None:
    now = utcnow()
    here_at = now - timedelta(hours=2)
    user, building, checkin, walk_s = _two_checkins(world, now, here_at + timedelta(seconds=45))
    # The stored end of ``here`` (30 s), then the walk, plus or minus the slack.
    there_at = here_at + timedelta(seconds=30 + walk_s + slack_s)
    here = climb_at(here_at)
    there = climb_at(there_at, ascent_m=13.0, building_id=building, checkin_id=checkin)
    order = [there, here] if later_first else [here, there]
    for item in order:
        result = user.ok(item)
        assert [a["id"] for a in result["accepted"]] == [item["id"]]
    assert _flags(world) == ({order[1]["id"]: {"impossible_sequence"}} if flagged else {})
    assert _verified(world, order[1]) == ("verified", 60)


def test_impossible_sequence_in_one_batch_flags_the_later_climb(world: World) -> None:
    now = utcnow()
    user, building, checkin, _ = _two_checkins(
        world, now, now - timedelta(hours=2) + timedelta(seconds=45)
    )
    here = climb_at(now - timedelta(hours=2))
    there = climb_at(
        now - timedelta(hours=2) + timedelta(seconds=60),
        ascent_m=13.0,
        building_id=building,
        checkin_id=checkin,
    )
    assert len(user.ok(there, here)["accepted"]) == 2
    assert _flags(world) == {there["id"]: {"impossible_sequence"}}


def test_impossible_on_both_sides_at_once_is_flagged_once(world: World) -> None:
    now = utcnow()
    t0 = now - timedelta(hours=2)
    split, back = t0 + timedelta(seconds=45), t0 + timedelta(seconds=105)
    user, building, checkin, _ = _two_checkins(world, now, split, back)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        again = db.execute(
            text(
                "INSERT INTO checkin (user_id, building_id, method, valid_during) "  # noqa: S608
                f"VALUES (:u, :b, 'qr', {TSTZRANGE_SQL}) RETURNING id::text"
            ),
            {"u": user.user_id, "b": world.building_id, "lo": back, "hi": now},
        ).scalar_one()
        db.commit()
    here = climb_at(t0)
    there = climb_at(
        t0 + timedelta(seconds=60), ascent_m=13.0, building_id=building, checkin_id=checkin
    )
    here_again = climb_at(t0 + timedelta(seconds=120), ascent_m=14.0, checkin_id=again)
    user.ok(here)
    user.ok(here_again)
    assert _flags(world) == {}
    user.ok(there)  # both its neighbours are 30 s away in the other building
    assert _flags(world) == {there["id"]: {"impossible_sequence"}}


# device_shared and device_burst


@pytest.mark.parametrize(("minutes", "flagged"), [(-1, True), (1, False)])
def test_device_shared_within_a_day(world: World, minutes: int, flagged: bool) -> None:
    one = world.climber()
    two = world.climber(device_id=one.device_id)
    start = utcnow() - timedelta(minutes=60)
    one.ok(climb_at(start))
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text("UPDATE segment_receipt SET created_at = :t WHERE user_id = :u"),
            {
                "t": utcnow() - rules.DEVICE_SHARED_WINDOW - timedelta(minutes=minutes),
                "u": one.user_id,
            },
        )
        db.commit()
    item = climb_at(start + timedelta(minutes=5))
    assert len(two.ok(item)["accepted"]) == 1
    assert _flags(world) == ({item["id"]: {"device_shared"}} if flagged else {})


def test_one_user_on_two_devices_is_not_device_shared(world: World) -> None:
    user = world.climber()
    start = utcnow() - timedelta(minutes=60)
    user.ok(climb_at(start))
    user.ok(
        climb_at(start + timedelta(minutes=5), ascent_m=13.0), device_id=world.second_device(user)
    )
    assert _flags(world) == {}


def test_device_burst_after_60_batches_in_an_hour(world: World) -> None:
    user = world.climber()
    limiter = world.client.app.state.rate_limiter  # type: ignore[attr-defined]
    for _ in range(rules.DEVICE_BATCHES_PER_HOUR - 1):
        assert limiter.hit("seg:device", str(user.device_id), 60, 3600).allowed
    start = utcnow() - timedelta(minutes=60)
    sixtieth, sixty_first = climb_at(start), climb_at(start + timedelta(minutes=5), ascent_m=13.0)
    user.ok(sixtieth)
    result = user.ok(sixty_first)
    assert result["rejected"] == []
    assert _flags(world) == {sixty_first["id"]: {"device_burst"}}
    assert _verified(world, sixty_first) == ("verified", 60)


class _DeviceBucketDown:
    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        if name == "seg:device":
            raise ValkeyError("down")
        return Decision(allowed=True, retry_after_s=0)


def test_device_burst_skipped_when_valkey_is_down(world: World) -> None:
    user = world.climber()
    item = climb_at(utcnow() - timedelta(minutes=60))
    assert len(_upload(world, user, item, limiter=_DeviceBucketDown()).accepted) == 1
    assert _flags(world) == {}


def test_a_resend_is_not_flagged_again(world: World) -> None:
    user = world.climber()
    start = utcnow() - timedelta(minutes=60)
    first, second = climb_at(start), climb_at(start + timedelta(minutes=5))
    user.ok(first, second)
    user.ok(first, second)
    assert _flags(world) == {second["id"]: {"identical_segment"}}
