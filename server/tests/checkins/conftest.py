"""Fixtures for check-in tests: a known square building, a QR key and an authenticated user."""

import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import qr_token
from tests.helpers import auth_headers, insert_user, new_email

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))
KEY_HEX = KEY.hex()
M_PER_DEG_LAT = 111_320.0
CENTRE_LAT, CENTRE_LON = 45.7472, 21.2266
HALF_SIDE_M = 20.0


def dlon(metres: float, lat: float = CENTRE_LAT) -> float:
    return metres / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def dlat(metres: float) -> float:
    return metres / M_PER_DEG_LAT


def east_of_edge(metres: float) -> tuple[float, float]:
    """(lat, lon) of a point ``metres`` east of the building's east edge, at centre latitude."""
    return CENTRE_LAT, CENTRE_LON + dlon(HALF_SIDE_M + metres)


def square_wkt(lat: float, lon: float, half_m: float = HALF_SIDE_M) -> str:
    x, y = dlon(half_m, lat), dlat(half_m)
    pts = [(lon - x, lat - y), (lon + x, lat - y), (lon + x, lat + y), (lon - x, lat + y)]
    pts.append(pts[0])
    return "POLYGON((" + ", ".join(f"{px:.8f} {py:.8f}" for px, py in pts) + "))"


def insert_building(client: TestClient, lat: float = CENTRE_LAT, lon: float = CENTRE_LON) -> int:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        bid = db.execute(
            text(
                "INSERT INTO building (name, footprint) "
                "VALUES ('test', ST_GeomFromText(:w, 4326)) RETURNING id"
            ),
            {"w": square_wkt(lat, lon)},
        ).scalar_one()
        db.commit()
    assert isinstance(bid, int)
    return bid


def token_for(building_id: int, key: bytes = KEY, nbf_off: int = -60, exp_off: int = 3600) -> str:
    now = int(time.time())
    return qr_token.sign(building_id, key, now + nbf_off, now + exp_off)


@dataclass
class Ctx:
    client: TestClient
    user_id: uuid.UUID
    headers: dict[str, str]
    building_id: int


def qr_body(token: str) -> dict[str, object]:
    return {"method": "qr", "qr_token": token}


def geo_body(lat: float, lon: float, accuracy_m: float | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"method": "geofence", "latitude": lat, "longitude": lon}
    if accuracy_m is not None:
        body["accuracy_m"] = accuracy_m
    return body


@pytest.fixture
def ctx(make_app: Callable[..., TestClient]) -> Ctx:
    client = make_app(qr_hmac_key=KEY_HEX)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        uid = insert_user(db, new_email())
    return Ctx(client, uid, auth_headers(client.app, uid), insert_building(client))
