"""Post fake climb segments to POST /segments, with no phone.

Fakes for week 1 (plan section 9.2): Ionut tests the server, Cristea drives the UI against Prism.
Segments follow the contract's Segment schema (contracts/openapi.yaml, 0.2.0-draft) and stay
inside its bounds, so a server rejects the bad kinds per item, never with 422.

Kinds:
  stairs    pass the scoring rule (plan 3.3): 4-8 steps per metre, 0.1-0.9 m/s, 5 s to 3 min.
  elevator  fast ascent (> 1.0 m/s) with fewer than 1 step per metre. Scores 0.
  shake     a small ascent (>= 2.0 m) with far more than 8 steps per metre. Scores 0.
  mixed     a seeded mix of the three.

Usage: python tools/fake_segments/fake_segments.py --count 5 --batch-size 5
       python tools/fake_segments/fake_segments.py --dry-run --count 3 --seed 1
Output with --seed is identical across runs (ids, keys and, unless --start is given, times).
Standard library only.
"""

import argparse
import http.client
import json
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

# Prism's default port. Prism ignores the /v1 base path of the contract's servers entry and
# serves the paths at the root, so the mock base has no /v1. A real server takes .../v1.
DEFAULT_BASE_URL = "http://127.0.0.1:4010"
DEFAULT_TOKEN = "prism-dummy-token"  # Prism only checks that a bearer token is present
TOKEN_ENV = "FLOORWARS_TOKEN"
CLASSIFIER_VERSION = "rules-1"
KINDS = ("stairs", "elevator", "shake", "mixed")
CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 20.0
MAX_BATCH = 100  # SegmentBatch.maxItems in the contract
# Fixed start for seeded runs so output does not depend on when the script runs.
SEEDED_START = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)

# Contract bounds (Segment schema) and starting thresholds (plan 2 and 3.3). Mirrors the rule;
# the server is the authority.
ASCENT_MIN_M, ASCENT_MAX_M = 2.0, 120.0
STEPS_MIN, STEPS_MAX = 1, 2000
STEPS_PER_M_MIN, STEPS_PER_M_MAX = 4.0, 8.0
SPEED_MIN_MPS, SPEED_MAX_MPS = 0.1, 0.9
DURATION_MIN_S, DURATION_MAX_S = 5.0, 180.0
# The plan does not set a cadence limit yet; keep generated stairs at a human step rate.
STAIRS_MAX_CADENCE_HZ = 3.0


def make_uuid(rng):
    """A version-4 UUID drawn from rng, so seeded runs repeat."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def iso(ts):
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stairs_values(rng):
    ascent = round(rng.uniform(ASCENT_MIN_M, 30.0), 1)
    steps_per_m = rng.uniform(5.0, 7.0)
    steps = round(ascent * steps_per_m)
    # Speed 0.2-0.7 m/s, narrowed so the window is 5-180 s and the cadence stays human.
    lo = max(0.2, ascent / DURATION_MAX_S)
    hi = min(0.7, ascent / DURATION_MIN_S, STAIRS_MAX_CADENCE_HZ / steps_per_m)
    speed = rng.uniform(lo, hi)
    duration = round(ascent / speed, 1)
    return ascent, duration, steps, round(rng.uniform(0.8, 0.99), 2)


def _elevator_values(rng):
    ascent = round(rng.uniform(6.0, 40.0), 1)
    speed = rng.uniform(1.2, 2.5)
    duration = round(ascent / speed, 1)
    steps = max(
        STEPS_MIN, round(ascent * rng.uniform(0.0, 0.5))
    )  # under 1 step per metre
    return ascent, duration, steps, round(rng.uniform(0.01, 0.2), 2)


def _shake_values(rng):
    ascent = round(rng.uniform(ASCENT_MIN_M, 2.6), 1)  # schema minimum, so not a 422
    duration = round(rng.uniform(30.0, 120.0), 1)
    steps = round(ascent * rng.uniform(20.0, 60.0))  # far above 8 steps per metre
    return ascent, duration, steps, round(rng.uniform(0.05, 0.4), 2)


_VALUES = {
    "stairs": _stairs_values,
    "elevator": _elevator_values,
    "shake": _shake_values,
}


def make_segment(kind, rng, *, checkin_id, building_id, started_at):
    """One Segment request item of the given kind ('stairs', 'elevator' or 'shake')."""
    if kind not in _VALUES:
        raise ValueError(f"unknown segment kind: {kind}")
    ascent, duration, steps, stair_prob = _VALUES[kind](rng)
    return {
        "id": make_uuid(rng),
        "checkin_id": checkin_id,
        "started_at": iso(started_at),
        "building_id": building_id,
        "ascent_m": ascent,
        "duration_s": duration,
        "vert_speed_mps": round(ascent / duration, 3),
        "steps": steps,
        "stair_prob": stair_prob,
        "classifier_version": CLASSIFIER_VERSION,
    }


def pick_kind(kind, rng):
    if kind != "mixed":
        return kind
    return rng.choices(("stairs", "elevator", "shake"), weights=(6, 2, 2))[0]


def make_segments(kind, rng, *, count, checkin_id, building_id, start):
    """count segments in time order, each starting after the previous one ends plus a short gap."""
    segments = []
    t = start
    for _ in range(count):
        seg = make_segment(
            pick_kind(kind, rng),
            rng,
            checkin_id=checkin_id,
            building_id=building_id,
            started_at=t,
        )
        segments.append(seg)
        t += timedelta(seconds=seg["duration_s"] + rng.uniform(20.0, 120.0))
    return segments


def make_batches(segments, batch_size, rng):
    """Split into SegmentBatch bodies, each with a new Idempotency-Key."""
    if not 1 <= batch_size <= MAX_BATCH:
        raise ValueError(f"batch size must be 1 to {MAX_BATCH}")
    return [
        {
            "idempotency_key": make_uuid(rng),
            "body": {"segments": segments[i : i + batch_size]},
        }
        for i in range(0, len(segments), batch_size)
    ]


def make_batch(kind, rng, *, count, checkin_id, building_id, start):
    """A single SegmentBatch body with count segments."""
    segs = make_segments(
        kind,
        rng,
        count=count,
        checkin_id=checkin_id,
        building_id=building_id,
        start=start,
    )
    return {"segments": segs}


def passes_scoring_rule(seg):
    """True if a segment would score under the starting thresholds (plan 3.3)."""
    ascent, steps, duration = seg["ascent_m"], seg["steps"], seg["duration_s"]
    return (
        ASCENT_MIN_M <= ascent <= ASCENT_MAX_M
        and STEPS_MIN <= steps <= STEPS_MAX
        and STEPS_PER_M_MIN <= steps / ascent <= STEPS_PER_M_MAX
        and SPEED_MIN_MPS <= seg["vert_speed_mps"] <= SPEED_MAX_MPS
        and DURATION_MIN_S <= duration <= DURATION_MAX_S
    )


def post_batch(base_url, token, key, body):
    """POST one batch. Returns (status, parsed JSON or raw text). Connect 10 s, read 20 s."""
    parts = urlsplit(base_url.rstrip("/") + "/segments")
    conn_cls = (
        http.client.HTTPSConnection
        if parts.scheme == "https"
        else http.client.HTTPConnection
    )
    conn = conn_cls(parts.hostname, parts.port, timeout=CONNECT_TIMEOUT_S)
    try:
        conn.connect()
        conn.sock.settimeout(READ_TIMEOUT_S)
        payload = json.dumps(body).encode("utf-8")
        conn.request(
            "POST",
            parts.path,
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, application/problem+json",
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": key,
            },
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = raw
        return resp.status, data
    finally:
        conn.close()


def summarize(label, status, data):
    if isinstance(data, dict) and status == 200:
        counts = " ".join(
            f"{k}={len(data.get(k) or [])}" for k in ("accepted", "rejected", "flips")
        )
        reasons = sorted({r.get("reason", "?") for r in data.get("rejected") or []})
        extra = f" reasons={','.join(reasons)}" if reasons else ""
        return f"{label} status={status} {counts}{extra}"
    if isinstance(data, dict):
        detail = data.get("title") or data.get("detail") or ""
        return f"{label} status={status} error={detail!r}"
    return f"{label} status={status} body={str(data)[:200]!r}"


def parse_start(value, seeded):
    if value is None:
        return SEEDED_START if seeded else datetime.now(UTC).replace(microsecond=0)
    if value == "now":
        return datetime.now(UTC).replace(microsecond=0)
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def build_parser():
    p = argparse.ArgumentParser(
        description="Post fake climb segments to POST /segments."
    )
    p.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base (default {DEFAULT_BASE_URL})",
    )
    p.add_argument(
        "--token",
        default=None,
        help=f"bearer token (default: ${TOKEN_ENV} or a Prism dummy)",
    )
    p.add_argument(
        "--building-id",
        type=int,
        default=1,
        help="building of the check-in (default 1)",
    )
    p.add_argument("--checkin-id", default=None, help="check-in UUID (default: random)")
    p.add_argument(
        "--count", type=int, default=5, help="segments to generate (default 5)"
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help=f"segments per request, 1-{MAX_BATCH}",
    )
    p.add_argument("--seed", type=int, default=None, help="seed for a reproducible run")
    p.add_argument(
        "--kind", choices=KINDS, default="stairs", help="segment kind (default stairs)"
    )
    p.add_argument(
        "--start",
        default=None,
        help="first started_at: ISO time or 'now' "
        "(default now; with --seed a fixed 2026-11-02T10:00:00Z)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the batches as JSON, send nothing"
    )
    p.add_argument(
        "--repeat-last",
        action="store_true",
        help="resend the last batch with the same Idempotency-Key",
    )
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.count < 1:
        print("--count must be at least 1", file=sys.stderr)
        return 2
    if not 1 <= args.batch_size <= MAX_BATCH:
        print(f"--batch-size must be 1 to {MAX_BATCH}", file=sys.stderr)
        return 2
    if args.building_id < 1:
        print("--building-id must be at least 1", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    checkin_id = args.checkin_id or make_uuid(rng)
    start = parse_start(args.start, args.seed is not None)
    segments = make_segments(
        args.kind,
        rng,
        count=args.count,
        checkin_id=checkin_id,
        building_id=args.building_id,
        start=start,
    )
    batches = make_batches(segments, args.batch_size, rng)

    if args.dry_run:
        print(json.dumps({"batches": batches}, indent=2))
        return 0

    token = args.token or os.environ.get(TOKEN_ENV) or DEFAULT_TOKEN
    sends = [(f"batch {i}/{len(batches)}", b) for i, b in enumerate(batches, 1)]
    if args.repeat_last:
        sends.append(("repeat of last batch", batches[-1]))
    for label, batch in sends:
        key = batch["idempotency_key"]
        try:
            status, data = post_batch(args.base_url, token, key, batch["body"])
        except OSError as exc:  # connection refused, timeout, DNS
            print(f"{label} key={key} failed: {exc}", file=sys.stderr)
            return 2
        print(f"{summarize(label, status, data)} key={key}")
        if status >= 400:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
