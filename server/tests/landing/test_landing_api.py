"""``POST /v1/landing-scans`` (W4-4) against Postgres and Valkey."""

import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app import leaderboards as lb
from app import qr_token
from app.auth.ratelimit import Decision
from app.config import Settings
from app.landing import service
from app.landing.schemas import LandingScanIn
from app.main import create_app
from app.segments import claim
from app.segments import service as segments_service
from app.segments.schemas import SegmentBatch
from app.valkey import ValkeyClient
from tests.checkins.conftest import KEY, KEY_HEX, insert_building, token_for
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import Climber, World, climb, make_world, scalar

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
P = "urn:floorwars:problem:"
MALFORMED = "fwl1.bad"


def sticker(building_id: int, key: bytes = KEY, nbf_off: int = -60, exp_off: int = 3600) -> str:
    now = int(time.time())
    return qr_token.sign(building_id, key, now + nbf_off, now + exp_off, landing=True)


def post_scan(user: Climber, **overrides: Any) -> Any:
    body = {"qr_token": sticker(user.building_id), "building_id": user.building_id, **overrides}
    return user.client.post("/v1/landing-scans", json=body, headers=user.headers)


def problem(response: Any, status: int, type_: str | None = None) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    if type_ is not None:
        assert response.json()["type"] == type_


@pytest.fixture
def world(make_app: Callable[..., TestClient]) -> World:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    return make_world(make_app(qr_hmac_key=KEY_HEX))


def test_route_matches_contract() -> None:
    paths = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"]
    contract = paths["/landing-scans"]["post"]
    served = create_app(Settings(env="dev", log_level="WARNING")).openapi()["paths"]
    post = served["/v1/landing-scans"]["post"]
    assert post["operationId"] == contract["operationId"] == "createLandingScan"
    assert set(post["responses"]) == set(contract["responses"])
    assert post["security"] == [{"bearerAuth": []}]


def test_scan_scores_once_and_matches_contract(world: World) -> None:
    user = world.climber()
    response = post_scan(user)
    assert response.status_code == 201, response.text
    body = response.json()
    schema = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["components"]["schemas"]
    shape = schema["LandingScan"]
    assert set(shape["required"]) <= set(body) <= set(shape["properties"])
    assert uuid.UUID(body["id"])
    assert body["building_id"] == user.building_id
    assert body["points"] == service.LANDING_SCAN_POINTS == 20
    assert set(body["flips"][0]) == set(schema["BuildingFlip"]["required"])

    # A retry within 10 minutes is a 429 and credits nothing.
    problem(post_scan(user), 429)
    assert scalar(world.client, "SELECT count(*) FROM landing_scan") == 1
    assert scalar(world.client, "SELECT points FROM team_building_score") == 20
    assert scalar(world.client, "SELECT steps FROM team_building_score") == 0
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert service.user_scan_points(db, user.user_id, world.season_id) == 20
        assert service.user_scan_points(db, uuid.uuid4(), world.season_id) == 0


def test_flip_writes_game_event_and_is_returned(world: World) -> None:
    user = world.climber("ETC")
    body = post_scan(user).json()
    assert body["flips"] == [
        {
            "building_id": user.building_id,
            "from_team": None,
            "to_team": "ETC",
            "at": body["flips"][0]["at"],
        }
    ]
    assert scalar(world.client, "SELECT count(*) FROM game_event") == 1
    assert scalar(world.client, "SELECT to_team FROM game_event") == world.team_ids["ETC"]
    assert scalar(world.client, "SELECT team_id FROM building_claim") == world.team_ids["ETC"]


def test_scan_points_count_in_the_owner_window(world: World) -> None:
    """60 steps of AC against three scans of ETC (60 points, reached later): AC keeps it, the
    fourth scan (80) flips it."""
    ac = world.climber("AC")
    ac.ok(climb(minutes_ago=30))
    etc = [world.climber("ETC") for _ in range(4)]
    for user in etc[:3]:
        assert post_scan(user).json()["flips"] == []
    flips = post_scan(etc[3]).json()["flips"]
    assert [(f["from_team"], f["to_team"]) for f in flips] == [("AC", "ETC")]
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        points = claim.rolling_points(db, world.season_id, world.building_id, datetime.now(UTC))
    assert [(p.code, p.points) for p in points] == [("ETC", 80), ("AC", 60)]


def test_entrance_code_is_not_a_sticker(world: World) -> None:
    user = world.climber()
    response = post_scan(user, qr_token=token_for(user.building_id))
    problem(response, 403, P + "sticker-invalid")


def test_sticker_is_refused_at_checkin(world: World) -> None:
    user = world.climber()
    body = {"method": "qr", "qr_token": sticker(user.building_id)}
    problem(world.client.post("/v1/checkins", json=body, headers=user.headers), 403)


def test_tampered_sticker(world: World) -> None:
    user = world.climber()
    good, other = sticker(user.building_id).split("."), sticker(user.building_id + 1).split(".")
    forged = ".".join([good[0], other[1], good[2]])
    problem(post_scan(user, qr_token=forged), 403, P + "sticker-invalid")


def test_wrong_building(world: World) -> None:
    user = world.climber()
    other = insert_building(world.client)
    response = post_scan(user, qr_token=sticker(other))
    problem(response, 403, P + "sticker-wrong-building")


@pytest.mark.parametrize(("nbf_off", "exp_off"), [(-7200, -60), (600, 3600)])
def test_sticker_outside_its_window(world: World, nbf_off: int, exp_off: int) -> None:
    user = world.climber()
    token = sticker(user.building_id, nbf_off=nbf_off, exp_off=exp_off)
    problem(post_scan(user, qr_token=token), 403, P + "sticker-expired")


def test_wrong_key(world: World) -> None:
    user = world.climber()
    token = sticker(user.building_id, key=bytes(range(1, 33)))
    problem(post_scan(user, qr_token=token), 403, P + "sticker-invalid")


def test_no_checkin(world: World) -> None:
    now = datetime.now(UTC)
    user = world.climber(valid_during=Range(now - timedelta(hours=3), now - timedelta(hours=1)))
    problem(post_scan(user), 403, P + "no-checkin")
    assert scalar(world.client, "SELECT count(*) FROM landing_scan") == 0
    # The refusal did not start the building's cooldown: a check-in later, the scan counts.
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text(
                "INSERT INTO checkin (user_id, building_id, method, valid_during) "
                "VALUES (:u, :b, 'qr', tstzrange(now(), now() + interval '1 hour'))"
            ),
            {"u": user.user_id, "b": user.building_id},
        )
        db.commit()
    assert post_scan(user).status_code == 201


def test_no_team(world: World) -> None:
    problem(post_scan(world.climber(team=None)), 403, P + "no-team")


def test_scanned_at_in_bounds_is_kept(world: World) -> None:
    user = world.climber()
    at = datetime.now(UTC) - timedelta(minutes=9)
    assert post_scan(user, scanned_at=at.isoformat()).status_code == 201
    assert scalar(world.client, "SELECT scanned_at FROM landing_scan") == at


@pytest.mark.parametrize("offset", [timedelta(minutes=-11), timedelta(minutes=6), None])
def test_scanned_at_out_of_bounds_uses_server_time(world: World, offset: timedelta | None) -> None:
    """The check-in starts now: only the server time is inside it, so 201 proves the swap."""
    now = datetime.now(UTC)
    user = world.climber(valid_during=Range(now - timedelta(seconds=5), now + timedelta(hours=1)))
    extra = {} if offset is None else {"scanned_at": (now + offset).isoformat()}
    assert post_scan(user, **extra).status_code == 201, extra
    stored = scalar(world.client, "SELECT scanned_at FROM landing_scan")
    assert abs(stored - now) < timedelta(seconds=30)


def test_scan_time_bounds() -> None:
    now = datetime(2026, 11, 20, 12, tzinfo=UTC)
    assert service.scan_time(now - timedelta(minutes=10), now) == now - timedelta(minutes=10)
    assert service.scan_time(now + timedelta(minutes=5), now) == now + timedelta(minutes=5)
    assert service.scan_time(now - timedelta(minutes=10, seconds=1), now) == now
    assert service.scan_time(now + timedelta(minutes=5, seconds=1), now) == now
    assert service.scan_time(None, now) == now


def test_building_limit_retry_after(world: World) -> None:
    user = world.climber()
    assert post_scan(user).status_code == 201
    response = post_scan(user)
    problem(response, 429)
    assert 590 <= int(response.headers["Retry-After"]) <= 600


def test_failure_after_the_cooldown_token_gives_it_back(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database error after the per-building token: nothing stored, the retry is not a 429."""
    user = world.climber()

    def broken(*args: Any) -> None:
        raise RuntimeError("database gone")

    monkeypatch.setattr(service.claim, "recompute_owner", broken)
    with pytest.raises(RuntimeError):
        post_scan(user)
    assert scalar(world.client, "SELECT count(*) FROM landing_scan") == 0
    monkeypatch.undo()
    assert post_scan(user).status_code == 201


def test_hourly_limit_counts_every_attempt(world: World) -> None:
    user = world.climber()
    for _ in range(service.SCANS_PER_HOUR):
        problem(post_scan(user, qr_token=MALFORMED), 403)
    response = post_scan(user)
    problem(response, 429)
    assert 1 <= int(response.headers["Retry-After"]) <= 600


def test_limiter_unavailable_is_503(make_app: Callable[..., TestClient]) -> None:
    world = make_world(make_app(qr_hmac_key=KEY_HEX, valkey_url=None))
    problem(post_scan(world.climber()), 503)


def test_key_missing_is_503(world: World, make_app: Callable[..., TestClient]) -> None:
    user = world.climber()
    user.client = make_app()
    problem(post_scan(user), 503)


@pytest.mark.parametrize(
    "body",
    [
        {"qr_token": "x", "building_id": 1, "extra": 1},
        {"qr_token": "x", "building_id": "1"},
        {"qr_token": "x", "building_id": 0},
        {"qr_token": "x", "building_id": 2147483648},
        {"qr_token": 1, "building_id": 1},
        {"qr_token": "x", "building_id": 1, "scanned_at": 1800000000},
        {"building_id": 1},
    ],
)
def test_bad_body_is_422(world: World, body: dict[str, Any]) -> None:
    user = world.climber()
    problem(world.client.post("/v1/landing-scans", json=body, headers=user.headers), 422)


def test_requires_token(world: World) -> None:
    response = world.client.post("/v1/landing-scans", json={"qr_token": "x", "building_id": 1})
    problem(response, 401)


def _boards(vk: ValkeyClient, season_id: int, building_id: int) -> list[Any]:
    keys = [lb.users_key(season_id), lb.teams_key(season_id)]
    keys.append(lb.building_key(season_id, building_id))
    return [sorted(lb.top(vk, key, 100) or []) for key in keys]


def test_rebuild_and_database_fallback_equal_incremental_boards(
    world: World, make_app: Callable[..., TestClient]
) -> None:
    vk: ValkeyClient = world.client.app.state.valkey  # type: ignore[attr-defined]
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert lb.rebuild(db, vk, world.season_id)  # built, so uploads update incrementally
    ac, etc = world.climber("AC"), world.climber("ETC")
    ac.ok(climb(minutes_ago=30))
    for user in (ac, etc):
        assert post_scan(user).status_code == 201
    incremental = _boards(vk, world.season_id, world.building_id)
    assert incremental[1] == sorted(
        [(str(world.team_ids["AC"]), 80), (str(world.team_ids["ETC"]), 20)]
    )

    vk.execute("DEL", lb.built_key(world.season_id))
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert lb.rebuild(db, vk, world.season_id)
    assert _boards(vk, world.season_id, world.building_id) == incremental

    without_valkey = make_app(valkey_url=None)
    for scope in ("individual", "team", "building"):
        params: dict[str, Any] = {"scope": scope, "season_id": world.season_id}
        if scope == "building":
            params["building_id"] = world.building_id
        live = world.client.get("/v1/leaderboards", params=params, headers=ac.headers)
        fallback = without_valkey.get("/v1/leaderboards", params=params, headers=ac.headers)
        assert live.status_code == fallback.status_code == 200, fallback.text
        assert live.json()["entries"] == fallback.json()["entries"], scope


class _Allow:
    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        return Decision(allowed=True, retry_after_s=0)

    def refund(self, name: str, subject: str, capacity: int, period_s: int) -> None:
        pass


def test_scan_and_segment_upload_in_parallel_leave_one_owner(world: World) -> None:
    """A scan (AC, 20) and a batch (ETC, 60) on one building at once, many rounds: the claim
    always equals a recompute from the stored rows, and the last event names the owner."""
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL, pool_size=4)
    errors: list[Exception] = []
    try:
        for _ in range(5):
            building = insert_building(world.client)
            world.building_id = building
            scanner, climber = world.climber("AC"), world.climber("ETC")
            barrier = threading.Barrier(2)
            req = LandingScanIn(qr_token=sticker(building), building_id=building)
            batch = SegmentBatch.model_validate(
                {
                    "device_id": str(climber.device_id),
                    "segments": [
                        {
                            "checkin_id": str(climber.checkin_id),
                            "building_id": building,
                            **climb(minutes_ago=5),
                        }
                    ],
                }
            )

            def do_scan(
                req: LandingScanIn = req, user: Climber = scanner, barrier: Any = barrier
            ) -> None:
                try:
                    with Session(engine) as db:
                        barrier.wait(5)
                        service.scan(
                            db, user.user_id, req, datetime.now(UTC), key=KEY, limiter=_Allow()
                        )
                except Exception as exc:
                    errors.append(exc)

            def do_upload(
                batch: SegmentBatch = batch, user: Climber = climber, barrier: Any = barrier
            ) -> None:
                try:
                    with Session(engine) as db:
                        barrier.wait(5)
                        segments_service.upload_batch(db, user.user_id, batch)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=do_scan), threading.Thread(target=do_upload)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
            assert not errors, errors[:1]
            with Session(engine) as db:
                now = datetime.now(UTC)
                owner = db.execute(
                    text("SELECT team_id FROM building_claim WHERE building_id = :b"),
                    {"b": building},
                ).scalar_one()
                last_event = db.execute(
                    text(
                        "SELECT to_team FROM game_event WHERE building_id = :b "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"b": building},
                ).scalar_one()
                points = claim.rolling_points(db, world.season_id, building, now)
            assert owner == last_event == points[0].team_id == world.team_ids["ETC"]
            assert [p.points for p in points] == [60, 20]
    finally:
        engine.dispose()


def test_prefix_swaps_are_refused_by_both_routes(world: World) -> None:
    """The prefix is not signed; the signed kind claim keeps the two codes apart."""
    user = world.climber()
    swapped = "fwq1." + sticker(user.building_id).removeprefix("fwl1.")
    body = {"method": "qr", "qr_token": swapped}
    problem(world.client.post("/v1/checkins", json=body, headers=user.headers), 403)
    entrance = "fwl1." + token_for(user.building_id).removeprefix("fwq1.")
    problem(post_scan(user, qr_token=entrance), 403, P + "sticker-invalid")
