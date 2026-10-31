"""POST /v1/checkins with method=qr."""

import base64
import json
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import qr_token
from tests.checkins.conftest import (
    KEY,
    OTHER_KEY,
    Ctx,
    insert_building,
    qr_body,
    token_for,
)
from tests.helpers import auth_headers, insert_user, new_email

PROBLEM = "application/problem+json"


def _post(ctx: Ctx, token: str) -> Any:
    return ctx.client.post("/v1/checkins", json=qr_body(token), headers=ctx.headers)


def _type(response: Any) -> str:
    assert response.headers["content-type"].startswith(PROBLEM)
    return str(response.json()["type"])


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_valid_qr_is_201_with_90_minute_range(ctx: Ctx) -> None:
    response = _post(ctx, token_for(ctx.building_id))
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"id", "building_id", "method", "valid_from", "valid_until"}
    assert body["building_id"] == ctx.building_id
    assert body["method"] == "qr"
    start = datetime.fromisoformat(body["valid_from"])
    end = datetime.fromisoformat(body["valid_until"])
    assert end - start == timedelta(seconds=5400)


def test_forged_signature(ctx: Ctx) -> None:
    _, payload, sig = token_for(ctx.building_id).split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["b"] = ctx.building_id + 1
    new_payload = _b64(json.dumps(forged, separators=(",", ":"), sort_keys=True).encode())
    response = _post(ctx, f"fwq1.{new_payload}.{sig}")
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:qr-invalid"


def test_wrong_key_has_same_type_as_bad_signature(ctx: Ctx) -> None:
    wrong_key = _post(ctx, token_for(ctx.building_id, key=OTHER_KEY))
    _, payload, _sig = token_for(ctx.building_id).split(".")
    bad_sig = _post(ctx, f"fwq1.{payload}.{_b64(b'x' * 32)}")
    assert wrong_key.status_code == bad_sig.status_code == 403
    assert _type(wrong_key) == _type(bad_sig) == "urn:floorwars:problem:qr-invalid"


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "fwq2.abc.def",
        "fwq1.onlyonepart",
        "fwq1.a.b.c",
        "fwq1.!!!.???",
        "fwq1." + _b64(b"not json") + "." + _b64(b"sig"),
        "x" * 600,
    ],
)
def test_malformed(ctx: Ctx, token: str) -> None:
    response = _post(ctx, token)
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:qr-malformed"


def test_expired(ctx: Ctx) -> None:
    now = int(time.time())
    token = qr_token.sign(ctx.building_id, KEY, now - 7200, now - 3600)
    response = _post(ctx, token)
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:qr-expired"


def test_not_yet_valid(ctx: Ctx) -> None:
    now = int(time.time())
    token = qr_token.sign(ctx.building_id, KEY, now + 3600, now + 7200)
    response = _post(ctx, token)
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:qr-not-yet-valid"


def test_unknown_building(ctx: Ctx) -> None:
    response = _post(ctx, token_for(ctx.building_id + 1000))
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:building-unknown"


def test_no_key_configured_is_503(make_app: Callable[..., TestClient]) -> None:
    client = make_app()
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        uid = insert_user(db, new_email())
    bid = insert_building(client)
    response = client.post(
        "/v1/checkins", json=qr_body(token_for(bid)), headers=auth_headers(client.app, uid)
    )
    assert response.status_code == 503
    assert _type(response) == "urn:floorwars:problem:qr-unavailable"


def test_unauthenticated_is_401(ctx: Ctx) -> None:
    response = ctx.client.post("/v1/checkins", json=qr_body(token_for(ctx.building_id)))
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [{}, {"method": "qr"}, {"method": "nfc", "qr_token": "x"}, {"method": "qr", "qr_token": 5}],
)
def test_invalid_body_is_422(ctx: Ctx, body: dict[str, object]) -> None:
    response = ctx.client.post("/v1/checkins", json=body, headers=ctx.headers)
    assert response.status_code == 422


def test_responses_do_not_echo_token(ctx: Ctx) -> None:
    token = token_for(ctx.building_id)
    ok = _post(ctx, token)
    bad = _post(ctx, token[:-3] + "AAA")
    for response in (ok, bad):
        assert token not in response.text
        assert token[:20] not in response.text
