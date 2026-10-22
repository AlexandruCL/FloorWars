"""Tests for the fake-segment generator. Run: python -m pytest -q tools/fake_segments"""

import json
import random
from datetime import UTC, datetime
from pathlib import Path

import fake_segments as fs
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "contracts" / "openapi.yaml"
START = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)
N = 300


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def segments(kind, seed=7, count=N):
    rng = random.Random(seed)
    return fs.make_segments(
        kind, rng, count=count, checkin_id=fs.make_uuid(rng), building_id=4, start=START
    )


# Scoring rule (plan 3.3) --------------------------------------------------------------------


def test_stairs_pass_the_scoring_rule():
    for seg in segments("stairs"):
        assert 4 <= seg["steps"] / seg["ascent_m"] <= 8, seg
        assert 0.1 <= seg["vert_speed_mps"] <= 0.9, seg
        assert 5 <= seg["duration_s"] <= 180, seg
        assert 2.0 <= seg["ascent_m"] <= 30.0, seg
        assert 1 <= seg["steps"] <= 2000, seg
        assert 0.8 <= seg["stair_prob"] <= 0.99, seg
        assert seg["classifier_version"] == "rules-1"
        assert seg["steps"] / seg["duration_s"] <= fs.STAIRS_MAX_CADENCE_HZ + 0.1, seg
        assert fs.passes_scoring_rule(seg)


def test_elevator_fails_the_rule():
    for seg in segments("elevator"):
        assert seg["vert_speed_mps"] > 1.0, seg
        assert seg["steps"] / seg["ascent_m"] < 1, seg
        assert not fs.passes_scoring_rule(seg)


def test_shake_fails_the_rule_but_keeps_schema_ascent():
    for seg in segments("shake"):
        assert seg["ascent_m"] >= 2.0, seg
        assert seg["steps"] / seg["ascent_m"] > 8, seg
        assert not fs.passes_scoring_rule(seg)


def test_mixed_has_all_kinds():
    segs = segments("mixed")
    scoring = sum(fs.passes_scoring_rule(s) for s in segs)
    assert 0 < scoring < len(segs)


def test_segments_are_in_time_order_and_unique():
    segs = segments("mixed")
    assert len({s["id"] for s in segs}) == len(segs)
    times = [s["started_at"] for s in segs]
    assert times == sorted(times)


# Contract (Segment schema) ------------------------------------------------------------------


def basic_errors(seg, spec):
    """Small schema check that needs no jsonschema: keys, types and numeric bounds."""
    fields = spec["components"]["schemas"]["SegmentFields"]
    props = fields["properties"]
    errors = [f"missing {k}" for k in fields["required"] if k not in seg]
    errors += [f"extra {k}" for k in seg if k not in props]
    types = {"string": str, "integer": int, "number": (int, float)}
    for key, value in seg.items():
        rule = props.get(key, {})
        if "type" in rule and (
            not isinstance(value, types[rule["type"]]) or isinstance(value, bool)
        ):
            errors.append(f"{key} type")
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{key} below minimum")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{key} above maximum")
        if "exclusiveMinimum" in rule and value <= rule["exclusiveMinimum"]:
            errors.append(f"{key} not above exclusiveMinimum")
    return errors


@pytest.mark.parametrize("kind", ["stairs", "elevator", "shake", "mixed"])
def test_segments_fit_schema_bounds(kind, spec):
    for seg in segments(kind):
        assert basic_errors(seg, spec) == [], seg


def test_basic_check_catches_bad_items(spec):
    seg = segments("stairs", count=1)[0]
    assert basic_errors(dict(seg, steps=0), spec)
    assert basic_errors(dict(seg, ascent_m=1.9), spec)
    assert basic_errors(dict(seg, floors_gained=3), spec)


@pytest.fixture(scope="module")
def validator_for(spec):
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    from referencing.jsonschema import DRAFT202012

    uri = "urn:floorwars:openapi"
    registry = referencing.Registry().with_resource(
        uri, referencing.Resource.from_contents(spec, default_specification=DRAFT202012)
    )

    def make(name):
        cls = jsonschema.Draft202012Validator
        return cls(
            {"$ref": f"{uri}#/components/schemas/{name}"},
            registry=registry,
            format_checker=cls.FORMAT_CHECKER,
        )

    return make


@pytest.mark.parametrize("kind", ["stairs", "elevator", "shake", "mixed"])
def test_segments_validate_with_jsonschema(kind, validator_for):
    validator = validator_for("Segment")
    for seg in segments(kind):
        errors = [e.message for e in validator.iter_errors(seg)]
        assert errors == [], (seg, errors)


def test_jsonschema_rejects_bad_items(validator_for):
    validator = validator_for("Segment")
    seg = segments("stairs", count=1)[0]
    assert not validator.is_valid(dict(seg, steps=0))
    assert not validator.is_valid(dict(seg, floors_gained=3))
    assert not validator.is_valid(dict(seg, id="not-a-uuid"))


def test_batches_validate_and_respect_max(validator_for):
    validator = validator_for("SegmentBatch")
    rng = random.Random(1)
    batches = fs.make_batches(segments("mixed", count=250), 100, rng)
    assert [len(b["body"]["segments"]) for b in batches] == [100, 100, 50]
    assert len({b["idempotency_key"] for b in batches}) == 3
    for b in batches:
        assert validator.is_valid(b["body"])
    with pytest.raises(ValueError):
        fs.make_batches(segments("stairs", count=1), 101, rng)


def test_make_batch_body_validates(validator_for):
    body = fs.make_batch(
        "stairs",
        random.Random(2),
        count=3,
        checkin_id=fs.make_uuid(random.Random(3)),
        building_id=4,
        start=START,
    )
    assert validator_for("SegmentBatch").is_valid(body)


# Determinism and CLI ------------------------------------------------------------------------


def test_seed_determinism():
    assert segments("mixed", seed=5) == segments("mixed", seed=5)
    assert segments("mixed", seed=5) != segments("mixed", seed=6)


def test_dry_run_prints_valid_deterministic_json(capsys, validator_for):
    argv = ["--dry-run", "--count", "3", "--seed", "1"]
    assert fs.main(argv) == 0
    first = capsys.readouterr().out
    assert fs.main(argv) == 0
    assert capsys.readouterr().out == first
    doc = json.loads(first)
    (batch,) = doc["batches"]
    assert len(batch["body"]["segments"]) == 3
    assert validator_for("SegmentBatch").is_valid(batch["body"])
    assert batch["body"]["segments"][0]["started_at"] == "2026-11-02T10:00:00Z"


def test_cli_rejects_bad_arguments(capsys):
    assert fs.main(["--dry-run", "--batch-size", "101"]) == 2
    assert fs.main(["--dry-run", "--count", "0"]) == 2
    capsys.readouterr()


def test_summary_line():
    data = {
        "accepted": [{"id": "a"}],
        "rejected": [{"id": "b", "reason": "speed"}],
        "flips": [],
    }
    line = fs.summarize("batch 1/1", 200, data)
    assert line == "batch 1/1 status=200 accepted=1 rejected=1 flips=0 reasons=speed"
    assert "status=422" in fs.summarize("batch 1/1", 422, {"title": "Unprocessable"})
