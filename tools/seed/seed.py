"""Idempotent seed for development and staging.

Creates two placeholder buildings near UPT (Timisoara), five teams and one active season on the
database in ``FLOORWARS_DATABASE_URL`` (or, if unset, the secret file
``/run/secrets/floorwars_database_url``, as mounted in the ``migrate`` container on the VM).
Running it twice changes nothing. It never creates users
or team memberships.

    python tools/seed/seed.py
"""

import math
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Connection, create_engine, text

METERS_PER_DEGREE_LAT = 111_320.0
HEX_RADIUS_M = 25.0

# (name, centre latitude, centre longitude). Names are the idempotency key.
BUILDINGS = [
    ("Placeholder A (UPT, replace with real footprint)", 45.7472, 21.2266),
    ("Placeholder B (UPT, replace with real footprint)", 45.7475, 21.2306),
]

TEAMS = [
    ("AC", "#1F77B4"),
    ("ETC", "#D62728"),
    ("MEC", "#2CA02C"),
    ("CHIM", "#FF7F0E"),
    ("CONSTR", "#9467BD"),
]

SEASON_DAYS = 14


def hexagon_wkt(lat: float, lon: float, radius_m: float = HEX_RADIUS_M) -> str:
    """Regular hexagon around a centre as a closed WKT POLYGON (lon lat order, 7 points)."""
    dlat = radius_m / METERS_PER_DEGREE_LAT
    dlon = radius_m / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    ring = [
        (
            lon + dlon * math.cos(math.radians(60 * i)),
            lat + dlat * math.sin(math.radians(60 * i)),
        )
        for i in range(6)
    ]
    ring.append(ring[0])
    return "POLYGON((" + ", ".join(f"{x:.7f} {y:.7f}" for x, y in ring) + "))"


def season_range(now: datetime) -> tuple[datetime, datetime]:
    """Monday 00:00 UTC of the current week, and 14 days after it."""
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, monday + timedelta(days=SEASON_DAYS)


def seed(conn: Connection, now: datetime | None = None) -> None:
    """Insert missing rows. Safe to call repeatedly."""
    now = now or datetime.now(UTC)
    for name, lat, lon in BUILDINGS:
        conn.execute(
            text(
                "INSERT INTO building (name, footprint) "
                "SELECT CAST(:name AS text), ST_GeomFromText(:wkt, 4326) "
                "WHERE NOT EXISTS (SELECT 1 FROM building WHERE name = CAST(:name AS text))"
            ),
            {"name": name, "wkt": hexagon_wkt(lat, lon)},
        )
    for code, color in TEAMS:
        conn.execute(
            text(
                "INSERT INTO team (code, color_hex) VALUES (:code, :color) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "color": color},
        )
    lo, hi = season_range(now)
    conn.execute(
        text(
            "INSERT INTO season (active_during) "
            "SELECT tstzrange(:lo, :hi) "
            "WHERE NOT EXISTS (SELECT 1 FROM season WHERE active_during && tstzrange(:lo, :hi))"
        ),
        {"lo": lo, "hi": hi},
    )


MOUNTED_URL_PATH = "/run/secrets/floorwars_database_url"


def database_url() -> str | None:
    """The database URL: the environment variable, else the mounted secret file (never echoed)."""
    url = os.environ.get("FLOORWARS_DATABASE_URL")
    if url:
        return url
    secret = Path(os.environ.get("FLOORWARS_DATABASE_URL_FILE", MOUNTED_URL_PATH))
    if secret.is_file():
        return secret.read_text(encoding="utf-8").strip() or None
    return None


def main() -> int:
    url = database_url()
    if not url:
        print(
            "error: set FLOORWARS_DATABASE_URL or mount the floorwars_database_url secret",
            file=sys.stderr,
        )
        return 1
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            seed(conn)
            counts = {
                table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
                for table in ("building", "team", "season")
            }
    finally:
        engine.dispose()
    print("seeded: " + ", ".join(f"{t}={n}" for t, n in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
