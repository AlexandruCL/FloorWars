"""``WS /v1/ws`` and the process hub (W4-3)."""

import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app import leaderboards
from app.api.v1 import ws
from app.auth.tokens import AccessTokens
from app.segments.models import Flip
from app.valkey import ValkeyClient
from tests.events.helpers import AT, add_flip, join, other_season
from tests.events.test_feed import assert_ws_event
from tests.helpers import TEST_JWT_KEY, TEST_VALKEY_URL, auth_headers
from tests.segments.api_world import Climber, World, climb, make_world

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")


@pytest.fixture
def world(make_app: Callable[..., TestClient]) -> World:
    return make_world(make_app())


@pytest.fixture
def vk() -> Iterator[ValkeyClient]:
    assert TEST_VALKEY_URL
    client = ValkeyClient(TEST_VALKEY_URL)
    yield client
    client.close()


def _state(client: TestClient) -> Any:
    return cast(Any, client.app).state


def live_flip(world: World, vk: ValkeyClient, season_id: int | None = None) -> int:
    """Commit a flip row, then publish it as the claim path does; returns its id."""
    season = world.season_id if season_id is None else season_id
    event_id = add_flip(world, season_id=season)
    _publish(world, vk, event_id, season)
    return event_id


def _publish(world: World, vk: ValkeyClient, event_id: int, season_id: int) -> None:
    flip = Flip(world.building_id, season_id, None, world.team_ids["AC"], None, "AC", AT, event_id)
    leaderboards.publish_flip(vk, flip)


def _ids(socket: Any, n: int) -> list[int]:
    out = []
    for _ in range(n):
        event = socket.receive_json()
        assert_ws_event(event)  # never an internal season_id
        out.append(event["event_id"])
    return out


def _deny(client: TestClient, url: str, headers: dict[str, str] | None = None) -> Any:
    with (
        pytest.raises(WebSocketDenialResponse) as denied,
        client.websocket_connect(url, headers=headers or {}),
    ):
        pass
    return denied.value


def test_401_on_the_upgrade(world: World) -> None:
    user = world.climber("AC")
    expired = AccessTokens(
        bytes.fromhex(TEST_JWT_KEY), "floorwars-api", 900, clock=lambda: time.time() - 901
    ).issue(user.user_id)
    wrong_key = AccessTokens(bytes.fromhex("22" * 32), "floorwars-api", 900).issue(user.user_id)
    gone = auth_headers(cast(Any, world.client.app), uuid.uuid4())  # valid token, no such user
    cases: list[tuple[str, dict[str, str] | None]] = [
        ("/v1/ws", None),
        ("/v1/ws", {"Authorization": f"Bearer {expired}"}),
        (f"/v1/ws?access_token={wrong_key}", None),
        ("/v1/ws?access_token=junk", None),
        ("/v1/ws", gone),
    ]
    for url, headers in cases:
        denied = _deny(world.client, url, headers)
        assert denied.status_code == 401, url
        assert denied.headers["content-type"] == "application/problem+json"
        assert denied.json()["status"] == 401


def test_bearer_and_query_token_both_accepted(world: World) -> None:
    user = world.climber("AC")
    first = add_flip(world)
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        assert _ids(socket, 1) == [first]
    token = user.headers["Authorization"].removeprefix("Bearer ")
    with world.client.websocket_connect(f"/v1/ws?since=0&access_token={token}") as socket:
        assert _ids(socket, 1) == [first]


def test_replay_from_since_then_live(world: World, vk: ValkeyClient) -> None:
    user = world.climber("AC")
    ids = [add_flip(world) for _ in range(3)]
    with world.client.websocket_connect(f"/v1/ws?since={ids[0]}", headers=user.headers) as s:
        assert _ids(s, 2) == ids[1:]
        live = live_flip(world, vk)
        event = s.receive_json()
        assert event["event_id"] == live
        assert "season_id" not in event


def test_replay_pages_through_more_than_one_page(world: World) -> None:
    user = world.climber("AC")
    with _state(world.client).sessionmaker() as db:
        ids = list(
            db.execute(
                text(
                    "INSERT INTO game_event (kind, season_id, building_id, to_team) "
                    "SELECT 'building_flipped', :s, :b, :t FROM generate_series(1, :n) "
                    "RETURNING id"
                ),
                {"s": world.season_id, "b": world.building_id, "t": world.team_ids["AC"]}
                | {"n": ws.MAX_LIMIT + 2},
            ).scalars()
        )
        db.commit()
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        assert _ids(socket, len(ids)) == ids


def test_no_gap_and_no_duplicate_at_the_replay_live_edge(
    world: World, vk: ValkeyClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flip committed (and published) just before the replay query is sent once; one committed
    just after it still arrives live. A last live flip marks the end of the stream."""
    user = world.climber("AC")
    real_page = ws._page
    edge: list[int] = []

    def page(factory: Any, user_id: uuid.UUID, since: int) -> Any:
        if edge:
            return real_page(factory, user_id, since)
        edge.append(live_flip(world, vk))  # in the replay and published live
        result = real_page(factory, user_id, since)
        edge.append(live_flip(world, vk))  # after the query: live only
        time.sleep(0.3)  # let the hub dispatch it while the replay is still running
        return result

    monkeypatch.setattr(ws, "_page", page)
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        assert _ids(socket, 1) == edge[:1]
        last = live_flip(world, vk)
        # One at a time, so a lost or repeated event fails here instead of blocking.
        assert _ids(socket, 1) == [edge[1]]
        assert _ids(socket, 1) == [last]


def test_a_lower_id_committed_after_the_replay_is_delivered(
    world: World, vk: ValkeyClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids are assigned before commit: #9 commits after the replay sent #10. Live #9 is delivered
    once; a live repeat of the replayed #10 is dropped."""
    user = world.climber("AC")
    real_page = ws._page
    ids: dict[str, int] = {}

    def page(factory: Any, user_id: uuid.UUID, since: int) -> Any:
        if ids:
            return real_page(factory, user_id, since)
        with _state(world.client).sessionmaker() as late:
            ids["late"] = late.execute(
                text(
                    "INSERT INTO game_event (kind, season_id, building_id, to_team) "
                    "VALUES ('building_flipped', :s, :b, :t) RETURNING id"
                ),
                {"s": world.season_id, "b": world.building_id, "t": world.team_ids["AC"]},
            ).scalar_one()  # not committed yet: invisible to the replay
            ids["replayed"] = add_flip(world)
            result = real_page(factory, user_id, since)
            late.commit()
        _publish(world, vk, ids["late"], world.season_id)
        _publish(world, vk, ids["replayed"], world.season_id)
        time.sleep(0.3)  # let the hub dispatch both while the replay is still running
        return result

    monkeypatch.setattr(ws, "_page", page)
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        assert _ids(socket, 1) == [ids["replayed"]]
        assert ids["late"] < ids["replayed"]
        last = live_flip(world, vk)  # sentinel: a lost #9 fails here instead of blocking
        assert _ids(socket, 1) == [ids["late"]]
        assert _ids(socket, 1) == [last]


def test_since_above_every_id_waits_for_a_live_event(world: World, vk: ValkeyClient) -> None:
    user = world.climber("AC")
    latest = add_flip(world)
    with world.client.websocket_connect(f"/v1/ws?since={latest}", headers=user.headers) as s:
        live = live_flip(world, vk)
        assert _ids(s, 1) == [live]


def test_live_events_follow_the_feed_visibility(world: World, vk: ValkeyClient) -> None:
    user = world.climber("AC")
    old = other_season(world.client)
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        live_flip(world, vk, season_id=old)  # a season the user has not joined: never sent
        visible = live_flip(world, vk)
        assert _ids(socket, 1) == [visible]
    join(world.client, user.user_id, old, world.team_ids["AC"])  # seen after a reconnect
    with world.client.websocket_connect(f"/v1/ws?since={visible}", headers=user.headers) as s:
        hidden_before = live_flip(world, vk, season_id=old)
        assert _ids(s, 1) == [hidden_before]


def test_a_flip_on_one_replica_reaches_a_socket_on_the_other(
    make_app: Callable[..., TestClient],
) -> None:
    """Two apps (two hubs) on one Valkey: a real upload on the first, the socket on the second."""
    world = make_world(make_app())
    other = make_app()
    climber = world.climber("AC")
    watcher = world.climber("ETC")
    headers = auth_headers(cast(Any, other.app), watcher.user_id)
    with other.websocket_connect("/v1/ws", headers=headers) as socket:
        climber.ok(climb())
        event = socket.receive_json()
    assert event["type"] == "building_flipped"
    assert (event["from_team"], event["to_team"]) == (None, "AC")
    assert set(event) == {"type", "event_id", "building_id", "from_team", "to_team", "at"}


def test_a_fourth_socket_closes_the_oldest_with_1008(world: World, vk: ValkeyClient) -> None:
    user = world.climber("AC")
    hub = _state(world.client).hub
    connect = world.client.websocket_connect
    with (
        connect("/v1/ws", headers=user.headers) as first,
        connect("/v1/ws", headers=user.headers),
        connect("/v1/ws", headers=user.headers),
    ):
        assert hub.count(user.user_id) == 3
        with connect("/v1/ws", headers=user.headers) as fourth:
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 1008
            assert hub.count(user.user_id) == 3
            live = live_flip(world, vk)
            assert _ids(fourth, 1) == [live]


def test_no_database_connection_is_held_in_the_live_phase(world: World, vk: ValkeyClient) -> None:
    user = world.climber("AC")
    first = add_flip(world)
    pool = _state(world.client).sessionmaker.kw["bind"].pool
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        assert _ids(socket, 1) == [first]
        live = live_flip(world, vk)
        assert _ids(socket, 1) == [live]
        assert pool.checkedout() == 0


def test_a_closed_socket_leaves_the_hub(world: World, vk: ValkeyClient) -> None:
    user: Climber = world.climber("AC")
    hub = _state(world.client).hub
    with world.client.websocket_connect("/v1/ws", headers=user.headers) as socket:
        socket.send_text("ignored")
        live = live_flip(world, vk)
        assert _ids(socket, 1) == [live]
    for _ in range(50):
        if hub.count(user.user_id) == 0:
            break
        time.sleep(0.02)
    assert hub.count(user.user_id) == 0


def test_bad_since_is_refused_before_accept(world: World) -> None:
    user = world.climber("AC")
    for since in ("-1", "x", str(2**63)):
        denied = _deny(world.client, f"/v1/ws?since={since}", user.headers)
        assert denied.status_code == 422
