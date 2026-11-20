"""Validate a response body against a schema of ``contracts/openapi.yaml``."""

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

_CONTRACT = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
)


def assert_matches(body: Any, schema_name: str, array: bool = False) -> None:
    ref = {"$ref": f"#/components/schemas/{schema_name}"}
    schema = {"type": "array", "items": ref} if array else ref
    Draft202012Validator({**schema, "components": _CONTRACT["components"]}).validate(body)
