"""Committed test data for the read endpoints, written with plain SQL (no segment pipeline)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.segments.partitions import ensure_partitions

TEAMS = (("AC", "#112233"), ("ETC", "#445566"), ("MEC", "#778899"))
POLYGON = "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))"


@dataclass
class World:
    season_id: int
    team_ids: dict[str, int]
    building_ids: list[int]
    users: dict[str, uuid.UUID] = field(default_factory=dict)
    checkins: dict[tuple[str, int], uuid.UUID] = field(default_factory=dict)


def seed(client: TestClient, buildings: int = 2, active: bool = True) -> World:
    """Teams AC, ETC, MEC, one season, ``buildings`` buildings and one user per team."""
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        ensure_partitions(db.connection(), months_ahead=1)
        team_ids = {
            code: db.execute(
                text("INSERT INTO team (code, color_hex) VALUES (:c, :h) RETURNING id"),
                {"c": code, "h": color},
            ).scalar_one()
            for code, color in TEAMS
        }
        start, end = (-60, 60) if active else (-90, -60)
        season_id = db.execute(
            text(
                "INSERT INTO season (active_during) VALUES (tstzrange("
                "now() + make_interval(days => :a), now() + make_interval(days => :b))) "
                "RETURNING id"
            ),
            {"a": start, "b": end},
        ).scalar_one()
        building_ids = [
            db.execute(
                text(
                    "INSERT INTO building (name, footprint) "
                    "VALUES (:n, ST_GeomFromText(:w, 4326)) RETURNING id"
                ),
                {"n": f"B{i}", "w": POLYGON},
            ).scalar_one()
            for i in range(buildings)
        ]
        world = World(season_id, team_ids, building_ids)
        for code, team_id in team_ids.items():
            user_id = db.execute(
                text('INSERT INTO "user" (email, display_name) VALUES (:e, :n) RETURNING id'),
                {"e": f"{code.lower()}@student.upt.ro", "n": f"user {code}"},
            ).scalar_one()
            db.execute(
                text(
                    "INSERT INTO team_membership (user_id, season_id, team_id) VALUES (:u, :s, :t)"
                ),
                {"u": user_id, "s": season_id, "t": team_id},
            )
            world.users[code] = user_id
        db.commit()
    return world


def add_segment(
    db: Session,
    world: World,
    team: str,
    building_index: int,
    points: int,
    started_at: datetime | None = None,
    status: str = "verified",
) -> None:
    """One segment of ``team``'s user. Rejected segments carry ``points`` 0 by the CHECKs."""
    building_id = world.building_ids[building_index]
    user_id = world.users[team]
    checkin_key = (team, building_id)
    if checkin_key not in world.checkins:
        world.checkins[checkin_key] = db.execute(
            text(
                "INSERT INTO checkin (user_id, building_id, method, valid_during) VALUES "
                "(:u, :b, 'qr', tstzrange(now() + make_interval(days => :a), "
                "now() + make_interval(days => :a + 1))) "
                "RETURNING id"
            ),
            {"u": user_id, "b": building_id, "a": -2 * (building_index + 1)},
        ).scalar_one()
    device_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO device (user_id, id, model, has_barometer) VALUES (:u, :d, 'P', true)"),
        {"u": user_id, "d": device_id},
    )
    rejected = status == "rejected"
    db.execute(
        text(
            "INSERT INTO climb_segment (id, device_id, user_id, team_id, season_id, checkin_id, "
            "building_id, status, reject_reason, steps, steps_scored, points, ascent_m, "
            "duration_s, vert_speed_mps, stair_prob, classifier_version, started_at) VALUES "
            "(:id, :d, :u, :t, :s, :c, :b, :st, :r, 40, :ss, :p, 6, 30, 0.2, 0.9, 'rules-1', :at)"
        ),
        {
            "id": uuid.uuid4(),
            "d": device_id,
            "u": user_id,
            "t": world.team_ids[team],
            "s": world.season_id,
            "c": world.checkins[checkin_key],
            "b": building_id,
            "st": status,
            "r": "speed" if rejected else None,
            "ss": 0 if rejected else 40,
            "p": 0 if rejected else points,
            "at": started_at or datetime.now(UTC) - timedelta(minutes=5),
        },
    )
    db.commit()


def set_owner(db: Session, world: World, team: str, building_index: int) -> datetime:
    claimed_at = datetime.now(UTC) - timedelta(hours=1)
    db.execute(
        text(
            "INSERT INTO building_claim (season_id, building_id, team_id, claimed_at) "
            "VALUES (:s, :b, :t, :at) ON CONFLICT (season_id, building_id) DO UPDATE "
            "SET team_id = :t, claimed_at = :at"
        ),
        {
            "s": world.season_id,
            "b": world.building_ids[building_index],
            "t": world.team_ids[team],
            "at": claimed_at,
        },
    )
    db.commit()
    return claimed_at
