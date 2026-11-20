"""Game events written straight to the database, for the feed and the socket tests."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.segments.api_world import TSTZRANGE_SQL, World, utcnow

AT = datetime(2026, 11, 20, 9, 30, 0, 123456, tzinfo=UTC)


def add_flip(world: World, season_id: int | None = None, frm: str | None = None) -> int:
    """A ``building_flipped`` row (``frm`` to the other team); returns its id."""
    to = "ETC" if frm == "AC" else "AC"
    return _insert(
        world.client,
        "INSERT INTO game_event (kind, season_id, building_id, from_team, to_team, created_at) "
        "VALUES ('building_flipped', :s, :b, :f, :t, :at) RETURNING id",
        s=world.season_id if season_id is None else season_id,
        b=world.building_id,
        f=None if frm is None else world.team_ids[frm],
        t=world.team_ids[to],
        at=AT,
    )


def add_season_state(world: World) -> int:
    return _insert(
        world.client,
        "INSERT INTO game_event (kind, season_id, payload) VALUES ('season_state', :s, "
        "CAST(:p AS jsonb)) RETURNING id",
        s=world.season_id,
        p='{"paused": true, "ends_at": "2026-12-01T00:00:00+00:00"}',
    )


def other_season(client: TestClient) -> int:
    return _insert(
        client,
        f"INSERT INTO season (active_during) VALUES ({TSTZRANGE_SQL}) RETURNING id",  # noqa: S608
        lo=utcnow().replace(year=2020),
        hi=utcnow().replace(year=2021),
    )


def join(client: TestClient, user_id: uuid.UUID, season_id: int, team_id: int) -> None:
    _insert(
        client,
        "INSERT INTO team_membership (user_id, season_id, team_id) VALUES (:u, :s, :t) "
        "RETURNING season_id",
        u=user_id,
        s=season_id,
        t=team_id,
    )


def _insert(client: TestClient, sql: str, **params: Any) -> int:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        value = db.execute(text(sql), params).scalar_one()
        db.commit()
    assert isinstance(value, int)
    return value
