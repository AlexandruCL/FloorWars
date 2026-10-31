"""Teams and seasons API: ``/v1/teams``, ``/v1/seasons/active``, ``/v1/seasons/{id}/join``."""

import threading

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import auth_headers, insert_user, new_email

PROBLEM = "urn:floorwars:problem:"


def add_team(client: TestClient, code: str, color: str = "#112233") -> int:
    with client.app.state.sessionmaker() as db:
        team_id = db.execute(
            text("INSERT INTO team (code, color_hex) VALUES (:c, :h) RETURNING id"),
            {"c": code, "h": color},
        ).scalar_one()
        db.commit()
    assert isinstance(team_id, int)
    return team_id


def add_season(client: TestClient, start: str, end: str) -> int:
    """A season between two offsets from now, for example ``("-1 day", "+1 day")``."""
    with client.app.state.sessionmaker() as db:
        season_id = db.execute(
            text(
                "INSERT INTO season (active_during) "
                "VALUES (tstzrange(now() + CAST(:s AS interval), now() + CAST(:e AS interval))) "
                "RETURNING id"
            ),
            {"s": start, "e": end},
        ).scalar_one()
        db.commit()
    assert isinstance(season_id, int)
    return season_id


def new_user(client: TestClient) -> dict[str, str]:
    with client.app.state.sessionmaker() as db:
        user_id = insert_user(db, new_email())
    return auth_headers(client.app, user_id)


def test_team_list_is_ordered_by_code_and_has_the_contract_shape(client: TestClient) -> None:
    b = add_team(client, "MEC", "#00ff00")
    a = add_team(client, "AC", "#FF0000")
    c = add_team(client, "ETC", "#0000FF")
    response = client.get("/v1/teams")
    assert response.status_code == 200
    assert response.json() == [
        {"id": a, "code": "AC", "color_hex": "#FF0000"},
        {"id": c, "code": "ETC", "color_hex": "#0000FF"},
        {"id": b, "code": "MEC", "color_hex": "#00ff00"},
    ]


def test_team_list_is_empty_without_teams(client: TestClient) -> None:
    assert client.get("/v1/teams").json() == []


def test_active_season_is_found(client: TestClient) -> None:
    add_season(client, "-30 days", "-10 days")
    active = add_season(client, "-1 day", "+1 day")
    add_season(client, "+10 days", "+30 days")
    response = client.get("/v1/seasons/active")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "starts_at", "ends_at"}
    assert body["id"] == active
    assert body["starts_at"] < body["ends_at"]


def test_no_active_season_is_404(client: TestClient) -> None:
    add_season(client, "-30 days", "-10 days")
    response = client.get("/v1/seasons/active")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == PROBLEM + "no-active-season"


def test_join_creates_a_membership(client: TestClient) -> None:
    team = add_team(client, "AC")
    season = add_season(client, "-1 day", "+1 day")
    response = client.post(
        f"/v1/seasons/{season}/join", json={"team_id": team}, headers=new_user(client)
    )
    assert response.status_code == 201
    assert response.json() == {"season_id": season, "team_id": team}
    with client.app.state.sessionmaker() as db:
        count = db.execute(text("SELECT count(*) FROM team_membership")).scalar_one()
    assert count == 1


def test_second_join_is_409_already_joined(client: TestClient) -> None:
    first = add_team(client, "AC")
    second = add_team(client, "ETC")
    season = add_season(client, "-1 day", "+1 day")
    headers = new_user(client)
    assert (
        client.post(f"/v1/seasons/{season}/join", json={"team_id": first}, headers=headers)
    ).status_code == 201
    response = client.post(f"/v1/seasons/{season}/join", json={"team_id": second}, headers=headers)
    assert response.status_code == 409
    assert response.json()["type"] == PROBLEM + "already-joined"


def test_unknown_season_is_404(client: TestClient) -> None:
    team = add_team(client, "AC")
    response = client.post("/v1/seasons/999/join", json={"team_id": team}, headers=new_user(client))
    assert response.status_code == 404
    assert response.json()["type"] == PROBLEM + "season-not-found"


def test_unknown_team_is_422(client: TestClient) -> None:
    season = add_season(client, "-1 day", "+1 day")
    response = client.post(
        f"/v1/seasons/{season}/join", json={"team_id": 999}, headers=new_user(client)
    )
    assert response.status_code == 422
    assert response.json()["type"] == PROBLEM + "team-not-found"


def test_season_not_running_is_409(client: TestClient) -> None:
    team = add_team(client, "AC")
    past = add_season(client, "-30 days", "-10 days")
    future = add_season(client, "+10 days", "+30 days")
    headers = new_user(client)
    for season in (past, future):
        response = client.post(
            f"/v1/seasons/{season}/join", json={"team_id": team}, headers=headers
        )
        assert response.status_code == 409
        assert response.json()["type"] == PROBLEM + "season-not-active"


def test_join_without_token_is_401(client: TestClient) -> None:
    team = add_team(client, "AC")
    season = add_season(client, "-1 day", "+1 day")
    response = client.post(f"/v1/seasons/{season}/join", json={"team_id": team})
    assert response.status_code == 401


def test_bad_body_is_422(client: TestClient) -> None:
    season = add_season(client, "-1 day", "+1 day")
    headers = new_user(client)
    for body in ({}, {"team_id": 0}, {"team_id": "1"}, {"team_id": 1, "x": 1}):
        response = client.post(f"/v1/seasons/{season}/join", json=body, headers=headers)
        assert response.status_code == 422


def test_concurrent_joins_by_one_user_give_one_201_and_one_409(client: TestClient) -> None:
    team = add_team(client, "AC")
    season = add_season(client, "-1 day", "+1 day")
    headers = new_user(client)
    barrier = threading.Barrier(2)
    statuses: list[int] = []
    lock = threading.Lock()

    def join() -> None:
        barrier.wait()
        response = client.post(
            f"/v1/seasons/{season}/join", json={"team_id": team}, headers=headers
        )
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=join) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [201, 409]


def test_membership_is_per_season_and_per_user(client: TestClient) -> None:
    team = add_team(client, "AC")
    season = add_season(client, "-1 day", "+1 day")
    for _ in range(2):
        response = client.post(
            f"/v1/seasons/{season}/join", json={"team_id": team}, headers=new_user(client)
        )
        assert response.status_code == 201
