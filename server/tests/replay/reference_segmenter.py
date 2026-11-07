"""Reference segmenter for the trace replay. TEST-ONLY: nothing in `app` imports this module.

A Python mirror of the Kotlin segmenter (app/android/.../floorsensors/segmenter/Segmenter.kt), so
that the recorded traces in `traces/` can be turned into the segments a phone would upload and be
run through the server rules (`test_replay.py`). It is not the production segmenter and it must not
be tuned to make traces pass; keep it in step with the Kotlin constants instead.

Steps, as in the Kotlin code:
  1. Sort the pressure samples by time. Median-smooth them with a centred 8 s window (shrunk to a
     symmetric window at both ends).
  2. Convert to altitude: alt = -SCALE_HEIGHT_M * ln(p), about 0.12 hPa per metre near sea level.
  3. A sample is "climbing" when the altitude gain over its 4 s window, per second, is at least
     0.05 m/s. Climbing samples closer than 15 s apart form one run (landings between flights).
  4. A run is a segment when its ascent is at least 1.0 m. Its steps are the step events from the
     run start to the run end plus 0.3 s (the step detector lags pressure).

Output items carry the fields of `SegmentFields` in contracts/openapi.yaml. Standard library only.
"""

from __future__ import annotations

import csv
import math
import uuid
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Mirrors SegmenterParams in Segmenter.kt.
SMOOTHING_WINDOW_S = 8.0
SPEED_WINDOW_S = 4.0
MIN_CLIMB_SPEED_MPS = 0.05
MAX_PAUSE_S = 15.0
MIN_SEGMENT_ASCENT_M = 1.0
STEP_LAG_S = 0.3
SCALE_HEIGHT_M = 8434.0

CLASSIFIER_VERSION = "rules-1"
# The reference segmenter has no classifier: the rules ignore stair_prob (only its 0 to 1 bound).
PLACEHOLDER_STAIR_PROB = 0.5
# Fixed namespace so ids are the same on every run.
_ID_NAMESPACE = uuid.UUID("6f1f5c0e-0000-4000-8000-00000000fa11")
FAKE_CHECKIN_ID = "00000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class Trace:
    """One recording: metadata plus pressure (ns, elapsed_s, hPa) and step times in ns."""

    name: str
    label: str
    placement: str
    start_utc: datetime
    pressure: list[tuple[int, float, float]]
    steps_ns: list[int]


def read_trace(path: Path) -> Trace:
    """Parse a trace CSV (docs/trace_format.md section 1)."""
    meta: dict[str, str] = {}
    pressure: list[tuple[int, float, float]] = []
    steps_ns: list[int] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith("#"):
            key, _, value = line[1:].strip().partition(",")
            meta[key.strip()] = value.strip()
    rows = csv.reader(line for line in lines if not line.startswith("#"))
    next(rows)  # header: sensor,timestamp_ns,elapsed_s,value
    for sensor, ts_ns, elapsed_s, value in rows:
        if sensor == "pressure":
            pressure.append((int(ts_ns), float(elapsed_s), float(value)))
        elif sensor == "step":
            steps_ns.append(int(ts_ns))
    start_utc = datetime.fromisoformat(meta["start_utc"].replace("Z", "+00:00"))
    return Trace(
        name=path.name,
        label=meta["label"],
        placement=meta["placement"],
        start_utc=start_utc,
        pressure=pressure,
        steps_ns=steps_ns,
    )


def _windows(t: list[int], window_s: float) -> list[tuple[int, int]]:
    """For each sample i, the indices lo..hi of the samples within window_s / 2 of it."""
    half = int(window_s / 2 * 1e9)
    return [(bisect_left(t, ti - half), bisect_right(t, ti + half) - 1) for ti in t]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]  # odd length: the window is symmetric


def segment_trace(
    trace: Trace,
    *,
    building_id: int = 1,
    checkin_id: str = FAKE_CHECKIN_ID,
) -> list[dict[str, object]]:
    """The segments (SegmentFields items) the Kotlin segmenter would find in a trace."""
    samples = sorted(trace.pressure)
    n = len(samples)
    if n < 2:
        return []
    t = [s[0] for s in samples]
    raw = [s[2] for s in samples]

    smooth = []
    for i, (lo, hi) in enumerate(_windows(t, SMOOTHING_WINDOW_S)):
        k = min(i - lo, hi - i)
        smooth.append(_median(raw[i - k : i + k + 1]))
    alt = [-SCALE_HEIGHT_M * math.log(p) for p in smooth]

    climbing = [False] * n
    for i, (lo, hi) in enumerate(_windows(t, SPEED_WINDOW_S)):
        if hi > lo:
            speed = (alt[hi] - alt[lo]) / ((t[hi] - t[lo]) / 1e9)
            climbing[i] = speed >= MIN_CLIMB_SPEED_MPS

    runs: list[list[int]] = []
    for i in range(n):
        if not climbing[i]:
            continue
        if runs and (t[i] - t[runs[-1][1]]) / 1e9 <= MAX_PAUSE_S:
            runs[-1][1] = i
        else:
            runs.append([i, i])

    steps = sorted(trace.steps_ns)
    lag_ns = int(STEP_LAG_S * 1e9)
    segments: list[dict[str, object]] = []
    for start, end in runs:
        ascent_m = alt[end] - alt[start]
        duration_s = (t[end] - t[start]) / 1e9
        if ascent_m < MIN_SEGMENT_ASCENT_M or duration_s <= 0:
            continue
        step_count = bisect_right(steps, t[end] + lag_ns) - bisect_left(steps, t[start])
        started_at = trace.start_utc + timedelta(seconds=samples[start][1])
        segments.append(
            {
                "id": str(uuid.uuid5(_ID_NAMESPACE, f"{trace.name}:{start}")),
                "checkin_id": checkin_id,
                "started_at": started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "building_id": building_id,
                "ascent_m": round(ascent_m, 3),
                "duration_s": round(duration_s, 3),
                "vert_speed_mps": round(ascent_m / duration_s, 4),
                "steps": step_count,
                "stair_prob": PLACEHOLDER_STAIR_PROB,
                "classifier_version": CLASSIFIER_VERSION,
            }
        )
    return segments
