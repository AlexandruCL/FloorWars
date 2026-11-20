"""``GET /v1/me/events`` and the seam ``app.events.feed`` (W4-2)."""

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import leaderboards
from app.config import Settings
from app.db.models import GameEvent, Team
from app.events.feed import event_json
from app.main import create_app
from tests.events.helpers import AT, add_flip, add_season_state, join, other_season
from tests.helpers import TEST_VALKEY_URL
from tests.segments.api_world import Climber, World, climb, make_world

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"


@cache
def _schemas() -> dict[str, Any]:
    schemas: dict[str, Any] = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["components"][
        "schemas"
    ]
    return schemas


def assert_ws_event(item: dict[str, Any]) -> None:
    """Exactly the contract's fields for the event's type (no ``season_id``, nothing extra)."""
    schemas = _schemas()
    if item["type"] == "building_flipped":
        expected = {"type", "event_id", *schemas["BuildingFlip"]["required"]}
        assert isinstance(item["building_id"], int)
        assert item["from_team"] is None or isinstance(item["from_team"], str)
        assert isinstance(item["to_team"], str)
        assert isinstance(item["at"], str)
    else:
        assert item["type"] == "season_state"
        expected = set(schemas["SeasonStateEvent"]["required"])
        assert isinstance(item["paused"], bool)
    assert set(item) == expected
    assert isinstance(item["event_id"], int)
    assert item["event_id"] >= 1


@pytest.fixture
def world(make_app: Callable[..., TestClient]) -> World:
    return make_world(make_app())


def _feed(user: Climber, **params: Any) -> Any:
    response = user.client.get("/v1/me/events", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_route_matches_contract() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"]["/me/events"]["get"]
    served = create_app(Settings(env="dev", log_level="WARNING")).openapi()
    actual = served["paths"]["/v1/me/events"]["get"]
    assert actual["operationId"] == contract["operationId"]
    assert set(actual["responses"]) == set(contract["responses"])
    page = served["components"]["schemas"]["GameEventPageOut"]
    assert set(page["properties"]) == set(_schemas()["GameEventPage"]["properties"])


def test_ascending_after_since(world: World) -> None:
    user = world.climber("AC")
    ids = [add_flip(world), add_flip(world, frm="AC"), add_flip(world, frm="ETC")]
    body = _feed(user, since=ids[0])
    assert [e["event_id"] for e in body["items"]] == ids[1:]  # since itself is excluded
    assert body["last_event_id"] == ids[2]
    assert body["has_more"] is False
    assert body["items"][0] == {
        "type": "building_flipped",
        "event_id": ids[1],
        "building_id": world.building_id,
        "from_team": "AC",
        "to_team": "ETC",
        "at": AT.isoformat(),
    }
    for item in _feed(user)["items"]:
        assert_ws_event(item)


def test_limit_and_has_more_at_the_boundary(world: World) -> None:
    user = world.climber("ETC")
    ids = [add_flip(world) for _ in range(3)]
    first = _feed(user, limit=2)
    assert [e["event_id"] for e in first["items"]] == ids[:2]
    assert (first["last_event_id"], first["has_more"]) == (ids[1], True)
    exact = _feed(user, limit=3)
    assert (len(exact["items"]), exact["has_more"]) == (3, False)
    rest = _feed(user, since=first["last_event_id"], limit=2)
    assert [e["event_id"] for e in rest["items"]] == ids[2:]
    assert rest["has_more"] is False


def test_empty_page_keeps_since(world: World) -> None:
    user = world.climber("AC")
    assert _feed(user) == {"items": [], "last_event_id": 0, "has_more": False}
    add_flip(world)
    assert _feed(user, since=999) == {"items": [], "last_event_id": 999, "has_more": False}


def test_events_of_every_joined_season_and_no_other(world: World) -> None:
    user = world.climber("AC")
    outsider = world.climber(None)  # joined no season
    old = other_season(world.client)
    hidden = add_flip(world, season_id=old)  # a season the user has not joined
    visible = add_flip(world, frm=None)  # not about the user's team's loss: still visible
    state = add_season_state(world)
    assert [e["event_id"] for e in _feed(user)["items"]] == [visible, state]
    assert _feed(outsider)["items"] == []
    join(world.client, user.user_id, old, world.team_ids["ETC"])
    assert [e["event_id"] for e in _feed(user)["items"]] == [hidden, visible, state]
    season_state = _feed(user, since=visible)["items"][0]
    assert_ws_event(season_state)
    assert season_state["paused"] is True


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_event_json_equals_the_published_flip(world: World) -> None:
    """A real flip through the claim path: the stored row gives the published event, byte for
    byte (the published text is ``flip_message`` plus the internal ``season_id``)."""
    published: list[str] = []
    real = cast(Any, world.client.app).state.valkey

    class Recorder:
        def execute(self, *args: Any) -> Any:
            if args[0] == "PUBLISH":
                assert args[1] == leaderboards.EVENTS_CHANNEL
                published.append(str(args[2]))
            return real.execute(*args)

    cast(Any, world.client.app).state.valkey = Recorder()
    user = world.climber("AC")
    user.ok(climb())
    assert len(published) == 1
    with cast(Any, world.client.app).state.sessionmaker() as db:
        row = db.execute(select(GameEvent)).scalar_one()
        codes = dict(db.execute(select(Team.id, Team.code)).all())
        stored = json.dumps(event_json(row, codes), separators=(",", ":"))
    tail = f',"season_id":{world.season_id}}}'
    assert published[0].endswith(tail)
    assert stored == published[0][: -len(tail)] + "}"
    assert _feed(user)["items"] == [json.loads(stored)]


def test_401_without_a_valid_token(world: World) -> None:
    assert world.client.get("/v1/me/events").status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert world.client.get("/v1/me/events", headers=bad).status_code == 401


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"since": -1}, {"since": 2**63}, {"since": "x"}],
)
def test_422_out_of_range(world: World, params: dict[str, Any]) -> None:
    user = world.climber("AC")
    response = user.client.get("/v1/me/events", params=params, headers=user.headers)
    assert response.status_code == 422
