"""A season, two teams, a building and checked-in users, for tests of ``POST /v1/segments``."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import Range

from tests.checkins.conftest import insert_building
from tests.helpers import auth_headers, insert_user, new_email

TSTZRANGE_SQL = "tstzrange(CAST(:lo AS timestamptz), CAST(:hi AS timestamptz))"


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ago(minutes: float) -> datetime:
    return utcnow() - timedelta(minutes=minutes)


def climb_at(when: datetime, **overrides: Any) -> dict[str, Any]:
    """``climb`` starting at ``when``."""
    return climb(started_at=when.isoformat(), **overrides)


def clock_hour(hours_ago: int = 1) -> datetime:
    """The start of a whole UTC hour in the past. Points count per clock hour, so a test summing
    steps must not depend on the minute it runs in. ``hours_ago=1`` is inside the default check-in
    of ``World.climber``."""
    return utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours_ago)


def climb(minutes_ago: float = 1.0, **overrides: Any) -> dict[str, Any]:
    """A verified climb: 60 steps, 12 m in 30 s. ``checkin_id`` and ``building_id`` get added by
    ``Climber.post``."""
    return {
        "id": str(uuid.uuid4()),
        "started_at": _ago(minutes_ago).isoformat(),
        "ascent_m": 12.0,
        "duration_s": 30.0,
        "vert_speed_mps": 0.4,
        "steps": 60,
        "stair_prob": 0.9,
        "classifier_version": "rules-1",
        **overrides,
    }


@dataclass
class Climber:
    client: TestClient
    user_id: uuid.UUID
    device_id: uuid.UUID
    checkin_id: uuid.UUID
    building_id: int
    headers: dict[str, str]

    def post(self, *items: dict[str, Any], key: str = "batch", **body: Any) -> Any:
        """Upload ``items``; sent as raw JSON so that NaN and huge numbers survive."""
        segments = [
            {"checkin_id": str(self.checkin_id), "building_id": self.building_id, **item}
            for item in items
        ]
        payload = {"device_id": str(self.device_id), "segments": segments, **body}
        return self.client.post(
            "/v1/segments",
            content=json.dumps(payload),
            headers={
                **self.headers,
                "Idempotency-Key": key,
                "Content-Type": "application/json",
            },
        )

    def ok(self, *items: dict[str, Any], **body: Any) -> dict[str, Any]:
        response = self.post(*items, **body)
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result


def scalar(client: TestClient, sql: str, **params: Any) -> Any:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return db.execute(text(sql), params).scalar()


@dataclass
class World:
    client: TestClient
    season_id: int
    team_ids: dict[str, int]
    building_id: int

    def climber(
        self,
        team: str | None = "AC",
        device_id: uuid.UUID | None = None,
        valid_during: Range[datetime] | None = None,
    ) -> Climber:
        """A user with a device, a team (``None``: no team) and an active check-in."""
        window = valid_during or Range(_ago(120), _ago(-60))
        with self.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            user_id = insert_user(db, new_email())
            device = device_id or uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO device (user_id, id, model, has_barometer) "
                    "VALUES (:u, :d, 'test', true)"
                ),
                {"u": user_id, "d": device},
            )
            if team is not None:
                db.execute(
                    text(
                        "INSERT INTO team_membership (user_id, season_id, team_id) "
                        "VALUES (:u, :s, :t)"
                    ),
                    {"u": user_id, "s": self.season_id, "t": self.team_ids[team]},
                )
            checkin_id = db.execute(
                text(
                    "INSERT INTO checkin (user_id, building_id, method, valid_during) "  # noqa: S608
                    f"VALUES (:u, :b, 'qr', {TSTZRANGE_SQL}) RETURNING id"
                ),
                {"u": user_id, "b": self.building_id, "lo": window.lower, "hi": window.upper},
            ).scalar_one()
            db.commit()
        return Climber(
            self.client,
            user_id,
            device,
            checkin_id,
            self.building_id,
            auth_headers(self.client.app, user_id),  # type: ignore[arg-type]
        )

    def second_device(self, user: Climber) -> str:
        """Register one more device for the user. No receipts match it yet."""
        device = uuid.uuid4()
        with self.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            db.execute(
                text(
                    "INSERT INTO device (user_id, id, model, has_barometer) "
                    "VALUES (:u, :d, 'test', true)"
                ),
                {"u": user.user_id, "d": device},
            )
            db.commit()
        return str(device)


def make_world(client: TestClient) -> World:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        season_id = db.execute(
            text(f"INSERT INTO season (active_during) VALUES ({TSTZRANGE_SQL}) RETURNING id"),  # noqa: S608
            {"lo": utcnow() - timedelta(days=30), "hi": utcnow() + timedelta(days=30)},
        ).scalar_one()
        teams = {
            code: db.execute(
                text("INSERT INTO team (code, color_hex) VALUES (:c, '#112233') RETURNING id"),
                {"c": code},
            ).scalar_one()
            for code in ("AC", "ETC")
        }
        db.commit()
    return World(client, season_id, teams, insert_building(client))
