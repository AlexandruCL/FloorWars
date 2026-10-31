"""RFC 9457 problem details for every error. No database needed."""

from fastapi.testclient import TestClient

from app.api.problems import ProblemError, too_many_requests
from app.config import Settings
from app.main import create_app


def _client() -> TestClient:
    app = create_app(Settings(env="dev", log_level="WARNING"))

    def boom() -> None:
        raise ProblemError(409, detail="Already joined.", type_="urn:floorwars:problem:x", n=1)

    def limited() -> None:
        raise too_many_requests("Slow down.", 7)

    def crash() -> None:
        raise RuntimeError("secret internals")

    app.add_api_route("/boom", boom)
    app.add_api_route("/limited", limited)
    app.add_api_route("/crash", crash)
    return TestClient(app, raise_server_exceptions=False)


def test_problem_error_renders_problem_json() -> None:
    response = _client().get("/boom")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "urn:floorwars:problem:x",
        "title": "Conflict",
        "status": 409,
        "detail": "Already joined.",
        "n": 1,
    }


def test_too_many_requests_sets_retry_after() -> None:
    response = _client().get("/limited")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"


def test_unknown_route_is_problem() -> None:
    response = _client().get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Not Found"


def test_unhandled_error_is_500_problem_without_details() -> None:
    response = _client().get("/crash")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert "secret internals" not in response.text
