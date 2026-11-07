"""Replay the real recordings in `traces/` through the server's pure plausibility rules.

Each trace is cut into segments by the test-only reference segmenter (a Python mirror of the
Kotlin one), and every segment goes through `app.segments.rules.check_item` with a context that
passes the database rules (check-in, season, team) and no recent steps, so only the pure rules 1,
2 and 5 to 7 (and the always-true rate limit) decide. No database is used.

Gate (Week 3): zero false positives. No `elevator_up`, `walk_flat`, `shake` or `blow` trace may
yield a segment that passes every rule. Recall of `stairs_up` is reported, not gated.

TODO (Week 4, with Cristea's evaluation): tune the segmenter and the thresholds on a split that is
never used for the reported result, then gate the `stairs_up` recall. Do not tune them here to make
a trace pass: a blocked trace goes into the report as a finding.

Run `pytest -q server/tests/replay -s` to see the confusion table.
"""

from __future__ import annotations

import csv
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.dialects.postgresql import Range

from app.segments import rules
from app.segments.models import ItemContext
from app.segments.schemas import Segment
from tests.replay.reference_segmenter import read_trace, segment_trace

TRACES = Path(__file__).resolve().parents[3] / "traces"
USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
NO_FALSE_POSITIVES = ("elevator_up", "walk_flat", "shake", "blow")
PASSED = "passed"
NO_SEGMENT = "no_segment"


def first_failed_reason(item: dict[str, Any]) -> str | None:
    """The first rule `check_item` fails for a segment item, or None if it passes every rule.

    The one place that binds the replay to the rules module. The context passes rules 3 and 4
    (check-in, season, team), so the answer comes from rules 1, 2 and 5 to 7.
    """
    segment = Segment.model_validate(item)
    ctx = ItemContext(
        checkin_user_id=USER_ID,
        checkin_building_id=segment.building_id,
        checkin_valid_during=Range(
            segment.started_at - timedelta(hours=1), segment.started_at + timedelta(hours=1)
        ),
        season_id=1,
        team_id=1,
    )
    # The recordings are days old: judge each one as if it was uploaded a minute after it started.
    return rules.check_item(
        segment,
        ctx,
        user_id=USER_ID,
        now=segment.started_at + timedelta(minutes=1),
        recent_verified_steps=0,
        overlaps_verified=False,
    )


@dataclass(frozen=True)
class Outcome:
    file: str
    label: str
    segments: int
    verdict: str  # PASSED, NO_SEGMENT or the first failed reason of the segment with most steps


def replay(path: Path, label: str) -> Outcome:
    trace = read_trace(path)
    assert trace.label == label, f"{path.name}: header label {trace.label} != labels.csv {label}"
    segments = segment_trace(trace)
    if not segments:
        return Outcome(path.name, label, 0, NO_SEGMENT)
    failed = [
        (reason, s["steps"]) for s in segments if (reason := first_failed_reason(s)) is not None
    ]
    if len(failed) < len(segments):
        return Outcome(path.name, label, len(segments), PASSED)
    # The main climb of the recording: the candidate with most steps decides the reported reason.
    return Outcome(path.name, label, len(segments), max(failed, key=lambda f: f[1])[0])


@pytest.fixture(scope="module")
def outcomes() -> list[Outcome]:
    with (TRACES / "labels.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows, "traces/labels.csv is empty"
    return [replay(TRACES / row["file"], row["label"]) for row in rows]


def by_label(outcomes: list[Outcome], label: str) -> list[Outcome]:
    return [o for o in outcomes if o.label == label]


def test_every_trace_file_is_labelled(outcomes: list[Outcome]) -> None:
    on_disk = {p.name for p in TRACES.glob("*.csv")} - {"labels.csv"}
    assert {o.file for o in outcomes} == on_disk


@pytest.mark.parametrize("label", NO_FALSE_POSITIVES)
def test_no_false_positives(outcomes: list[Outcome], label: str) -> None:
    rows = by_label(outcomes, label)
    assert rows, f"no {label} traces in labels.csv"
    passed = [o.file for o in rows if o.verdict == PASSED]
    assert passed == [], f"{label} traces that pass every rule: {passed}"


def test_the_gate_is_not_empty(outcomes: list[Outcome]) -> None:
    """Zero false positives means little if the segmenter finds nothing: it finds the climbs."""
    for label in ("elevator_up", "stairs_up"):
        rows = by_label(outcomes, label)
        assert any(o.segments for o in rows), f"no candidate segment in any {label} trace"


def test_confusion_table(outcomes: list[Outcome]) -> None:
    """Prints rows = label, columns = passed / no segment / rejected by first failed reason."""
    labels = sorted({o.label for o in outcomes})
    reasons = sorted({o.verdict for o in outcomes} - {PASSED, NO_SEGMENT})
    columns = [PASSED, NO_SEGMENT, *reasons]
    widths = [max(len(c), 3) for c in columns]
    lines = [
        "trace replay (reference segmenter + app.segments.rules, pure rules only)",
        f"{'label':<12} {'n':>3}  "
        + "  ".join(c.rjust(w) for c, w in zip(columns, widths, strict=True)),
    ]
    for label in labels:
        counts = Counter(o.verdict for o in by_label(outcomes, label))
        cells = "  ".join(str(counts[c]).rjust(w) for c, w in zip(columns, widths, strict=True))
        lines.append(f"{label:<12} {sum(counts.values()):>3}  {cells}")
    stairs = by_label(outcomes, "stairs_up")
    kept = sum(o.verdict == PASSED for o in stairs)
    lines.append(f"stairs_up recall (reported, not gated): {kept}/{len(stairs)}")
    print("\n" + "\n".join(lines))  # shown with -s
