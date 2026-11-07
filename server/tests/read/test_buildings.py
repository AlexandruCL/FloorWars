from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.helpers import auth_headers, insert_user, new_email

WKT = "POLYGON((21.2 45.7, 21.201 45.7, 21.201 45.701, 21.2 45.701, 21.2 45.7))"


def _add_buildings(client: TestClient, *names: str) -> None:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        for name in names:
            db.execute(
                text(
                    "INSERT INTO building (name, footprint) VALUES (:n, ST_GeomFromText(:w, 4326))"
                ),
                {"n": name, "w": WKT},
            )
        db.commit()


def _headers(client: TestClient) -> dict[str, str]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        user_id = insert_user(db, new_email())
    return auth_headers(client.app, user_id)


def test_list_buildings_ordered_by_name(client: TestClient) -> None:
    _add_buildings(client, "Rectorat", "Aula", "Biblioteca")
    response = client.get("/v1/buildings", headers=_headers(client))
    assert response.status_code == 200
    body = response.json()
    assert [b["name"] for b in body] == ["Aula", "Biblioteca", "Rectorat"]
    assert all(set(b) == {"id", "name"} and isinstance(b["id"], int) for b in body)


def test_list_buildings_empty(client: TestClient) -> None:
    response = client.get("/v1/buildings", headers=_headers(client))
    assert response.status_code == 200
    assert response.json() == []


def test_list_buildings_requires_token(client: TestClient) -> None:
    response = client.get("/v1/buildings")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
