"""The hub without sockets, and the 401 and the logs through a real uvicorn server."""

import logging
import socket
import threading
import time
import uuid

import pytest
import uvicorn
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from app.logging_config import configure_logging
from app.main import create_app
from app.realtime.hub import CLOSE_POLICY, MAX_QUEUED, Hub
from tests.helpers import TEST_DB_URL, settings_for_tests


def _message(event_id: int, season_id: int | None = 1) -> str:
    return (
        f'{{"type":"building_flipped","event_id":{event_id},"building_id":4,'
        f'"from_team":null,"to_team":"AC","at":"2026-11-20T09:30:00+00:00","season_id":{season_id}}}'
    )


def test_dispatch_strips_season_id_and_applies_visibility() -> None:
    hub = Hub(None)
    member = hub.register(uuid.uuid4(), frozenset({1}))
    stranger = hub.register(uuid.uuid4(), frozenset({2}))
    hub.dispatch(_message(7).encode())
    hub.dispatch(_message(8, season_id=None))  # no season: nobody
    hub.dispatch("not json")
    hub.dispatch('{"no": "event_id"}')
    assert member.queue.get_nowait() == (
        7,
        '{"type":"building_flipped","event_id":7,"building_id":4,"from_team":null,'
        '"to_team":"AC","at":"2026-11-20T09:30:00+00:00"}',
    )
    assert member.queue.empty()
    assert stranger.queue.empty()


def test_a_slow_socket_is_dropped_not_waited_for() -> None:
    hub = Hub(None)
    user = uuid.uuid4()
    slow = hub.register(user, frozenset({1}))
    for i in range(MAX_QUEUED + 1):
        hub.dispatch(_message(i + 1))
    assert hub.count(user) == 0
    assert slow.queue.get_nowait() == CLOSE_POLICY
    assert slow.queue.empty()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


@pytest.mark.skipif(not TEST_DB_URL, reason="FLOORWARS_TEST_DATABASE_URL not set")
def test_uvicorn_sends_the_401_and_logs_no_token(capsys: pytest.CaptureFixture[str]) -> None:
    """Starlette's denial response passes through uvicorn's websockets implementation, and the
    upgrade's log line carries no access token."""
    app = create_app(settings_for_tests(log_level="INFO"))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.05)
        url = f"ws://127.0.0.1:{port}/v1/ws?since=0&access_token=secret-xyz"
        with pytest.raises(InvalidStatus) as denied, connect(url):
            pass
        assert denied.value.response.status_code == 401
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    out = capsys.readouterr().out
    assert "/v1/ws?since=0&access_token=[redacted]" in out
    assert "secret-xyz" not in out


@pytest.mark.parametrize("name", ["uvicorn.error", "uvicorn.access"])
def test_access_token_is_redacted_in_uvicorn_logs(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO")
    logging.getLogger(name).info(
        '%s - "GET %s HTTP/1.1" %d', "1.2.3.4:5", "/v1/ws?access_token=xyz&since=3", 401
    )
    out = capsys.readouterr().out
    assert "access_token=[redacted]&since=3" in out
    assert "xyz" not in out
