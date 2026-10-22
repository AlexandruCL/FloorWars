import io
import json
import logging

from app.config import Settings
from app.logging_config import UVICORN_LOGGERS, build_formatter, configure_logging


def test_log_record_is_single_line_json_with_required_fields() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(build_formatter())
    log = logging.getLogger("floorwars.test")
    log.addHandler(handler)
    log.propagate = False
    try:
        log.warning("hello %s", "world", extra={"request_id": "abc", "color_message": "\x1b[1mhi"})
    finally:
        log.removeHandler(handler)

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "floorwars.test"
    assert payload["message"] == "hello world"
    assert "timestamp" in payload
    assert payload["request_id"] == "abc"
    assert "color_message" not in payload


def test_configure_logging_routes_uvicorn_through_root() -> None:
    configure_logging("INFO")

    root_handlers = logging.getLogger().handlers
    assert any(type(h.formatter).__name__ == "JsonFormatter" for h in root_handlers)
    for name in UVICORN_LOGGERS:
        uv = logging.getLogger(name)
        assert uv.handlers == []
        assert uv.propagate is True


def test_settings_hide_secrets_in_repr() -> None:
    settings = Settings(database_url="postgresql://u:hunter2@db/floorwars")  # type: ignore[arg-type]

    assert "hunter2" not in repr(settings)
    assert settings.database_url is not None
    assert "hunter2" in settings.database_url.get_secret_value()
