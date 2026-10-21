"""Generate synthetic sensor traces in the T4 export format.

These are test fixtures, not recordings. Every file says so in its name,
in its metadata (# synthetic,true; # device_model,SYNTHETIC) and in labels.csv.

Usage: python tools/synthetic_traces/generate.py [--out DIR]
Output is byte-identical across runs for the same SEED.
"""

import argparse
import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261021
GENERATOR = "tools/synthetic_traces/generate.py"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "fixtures" / "synthetic"

LABELS = ["stairs_up", "stairs_down", "elevator_up", "walk_flat", "shake", "blow"]
PLACEMENTS = ["pocket", "hand", "bag"]

DURATION_S = 30.0
PRESSURE_HZ = 50
HPA_PER_M = 0.12  # near sea level
FLOOR_M = 3.5
# Fixed so output does not depend on when the script runs.
BASE_START = datetime(2026, 10, 19, 9, 0, 0, tzinfo=timezone.utc)

NOISE_HPA = {"hand": 0.012, "pocket": 0.015, "bag": 0.02}
STEP_DROP = {"hand": 0.02, "pocket": 0.03, "bag": 0.12}
STEP_HZ = {"stairs_up": (1.4, 1.7), "stairs_down": (1.7, 2.1), "walk_flat": (1.7, 2.0)}


def stairs_height(rng, up):
    """Piecewise-linear height: a short walk-in, then half-floor flights split by landings."""
    speed = rng.uniform(0.45, 0.55) if up else rng.uniform(0.55, 0.65)
    flight_m = FLOOR_M / 2
    segments = [(rng.uniform(2.0, 4.0), 0.0)]  # (duration s, vertical speed m/s)
    while sum(d for d, _ in segments) < DURATION_S:
        segments.append((flight_m / speed, speed if up else -speed))
        segments.append((rng.uniform(1.5, 2.5), 0.0))

    def height(t):
        h, start = 0.0, 0.0
        for duration, v in segments:
            if t < start + duration:
                return h + v * (t - start)
            h += v * duration
            start += duration
        return h

    return height


def elevator_height(rng):
    wait = rng.uniform(4.0, 7.0)
    rise = rng.randint(3, 6) * FLOOR_M
    travel = rise / rng.uniform(1.0, 1.4)

    def height(t):
        x = min(max((t - wait) / travel, 0.0), 1.0)
        return rise * (3 * x * x - 2 * x * x * x)  # smoothstep: eased start and stop

    return height


def blow_bumps(rng):
    """Short positive pressure bumps from blowing on the sensor vent."""
    bumps = []
    for _ in range(rng.randint(2, 4)):
        bumps.append((rng.uniform(3.0, 26.0), rng.uniform(0.8, 2.0), rng.uniform(0.3, 1.2)))

    def extra(t):
        total = 0.0
        for start, duration, amplitude in bumps:
            if start <= t < start + duration:
                total += amplitude * math.sin(math.pi * (t - start) / duration)
        return total

    return extra


def pressure_rows(rng, label, placement):
    base = rng.uniform(1005.0, 1020.0)
    drift = rng.uniform(-0.002, 0.002)  # hPa/s, weather
    noise = NOISE_HPA[placement] * (3.0 if label == "shake" else 1.0)
    height = {
        "stairs_up": lambda r: stairs_height(r, up=True),
        "stairs_down": lambda r: stairs_height(r, up=False),
        "elevator_up": elevator_height,
    }.get(label, lambda r: (lambda t: 0.0))(rng)
    extra = blow_bumps(rng) if label == "blow" else (lambda t: 0.0)

    times = []
    t = rng.uniform(0.005, 0.02)
    while t < DURATION_S:
        times.append(t)
        t += 1 / PRESSURE_HZ + rng.gauss(0, 0.0004)
    clean = [base - HPA_PER_M * height(t) + drift * t + extra(t) for t in times]
    # The sensor's own low-pass filter; roughly 0.3 s.
    window = 15
    smooth = []
    for i in range(len(clean)):
        chunk = clean[max(0, i - window + 1) : i + 1]
        smooth.append(sum(chunk) / len(chunk))
    return [(t, "pressure", round(p + rng.gauss(0, noise), 4)) for t, p in zip(times, smooth)]


def step_rows(rng, label, placement):
    if label not in STEP_HZ:
        return []
    cadence = rng.uniform(*STEP_HZ[label])
    rows = []
    t = rng.uniform(0.5, 1.5)
    end = DURATION_S - rng.uniform(0.0, 1.0)
    while t < end:
        if rng.random() >= STEP_DROP[placement]:
            rows.append((t, "step", 1.0))
        t += (1 / cadence) * (1 + rng.gauss(0, 0.05))
    return rows


def iso_utc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def plan():
    """24 traces: every label with every placement, plus one extra placement per label."""
    for i, label in enumerate(LABELS):
        for placement in PLACEMENTS + [PLACEMENTS[i % len(PLACEMENTS)]]:
            yield label, placement


def write_trace(out_dir, index, label, placement):
    seed = SEED + index
    rng = random.Random(seed)
    start = BASE_START + timedelta(minutes=3 * index)
    start_elapsed_ns = rng.randint(100, 900) * 1_000_000_000 + rng.randint(0, 999_999_999)
    rows = sorted(pressure_rows(rng, label, placement) + step_rows(rng, label, placement))
    stop = start + timedelta(seconds=rows[-1][0] + 0.02)

    name = f"synthetic_{label}_{placement}_{start.strftime('%Y%m%dT%H%M%SZ')}.csv"
    metadata = [
        ("synthetic", "true"),
        ("generator", GENERATOR),
        ("seed", str(seed)),
        ("device_model", "SYNTHETIC"),
        ("has_barometer", "true"),
        ("label", label),
        ("placement", placement),
        ("start_utc", iso_utc(start)),
        ("stop_utc", iso_utc(stop)),
    ]
    with open(out_dir / name, "w", newline="\n", encoding="utf-8") as f:
        for key, value in metadata:
            f.write(f"# {key},{value}\n")
        f.write("sensor,timestamp_ns,elapsed_s,value\n")
        for t, sensor, value in rows:
            f.write(f"{sensor},{start_elapsed_ns + round(t * 1e9)},{t:.3f},{value}\n")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    out_dir = parser.parse_args().out
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("synthetic_*.csv"):
        old.unlink()

    entries = []
    for index, (label, placement) in enumerate(plan()):
        entries.append((write_trace(out_dir, index, label, placement), label, placement))

    with open(out_dir / "labels.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["file", "label", "placement", "device", "floor_range", "notes"])
        for name, label, placement in entries:
            writer.writerow([name, label, placement, "SYNTHETIC", "n/a", "synthetic"])
    print(f"wrote {len(entries)} traces and labels.csv to {out_dir}")


if __name__ == "__main__":
    main()
