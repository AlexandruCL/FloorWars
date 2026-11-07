"""The request level of ``POST /v1/segments``: auth, upload bucket, headers, batch shape, contract.

None of these reach the repository: the requests stop before the service runs.
"""

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from fastapi.testclient import TestClient

from app.auth.ratelimit import Decision
from app.config import Settings
from app.main import create_app
from app.segments import rules
from app.segments.schemas import RejectedSegment
from app.valkey import ValkeyError
from tests.helpers import TEST_VALKEY_URL, auth_headers, insert_user, new_email
from tests.segments.test_rules import raw_item

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
KEY = {"Idempotency-Key": "batch-1"}


def _user_headers(client: TestClient) -> dict[str, str]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        user_id = insert_user(db, new_email())
    return {**auth_headers(client.app, user_id), **KEY}  # type: ignore[arg-type]


def _batch(**overrides: Any) -> dict[str, Any]:
    return {"device_id": str(uuid.uuid4()), "segments": [raw_item()], **overrides}


def _assert_problem(response: Any, status: int) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"


def test_route_matches_contract() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["paths"]["/segments"]
    served = create_app(Settings(env="dev", log_level="WARNING")).openapi()["paths"]["/v1/segments"]
    assert set(served) == set(contract) == {"post"}
    assert served["post"]["operationId"] == contract["post"]["operationId"]
    assert set(served["post"]["responses"]) == set(contract["post"]["responses"])
    assert served["post"]["security"] == [{"bearerAuth": []}]
    header = next(p for p in served["post"]["parameters"] if p["name"] == "Idempotency-Key")
    assert header["required"] is True
    assert header["in"] == "header"
    assert header["schema"]["minLength"] == 1
    assert header["schema"]["maxLength"] == 255


def test_reasons_and_limits_match_contract() -> None:
    schemas = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))["components"]["schemas"]
    served = RejectedSegment.model_json_schema()["properties"]["reason"]["enum"]
    assert set(served) == set(schemas["RejectedSegment"]["properties"]["reason"]["enum"])
    assert "stair_prob_range" in served
    assert schemas["SegmentBatch"]["properties"]["segments"]["maxItems"] == rules.BATCH_MAX
    version = schemas["SegmentFields"]["properties"]["classifier_version"]
    assert version["maxLength"] == 64


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nonsense"}])
def test_401_comes_first(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/v1/segments", json={"not": "a batch"}, headers=headers)
    _assert_problem(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
@pytest.mark.parametrize(
    "body",
    [
        [],
        {},
        {"segments": [raw_item()]},
        {"device_id": "nope", "segments": [raw_item()]},
        _batch(segments=[]),
        _batch(segments=[raw_item() for _ in range(101)]),
        _batch(extra=1),
        _batch(segments=[{**raw_item(), "device_id": str(uuid.uuid4())}]),
        _batch(segments=[raw_item(steps="60")]),
        _batch(segments=[raw_item(classifier_version="x" * 65)]),
    ],
)
def test_422_for_a_body_that_is_not_a_batch(client: TestClient, body: Any) -> None:
    response = client.post("/v1/segments", json=body, headers=_user_headers(client))
    _assert_problem(response, 422)
    assert "errors" in response.json()


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
@pytest.mark.parametrize("key", [None, "", "k" * 256])
def test_422_for_a_bad_idempotency_key(client: TestClient, key: str | None) -> None:
    headers = _user_headers(client)
    del headers["Idempotency-Key"]
    if key is not None:
        headers["Idempotency-Key"] = key
    _assert_problem(client.post("/v1/segments", json=_batch(), headers=headers), 422)


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_upload_bucket_is_per_user_and_counts_invalid_requests(client: TestClient) -> None:
    headers = _user_headers(client)
    for _ in range(rules.UPLOADS_PER_HOUR):
        assert client.post("/v1/segments", json={}, headers=headers).status_code == 422
    limited = client.post("/v1/segments", json={}, headers=headers)
    _assert_problem(limited, 429)
    assert int(limited.headers["retry-after"]) >= 1
    assert client.post("/v1/segments", json={}, headers=_user_headers(client)).status_code == 422


@pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")
def test_malformed_json_answers_before_auth_and_spends_no_token(client: TestClient) -> None:
    json_type = {"Content-Type": "application/json"}
    _assert_problem(client.post("/v1/segments", content=b"{", headers=json_type), 422)
    headers = {**_user_headers(client), **json_type}
    for _ in range(rules.UPLOADS_PER_HOUR + 1):
        assert client.post("/v1/segments", content=b"{", headers=headers).status_code == 422
    assert client.post("/v1/segments", json={}, headers=headers).status_code == 422


class _Limiter:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, str, int, int]] = []

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        self.calls.append((name, subject, capacity, period_s))
        if self.failure:
            raise self.failure
        return Decision(allowed=False, retry_after_s=7)


def test_bucket_name_and_size(make_app: Callable[..., TestClient]) -> None:
    client = make_app()
    limiter = _Limiter()
    cast(Any, client.app).state.rate_limiter = limiter
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        user_id = insert_user(db, new_email())
    headers = {**auth_headers(cast(Any, client.app), user_id), **KEY}
    response = client.post("/v1/segments", json=_batch(), headers=headers)
    _assert_problem(response, 429)
    assert response.headers["retry-after"] == "7"
    assert limiter.calls == [("seg:user", str(user_id), 60, 3600)]


def test_503_when_valkey_is_down(client: TestClient) -> None:
    cast(Any, client.app).state.rate_limiter = _Limiter(ValkeyError("down"))
    _assert_problem(client.post("/v1/segments", json=_batch(), headers=_user_headers(client)), 503)


def test_503_without_a_limiter(client: TestClient) -> None:
    cast(Any, client.app).state.rate_limiter = None
    _assert_problem(client.post("/v1/segments", json=_batch(), headers=_user_headers(client)), 503)
