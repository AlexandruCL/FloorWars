"""Security pass (plan 7.11, W5-5): no CORS, and every request input is bounded."""

from typing import Any

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _app() -> Any:
    return create_app(Settings(env="dev", log_level="WARNING"))


def test_no_cors_headers() -> None:
    """The app is native and the admin panel is same origin: a browser gets no allow-origin."""
    app = _app()
    assert all(m.cls is not CORSMiddleware for m in app.user_middleware)
    client = TestClient(app)
    headers = {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}
    for response in (
        client.get("/healthz", headers={"Origin": "https://evil.example"}),
        client.options("/v1/auth/otp", headers=headers),
    ):
        assert not any(k.lower().startswith("access-control-") for k in response.headers)


# Inputs that are deliberately not bounded in the schema, with the reason. Everything else with a
# number or a free string must carry a bound, so a new request field cannot slip in unbounded.
UNBOUNDED_ON_PURPOSE = {
    # POST /v1/segments: a number outside its range must reach the rules and come back as one
    # rejected item, not as a 422 for the whole batch (Week 3 decision 4; segments/schemas.py).
    "Segment.building_id",
    "Segment.ascent_m",
    "Segment.duration_s",
    "Segment.vert_speed_mps",
    "Segment.steps",
    "Segment.stair_prob",
    # Checked against geofence_max_accuracy_m (1 to 1000) in the check-in rules.
    "GeofenceCheckinRequest.accuracy_m",
}
FREE_FORMATS = {"uuid", "date-time", "date"}


def _resolve(schemas: dict[str, Any], schema: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ref = schema.get("$ref")
    if ref is None:
        return "", schema
    name = ref.rsplit("/", 1)[1]
    return name, schemas[name]


def _check(schemas: dict[str, Any], where: str, schema: dict[str, Any], out: list[str]) -> None:
    name, schema = _resolve(schemas, schema)
    where = name or where
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            _check(schemas, where, sub, out)
    kind = schema.get("type")
    if kind == "object":
        for prop, sub in schema.get("properties", {}).items():
            _check(schemas, f"{where}.{prop}", sub, out)
    elif kind == "array":
        if "maxItems" not in schema:
            out.append(f"{where}: array without maxItems")
        _check(schemas, where, schema["items"], out)
    elif kind == "string":
        free = "enum" not in schema and "const" not in schema and "pattern" not in schema
        if free and schema.get("format") not in FREE_FORMATS and "maxLength" not in schema:
            out.append(f"{where}: string without maxLength")
    elif kind in ("integer", "number") and where not in UNBOUNDED_ON_PURPOSE:
        lower = "minimum" in schema or "exclusiveMinimum" in schema
        upper = "maximum" in schema or "exclusiveMaximum" in schema
        if not (lower and upper):
            out.append(f"{where}: number without minimum and maximum")


def test_request_inputs_are_bounded() -> None:
    spec = _app().openapi()
    schemas = spec["components"]["schemas"]
    problems: list[str] = []
    for path, item in spec["paths"].items():
        for method, op in item.items():
            where = f"{method.upper()} {path}"
            for param in op.get("parameters", []):
                _check(schemas, f"{where} {param['name']}", param["schema"], problems)
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body:
                _check(schemas, where, body["schema"], problems)
    assert not problems, problems
