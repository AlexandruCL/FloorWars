# ruff: noqa: S101
"""Seed tests. Database tests need FLOORWARS_TEST_DATABASE_URL (migrated, throwaway database)."""

import math
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import seed
from sqlalchemy import Connection, create_engine, text

TEST_DB_URL = os.environ.get("FLOORWARS_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_DB_URL, reason="FLOORWARS_TEST_DATABASE_URL not set")

TABLES = ("building", "team", "season", '"user"', "team_membership")


@pytest.fixture
def conn() -> Iterator[Connection]:
    """A connection whose outer transaction is always rolled back."""
    assert TEST_DB_URL is not None
    engine = create_engine(TEST_DB_URL)
    with engine.connect() as connection:
        tx = connection.begin()
        try:
            yield connection
        finally:
            tx.rollback()
    engine.dispose()


def _counts(conn: Connection) -> dict[str, int]:
    return {
        t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()  # noqa: S608
        for t in TABLES
    }


def test_hexagon_wkt_is_closed_with_seven_points() -> None:
    wkt = seed.hexagon_wkt(45.7472, 21.2266)
    points = re.findall(r"(-?\d+\.\d+) (-?\d+\.\d+)", wkt)
    assert len(points) == 7
    assert points[0] == points[-1]


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + (
        math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def test_hexagon_vertices_are_25_m_from_the_centre() -> None:
    for lat, lon in [(45.7472, 21.2266), (45.7475, 21.2306)]:
        wkt = seed.hexagon_wkt(lat, lon)
        points = [(float(x), float(y)) for x, y in re.findall(r"(-?\d+\.\d+) (-?\d+\.\d+)", wkt)]
        assert len(points) == 7
        for x, y in points[:6]:
            assert abs(_haversine_m(lat, lon, y, x) - 25.0) < 0.5


def test_season_range_starts_monday() -> None:
    lo, hi = seed.season_range(datetime(2026, 11, 4, 15, 30, tzinfo=UTC))  # a Wednesday
    assert lo == datetime(2026, 11, 2, tzinfo=UTC)
    assert (hi - lo).days == 14


@needs_db
def test_seed_twice_same_counts(conn: Connection) -> None:
    seed.seed(conn)
    first = _counts(conn)
    seed.seed(conn)
    assert _counts(conn) == first
    assert first['"user"'] == 0
    assert first["team_membership"] == 0


@needs_db
def test_seeded_rows(conn: Connection) -> None:
    seed.seed(conn)
    names = [name for name, _, _ in seed.BUILDINGS]
    expected_points = {"Facultatea de Automatica si Calculatoare": 23, "Facultatea de Mecanica": 13}
    rows = conn.execute(
        text(
            "SELECT name, ST_IsValid(footprint), ST_NPoints(footprint),"
            " ST_IsClosed(ST_ExteriorRing(footprint)), ST_SRID(footprint)"
            " FROM building WHERE name = ANY(:names)"
        ),
        {"names": names},
    ).all()
    assert len(rows) == 2
    for name, valid, npoints, closed, srid in rows:
        assert (valid, npoints, closed, srid) == (True, expected_points[name], True, 4326)
    colors = (
        conn.execute(
            text("SELECT color_hex FROM team WHERE code = ANY(:codes)"),
            {"codes": [code for code, _ in seed.TEAMS]},
        )
        .scalars()
        .all()
    )
    assert len(colors) == 5
    assert len(set(colors)) == 5


@needs_db
def test_real_footprints_are_sensible_sizes(conn: Connection) -> None:
    seed.seed(conn)
    areas = dict(
        conn.execute(
            text("SELECT name, ST_Area(footprint::geography) FROM building WHERE name = ANY(:n)"),
            {"n": [name for name, _, _ in seed.BUILDINGS]},
        ).all()
    )
    assert 1000 < areas["Facultatea de Automatica si Calculatoare"] < 10000
    assert 1000 < areas["Facultatea de Mecanica"] < 10000


@needs_db
def test_placeholder_rows_are_renamed_in_place_keeping_their_id(conn: Connection) -> None:
    name, _, old = seed.BUILDINGS[0]
    ids = [
        conn.execute(
            text(
                "INSERT INTO building (name, footprint) VALUES (:n,"
                " ST_GeomFromText(:w, 4326)) RETURNING id"
            ),
            {"n": n, "w": seed.hexagon_wkt(45.7472, 21.2266 + i * 0.01)},
        ).scalar_one()
        for i, n in enumerate([old, seed.OLD_PLACEHOLDER_B])
    ]
    seed.seed(conn)
    seed.seed(conn)
    row = conn.execute(text("SELECT name FROM building WHERE id = :i"), {"i": ids[0]}).scalar_one()
    assert row == name
    assert conn.execute(text("SELECT count(*) FROM building")).scalar_one() == 2


@needs_db
def test_season_active_now(conn: Connection) -> None:
    seed.seed(conn)
    active = conn.execute(
        text("SELECT count(*) FROM season WHERE active_during @> now()")
    ).scalar_one()
    assert active == 1


def test_database_url_prefers_env_then_secret_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: "os.PathLike[str]"
) -> None:
    secret = os.path.join(tmp_path, "floorwars_database_url")
    with open(secret, "w", encoding="utf-8") as fh:
        fh.write("postgresql+psycopg://from-file" + chr(10))
    monkeypatch.setenv("FLOORWARS_DATABASE_URL_FILE", secret)
    monkeypatch.setenv("FLOORWARS_DATABASE_URL", "postgresql+psycopg://from-env")
    assert seed.database_url() == "postgresql+psycopg://from-env"
    monkeypatch.delenv("FLOORWARS_DATABASE_URL")
    assert seed.database_url() == "postgresql+psycopg://from-file"
    monkeypatch.setenv("FLOORWARS_DATABASE_URL_FILE", os.path.join(tmp_path, "missing"))
    assert seed.database_url() is None
