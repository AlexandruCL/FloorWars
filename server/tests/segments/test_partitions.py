"""Partitions of ``climb_segment``: creation, idempotency, routing, year boundaries."""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.segments.partitions import ensure_partitions
from tests.helpers import TEST_DB_URL

SERVER_DIR = Path(__file__).resolve().parents[2]
# Far from now, so these never collide with the partitions the migration created.
FAR = datetime(2031, 6, 15, 12, tzinfo=UTC)


@pytest.fixture
def conn(clean: None) -> Iterator[Connection]:
    """A connection whose transaction is rolled back, so created partitions disappear."""
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    with engine.connect() as connection:
        tx = connection.begin()
        try:
            yield connection
        finally:
            tx.rollback()
    engine.dispose()


def _partitions(conn: Connection) -> set[str]:
    names = conn.execute(
        text(
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = 'climb_segment'::regclass"
        )
    ).scalars()
    return set(names)


def test_migration_covers_the_previous_current_and_next_two_months(conn: Connection) -> None:
    now = conn.execute(text("SELECT now()")).scalar_one()
    expected = {
        f"climb_segment_{month:%Y%m}"
        for month in conn.execute(
            text(
                "SELECT date_trunc('month', :now AT TIME ZONE 'UTC') + make_interval(months => m) "
                "FROM generate_series(-1, 2) AS m"
            ),
            {"now": now},
        ).scalars()
    }
    assert _partitions(conn) >= expected


def test_ensure_creates_the_range_and_returns_names(conn: Connection) -> None:
    names = ensure_partitions(conn, now=FAR)
    assert names == [
        "climb_segment_203105",
        "climb_segment_203106",
        "climb_segment_203107",
        "climb_segment_203108",
    ]
    assert _partitions(conn) >= set(names)


def test_ensure_is_idempotent(conn: Connection) -> None:
    first = ensure_partitions(conn, now=FAR)
    before = _partitions(conn)
    assert ensure_partitions(conn, now=FAR) == first
    assert _partitions(conn) == before


def test_months_ahead_controls_the_range(conn: Connection) -> None:
    assert ensure_partitions(conn, months_ahead=0, now=FAR) == [
        "climb_segment_203105",
        "climb_segment_203106",
    ]


def test_negative_months_ahead_is_refused(conn: Connection) -> None:
    with pytest.raises(ValueError, match="months_ahead"):
        ensure_partitions(conn, months_ahead=-1, now=FAR)


def test_year_boundaries(conn: Connection) -> None:
    january = datetime(2032, 1, 10, tzinfo=UTC)
    assert ensure_partitions(conn, months_ahead=0, now=january) == [
        "climb_segment_203112",
        "climb_segment_203201",
    ]
    november = datetime(2032, 11, 10, tzinfo=UTC)
    assert ensure_partitions(conn, now=november)[-2:] == [
        "climb_segment_203212",
        "climb_segment_203301",
    ]


def test_month_is_taken_in_utc(conn: Connection) -> None:
    # 2031-07-01 01:00 at +03:00 is still June in UTC.
    local = datetime.fromisoformat("2031-07-01T01:00:00+03:00")
    assert ensure_partitions(conn, months_ahead=0, now=local) == [
        "climb_segment_203105",
        "climb_segment_203106",
    ]


INSERT_SEGMENT = text(
    "INSERT INTO climb_segment (id, device_id, user_id, team_id, season_id, checkin_id, "
    "building_id, status, steps, steps_scored, points, ascent_m, duration_s, vert_speed_mps, "
    "stair_prob, classifier_version, started_at) VALUES (:id, gen_random_uuid(), :u, :team, "
    ":season, :checkin, :building, 'verified', 40, 40, 40, 6, 30, 0.2, 0.9, 'rules-1', :started_at)"
)


@pytest.fixture
def refs(conn: Connection) -> dict[str, object]:
    """The rows a segment refers to, inside the rolled-back transaction."""
    user_id = conn.execute(
        text(
            'INSERT INTO "user" (email, display_name) '
            "VALUES ('routing@student.upt.ro', 'r') RETURNING id"
        )
    ).scalar_one()
    team = conn.execute(
        text("INSERT INTO team (code, color_hex) VALUES ('AC', '#112233') RETURNING id")
    ).scalar_one()
    season = conn.execute(
        text(
            "INSERT INTO season (active_during) "
            "VALUES (tstzrange('2031-01-01', '2032-12-31')) RETURNING id"
        )
    ).scalar_one()
    building = conn.execute(
        text(
            "INSERT INTO building (name, footprint) VALUES ('Lib', "
            "ST_GeomFromText('POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))', 4326)) RETURNING id"
        )
    ).scalar_one()
    checkin = conn.execute(
        text(
            "INSERT INTO checkin (user_id, building_id, method, valid_during) "
            "VALUES (:u, :b, 'qr', tstzrange('2031-06-01', '2031-06-02')) RETURNING id"
        ),
        {"u": user_id, "b": building},
    ).scalar_one()
    return {
        "u": user_id,
        "team": team,
        "season": season,
        "building": building,
        "checkin": checkin,
    }


def _route(conn: Connection, refs: dict[str, object], started_at: datetime) -> str:
    segment_id = uuid.uuid4()
    conn.execute(INSERT_SEGMENT, {"id": segment_id, "started_at": started_at, **refs})
    table = conn.execute(
        text("SELECT tableoid::regclass::text FROM climb_segment WHERE id = :id"),
        {"id": segment_id},
    ).scalar_one()
    assert isinstance(table, str)
    return table


def test_row_goes_to_the_partition_of_its_month(conn: Connection, refs: dict[str, object]) -> None:
    ensure_partitions(conn, now=FAR)
    assert _route(conn, refs, FAR) == "climb_segment_203106"
    # Upper bound is exclusive: the last instant of June, then the first of July.
    assert _route(conn, refs, datetime(2031, 6, 30, 23, 59, 59, tzinfo=UTC)) == (
        "climb_segment_203106"
    )
    assert _route(conn, refs, datetime(2031, 7, 1, tzinfo=UTC)) == "climb_segment_203107"


def test_row_outside_every_partition_is_refused(conn: Connection, refs: dict[str, object]) -> None:
    # No default partition: this is why the service rejects such a started_at before the insert.
    with pytest.raises(DBAPIError, match="no partition of relation"):
        conn.execute(
            INSERT_SEGMENT,
            {"id": uuid.uuid4(), "started_at": datetime(2040, 1, 1, tzinfo=UTC), **refs},
        )


def test_cli_creates_partitions(clean: None) -> None:
    assert TEST_DB_URL
    env = {
        **os.environ,
        "FLOORWARS_ENV": "dev",
        "FLOORWARS_DATABASE_URL": TEST_DB_URL,
    }
    done = subprocess.run(
        [sys.executable, "-m", "app.segments.partitions"],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-500:]
    assert "climb_segment_" in done.stdout
