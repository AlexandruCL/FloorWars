"""``GET /v1/leaderboards``: the three scopes, the database fallback, the lazy rebuild."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app import leaderboards as lb
from app.valkey import ValkeyClient
from tests.helpers import TEST_VALKEY_URL, auth_headers
from tests.read.seed import World, add_segment, seed


@pytest.fixture
def valkey_client(client: TestClient) -> ValkeyClient:
    """The app's own Valkey client (``app.state.valkey``, closed with the app)."""
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    vk: ValkeyClient = client.app.state.valkey  # type: ignore[attr-defined]
    return vk


@pytest.fixture
def rebuilds(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The seasons rebuilt so far. The real rebuild still runs."""
    calls: list[int] = []
    real = lb.rebuild

    def spy(db: Session, vk: lb.Commands, season_id: int) -> None:
        calls.append(season_id)
        real(db, vk, season_id)

    monkeypatch.setattr(lb, "rebuild", spy)
    return calls


def _populate(client: TestClient) -> World:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "ETC", 0, 100)
        add_segment(db, world, "ETC", 1, 50)
        add_segment(db, world, "AC", 0, 120)
        add_segment(db, world, "MEC", 1, 10)
        add_segment(db, world, "MEC", 1, 0, status="rejected")
    return world


def _board(client: TestClient, world: World, **params: object) -> Response:
    headers = auth_headers(client.app, world.users["AC"])
    return client.get("/v1/leaderboards", params=params, headers=headers)  # type: ignore[arg-type]


def _rows(response: Response) -> list[tuple[int, str, int]]:
    assert response.status_code == 200, response.text
    return [(e["rank"], e["name"], e["points"]) for e in response.json()["entries"]]


def test_team_board_from_database_without_valkey(make_app: Callable[..., TestClient]) -> None:
    client = make_app(valkey_url=None)
    assert client.app.state.valkey is None  # type: ignore[attr-defined]
    world = _populate(client)
    response = _board(client, world, scope="team")
    assert response.json()["season_id"] == world.season_id
    assert response.json()["building_id"] is None
    assert _rows(response) == [(1, "ETC", 150), (2, "AC", 120), (3, "MEC", 10)]
    assert response.json()["entries"][0]["id"] == "ETC"


def test_individual_board_names_and_ids(client: TestClient) -> None:
    world = _populate(client)
    response = _board(client, world, scope="individual", limit=2)
    assert _rows(response) == [(1, "user ETC", 150), (2, "user AC", 120)]
    assert response.json()["entries"][0]["id"] == str(world.users["ETC"])


def test_building_board_ranks_teams_in_that_building(client: TestClient) -> None:
    world = _populate(client)
    response = _board(client, world, scope="building", building_id=world.building_ids[0])
    assert response.json()["building_id"] == world.building_ids[0]
    assert _rows(response) == [(1, "AC", 120), (2, "ETC", 100)]


def test_building_board_requires_building_id(client: TestClient) -> None:
    world = _populate(client)
    assert _board(client, world, scope="building").status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"scope": "x"},
        {"scope": "team", "limit": 101},
        {"scope": "team", "season_id": 2147483648},
        {"scope": "team", "building_id": 2147483648},
        {"scope": "building", "building_id": 2147483648},
    ],
)
def test_bad_query_is_422(client: TestClient, params: dict[str, object]) -> None:
    world = seed(client)
    assert _board(client, world, **params).status_code == 422


@pytest.mark.parametrize(
    ("params", "problem"),
    [
        ({"scope": "team", "season_id": 2147483647}, "season-not-found"),
        ({"scope": "building", "building_id": 2147483647}, "building-not-found"),
    ],
)
def test_ids_at_the_int4_bound_are_valid_queries(
    client: TestClient, params: dict[str, object], problem: str
) -> None:
    world = seed(client)
    response = _board(client, world, **params)
    assert response.status_code == 404
    assert response.json()["type"].endswith(problem)


def test_building_id_is_ignored_for_other_scopes(client: TestClient) -> None:
    world = _populate(client)
    response = _board(client, world, scope="team", building_id=world.building_ids[0])
    assert response.json()["building_id"] is None
    assert _rows(response)[0] == (1, "ETC", 150)


def test_building_id_of_no_building_is_ignored_for_other_scopes(client: TestClient) -> None:
    world = _populate(client)
    assert _board(client, world, scope="team", building_id=9999).status_code == 200


@pytest.mark.parametrize("valkey_url", [TEST_VALKEY_URL, None])
def test_unknown_season_is_404(make_app: Callable[..., TestClient], valkey_url: str | None) -> None:
    client = make_app(valkey_url=valkey_url)
    world = _populate(client)
    response = _board(client, world, scope="team", season_id=world.season_id + 100)
    assert response.status_code == 404
    assert response.json()["type"] == "urn:floorwars:problem:season-not-found"


@pytest.mark.parametrize("valkey_url", [TEST_VALKEY_URL, None])
def test_unknown_building_is_404(
    make_app: Callable[..., TestClient], valkey_url: str | None
) -> None:
    client = make_app(valkey_url=valkey_url)
    world = _populate(client)
    response = _board(client, world, scope="building", building_id=9999)
    assert response.status_code == 404
    assert response.json()["type"] == "urn:floorwars:problem:building-not-found"


def test_explicit_season_without_data_is_empty(client: TestClient) -> None:
    world = seed(client)
    response = _board(client, world, scope="team", season_id=world.season_id)
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_no_active_season_is_404(client: TestClient) -> None:
    world = seed(client, active=False)
    assert _board(client, world, scope="team").status_code == 404


def test_requires_token(client: TestClient) -> None:
    assert client.get("/v1/leaderboards", params={"scope": "team"}).status_code == 401


def test_missing_keys_are_rebuilt_from_the_database(
    client: TestClient, valkey_client: ValkeyClient
) -> None:
    world = _populate(client)
    assert valkey_client.execute("EXISTS", lb.teams_key(world.season_id)) == 0
    assert _rows(_board(client, world, scope="team")) == [
        (1, "ETC", 150),
        (2, "AC", 120),
        (3, "MEC", 10),
    ]
    assert valkey_client.execute("EXISTS", lb.teams_key(world.season_id)) == 1
    assert valkey_client.execute("EXISTS", lb.users_key(world.season_id)) == 1


def test_missing_key_with_points_is_rebuilt_once(
    client: TestClient, valkey_client: ValkeyClient, rebuilds: list[int]
) -> None:
    world = _populate(client)
    assert valkey_client.execute("EXISTS", lb.teams_key(world.season_id)) == 0
    for _ in range(2):
        assert _rows(_board(client, world, scope="team"))[0] == (1, "ETC", 150)
    assert rebuilds == [world.season_id]


@pytest.mark.parametrize("scope", ["individual", "team", "building"])
def test_a_season_without_points_is_empty_and_never_rebuilt(
    client: TestClient, valkey_client: ValkeyClient, rebuilds: list[int], scope: str
) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "ETC", 0, 0)  # verified, but no points
        add_segment(db, world, "AC", 0, 0, status="rejected")
    params = {"scope": scope, "building_id": world.building_ids[0]}
    for _ in range(2):
        assert _rows(_board(client, world, **params)) == []
    assert rebuilds == []
    assert valkey_client.execute("EXISTS", lb.teams_key(world.season_id)) == 0


def test_a_building_without_points_is_empty_and_not_rebuilt(
    client: TestClient, valkey_client: ValkeyClient, rebuilds: list[int]
) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "ETC", 0, 100)
    assert _rows(_board(client, world, scope="building", building_id=world.building_ids[1])) == []
    assert rebuilds == []
    assert valkey_client.execute("EXISTS", lb.teams_key(world.season_id)) == 0


def test_a_building_with_points_is_rebuilt_when_its_key_is_missing(
    client: TestClient, valkey_client: ValkeyClient, rebuilds: list[int]
) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "ETC", 0, 100)
    board = _board(client, world, scope="building", building_id=world.building_ids[0])
    assert _rows(board) == [(1, "ETC", 100)]
    assert rebuilds == [world.season_id]
    assert valkey_client.execute("EXISTS", lb.building_key(world.season_id, world.building_ids[0]))


def test_reads_valkey_when_the_key_exists(client: TestClient, valkey_client: ValkeyClient) -> None:
    world = _populate(client)
    valkey_client.execute("ZADD", lb.teams_key(world.season_id), 999, str(world.team_ids["MEC"]))
    assert _rows(_board(client, world, scope="team")) == [(1, "MEC", 999)]


def test_rebuild_equals_incremental(client: TestClient, valkey_client: ValkeyClient) -> None:
    world = _populate(client)
    season = world.season_id
    for team, building, user_team, points in (
        ("ETC", 0, "ETC", 100),
        ("ETC", 1, "ETC", 50),
        ("AC", 0, "AC", 120),
        ("MEC", 1, "MEC", 10),
    ):
        lb.record_verified(
            valkey_client,
            season,
            world.users[user_team],
            world.team_ids[team],
            world.building_ids[building],
            points,
        )
    keys = [
        lb.users_key(season),
        lb.teams_key(season),
        *(lb.building_key(season, b) for b in world.building_ids),
    ]
    incremental = {k: lb.top(valkey_client, k, 100) for k in keys}
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        lb.rebuild(db, valkey_client, season)
        lb.rebuild(db, valkey_client, season)  # idempotent
    assert {k: lb.top(valkey_client, k, 100) for k in keys} == incremental


def test_valkey_down_falls_back_to_the_database(client: TestClient) -> None:
    world = _populate(client)
    client.app.state.valkey = ValkeyClient("redis://127.0.0.1:1/0", timeout_s=0.2)  # type: ignore[attr-defined]
    assert _rows(_board(client, world, scope="team")) == [
        (1, "ETC", 150),
        (2, "AC", 120),
        (3, "MEC", 10),
    ]
