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

# Real footprints, drawn by Ionut at geojson.io (WGS 84, lon lat). Names are the idempotency key.
# ``replaces`` is the name a placeholder row had before: such a row is renamed and updated in place,
# so the building keeps its id (printed QR codes stay valid).
AC_FOOTPRINT = (
    "POLYGON((21.2259069 45.7474217, 21.2262371 45.7474267, 21.2262385 45.7475219,"
    " 21.2264352 45.7475229, 21.2264366 45.7473556, 21.227551 45.7473674,"
    " 21.2275531 45.7472409, 21.2282673 45.7472435, 21.2282673 45.7471257,"
    " 21.2275174 45.7471141, 21.2275112 45.7470647, 21.2273175 45.7470618,"
    " 21.2273175 45.7471446, 21.2271237 45.7471461, 21.2271234 45.7471899,"
    " 21.2264402 45.7471827, 21.2262757 45.7471812, 21.226284 45.7470911,"
    " 21.2260653 45.7470911, 21.2260632 45.7472844, 21.2259174 45.7472902,"
    " 21.2259153 45.7474181, 21.2259069 45.7474217))"
)
# The drawn line ended a few centimetres past its start, which made the closed ring cross itself;
# the stray last vertex was dropped so the ring closes from the previous vertex.
MECANICA_FOOTPRINT = (
    "POLYGON((21.2267229 45.7465834, 21.2272669 45.7466039, 21.2272634 45.7466328,"
    " 21.2274741 45.7466449, 21.227519 45.7462219, 21.2273566 45.7462099,"
    " 21.2273532 45.7462689, 21.2269629 45.7462484, 21.2269629 45.7462171,"
    " 21.226868 45.7462147, 21.2268662 45.7462508, 21.2267626 45.746246,"
    " 21.2267229 45.7465834))"
)
OLD_PLACEHOLDER_A = "Placeholder A (UPT, replace with real footprint)"
OLD_PLACEHOLDER_B = "Placeholder B (UPT, replace with real footprint)"
BUILDINGS = [
    ("Facultatea de Automatica si Calculatoare", AC_FOOTPRINT, OLD_PLACEHOLDER_A),
    ("Facultatea de Mecanica", MECANICA_FOOTPRINT, OLD_PLACEHOLDER_B),
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
    for name, wkt, replaces in BUILDINGS:
        params = {"name": name, "wkt": wkt, "old": replaces}
        # A row with the real name only gets its footprint refreshed; a placeholder row is
        # renamed in place (same id); otherwise a new row is inserted.
        updated = conn.execute(
            text(
                "UPDATE building SET footprint = ST_GeomFromText(:wkt, 4326)"
                " WHERE name = CAST(:name AS text)"
            ),
            params,
        ).rowcount
        if not updated:
            updated = conn.execute(
                text(
                    "UPDATE building SET name = CAST(:name AS text),"
                    " footprint = ST_GeomFromText(:wkt, 4326)"
                    " WHERE name = CAST(:old AS text)"
                ),
                params,
            ).rowcount
        if not updated:
            conn.execute(
                text(
                    "INSERT INTO building (name, footprint)"
                    " VALUES (CAST(:name AS text), ST_GeomFromText(:wkt, 4326))"
                ),
                params,
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
