"""``POST /v1/segments`` end to end: per-item results, stored rows, flips and isolation."""

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range

from app.segments import repository, service
from app.segments.models import Flip
from app.segments.schemas import Segment, SegmentBatch
from app.valkey import ValkeyError
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import (
    TSTZRANGE_SQL,
    World,
    climb,
    make_world,
    scalar,
    utcnow,
)

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


def test_a_verified_climb_scores_and_claims(world: World) -> None:
    user = world.climber("AC")
    item = climb()
    result = user.ok(item)
    assert result["accepted"] == [{"id": item["id"], "steps_scored": 60, "points": 60}]
    assert result["rejected"] == []
    flip = result["flips"][0]
    assert set(flip) == {"building_id", "from_team", "to_team", "at"}
    assert (flip["building_id"], flip["from_team"], flip["to_team"]) == (
        world.building_id,
        None,
        "AC",
    )
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60
    assert scalar(world.client, "SELECT status FROM climb_segment") == "verified"
    assert scalar(world.client, "SELECT status FROM segment_receipt") == "verified"
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0


def test_a_flip_names_both_teams(world: World) -> None:
    world.climber("AC").ok(climb())
    result = world.climber("ETC").ok(
        climb(steps=90, ascent_m=15.0, duration_s=40.0, vert_speed_mps=0.375)
    )
    assert [(f["from_team"], f["to_team"]) for f in result["flips"]] == [("AC", "ETC")]


def test_partial_success(world: World) -> None:
    user = world.climber()
    good, flat, unknown = (
        climb(minutes_ago=3),
        climb(steps=500, minutes_ago=2),
        climb(checkin_id=str(uuid.uuid4())),
    )
    result = user.ok(good, flat, unknown)
    assert [a["id"] for a in result["accepted"]] == [good["id"]]
    assert {r["id"]: r["reason"] for r in result["rejected"]} == {
        flat["id"]: "pressure_steps_mismatch",
        unknown["id"]: "no_checkin",
    }


def test_items_run_in_started_at_order_whatever_the_request_order(world: World) -> None:
    user = world.climber()
    # 200 steps each. Earlier first: 200 points, then 100 full + 100 halved = 150.
    big: dict[str, Any] = {
        "steps": 200,
        "ascent_m": 40.0,
        "duration_s": 100.0,
        "vert_speed_mps": 0.4,
    }
    late, early = climb(minutes_ago=2, **big), climb(minutes_ago=30, **big)
    accepted = {a["id"]: a["points"] for a in user.ok(late, early)["accepted"]}
    assert accepted == {early["id"]: 200, late["id"]: 150}
    assert scalar(world.client, "SELECT points FROM team_building_score") == 350
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 400


def test_hourly_points_count_earlier_batches(world: World) -> None:
    user = world.climber()
    big: dict[str, Any] = {
        "steps": 280,
        "ascent_m": 56.0,
        "duration_s": 140.0,
        "vert_speed_mps": 0.4,
    }
    user.ok(climb(minutes_ago=30, **big))
    # 280 earlier, so 20 full and 40 halved.
    assert user.ok(climb(minutes_ago=1))["accepted"][0]["points"] == 40


def test_600_verified_steps_per_ten_minutes(world: World) -> None:
    user = world.climber()
    big: dict[str, Any] = {
        "steps": 300,
        "ascent_m": 60.0,
        "duration_s": 120.0,
        "vert_speed_mps": 0.5,
    }
    first, second, third = (climb(minutes_ago=m, **big) for m in (9, 6, 3))
    result = user.ok(first, second, third)
    assert {a["id"] for a in result["accepted"]} == {first["id"], second["id"]}
    assert result["rejected"] == [{"id": third["id"], "reason": "rate_limit"}]
    assert scalar(world.client, "SELECT rule FROM fraud_flag") == "rate_limit"
    # The rejected climb is kept for the history, and does not score.
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 600
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 3


def test_upload_order_cannot_bypass_the_rate_limit(world: World) -> None:
    user = world.climber()
    big: dict[str, Any] = {
        "steps": 300,
        "ascent_m": 60.0,
        "duration_s": 120.0,
        "vert_speed_mps": 0.5,
    }
    newest, middle, oldest = (climb(minutes_ago=m, **big) for m in (3, 6, 9))
    user.ok(newest)
    user.ok(middle)
    assert user.ok(oldest)["rejected"] == [{"id": oldest["id"], "reason": "rate_limit"}]
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 600


def test_upload_order_cannot_bypass_the_hourly_halving(world: World) -> None:
    user = world.climber()
    big: dict[str, Any] = {
        "steps": 280,
        "ascent_m": 56.0,
        "duration_s": 140.0,
        "vert_speed_mps": 0.4,
    }
    user.ok(climb(minutes_ago=1, **big))
    # 280 later, so 20 full and 40 halved.
    assert user.ok(climb(minutes_ago=30))["accepted"][0]["points"] == 40


def test_the_windows_are_open_at_both_ends(world: World) -> None:
    user = world.climber()
    big: dict[str, Any] = {
        "steps": 540,
        "ascent_m": 100.0,
        "duration_s": 180.0,
        "vert_speed_mps": 0.55,
    }
    base = utcnow() - timedelta(minutes=30)

    def at(delta: timedelta, **fields: Any) -> dict[str, Any]:
        return climb(started_at=(base + delta).isoformat(), **fields)

    assert user.ok(at(timedelta(minutes=10), **big))["accepted"]
    # Exactly 10 minutes before the first: neither counts the other.
    assert user.ok(at(timedelta(0), **big))["accepted"]
    # Inside both windows.
    between = at(timedelta(minutes=5))
    assert user.ok(between)["rejected"] == [{"id": between["id"], "reason": "rate_limit"}]


@pytest.mark.parametrize(
    "bad",
    [
        {"vert_speed_mps": 1e300},
        {"vert_speed_mps": 1e-300},
        {"vert_speed_mps": float("nan")},
        {"vert_speed_mps": float("inf")},
    ],
)
def test_extreme_speed_is_stored_as_a_rejected_row(world: World, bad: dict[str, float]) -> None:
    result = world.climber().ok(climb(**bad))
    assert [r["reason"] for r in result["rejected"]] == ["speed"]
    assert scalar(world.client, "SELECT reject_reason FROM climb_segment") == "speed"
    assert scalar(world.client, "SELECT rule FROM fraud_flag") == "speed"
    assert scalar(world.client, "SELECT count(*) FROM team_building_score") == 0


def test_a_tiny_stair_prob_is_stored_as_zero_and_the_climb_verified(world: World) -> None:
    # Inside the 0 to 1 rule, too small for a real: the cast must not lose the batch.
    item = climb(stair_prob=1e-50)
    result = world.climber().ok(item)
    assert [a["id"] for a in result["accepted"]] == [item["id"]]
    assert scalar(world.client, "SELECT status FROM climb_segment") == "verified"
    assert scalar(world.client, "SELECT stair_prob FROM climb_segment") == 0.0


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ({"steps": 0}, "steps_range"),
        ({"steps": 10**30}, "steps_range"),
        ({"ascent_m": float("nan")}, "ascent_range"),
        ({"ascent_m": 10**400}, "ascent_range"),
        ({"duration_s": float("-inf")}, "duration"),
        ({"stair_prob": 1.5}, "stair_prob_range"),
        ({"stair_prob": float("nan")}, "stair_prob_range"),
        ({"building_id": 10**30}, "building_mismatch"),
    ],
)
def test_receipt_only_rejections_are_flagged_without_a_row(
    world: World, bad: dict[str, Any], reason: str
) -> None:
    result = world.climber().ok(climb(**bad))
    assert [r["reason"] for r in result["rejected"]] == [reason]
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 0
    assert scalar(world.client, "SELECT reject_reason FROM segment_receipt") == reason
    assert scalar(world.client, "SELECT rule FROM fraud_flag") == reason


@pytest.mark.parametrize("started_at", ["far past", "far future"])
def test_state_rejections_are_not_flagged(world: World, started_at: str) -> None:
    when = "0001-01-01T00:00:00+14:00" if started_at == "far past" else "9999-12-31T23:59:59-14:00"
    result = world.climber().ok(climb(started_at=when))
    assert [r["reason"] for r in result["rejected"]] == ["started_at_range"]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 0


def test_no_team(world: World) -> None:
    result = world.climber(team=None).ok(climb())
    assert [r["reason"] for r in result["rejected"]] == ["no_team"]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0


def test_season_inactive(world: World) -> None:
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text(f"UPDATE season SET active_during = {TSTZRANGE_SQL}"),  # noqa: S608
            {"lo": utcnow() - timedelta(days=30), "hi": utcnow() - timedelta(days=20)},
        )
        db.commit()
    result = world.climber().ok(climb())
    assert [r["reason"] for r in result["rejected"]] == ["season_inactive"]


def test_a_climb_ending_after_the_checkin_still_counts(world: World) -> None:
    # Check-in ended 5 s ago; the 30 s climb started 20 s ago, so it ended after valid_until.
    now = utcnow()
    user = world.climber(
        valid_during=Range(now - timedelta(minutes=30), now - timedelta(seconds=5))
    )
    inside = climb(minutes_ago=20 / 60)
    assert [a["id"] for a in user.ok(inside)["accepted"]] == [inside["id"]]
    after = climb(minutes_ago=1 / 60)
    assert [r["reason"] for r in user.ok(after)["rejected"]] == ["no_checkin"]


# Devices and isolation between users.


def test_403_for_a_device_of_nobody_or_of_another_user(world: World) -> None:
    user, other = world.climber(), world.climber("ETC")
    for device in (uuid.uuid4(), other.device_id):
        response = user.post(climb(), device_id=str(device))
        assert response.status_code == 403, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"] == "urn:floorwars:problem:device-unknown"
    assert scalar(world.client, "SELECT count(*) FROM segment_receipt") == 0


def test_checkin_of_another_user_is_refused(world: World) -> None:
    user, other = world.climber(), world.climber("ETC")
    result = user.ok(climb(checkin_id=str(other.checkin_id)))
    assert [r["reason"] for r in result["rejected"]] == ["no_checkin"]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0


def test_receipt_of_another_user_on_a_shared_device_id_is_not_shown(world: World) -> None:
    device = uuid.uuid4()
    first, second = world.climber("AC", device), world.climber("ETC", device)
    item = climb()
    assert first.ok(item)["accepted"][0]["points"] == 60
    result = second.ok(item)
    assert result == {
        "accepted": [],
        "rejected": [{"id": item["id"], "reason": "no_checkin"}],
        "flips": [],
    }
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1


def test_response_carries_only_the_callers_ids(world: World) -> None:
    other, user = world.climber("ETC"), world.climber()
    other.ok(climb(minutes_ago=5))
    item = climb()
    body = user.post(item).text
    assert str(other.user_id) not in body
    assert str(other.device_id) not in body
    assert str(other.checkin_id) not in body


def test_same_segment_from_a_second_device_scores_once(world: World) -> None:
    user = world.climber()
    item = climb()
    user.ok(item)
    result = user.ok(item, device_id=world.second_device(user))
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0


def test_a_rejected_climb_resent_from_a_second_device_is_flagged_once(world: World) -> None:
    user = world.climber()
    item = climb(steps=500)
    assert user.ok(item)["rejected"] == [{"id": item["id"], "reason": "pressure_steps_mismatch"}]
    result = user.ok(item, device_id=world.second_device(user))
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 1
    assert scalar(world.client, "SELECT count(*) FROM segment_receipt") == 2


@pytest.mark.parametrize("body", [{"steps": 0}, {"building_id": 10**30}])
def test_a_taken_id_is_answered_before_the_rules_judge_the_caller(
    world: World, body: dict[str, Any]
) -> None:
    # These rules store no row, so no insert conflict would catch the id: only the check before
    # the rules stops a flag on the caller.
    item = climb()
    world.climber("AC").ok(item)
    result = world.climber("ETC").ok({**item, **body})
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1


def test_a_taken_id_overlapping_the_callers_own_climb_is_not_flagged(world: World) -> None:
    # B's own climb shares the time of A's. Judged, A's id would be B's overlap, with a flag.
    item = climb(minutes_ago=5)
    world.climber("AC").ok(item)
    other = world.climber("ETC")
    started = datetime.fromisoformat(item["started_at"]) + timedelta(seconds=10)
    assert other.ok(climb(started_at=started.isoformat()))["accepted"]
    result = other.ok(item)
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 2


@pytest.fixture
def lost_race(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check before the rules sees nothing, as when a concurrent upload has not committed."""
    monkeypatch.setattr(repository, "segment_exists", lambda *_: False)


@pytest.mark.usefixtures("lost_race")
def test_a_verified_item_losing_the_insert_race_changes_nothing(world: World) -> None:
    item = climb()
    world.climber("AC").ok(item)
    result = world.climber("ETC").ok(item)
    assert result == {
        "accepted": [],
        "rejected": [{"id": item["id"], "reason": "no_checkin"}],
        "flips": [],
    }
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1
    assert scalar(world.client, "SELECT count(*) FROM team_building_score") == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


@pytest.mark.usefixtures("lost_race")
def test_a_rejected_item_losing_the_insert_race_is_not_flagged(world: World) -> None:
    item = climb()
    world.climber("AC").ok(item)
    # Fails a rule that stores a row: too many steps per metre.
    result = world.climber("ETC").ok({**item, "steps": 500})
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 0
    assert scalar(world.client, "SELECT count(*) FROM climb_segment") == 1
    assert scalar(world.client, "SELECT status FROM climb_segment") == "verified"


# After the commit.


class _Board:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.scored: list[service.ScoredSegment] = []
        self.flips: list[Flip] = []

    def record_verified(self, scored: service.ScoredSegment) -> None:
        if self.failure:
            raise self.failure
        self.scored.append(scored)

    def publish_flip(self, flip: Flip) -> None:
        self.flips.append(flip)


def _batch_for(world: World) -> tuple[Any, SegmentBatch]:
    user = world.climber()
    item = {
        **climb(),
        "checkin_id": str(user.checkin_id),
        "building_id": user.building_id,
    }
    return user, SegmentBatch(device_id=user.device_id, segments=[Segment.model_validate(item)])


def test_leaderboards_hear_about_verified_segments_and_flips(world: World) -> None:
    user, batch = _batch_for(world)
    board = _Board()
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        service.upload_batch(db, user.user_id, batch, board)
    assert [(s.user_id, s.points, s.steps) for s in board.scored] == [(user.user_id, 60, 60)]
    assert [f.to_code for f in board.flips] == ["AC"]


def test_a_leaderboard_error_does_not_fail_or_undo_the_upload(world: World) -> None:
    user, batch = _batch_for(world)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        result = service.upload_batch(db, user.user_id, batch, _Board(ValkeyError("down")))
    assert len(result.accepted) == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60


def test_an_unexpected_leaderboard_error_is_logged_and_still_answers_success(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    # The batch is committed by then: a 500 would tell the client it was lost.
    user, batch = _batch_for(world)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        result = service.upload_batch(db, user.user_id, batch, _Board(RuntimeError("bug")))
    assert len(result.accepted) == 1
    assert [f.to_team for f in result.flips] == ["AC"]
    assert scalar(world.client, "SELECT points FROM team_building_score") == 60
    record = next(r for r in caplog.records if r.message == "leaderboard update failed")
    assert record.levelname == "ERROR"
    assert record.exc_info is not None


def test_flip_time_is_iso_and_aware(world: World) -> None:
    flip = world.climber().ok(climb())["flips"][0]
    assert datetime.fromisoformat(flip["at"]).tzinfo is not None
