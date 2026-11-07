from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx import Response

from tests.helpers import auth_headers
from tests.read.seed import World, add_segment, seed, set_owner


def _get(client: TestClient, world: World, building_id: int) -> Response:
    headers = auth_headers(client.app, world.users["AC"])
    return client.get(f"/v1/buildings/{building_id}/standings", headers=headers)


def test_owner_and_points_ordered(client: TestClient) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "ETC", 0, 100)
        add_segment(db, world, "ETC", 0, 50)
        add_segment(db, world, "AC", 0, 70)
        claimed_at = set_owner(db, world, "ETC", 0)
    response = _get(client, world, world.building_ids[0])
    assert response.status_code == 200
    body = response.json()
    assert body["building_id"] == world.building_ids[0]
    assert body["season_id"] == world.season_id
    assert body["owner"] == {"id": world.team_ids["ETC"], "code": "ETC", "color_hex": "#445566"}
    assert datetime.fromisoformat(body["claimed_at"]) == claimed_at
    assert [(t["code"], t["points"]) for t in body["teams"]] == [
        ("ETC", 150),
        ("AC", 70),
        ("MEC", 0),
    ]
    assert set(body["teams"][0]) == {"team_id", "code", "color_hex", "points"}
    window_start = datetime.fromisoformat(body["window_start"])
    assert abs((datetime.now(UTC) - window_start) - timedelta(days=7)) < timedelta(minutes=1)


def test_unowned_building_lists_every_team_with_zero(client: TestClient) -> None:
    world = seed(client)
    body = _get(client, world, world.building_ids[1]).json()
    assert body["owner"] is None
    assert body["claimed_at"] is None
    assert [(t["code"], t["points"]) for t in body["teams"]] == [
        ("AC", 0),
        ("ETC", 0),
        ("MEC", 0),
    ]


def test_ties_ordered_by_code(client: TestClient) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "MEC", 0, 10)
        add_segment(db, world, "ETC", 0, 10)
    body = _get(client, world, world.building_ids[0]).json()
    assert [t["code"] for t in body["teams"]] == ["ETC", "MEC", "AC"]


def test_window_edge_and_other_buildings_and_rejected(client: TestClient) -> None:
    world = seed(client)
    now = datetime.now(UTC)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, "AC", 0, 30, started_at=now - timedelta(days=6, hours=23))
        add_segment(db, world, "AC", 0, 500, started_at=now - timedelta(days=7, hours=1))
        add_segment(db, world, "AC", 1, 900)  # another building
        add_segment(db, world, "MEC", 0, 0, status="rejected")
    body = _get(client, world, world.building_ids[0]).json()
    assert {t["code"]: t["points"] for t in body["teams"]} == {"AC": 30, "ETC": 0, "MEC": 0}


def test_unknown_building_is_404(client: TestClient) -> None:
    world = seed(client)
    response = _get(client, world, 9999)
    assert response.status_code == 404
    assert response.json()["type"].endswith("building-not-found")


def test_no_active_season_is_404(client: TestClient) -> None:
    world = seed(client, active=False)
    response = _get(client, world, world.building_ids[0])
    assert response.status_code == 404
    assert response.json()["type"].endswith("no-active-season")


def test_standings_require_token(client: TestClient) -> None:
    world = seed(client)
    response = client.get(f"/v1/buildings/{world.building_ids[0]}/standings")
    assert response.status_code == 401


def test_invalid_id_is_422(client: TestClient) -> None:
    world = seed(client)
    assert _get(client, world, 0).status_code == 422
