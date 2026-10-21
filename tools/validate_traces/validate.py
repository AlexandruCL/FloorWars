"""Check sensor trace CSVs against docs/trace_format.md, section 4 checks 1-9.

Usage: python tools/validate_traces/validate.py <dir_or_file> [...]
Prints one line per file: PASS, or FAIL with the failed check numbers and why.
Files with # synthetic,true are tagged SYNTHETIC but pass or fail on the same checks.
Directories are scanned for *.csv (not recursive); labels.csv is skipped there.
Exit code 1 if any file fails.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

# Thresholds from docs/trace_format.md section 4. Tunable after the first real recordings.
MIN_PRESSURE_S = 25.0  # check 2: span of pressure readings
MAX_PRESSURE_GAP_S = 1.0  # check 2: longest allowed gap between pressure readings
PRESSURE_HZ = (20.0, 100.0)  # check 3
PRESSURE_HPA = (800.0, 1100.0)  # check 4
STEP_HZ = (1.0, 3.0)  # check 5: (steps - 1) / (last step - first step), so needs 2+ steps
STAIRS_NET_HPA = (0.5, 3.0)  # check 6: size of the net change; up falls, down rises
ELEVATOR_NET_HPA = (1.0, 4.0)  # check 7: size of the net change; elevator_up falls
NET_WINDOW_S = 1.0  # checks 6, 7, 9: net change compares the first and last second (section 3)
ELAPSED_TOLERANCE_S = 0.0015  # check 1: elapsed_s is rounded to 3 decimals
HPA_PER_M = 0.12  # check 9: net pressure change to metres of height (plan 3.3)
STAIRS_STEPS_PER_M = (4.0, 8.0)  # check 9: stairs_up/down, steps per metre of net height change
ELEVATOR_MAX_STEPS_PER_M = 1.0  # check 9: elevator_up must stay strictly below this
FLAT_MAX_ASCENT_M = 2.0  # check 9: walk_flat and shake net ascent must stay under this

LABELS = ["stairs_up", "stairs_down", "elevator_up", "walk_flat", "shake", "blow"]
PLACEMENTS = ["pocket", "hand", "bag"]
STEP_LABELS = {"stairs_up", "stairs_down", "walk_flat"}
REQUIRED_META = ["device_model", "has_barometer", "label", "placement", "start_utc", "stop_utc"]
SYNTHETIC_META = ["synthetic", "generator", "seed"]
COLUMNS = ["sensor", "timestamp_ns", "elapsed_s", "value"]
ISO_UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")
INTEGER = re.compile(r"\d+")
ELAPSED = re.compile(r"-?\d+\.\d{3}")


def check_metadata(meta_rows, fail):
    keys, meta = [], {}
    for row in meta_rows:
        if len(row) != 2 or not row[0].startswith("# "):
            fail(1, f"bad metadata line {','.join(row)!r}")
            continue
        key = row[0][2:]
        if key in meta:
            fail(1, f"duplicate metadata {key}")
        keys.append(key)
        meta[key] = row[1]

    expected = (SYNTHETIC_META if "synthetic" in meta else []) + REQUIRED_META
    missing = [k for k in expected if k not in meta]
    unknown = [k for k in keys if k not in expected]
    if missing:
        fail(1, f"missing metadata {', '.join(missing)}")
    if unknown:
        fail(1, f"unknown metadata {', '.join(unknown)}")
    if not missing and not unknown and keys != expected:
        fail(1, "metadata out of order")

    synthetic = meta.get("synthetic") == "true"
    if "synthetic" in meta and not synthetic:
        fail(1, f"synthetic is {meta['synthetic']!r}, expected true")
    if "seed" in meta and not INTEGER.fullmatch(meta["seed"]):
        fail(1, f"seed {meta['seed']!r} is not an integer")
    if "device_model" in meta and not meta["device_model"].strip():
        fail(1, "empty device_model")
    if not synthetic and meta.get("device_model") == "SYNTHETIC":
        fail(1, "device_model SYNTHETIC on a file without # synthetic,true")
    if "has_barometer" in meta and meta["has_barometer"] not in ("true", "false"):
        fail(1, f"has_barometer {meta['has_barometer']!r}")
    if "label" in meta and meta["label"] not in LABELS:
        fail(1, f"unknown label {meta['label']!r}")
    if "placement" in meta and meta["placement"] not in PLACEMENTS:
        fail(1, f"unknown placement {meta['placement']!r}")
    for key in ("start_utc", "stop_utc"):
        if key in meta and not ISO_UTC.fullmatch(meta[key]):
            fail(1, f"{key} {meta[key]!r} is not ISO 8601 UTC with milliseconds")
    if all(ISO_UTC.fullmatch(meta.get(k, "")) for k in ("start_utc", "stop_utc")):
        if meta["stop_utc"] < meta["start_utc"]:
            fail(1, "stop_utc is before start_utc")
    return meta, synthetic


def check_rows(rows, first_line, fail):
    """Returns pressure as [(timestamp_ns, hPa)] and steps as [timestamp_ns], in file order."""
    pressure, steps = [], []
    previous_ts, offset = None, None
    for n, row in enumerate(rows, start=first_line):
        if len(row) != 4:
            fail(1, f"line {n}: {len(row)} columns")
            continue
        sensor, ts_text, elapsed_text, value_text = row
        if sensor not in ("pressure", "step"):
            fail(1, f"line {n}: unknown sensor {sensor!r}")
            continue
        if not INTEGER.fullmatch(ts_text) or not ELAPSED.fullmatch(elapsed_text):
            fail(1, f"line {n}: bad timestamp_ns or elapsed_s")
            continue
        try:
            value = float(value_text)
        except ValueError:
            fail(1, f"line {n}: value {value_text!r} is not a number")
            continue
        ts = int(ts_text)
        if previous_ts is not None and ts < previous_ts:
            fail(1, f"line {n}: timestamp_ns goes backwards")
        previous_ts = ts
        # elapsed_s must track timestamp_ns; its zero point can be before the first event.
        this_offset = float(elapsed_text) - ts / 1e9
        if offset is None:
            offset = this_offset
        elif abs(this_offset - offset) > ELAPSED_TOLERANCE_S:
            fail(1, f"line {n}: elapsed_s does not match timestamp_ns")
        if sensor == "step":
            if value != 1:
                fail(1, f"line {n}: step value {value_text!r}, expected 1")
            steps.append(ts)
        else:
            pressure.append((ts, value))
    return pressure, steps


def net_change(pressure):
    first_ts, last_ts = pressure[0][0], pressure[-1][0]
    window_ns = NET_WINDOW_S * 1e9
    head = [v for ts, v in pressure if ts - first_ts <= window_ns]
    tail = [v for ts, v in pressure if last_ts - ts <= window_ns]
    return sum(tail) / len(tail) - sum(head) / len(head)


def check_file(path):
    """Returns (failed checks as {number: reason}, is_synthetic)."""
    failed = {}

    def fail(check, reason):
        failed.setdefault(check, reason)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        return {1: f"unreadable: {e}"}, False
    table = list(csv.reader(lines))

    header_at = 0
    while header_at < len(table) and table[header_at] and table[header_at][0].startswith("#"):
        header_at += 1
    meta, synthetic = check_metadata(table[:header_at], fail)
    if header_at >= len(table) or table[header_at] != COLUMNS:
        fail(1, f"column header is not {','.join(COLUMNS)} (checks 2-8 not run)")
        return failed, synthetic
    pressure, steps = check_rows(table[header_at + 1 :], header_at + 2, fail)
    pressure.sort()
    steps.sort()
    label = meta.get("label") if meta.get("label") in LABELS else None

    # 2. Duration and gaps.
    if not pressure:
        fail(2, "no pressure rows")
    else:
        span = (pressure[-1][0] - pressure[0][0]) / 1e9
        gap = max(((b[0] - a[0]) / 1e9 for a, b in zip(pressure, pressure[1:])), default=0.0)
        if span < MIN_PRESSURE_S:
            fail(2, f"pressure spans {span:.2f} s, need {MIN_PRESSURE_S:g}")
        if gap > MAX_PRESSURE_GAP_S:
            fail(2, f"pressure gap of {gap:.2f} s")

    # 3. Sampling rate.
    if len(pressure) < 2 or pressure[-1][0] == pressure[0][0]:
        fail(3, "fewer than two pressure readings")
    else:
        rate = (len(pressure) - 1) / ((pressure[-1][0] - pressure[0][0]) / 1e9)
        if not PRESSURE_HZ[0] <= rate <= PRESSURE_HZ[1]:
            fail(3, f"pressure rate {rate:.1f} Hz")

    # 4. Pressure range.
    bad = [v for _, v in pressure if not PRESSURE_HPA[0] <= v <= PRESSURE_HPA[1]]
    if bad:
        fail(4, f"{len(bad)} pressure value(s) out of range, first {bad[0]:g} hPa")

    # 5. Steps for walking labels.
    if label in STEP_LABELS:
        if len(steps) < 2 or steps[-1] == steps[0]:
            fail(5, f"{len(steps)} step event(s), step rate needs at least 2")
        else:
            step_rate = (len(steps) - 1) / ((steps[-1] - steps[0]) / 1e9)
            if not STEP_HZ[0] <= step_rate <= STEP_HZ[1]:
                fail(5, f"step rate {step_rate:.2f} Hz")

    # 6 and 7. Net pressure change: stairs up and elevator up fall, stairs down rises.
    limits = {"stairs_up": (6, -1, STAIRS_NET_HPA), "stairs_down": (6, 1, STAIRS_NET_HPA),
              "elevator_up": (7, -1, ELEVATOR_NET_HPA)}.get(label)
    if limits:
        check, sign, (low, high) = limits
        if not pressure:
            fail(check, "no pressure rows")
        else:
            net = net_change(pressure)
            if net * sign <= 0 or not low <= abs(net) <= high:
                fail(check, f"net change {net:+.3f} hPa")

    # 8. has_barometer agrees with the pressure rows.
    if meta.get("has_barometer") in ("true", "false"):
        if (meta["has_barometer"] == "true") != bool(pressure):
            fail(8, f"has_barometer {meta['has_barometer']} with {len(pressure)} pressure rows")

    # 9. Pressure-steps match, the scoring rule: steps must fit the height change.
    if label in ("stairs_up", "stairs_down", "elevator_up", "walk_flat", "shake"):
        if not pressure:
            fail(9, "no pressure rows")
        else:
            ascent_m = -net_change(pressure) / HPA_PER_M  # pressure falls as height rises
            per_m = len(steps) / abs(ascent_m) if ascent_m else float("inf")
            if label in ("walk_flat", "shake"):
                if ascent_m >= FLAT_MAX_ASCENT_M:
                    fail(9, f"net ascent {ascent_m:.2f} m with {len(steps)} steps")
            elif label == "elevator_up":
                if per_m >= ELEVATOR_MAX_STEPS_PER_M:
                    fail(9, f"{len(steps)} steps over {ascent_m:+.2f} m ({per_m:.2f} per metre)")
            elif not STAIRS_STEPS_PER_M[0] <= per_m <= STAIRS_STEPS_PER_M[1]:
                fail(9, f"{len(steps)} steps over {ascent_m:+.2f} m ({per_m:.2f} per metre)")

    return failed, synthetic


def expand(paths):
    for path in paths:
        if path.is_dir():
            yield from sorted(p for p in path.glob("*.csv") if p.name != "labels.csv")
        else:
            yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, metavar="dir_or_file")
    paths = parser.parse_args().paths
    missing = [p for p in paths if not p.exists()]
    if missing:
        parser.error(f"not found: {', '.join(map(str, missing))}")

    any_failed = False
    for path in expand(paths):
        failed, synthetic = check_file(path)
        kind = "SYNTHETIC" if synthetic else "REAL"
        if failed:
            any_failed = True
            checks = ",".join(str(c) for c in sorted(failed))
            reasons = "; ".join(f"{c}: {failed[c]}" for c in sorted(failed))
            print(f"FAIL {checks:<9} {kind:<9} {path}  [{reasons}]")
        else:
            print(f"PASS {'':<9} {kind:<9} {path}")
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
