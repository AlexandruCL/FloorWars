"""The plausibility rules: every bound on both sides, and the order of the rules. No database."""

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import Range

from app.segments import claim, rules
from app.segments.models import ItemContext
from app.segments.schemas import Segment, SegmentBatch

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
USER = uuid.uuid4()
BUILDING = 7


def raw_item(**overrides: Any) -> dict[str, Any]:
    """A segment passing every rule: 60 steps, 12 m in 30 s (0.4 m/s, 5 steps/m, 2 steps/s)."""
    return {
        "id": str(uuid.uuid4()),
        "checkin_id": str(uuid.uuid4()),
        "started_at": NOW.isoformat(),
        "building_id": BUILDING,
        "ascent_m": 12.0,
        "duration_s": 30.0,
        "vert_speed_mps": 0.4,
        "steps": 60,
        "stair_prob": 0.9,
        "classifier_version": "rules-1",
        **overrides,
    }


def item(**overrides: Any) -> Segment:
    return Segment.model_validate(raw_item(**overrides))


def ctx(**overrides: Any) -> ItemContext:
    values: dict[str, Any] = {
        "checkin_user_id": USER,
        "checkin_building_id": BUILDING,
        "checkin_valid_during": Range(NOW - timedelta(minutes=30), NOW + timedelta(minutes=60)),
        "season_id": 1,
        "team_id": 2,
        **overrides,
    }
    return ItemContext(**values)


def check(
    segment: Segment, context: ItemContext | None = None, recent: int = 0, overlaps: bool = False
) -> str | None:
    return rules.check_item(
        segment,
        context or ctx(),
        user_id=USER,
        now=NOW,
        recent_verified_steps=recent,
        overlaps_verified=overlaps,
    )


def test_a_plausible_segment_passes() -> None:
    assert check(item()) is None


@pytest.mark.parametrize(
    ("delta", "reason"),
    [
        (-rules.STARTED_AT_MAX_AGE, None),
        (-rules.STARTED_AT_MAX_AGE - timedelta(seconds=1), "started_at_range"),
        (rules.STARTED_AT_FUTURE_SKEW, None),
        (rules.STARTED_AT_FUTURE_SKEW + timedelta(seconds=1), "started_at_range"),
    ],
)
def test_started_at_bounds(delta: timedelta, reason: str | None) -> None:
    assert rules.check_bounds(item(started_at=(NOW + delta).isoformat()), NOW) == reason


def test_started_at_far_outside_is_safe() -> None:
    assert rules.check_bounds(item(started_at="0001-01-01T00:00:00+14:00"), NOW) == (
        "started_at_range"
    )
    assert rules.check_bounds(item(started_at="9999-12-31T23:59:59-14:00"), NOW) == (
        "started_at_range"
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("steps", 1, None),
        ("steps", 0, "steps_range"),
        ("steps", 2000, None),
        ("steps", 2001, "steps_range"),
        ("ascent_m", 2.0, None),
        ("ascent_m", 1.999, "ascent_range"),
        ("ascent_m", 120.0, None),
        ("ascent_m", 120.001, "ascent_range"),
        ("ascent_m", math.nan, "ascent_range"),
        ("ascent_m", math.inf, "ascent_range"),
        ("duration_s", 5.0, None),
        ("duration_s", 4.999, "duration"),
        ("duration_s", 180.0, None),
        ("duration_s", 180.001, "duration"),
        ("duration_s", math.nan, "duration"),
        ("duration_s", -math.inf, "duration"),
        ("stair_prob", 0, None),
        ("stair_prob", -0.001, "stair_prob_range"),
        ("stair_prob", 1, None),
        ("stair_prob", 1.001, "stair_prob_range"),
        ("stair_prob", math.nan, "stair_prob_range"),
        ("stair_prob", math.inf, "stair_prob_range"),
    ],
)
def test_range_bounds(field: str, value: float, reason: str | None) -> None:
    assert rules.check_bounds(item(**{field: value}), NOW) == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        # 0.1 and 0.9 m/s themselves, with a matching ascent and duration.
        ({"ascent_m": 3.0, "duration_s": 30.0, "vert_speed_mps": 0.1, "steps": 15}, None),
        ({"ascent_m": 3.0, "duration_s": 30.0, "vert_speed_mps": 0.099, "steps": 15}, "speed"),
        ({"ascent_m": 27.0, "duration_s": 30.0, "vert_speed_mps": 0.9, "steps": 135}, "cadence"),
        ({"ascent_m": 27.0, "duration_s": 30.0, "vert_speed_mps": 0.901, "steps": 135}, "speed"),
        # Against the measured 0.4 m/s: 20 percent is allowed, more is not.
        ({"vert_speed_mps": 0.479}, None),
        ({"vert_speed_mps": 0.481}, "speed"),
        ({"vert_speed_mps": 0.321}, None),
        ({"vert_speed_mps": 0.319}, "speed"),
        ({"vert_speed_mps": math.nan}, "speed"),
        ({"vert_speed_mps": math.inf}, "speed"),
        # Steps per metre on 12 m: 48 is 4.0, 120 is 10.0.
        ({"steps": 48}, None),
        ({"steps": 47}, "pressure_steps_mismatch"),
        ({"steps": 90}, None),
        ({"steps": 120, "duration_s": 40.0, "vert_speed_mps": 0.3}, None),
        ({"steps": 121, "duration_s": 45.0, "vert_speed_mps": 0.267}, "pressure_steps_mismatch"),
        # Cadence on 20 s, 8 m (0.4 m/s): 60 steps is 3.0 per second and 7.5 per metre.
        ({"ascent_m": 8.0, "duration_s": 20.0, "steps": 60}, None),
        ({"ascent_m": 8.0, "duration_s": 20.0, "steps": 61}, "cadence"),
    ],
)
def test_physics_bounds(overrides: dict[str, Any], reason: str | None) -> None:
    assert check(item(**overrides)) == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"checkin_user_id": None, "checkin_building_id": None, "checkin_valid_during": None},
            "no_checkin",
        ),
        ({"checkin_user_id": uuid.uuid4()}, "no_checkin"),
        ({"checkin_building_id": BUILDING + 1}, "building_mismatch"),
        ({"season_id": None, "team_id": None}, "season_inactive"),
        ({"team_id": None}, "no_team"),
    ],
)
def test_state_rules(overrides: dict[str, Any], reason: str) -> None:
    assert check(item(), ctx(**overrides)) == reason


def test_checkin_window_is_half_open_and_only_the_start_counts() -> None:
    until = NOW + timedelta(seconds=10)
    window = Range(NOW - timedelta(minutes=30), until)
    # Starts at the last moment and ends 30 s after the check-in: it still counts.
    last = item(started_at=(until - timedelta(microseconds=1)).isoformat())
    assert check(last, ctx(checkin_valid_during=window)) is None
    assert check(item(started_at=until.isoformat()), ctx(checkin_valid_during=window)) == (
        "no_checkin"
    )
    assert check(item(), ctx(checkin_valid_during=Range(NOW, until))) is None
    before = item(started_at=(NOW - timedelta(seconds=1)).isoformat())
    assert check(before, ctx(checkin_valid_during=Range(NOW, until))) == "no_checkin"


@pytest.mark.parametrize(("recent", "reason"), [(540, None), (541, "rate_limit")])
def test_verified_steps_per_ten_minutes(recent: int, reason: str | None) -> None:
    assert check(item(), recent=recent) == reason


def test_rule_order_first_failure_wins() -> None:
    """Everything is broken at first; fixing the reported rule exposes the next one."""
    broken: dict[str, Any] = {
        "started_at": (NOW + timedelta(days=1)).isoformat(),
        "steps": 0,
        "ascent_m": 1.0,
        "duration_s": 1.0,
        "stair_prob": 2.0,
        "vert_speed_mps": 5.0,
    }
    bad_ctx: dict[str, Any] = {
        "checkin_user_id": uuid.uuid4(),
        "checkin_building_id": BUILDING + 1,
        "season_id": None,
        "team_id": None,
    }
    expected = [
        ("started_at", None, "started_at_range"),
        ("steps", None, "steps_range"),
        ("ascent_m", None, "ascent_range"),
        ("duration_s", None, "duration"),
        ("stair_prob", None, "stair_prob_range"),
        (None, "checkin_user_id", "no_checkin"),
        (None, "checkin_building_id", "building_mismatch"),
        (None, "season_id", "season_inactive"),
        (None, "team_id", "no_team"),
    ]
    for field, ctx_field, reason in expected:
        assert check(item(**broken), ctx(**bad_ctx), recent=9999, overlaps=True) == reason
        if field:
            del broken[field]
        if ctx_field:
            del bad_ctx[ctx_field]
    # The physics rules, each case also failing the later ones.
    both: dict[str, Any] = {"recent": 9999, "overlaps": True}
    assert check(item(vert_speed_mps=5.0, steps=200), **both) == "speed"
    assert check(item(steps=200), **both) == "pressure_steps_mismatch"
    # 71 steps on 12 m in 20 s: 5.9 steps per metre, 3.55 steps per second, 0.6 m/s.
    assert check(item(duration_s=20.0, vert_speed_mps=0.6, steps=71), **both) == "cadence"
    assert check(item(), **both) == "overlap"
    assert check(item(), recent=9999) == "rate_limit"


@pytest.mark.parametrize(
    ("steps", "hour_steps", "points"),
    [
        (0, 0, 0),
        (299, 0, 299),
        (300, 0, 300),
        (301, 0, 300),  # 300 + floor(0.5)
        (302, 0, 301),
        (0, 100, 0),
        (299, 100, 249),  # 200 full, 99 halved: floor(249.5)
        (300, 100, 250),
        (301, 100, 250),  # floor(250.5)
        (100, 300, 50),
        (100, 500, 50),  # steps of the hour beyond 300 do not lower it further
        (1, 299, 1),
        (1, 300, 0),  # floor(0.5)
    ],
)
def test_points_formula(steps: int, hour_steps: int, points: int) -> None:
    assert claim.points_for(steps, hour_steps) == points


def test_reason_sets_are_real_reasons() -> None:
    assert {"started_at_range", "no_checkin", "season_inactive", "no_team"} == rules.NOT_FRAUD
    assert rules.NOT_FRAUD <= rules.RECEIPT_ONLY
    stores_a_row = {"speed", "pressure_steps_mismatch", "cadence", "overlap", "rate_limit"}
    assert not rules.RECEIPT_ONLY & stores_a_row


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        (0.5, 0.5),
        (1e300, math.inf),
        (-1e300, -math.inf),
        (1e-300, 0.0),
        (math.inf, math.inf),
    ],
)
def test_storable_real(value: float, stored: float) -> None:
    assert rules.storable_real(value) == stored


def test_storable_real_keeps_nan() -> None:
    assert math.isnan(rules.storable_real(math.nan))


# The request model accepts any number and refuses anything that is not a valid batch.


@pytest.mark.parametrize(
    "fields",
    [
        {"steps": -5},
        {"steps": 10**30},
        {"building_id": -1},
        {"ascent_m": 1e308},
        {"ascent_m": 10**400},
        {"duration_s": -(10**400)},
        {"stair_prob": math.nan},
        {"vert_speed_mps": -math.inf},
    ],
)
def test_out_of_range_numbers_parse(fields: dict[str, Any]) -> None:
    item(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"id": 5},
        {"id": "nope"},
        {"checkin_id": None},
        {"steps": 1.5},
        {"steps": True},
        {"steps": "60"},
        {"building_id": 7.0},
        {"ascent_m": "12"},
        {"ascent_m": True},
        {"started_at": 1700000000},
        {"started_at": "1700000000"},
        {"started_at": "2026-11-07T12:00:00"},
        {"started_at": "2026-11-07"},
        {"classifier_version": ""},
        {"classifier_version": 1},
        {"classifier_version": "x" * 65},
        {"classifier_version": "a\x00b"},
        {"classifier_version": "a\nb"},
        {"device_id": str(uuid.uuid4())},
    ],
)
def test_invalid_items_are_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        item(**fields)


def test_classifier_version_limit_is_inclusive() -> None:
    assert item(classifier_version="x" * 64).classifier_version == "x" * 64


@pytest.mark.parametrize("count", [0, 101])
def test_batch_size_is_bounded(count: int) -> None:
    with pytest.raises(ValidationError):
        SegmentBatch.model_validate(
            {"device_id": str(uuid.uuid4()), "segments": [raw_item() for _ in range(count)]}
        )


def test_batch_needs_a_device_and_nothing_else() -> None:
    good = {"device_id": str(uuid.uuid4()), "segments": [raw_item() for _ in range(100)]}
    assert len(SegmentBatch.model_validate(good).segments) == 100
    with pytest.raises(ValidationError):
        SegmentBatch.model_validate({"segments": [raw_item()]})
    with pytest.raises(ValidationError):
        SegmentBatch.model_validate({**good, "extra": 1})
