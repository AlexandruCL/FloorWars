"""Tables of ``0004_segments``: constraints, deletes, and the repository functions on them."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.segments import repository
from app.segments.models import STATUS_REJECTED, STATUS_VERIFIED, SegmentRow
from tests.helpers import TEST_DB_URL


@dataclass(frozen=True)
class World:
    user_id: uuid.UUID
    device_id: uuid.UUID
    team_id: int
    season_id: int
    building_id: int
    checkin_id: uuid.UUID
    started_at: datetime


@pytest.fixture
def db(clean: None) -> Iterator[Session]:
    """A session on the test database; rolled back unless the test commits."""
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


@pytest.fixture
def world(db: Session) -> World:
    """A user with a device, a team in the active season, and a check-in at a building."""
    started_at = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=10)
    user_id = db.execute(
        text(
            'INSERT INTO "user" (email, display_name) '
            "VALUES ('schema@student.upt.ro', 's') RETURNING id"
        )
    ).scalar_one()
    device_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO device (user_id, id, model, has_barometer) VALUES (:u, :d, 'Pixel', true)"
        ),
        {"u": user_id, "d": device_id},
    )
    team_id = db.execute(
        text("INSERT INTO team (code, color_hex) VALUES ('AC', '#112233') RETURNING id")
    ).scalar_one()
    season_id = db.execute(
        text(
            "INSERT INTO season (active_during) "
            "VALUES (tstzrange(now() - interval '60 days', now() + interval '60 days')) "
            "RETURNING id"
        )
    ).scalar_one()
    db.execute(
        text("INSERT INTO team_membership (user_id, season_id, team_id) VALUES (:u, :s, :t)"),
        {"u": user_id, "s": season_id, "t": team_id},
    )
    building_id = db.execute(
        text(
            "INSERT INTO building (name, footprint) VALUES ('Lib', "
            "ST_GeomFromText('POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))', 4326)) RETURNING id"
        )
    ).scalar_one()
    checkin_id = db.execute(
        text(
            "INSERT INTO checkin (user_id, building_id, method, valid_during) VALUES (:u, :b, "
            "'qr', tstzrange(now() - interval '30 minutes', now() + interval '60 minutes')) "
            "RETURNING id"
        ),
        {"u": user_id, "b": building_id},
    ).scalar_one()
    return World(user_id, device_id, team_id, season_id, building_id, checkin_id, started_at)


def _row(world: World, **overrides: Any) -> SegmentRow:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "device_id": world.device_id,
        "user_id": world.user_id,
        "team_id": world.team_id,
        "season_id": world.season_id,
        "checkin_id": world.checkin_id,
        "building_id": world.building_id,
        "status": STATUS_VERIFIED,
        "reject_reason": None,
        "steps": 40,
        "steps_scored": 40,
        "points": 40,
        "ascent_m": 6.0,
        "duration_s": 30.0,
        "vert_speed_mps": 0.2,
        "stair_prob": 0.9,
        "classifier_version": "rules-1",
        "started_at": world.started_at,
        **overrides,
    }
    return SegmentRow(**values)


def _rejected(world: World, **overrides: Any) -> SegmentRow:
    values: dict[str, Any] = {
        "status": STATUS_REJECTED,
        "reject_reason": "speed",
        "steps_scored": 0,
        "points": 0,
        **overrides,
    }
    return _row(world, **values)


def test_valid_verified_and_rejected_rows_are_stored(db: Session, world: World) -> None:
    repository.insert_segment(db, _row(world))
    # Numbers a verified row may not have are fine on a rejected one.
    repository.insert_segment(db, _rejected(world, steps=5000, ascent_m=500.0, stair_prob=7.0))
    assert db.execute(text("SELECT count(*) FROM climb_segment")).scalar_one() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": 0},
        {"steps": 2001},
        {"ascent_m": 1.99},
        {"ascent_m": 120.5},
        {"stair_prob": -0.1},
        {"stair_prob": 1.1},
        {"stair_prob": float("nan")},
    ],
)
def test_verified_row_out_of_bounds_is_refused(
    db: Session, world: World, overrides: dict[str, Any]
) -> None:
    with pytest.raises(IntegrityError, match="ck_climb_segment_verified_bounds"):
        repository.insert_segment(db, _row(world, **overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": 1, "steps_scored": 1},
        {"steps": 2000, "steps_scored": 2000},
        {"ascent_m": 2.0},
        {"ascent_m": 120.0},
        {"stair_prob": 0.0},
        {"stair_prob": 1.0},
    ],
)
def test_verified_row_on_the_bounds_is_stored(
    db: Session, world: World, overrides: dict[str, Any]
) -> None:
    repository.insert_segment(db, _row(world, **overrides))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": "pending"}, "ck_climb_segment_status"),
        ({"steps_scored": -1}, "ck_climb_segment_steps_scored_range"),
        ({"steps_scored": 2001}, "ck_climb_segment_steps_scored_range"),
        ({"points": -1}, "ck_climb_segment_points_not_negative"),
        ({"reject_reason": "speed"}, "ck_climb_segment_reject_reason_if_rejected"),
    ],
)
def test_constraints_on_a_verified_row(
    db: Session, world: World, overrides: dict[str, Any], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        repository.insert_segment(db, _row(world, **overrides))


def test_rejected_row_needs_a_reason(db: Session, world: World) -> None:
    with pytest.raises(IntegrityError, match="ck_climb_segment_reject_reason_if_rejected"):
        repository.insert_segment(db, _rejected(world, reject_reason=None))


def test_segment_foreign_keys(db: Session, world: World) -> None:
    with pytest.raises(IntegrityError, match="fk_climb_segment_checkin_id_checkin"):
        repository.insert_segment(db, _row(world, checkin_id=uuid.uuid4()))


def test_primary_key_is_id_and_started_at(db: Session, world: World) -> None:
    row = _row(world)
    assert repository.insert_segment(db, row) is True
    # Same id at another time: allowed by the key (segment_receipt decides resends).
    later = replace(row, started_at=row.started_at + timedelta(seconds=1))
    assert repository.insert_segment(db, later) is True
    # Same key, other values: reported, and the stored row stays as it was.
    assert repository.insert_segment(db, replace(row, steps=99, device_id=uuid.uuid4())) is False
    stored = db.execute(
        text("SELECT steps FROM climb_segment WHERE id = :i AND started_at = :s"),
        {"i": row.id, "s": row.started_at},
    ).scalar_one()
    assert stored == row.steps


def test_score_points_cannot_go_negative(db: Session, world: World) -> None:
    with pytest.raises(IntegrityError, match="ck_team_building_score_points_not_negative"):
        repository.add_score(db, world.season_id, world.building_id, world.team_id, -1, 0)


def test_game_event_kind_is_checked(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_game_event_kind"):
        db.execute(text("INSERT INTO game_event (kind) VALUES ('other')"))


def test_game_event_defaults(db: Session) -> None:
    payload = db.execute(
        text("INSERT INTO game_event (kind) VALUES ('season_state') RETURNING payload")
    ).scalar_one()
    assert payload == {}


def test_deleting_a_user_removes_their_segment_data(db: Session, world: World) -> None:
    row = _row(world)
    repository.insert_segment(db, row)
    repository.insert_receipt(
        db, world.device_id, row.id, world.user_id, STATUS_VERIFIED, None, row.steps_scored
    )
    repository.add_fraud_flag(db, row.id, row.started_at, world.user_id, "speed")
    db.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": world.user_id})
    for table in ("climb_segment", "segment_receipt", "fraud_flag", "checkin"):
        count = db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
        assert count == 0, table


def test_a_partition_drop_is_not_blocked_by_fraud_flags(db: Session, world: World) -> None:
    db.execute(
        text(
            "CREATE TABLE public.climb_segment_203106 PARTITION OF public.climb_segment "
            "FOR VALUES FROM ('2031-06-01 00:00:00+00') TO ('2031-07-01 00:00:00+00')"
        )
    )
    started_at = datetime(2031, 6, 15, tzinfo=UTC)
    row = _rejected(world, started_at=started_at)
    repository.insert_segment(db, row)
    repository.add_fraud_flag(db, row.id, started_at, world.user_id, "speed")
    db.execute(text("DROP TABLE public.climb_segment_203106"))
    assert db.execute(text("SELECT count(*) FROM fraud_flag")).scalar_one() == 1


# Repository functions.


def test_lock_user(db: Session, world: World) -> None:
    assert repository.lock_user(db, world.user_id) is True
    assert repository.lock_user(db, uuid.uuid4()) is False


def test_device_belongs_is_per_user(db: Session, world: World) -> None:
    assert repository.device_belongs(db, world.user_id, world.device_id) is True
    assert repository.device_belongs(db, world.user_id, uuid.uuid4()) is False
    assert repository.device_belongs(db, uuid.uuid4(), world.device_id) is False


def test_receipt_roundtrip_and_first_answer_wins(db: Session, world: World) -> None:
    segment_id = uuid.uuid4()
    assert repository.get_receipt(db, world.device_id, segment_id) is None
    repository.insert_receipt(
        db, world.device_id, segment_id, world.user_id, "rejected", "speed", 0
    )
    repository.insert_receipt(db, world.device_id, segment_id, world.user_id, "verified", None, 9)
    receipt = repository.get_receipt(db, world.device_id, segment_id)
    assert receipt is not None
    assert (receipt.status, receipt.reject_reason, receipt.steps_scored) == ("rejected", "speed", 0)
    assert (receipt.device_id, receipt.id, receipt.user_id) == (
        world.device_id,
        segment_id,
        world.user_id,
    )


def test_load_context_finds_everything(db: Session, world: World) -> None:
    ctx = repository.load_context(db, world.user_id, world.checkin_id, world.started_at)
    assert ctx.checkin_user_id == world.user_id
    assert ctx.checkin_building_id == world.building_id
    assert ctx.season_id == world.season_id
    assert ctx.team_id == world.team_id
    assert ctx.checkin_valid_during is not None
    assert ctx.checkin_valid_during.contains(world.started_at)
    assert not ctx.checkin_valid_during.contains(world.started_at + timedelta(days=1))


def test_load_context_unknown_checkin_keeps_season_and_team(db: Session, world: World) -> None:
    ctx = repository.load_context(db, world.user_id, uuid.uuid4(), world.started_at)
    assert ctx.checkin_user_id is None
    assert ctx.checkin_building_id is None
    assert ctx.checkin_valid_during is None
    assert (ctx.season_id, ctx.team_id) == (world.season_id, world.team_id)


def test_load_context_outside_any_season(db: Session, world: World) -> None:
    ctx = repository.load_context(
        db, world.user_id, world.checkin_id, world.started_at + timedelta(days=365)
    )
    assert ctx.checkin_user_id == world.user_id
    assert ctx.season_id is None
    assert ctx.team_id is None


def test_load_context_user_without_team_and_foreign_checkin(db: Session, world: World) -> None:
    other = db.execute(
        text(
            'INSERT INTO "user" (email, display_name) '
            "VALUES ('other@student.upt.ro', 'o') RETURNING id"
        )
    ).scalar_one()
    ctx = repository.load_context(db, other, world.checkin_id, world.started_at)
    assert ctx.season_id == world.season_id
    assert ctx.team_id is None
    assert ctx.checkin_user_id == world.user_id  # the rule compares it and answers no_checkin


def test_verified_steps_interval_is_open_then_closed(db: Session, world: World) -> None:
    at = world.started_at
    repository.insert_segment(db, _row(world, started_at=at, steps=40, steps_scored=40))
    # Visible before commit: an earlier item of the same batch must count.
    assert repository.verified_steps_between(db, world.user_id, at - timedelta(minutes=1), at) == 40
    assert repository.verified_steps_between(db, world.user_id, at, at + timedelta(minutes=1)) == 0


def test_verified_steps_ignores_rejected_and_other_users(db: Session, world: World) -> None:
    at = world.started_at
    repository.insert_segment(db, _rejected(world, started_at=at))
    window = (at - timedelta(minutes=1), at + timedelta(minutes=1))
    assert repository.verified_steps_between(db, world.user_id, *window) == 0
    repository.insert_segment(db, _row(world, started_at=at))
    assert repository.verified_steps_between(db, world.user_id, *window) == 40
    assert repository.verified_steps_between(db, uuid.uuid4(), *window) == 0


def test_add_score_accumulates(db: Session, world: World) -> None:
    for points, steps in ((10, 10), (5, 10)):
        repository.add_score(db, world.season_id, world.building_id, world.team_id, points, steps)
    row = db.execute(text("SELECT points, steps FROM team_building_score")).one()
    assert (row.points, row.steps) == (15, 20)


def test_add_fraud_flag_is_unresolved(db: Session, world: World) -> None:
    segment_id = uuid.uuid4()
    repository.add_fraud_flag(db, segment_id, world.started_at, world.user_id, "cadence")
    row = db.execute(text("SELECT segment_id, rule, resolved_at FROM fraud_flag")).one()
    assert (row.segment_id, row.rule, row.resolved_at) == (segment_id, "cadence", None)
