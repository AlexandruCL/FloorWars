from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    return TestClient(create_app(Settings(env="dev", log_level="WARNING")))


def test_healthz_returns_ok() -> None:
    response = make_client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_stub_is_prometheus_text() -> None:
    response = make_client().get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "floorwars_up 1" in response.text.splitlines()
