"""``GET /v1/me/export`` and ``DELETE /v1/me`` (W5-4), on the real upload pipeline."""

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import leaderboards as lb
from app.auth.ratelimit import hashed_subject
from app.config import Settings
from app.db.models import FraudFlag
from app.logging_config import build_formatter
from app.main import create_app
from app.realtime.hub import CLOSE_POLICY, Hub
from app.segments import repository
from app.segments.partitions import ensure_partitions
from app.valkey import ValkeyClient
from tests.helpers import TEST_VALKEY_URL
from tests.me.contract import assert_matches
from tests.segments.api_world import Climber, World, climb, make_world, scalar

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"


@dataclass
class Game:
    world: World
    victim: Climber  # AC, owns the building only through their own points
    rival: Climber  # ETC, fewer points than the victim
    vk: ValkeyClient


def _db(client: TestClient) -> Any:
    return cast(Any, client.app).state.sessionmaker()


@pytest.fixture
def game(make_app: Callable[..., TestClient]) -> Game:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    client = make_app()
    with _db(client) as db:
        ensure_partitions(db.connection())
        db.commit()
    world = make_world(client)
    rival, victim = world.climber("ETC"), world.climber("AC")
    rival.ok(climb(minutes_ago=5))
    victim.ok(climb(minutes_ago=3), climb(minutes_ago=1))
    now = datetime.now(UTC)
    with _db(client) as db:
        # A landing scan (counted in the score) and the rows the pipeline does not write.
        db.execute(
            text(
                "INSERT INTO landing_scan (user_id, building_id, season_id, team_id, checkin_id, "
                "points, scanned_at) VALUES (:u, :b, :s, :t, :c, 10, :at)"
            ),
            {
                "u": victim.user_id,
                "b": world.building_id,
                "s": world.season_id,
                "t": world.team_ids["AC"],
                "c": victim.checkin_id,
                "at": now - timedelta(minutes=2),
            },
        )
        repository.add_score(db, world.season_id, world.building_id, world.team_ids["AC"], 10, 0)
        repository.add_fraud_flag(db, uuid.uuid4(), now, victim.user_id, "device_burst")
        repository.add_fraud_flag(db, uuid.uuid4(), now, rival.user_id, "device_burst")
        for user in (victim, rival):
            db.execute(
                text(
                    "INSERT INTO refresh_token (user_id, token_hash, family_id, expires_at) "
                    "VALUES (:u, :h, gen_random_uuid(), now() + interval '1 day')"
                ),
                {"u": user.user_id, "h": uuid.uuid4().bytes},
            )
        # A rejected segment in last month's partition: the cascade must reach every partition.
        db.execute(
            text(
                "INSERT INTO climb_segment (id, device_id, user_id, team_id, season_id, "
                "checkin_id, building_id, status, reject_reason, steps, steps_scored, points, "
                "ascent_m, duration_s, vert_speed_mps, stair_prob, classifier_version, "
                "started_at) VALUES (gen_random_uuid(), :d, :u, :t, :s, :c, :b, 'rejected', "
                "'speed', 40, 0, 0, 6, 30, 0.2, 0.9, 'rules-1', :at)"
            ),
            {
                "d": victim.device_id,
                "u": victim.user_id,
                "t": world.team_ids["AC"],
                "s": world.season_id,
                "c": victim.checkin_id,
                "b": world.building_id,
                "at": (now.replace(day=1) - timedelta(days=3)),
            },
        )
        db.commit()
    vk = ValkeyClient(TEST_VALKEY_URL)
    with _db(client) as db:
        assert lb.rebuild(db, vk, world.season_id)  # built: the cleanup must undo live boards
    return Game(world, victim, rival, vk)


def _eventually(check: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + 5
    while not check():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def _owner(game: Game) -> str | None:
    return cast(
        str | None,
        scalar(
            game.world.client,
            "SELECT team.code FROM building_claim JOIN team ON team.id = building_claim.team_id "
            "WHERE season_id = :s AND building_id = :b",
            s=game.world.season_id,
            b=game.world.building_id,
        ),
    )


# --- routes against the contract -------------------------------------------------------------


def test_routes_match_contract() -> None:
    paths = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"]
    served = create_app(Settings(env="dev", log_level="WARNING")).openapi()["paths"]
    for path, method in (("/me/export", "get"), ("/me", "delete")):
        ours, theirs = served[f"/v1{path}"][method], paths[path][method]
        assert ours["operationId"] == theirs["operationId"]
        assert set(ours["responses"]) == set(theirs["responses"])
        assert ours["security"] == [{"bearerAuth": []}]


# --- export -----------------------------------------------------------------------------------


def test_export_shape_and_only_the_callers_rows(game: Game) -> None:
    client, victim, rival = game.world.client, game.victim, game.rival
    r = client.get("/v1/me/export", headers=victim.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert_matches(body, "MyDataExport")
    assert body["user"]["id"] == str(victim.user_id)
    counts = {k: len(v) for k, v in body.items() if isinstance(v, list)}
    assert counts == {
        "devices": 1,
        "memberships": 1,
        "checkins": 1,
        "segments": 3,
        "landing_scans": 1,
        "fraud_flags": scalar(
            client, "SELECT count(*) FROM fraud_flag WHERE user_id = :u", u=victim.user_id
        ),
    }
    assert set(body["checkins"][0]) >= {"building_id", "method", "valid_from", "valid_to"}
    assert {s["status"] for s in body["segments"]} == {"verified", "rejected"}
    dump = json.dumps(body)
    for secret in ("token_hash", "code_hash", "salt", "user_id"):
        assert secret not in dump
    for foreign in (rival.user_id, rival.device_id, rival.checkin_id):
        assert str(foreign) not in dump


def test_export_limit_401_and_503(game: Game, make_app: Callable[..., TestClient]) -> None:
    client = game.world.client
    assert client.get("/v1/me/export").status_code == 401
    for _ in range(3):
        assert client.get("/v1/me/export", headers=game.victim.headers).status_code == 200
    r = client.get("/v1/me/export", headers=game.victim.headers)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert client.get("/v1/me/export", headers=game.rival.headers).status_code == 200  # per user
    no_valkey = make_app(valkey_url=None)
    headers = {"Authorization": game.victim.headers["Authorization"]}
    assert no_valkey.get("/v1/me/export", headers=headers).status_code == 503


# --- delete -----------------------------------------------------------------------------------


def test_delete_removes_every_row_and_rebalances_the_game(game: Game) -> None:
    client, world, victim, vk = game.world.client, game.world, game.victim, game.vk
    assert _owner(game) == "AC"
    latest = scalar(client, "SELECT max(id) FROM game_event")
    rival_flags = scalar(
        client, "SELECT count(*) FROM fraud_flag WHERE user_id <> :u", u=victim.user_id
    )
    with (
        client.websocket_connect("/v1/ws", headers=victim.headers) as mine,
        client.websocket_connect(f"/v1/ws?since={latest}", headers=game.rival.headers) as theirs,
    ):
        hub = cast(Any, client.app).state.hub
        assert _eventually(lambda: hub.count(victim.user_id) == 1)
        assert client.delete("/v1/me", headers=victim.headers).status_code == 204
        # Checked before receiving, so a missing close fails instead of blocking forever.
        assert _eventually(lambda: hub.count(victim.user_id) == 0)
        assert _owner(game) == "ETC"  # before receiving: no flip would block the receive
        # The rival sees the flip; the victim's socket is closed with 1008.
        event = theirs.receive_json()
        assert (event["type"], event["from_team"], event["to_team"]) == (
            "building_flipped",
            "AC",
            "ETC",
        )
        with pytest.raises(WebSocketDisconnect) as closed:
            while True:
                mine.receive_json()
        assert closed.value.code == CLOSE_POLICY

    # Every table with a user_id (partitions included) holds nothing of the victim.
    with _db(client) as db:
        tables = db.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'user_id'"
            )
        ).scalars()
        left = {
            t: db.execute(
                text(f'SELECT count(*) FROM "{t}" WHERE user_id = :u'),  # noqa: S608
                {"u": victim.user_id},
            ).scalar_one()
            for t in tables
        }
    assert "climb_segment" in left and "landing_scan" in left
    assert set(left.values()) == {0}, left
    assert scalar(client, 'SELECT count(*) FROM "user" WHERE id = :u', u=victim.user_id) == 0
    assert scalar(client, "SELECT count(*) FROM fraud_flag") == rival_flags  # the rival's stay

    # team_building_score equals a fresh sum of what is left; the building flipped to ETC.
    with _db(client) as db:
        stored = {
            (r.team_id, r.points, r.steps)
            for r in db.execute(text("SELECT * FROM team_building_score"))
            if r.points or r.steps
        }
        fresh = {
            (r.team_id, r.points, r.steps)
            for r in db.execute(
                text(
                    "SELECT team_id, sum(points)::int AS points, sum(steps)::int AS steps "
                    "FROM climb_segment WHERE status = 'verified' GROUP BY team_id"
                )
            )
        }
    assert stored == fresh == {(world.team_ids["ETC"], 60, 60)}
    assert _owner(game) == "ETC"

    # Boards: the victim left at once, and the next read rebuilds the rest from the database.
    users_board = lb.top(vk, lb.users_key(world.season_id), 10) or []
    assert str(victim.user_id) not in dict(users_board)
    assert not lb.is_built(vk, world.season_id)
    r = client.get(
        "/v1/leaderboards",
        params={"season_id": world.season_id, "scope": "team"},
        headers=game.rival.headers,
    )
    assert r.status_code == 200, r.text
    assert lb.top(vk, lb.teams_key(world.season_id), 10) == [(str(world.team_ids["ETC"]), 60)]
    assert lb.top(vk, lb.users_key(world.season_id), 10) == [(str(game.rival.user_id), 60)]

    # The token is dead.
    assert client.delete("/v1/me", headers=victim.headers).status_code == 401
    assert client.get("/v1/me/export", headers=victim.headers).status_code == 401


def test_delete_401_without_token(client: TestClient) -> None:
    assert client.delete("/v1/me").status_code == 401


def test_delete_survives_a_dead_valkey(game: Game) -> None:
    """The follow-ups after the commit are best effort: the 204 does not depend on them."""

    class Dead:
        def execute(self, *args: object) -> object:
            raise RuntimeError("down")

    state = cast(Any, game.world.client.app).state
    state.valkey = Dead()
    assert game.world.client.delete("/v1/me", headers=game.victim.headers).status_code == 204


# --- hub ----------------------------------------------------------------------------------------


def test_hub_closes_only_that_users_sockets() -> None:
    hub = Hub(None)
    gone, other = uuid.uuid4(), uuid.uuid4()
    a, b = hub.register(gone, frozenset({1})), hub.register(gone, frozenset({1}))
    keep = hub.register(other, frozenset({1}))
    hub.close_user("not a uuid")
    hub.close_user(str(gone).encode())
    assert a.queue.get_nowait() == b.queue.get_nowait() == CLOSE_POLICY
    assert hub.count(gone) == 0
    assert keep.queue.empty() and hub.count(other) == 1


def test_export_has_the_flag_resolution_note(game: Game) -> None:
    """Turns on once ``fraud_flag.resolution_note`` (``0008_w5_admin``) is on this branch: the
    export writes every stored column, so the note needs no code here."""
    if "resolution_note" not in FraudFlag.__table__.columns:
        pytest.skip("TODO(W5-4): fraud_flag.resolution_note arrives with 0008_w5_admin")
    r = game.world.client.get("/v1/me/export", headers=game.victim.headers)
    assert set(r.json()["fraud_flags"][0]) >= {
        "rule",
        "created_at",
        "resolved_at",
        "resolution_note",
    }


def test_delete_logs_a_hash_and_counts_only(game: Game, caplog: pytest.LogCaptureFixture) -> None:
    victim = game.victim
    email = scalar(game.world.client, 'SELECT email FROM "user" WHERE id = :u', u=victim.user_id)
    caplog.set_level(logging.INFO, logger="app.me.gdpr")
    assert game.world.client.delete("/v1/me", headers=victim.headers).status_code == 204
    (record,) = [r for r in caplog.records if r.getMessage() == "account deleted"]
    assert cast(Any, record).user == hashed_subject(str(victim.user_id))
    assert cast(Any, record).rows["climb_segment"] == 3
    line = build_formatter().format(record)
    assert json.loads(line)["rows"]["landing_scan"] == 1
    assert email not in line and str(victim.user_id) not in line
