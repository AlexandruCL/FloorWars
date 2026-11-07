"""Tests of the test-only reference segmenter (no server rules, no database)."""

# Seeded random.Random makes reproducible test data, it is not used for security (S311).
# ruff: noqa: S311

from __future__ import annotations

import csv
import random
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.replay.reference_segmenter import Trace, read_trace, segment_trace

TRACES = Path(__file__).resolve().parents[3] / "traces"
HPA_PER_M = 0.12
START = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)

SEGMENT_FIELDS = {
    "id",
    "checkin_id",
    "started_at",
    "building_id",
    "ascent_m",
    "duration_s",
    "vert_speed_mps",
    "steps",
    "stair_prob",
    "classifier_version",
}


def synthetic(climb_from: float, climb_to: float, speed_mps: float, step_hz: float) -> Trace:
    """40 s at 10 Hz: flat, a climb at speed_mps between climb_from and climb_to s, flat."""
    rng = random.Random(1)
    base = 1000.0
    pressure = []
    for i in range(400):
        t = i / 10
        height = speed_mps * (min(max(t, climb_from), climb_to) - climb_from)
        pressure.append(
            (int(t * 1e9) + 1_000_000_000, t, base - HPA_PER_M * height + rng.gauss(0, 0.01))
        )
    steps = [int(i / step_hz * 1e9) + 1_000_000_000 for i in range(int(40 * step_hz))]
    return Trace("synthetic.csv", "stairs_up", "hand", START, pressure, steps)


def test_a_slow_climb_with_steps_is_one_segment():
    (seg,) = segment_trace(synthetic(8.0, 28.0, 0.15, 2.0))
    assert set(seg) == SEGMENT_FIELDS
    assert 2.2 <= seg["ascent_m"] <= 3.4, seg  # 3 m climbed, a little lost at the edges
    assert 10 <= seg["duration_s"] <= 26, seg
    assert 35 <= seg["steps"] <= 60, seg
    assert seg["vert_speed_mps"] == pytest.approx(seg["ascent_m"] / seg["duration_s"], rel=0.01)
    assert seg["started_at"].startswith("2026-11-02T10:00:")


def test_flat_pressure_gives_no_segment():
    assert segment_trace(synthetic(8.0, 8.0, 0.0, 2.0)) == []


def test_a_climb_without_steps_is_a_segment_with_zero_steps():
    (seg,) = segment_trace(synthetic(8.0, 24.0, 0.6, 0.0))  # a lift: no step events
    assert seg["steps"] == 0
    assert seg["ascent_m"] > 6


def test_ids_are_stable_and_unique():
    trace = synthetic(5.0, 15.0, 0.3, 2.0)
    assert segment_trace(trace) == segment_trace(trace)
    other = replace(trace, name="other.csv")
    assert segment_trace(trace)[0]["id"] != segment_trace(other)[0]["id"]


def test_out_of_order_samples_and_steps_do_not_matter():
    trace = synthetic(8.0, 28.0, 0.15, 2.0)
    shuffled = replace(
        trace,
        pressure=random.Random(2).sample(trace.pressure, len(trace.pressure)),
        steps_ns=random.Random(3).sample(trace.steps_ns, len(trace.steps_ns)),
    )
    assert segment_trace(shuffled) == segment_trace(trace)


def test_too_few_samples_give_no_segment():
    assert segment_trace(Trace("x.csv", "walk_flat", "hand", START, [(1, 0.0, 1000.0)], [])) == []


def test_read_trace_parses_a_real_file():
    first = next(csv.DictReader((TRACES / "labels.csv").open(encoding="utf-8")))
    trace = read_trace(TRACES / first["file"])
    assert trace.label == first["label"]
    assert trace.placement == first["placement"]
    assert trace.pressure
    assert trace.start_utc.tzinfo is not None
