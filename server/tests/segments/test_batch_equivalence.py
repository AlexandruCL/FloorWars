"""Finding 9: the batched ``upload_batch`` answers and writes exactly what the old per-item one did.

``_old_upload_batch`` is the per-item path of e34ea96, kept here as the reference. Each random
scenario runs old then new from the same committed state (each in a rolled-back savepoint) and
compares the result and every table the upload writes.
"""

import json
import random
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.api.problems import forbidden, unauthorized
from app.auth.ratelimit import Decision
from app.segments import claim, repository, rules, service
from app.segments.models import STATUS_REJECTED, STATUS_VERIFIED, Flip, ItemContext
from app.segments.schemas import (
    AcceptedSegment,
    BuildingFlip,
    RejectedSegment,
    SegmentBatch,
    SegmentBatchResult,
)
from app.segments.service import (
    ID_TAKEN_REASON,
    ScoredSegment,
    _add_scores,
    _from_receipt,
    _RejectionBudget,
    _row,
)
from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import World, clock_hour, make_world, utcnow

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")

SEED = 20260509
SCENARIOS = 30
TABLES = (
    "climb_segment",
    "segment_receipt",
    "fraud_flag",
    "team_building_score",
    "building_claim",
    "game_event",
)
# Set by the database clock or a sequence, not by the upload.
VOLATILE = {"received_at", "created_at", "updated_at"}
SERIAL_ID_TABLES = {"fraud_flag", "game_event"}


@pytest.fixture(autouse=True)
def _leave_database_empty(clean: None) -> Iterator[None]:
    yield
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text('TRUNCATE team, season, building, "user" RESTART IDENTITY CASCADE'))
    finally:
        engine.dispose()


# ---- the reference: per-item path of e34ea96 -------------------------------------------------


def _id_taken(db, item, device_id, user_id, result, store=True):  # type: ignore[no-untyped-def]
    if store:
        repository.insert_receipt(
            db, device_id, item.id, user_id, STATUS_REJECTED, ID_TAKEN_REASON, 0
        )
    result.rejected.append(RejectedSegment(id=item.id, reason=ID_TAKEN_REASON))


def _check(db, item, user_id, now):  # type: ignore[no-untyped-def]
    reason = rules.check_bounds(item, now)
    if reason is not None:
        return reason, None
    ctx = repository.load_context(db, user_id, item.checkin_id, item.started_at)
    reason = rules.check_state_and_physics(item, ctx, user_id)
    if reason is not None:
        return reason, ctx
    recent = repository.verified_steps_around(db, user_id, item.started_at, rules.RATE_WINDOW)
    overlaps = repository.overlaps_verified(db, user_id, item.started_at, item.duration_s)
    reason = rules.check_limits(item, recent_verified_steps=recent, overlaps_verified=overlaps)
    return reason, ctx


def _is_flagged(db, item, device_id, user_id, reason):  # type: ignore[no-untyped-def]
    if reason in rules.NOT_FRAUD:
        return False
    if reason == "rate_limit":
        earlier = repository.verified_steps_before(db, user_id, item.started_at, rules.RATE_WINDOW)
        return rules.over_step_cap(item, earlier)
    if reason == "overlap":
        return repository.overlaps_verified(
            db, user_id, item.started_at, item.duration_s, device_id=device_id
        )
    return True


def _reject(db, item, device_id, user_id, reason, ctx, result, budget):  # type: ignore[no-untyped-def]
    if not budget.take():
        result.rejected.append(RejectedSegment(id=item.id, reason=reason))
        return
    if ctx is not None and reason not in rules.RECEIPT_ONLY:
        row = _row(item, device_id, user_id, ctx, reason, 0)
        if not repository.insert_segment(db, row):
            _id_taken(db, item, device_id, user_id, result)
            return
    if _is_flagged(db, item, device_id, user_id, reason):
        repository.add_fraud_flag(db, item.id, item.started_at, user_id, reason)
    repository.insert_receipt(db, device_id, item.id, user_id, STATUS_REJECTED, reason, 0)
    result.rejected.append(RejectedSegment(id=item.id, reason=reason))


def _accept(db, item, device_id, user_id, ctx: ItemContext, result):  # type: ignore[no-untyped-def]
    hour_steps = repository.verified_steps_in_hour(db, user_id, item.started_at)
    points = claim.points_for(item.steps, hour_steps)
    row = _row(item, device_id, user_id, ctx, None, points)
    if not repository.insert_segment(db, row):
        _id_taken(db, item, device_id, user_id, result)
        return None
    repository.insert_receipt(db, device_id, item.id, user_id, STATUS_VERIFIED, None, item.steps)
    result.accepted.append(AcceptedSegment(id=item.id, steps_scored=item.steps, points=points))
    return ScoredSegment(row.season_id, user_id, row.team_id, row.building_id, points, item.steps)


def _old_upload_batch(db, user_id, batch, now, limiter):  # type: ignore[no-untyped-def]
    if not repository.lock_user(db, user_id):
        raise unauthorized("Invalid or expired access token.")
    if not repository.device_belongs(db, user_id, batch.device_id):
        raise forbidden("This device is not registered to you.", type_=service.DEVICE_UNKNOWN)
    budget = _RejectionBudget(limiter, user_id)
    result = SegmentBatchResult(accepted=[], rejected=[], flips=[])
    scored: list[ScoredSegment] = []
    for item in sorted(batch.segments, key=lambda s: (s.started_at, s.id)):
        receipt = repository.get_receipt(db, batch.device_id, item.id)
        if receipt is not None:
            _from_receipt(receipt, user_id, result)
            continue
        if repository.segment_exists(db, item.id, item.started_at):
            _id_taken(db, item, batch.device_id, user_id, result, budget.take())
            continue
        reason, ctx = _check(db, item, user_id, now)
        if reason is not None:
            _reject(db, item, batch.device_id, user_id, reason, ctx, result, budget)
            continue
        assert ctx is not None
        segment = _accept(db, item, batch.device_id, user_id, ctx, result)
        if segment is not None:
            scored.append(segment)
    _add_scores(db, scored)
    flips: list[Flip] = []
    for season_id, building_id in sorted({(s.season_id, s.building_id) for s in scored}):
        flip = claim.recompute_owner(db, season_id, building_id, now)
        if flip is not None:
            flips.append(flip)
    db.commit()
    result.flips = [
        BuildingFlip(building_id=f.building_id, from_team=f.from_code, to_team=f.to_code, at=f.at)
        for f in flips
    ]
    return result


# ---- scenario generation ----------------------------------------------------------------------


class _Limiter:
    """Allows the first ``allowed`` ``seg:rej`` hits, then denies. Counts the denials."""

    def __init__(self, allowed: int) -> None:
        self.left = allowed
        self.denied = 0

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        if name != "seg:rej":
            return Decision(allowed=True, retry_after_s=0)
        self.left -= 1
        if self.left < 0:
            self.denied += 1
        return Decision(allowed=self.left >= 0, retry_after_s=60)


def _item(start: datetime, n_steps: int = 60, **over: Any) -> dict[str, Any]:
    ascent = n_steps / 5
    return {
        "id": str(uuid.uuid4()),
        "started_at": start.isoformat(),
        "ascent_m": ascent,
        "duration_s": ascent / 0.4,
        "vert_speed_mps": 0.4,
        "steps": n_steps,
        "stair_prob": 0.9,
        "classifier_version": "rules-1",
        **over,
    }


def _start(item: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(item["started_at"])


class _Gen:
    def __init__(self, rng: random.Random, base: datetime, now: datetime) -> None:
        self.rng, self.base, self.now = rng, base, now

    def when(self) -> datetime:
        # Around a UTC clock-hour boundary, whole seconds.
        return self.base + timedelta(seconds=self.rng.randint(-2400, 2400))

    def simple(self, kind: str, ref: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        r, t = self.rng, self.when()
        steps = r.choice([20, 60, 100, 200, 300])
        match kind:
            case "speed":
                return [_item(t, steps, vert_speed_mps=0.05)]
            case "pressure":
                return [_item(t, 60, steps=400)]
            case "cadence":
                return [_item(t, 60, steps=60, ascent_m=6.0, duration_s=15.0, vert_speed_mps=0.4)]
            case "steps_range":
                return [_item(t, 60, steps=0)]
            case "ascent_range":
                return [_item(t, 60, ascent_m=500.0)]
            case "duration":
                return [_item(t, 60, duration_s=1.0)]
            case "stair_prob":
                return [_item(t, 60, stair_prob=2.0)]
            case "started_at_range":
                return [_item(self.now - timedelta(days=r.choice([8, 30])))]
            case "future":
                return [_item(self.now + timedelta(hours=1))]
            case "mismatch":
                return [_item(t, steps, building_id=999_999)]
            case "unknown_checkin":
                return [_item(t, steps, checkin_id=str(uuid.uuid4()))]
            case "cluster":  # 300-step climbs 160 s apart: the 600 steps/10 min cap, both sides
                c = self.when()
                return [_item(c + timedelta(seconds=160 * i), 300) for i in range(r.randint(3, 6))]
            case "overlap" if ref is not None:
                return [_item(_start(ref) + timedelta(seconds=r.randint(-10, 20)), 60)]
            case "equal_start" if ref is not None:
                return [_item(_start(ref), steps)]
        return [_item(t, steps)]  # "verified" and anything without a reference


KINDS = (
    ["verified"] * 12
    + ["speed", "pressure", "cadence", "steps_range", "ascent_range", "duration", "stair_prob"]
    + ["started_at_range", "future", "mismatch", "unknown_checkin", "cluster", "cluster"]
    + ["foreign_checkin", "overlap", "overlap_hist", "equal_start", "resend", "dup_same"]
    + ["dup_diff", "other_same", "other_diff"]
)
HISTORY_KINDS = KINDS[:21]  # the kinds that need no reference


def _add(
    items: list[dict[str, Any]], kinds: dict[str, list[str]], kind: str, new: list[dict[str, Any]]
) -> None:
    items.extend(new)
    for i in new:
        kinds.setdefault(i["id"], []).append(kind)


def _snapshot(db: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for table in TABLES:
        rows = db.execute(text(f"SELECT to_jsonb(t) FROM {table} t")).scalars().all()  # noqa: S608
        clean = []
        for row in rows:
            row = {k: v for k, v in row.items() if k not in VOLATILE}
            if table in SERIAL_ID_TABLES:
                row.pop("id", None)
            clean.append(json.dumps(row, sort_keys=True))
        out[table] = sorted(clean)
    return out


def _new_upload(
    db: Session, user_id: uuid.UUID, batch: SegmentBatch, now: datetime, lim: Any
) -> SegmentBatchResult:
    return service.upload_batch(db, user_id, batch, now=now, limiter=lim)


def _run(engine: Any, runner: Callable[..., SegmentBatchResult], *args: Any) -> tuple[Any, Any]:
    """Run in a savepoint of an outer transaction that is rolled back: ``db.commit()`` releases
    the savepoint, the snapshot sees the result, the database is left as it was."""
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
                result = runner(db, *args)
                return result.model_dump(mode="json"), _snapshot(db)
        finally:
            outer.rollback()


def test_old_and_new_upload_agree(make_app: Callable[..., TestClient]) -> None:
    client = make_app()
    world: World = make_world(client)
    sessionmaker = client.app.state.sessionmaker  # type: ignore[attr-defined]
    engine = sessionmaker.kw["bind"]
    rng = random.Random(SEED)  # noqa: S311
    seen: Counter[str] = Counter()

    for n in range(SCENARIOS):
        now = utcnow()
        gen = _Gen(rng, clock_hour(1), now)
        window = Range(now - timedelta(hours=3), now + timedelta(hours=1))
        user = world.climber(team=rng.choice(["AC", "ETC"]), valid_during=window)
        other = world.climber(team=rng.choice(["AC", "ETC"]), valid_during=window)
        devices = [user.device_id, uuid.UUID(world.second_device(user))]

        def make_batch(
            device: uuid.UUID, items: list[dict[str, Any]], who: Any = user
        ) -> SegmentBatch:
            segs = [
                {"checkin_id": str(who.checkin_id), "building_id": who.building_id, **i}
                for i in items
            ]
            return SegmentBatch.model_validate({"device_id": device, "segments": segs})

        # Earlier history, committed: the user's on either device, and another user's.
        pool: list[dict[str, Any]] = []
        for _ in range(rng.choice([0, 1, 2])):
            hist = [
                i for _ in range(rng.randint(3, 25)) for i in gen.simple(rng.choice(HISTORY_KINDS))
            ][:100]
            with sessionmaker() as db:
                service.upload_batch(
                    db, user.user_id, make_batch(rng.choice(devices), hist), now=now
                )
            pool += hist
        other_pool = [i for _ in range(rng.randint(0, 6)) for i in gen.simple("verified")]
        if other_pool:
            with sessionmaker() as db:
                service.upload_batch(
                    db, other.user_id, make_batch(other.device_id, other_pool, other), now=now
                )

        # The batch under test.
        items: list[dict[str, Any]] = []
        kinds: dict[str, list[str]] = {}

        for _ in range(rng.randint(1, 100)):
            kind = rng.choice(KINDS)
            ref = rng.choice(items) if items else None
            if kind == "foreign_checkin":
                _add(
                    items,
                    kinds,
                    kind,
                    [{**gen.simple("verified")[0], "checkin_id": str(other.checkin_id)}],
                )
            elif kind == "overlap_hist" and pool:
                _add(items, kinds, kind, gen.simple("overlap", rng.choice(pool)))
            elif kind == "resend" and pool:
                old = rng.choice(pool)
                _add(
                    items, kinds, kind, [{**old, "steps": 70} if rng.random() < 0.2 else dict(old)]
                )
            elif kind == "dup_same" and ref:
                _add(items, kinds, kind, [dict(ref)])
            elif kind == "dup_diff" and ref:
                _add(
                    items,
                    kinds,
                    kind,
                    [{**ref, "started_at": (_start(ref) + timedelta(seconds=7)).isoformat()}],
                )
            elif kind in ("other_same", "other_diff") and other_pool:
                o = dict(rng.choice(other_pool))
                if kind == "other_diff":
                    o["started_at"] = (_start(o) + timedelta(seconds=9)).isoformat()
                _add(items, kinds, kind, [o])
            else:
                _add(items, kinds, kind, gen.simple(kind, ref))
        items = items[:100]
        rng.shuffle(items)
        batch = make_batch(rng.choice(devices), items)
        allowed = rng.choice([None, 0, 3, 8, 30])

        old_lim, new_lim = (
            (None, None) if allowed is None else (_Limiter(allowed), _Limiter(allowed))
        )
        old_result, old_snap = _run(engine, _old_upload_batch, user.user_id, batch, now, old_lim)
        new_result, new_snap = _run(engine, _new_upload, user.user_id, batch, now, new_lim)
        assert old_result == new_result, f"scenario {n}: result differs"
        for table in TABLES:
            assert old_snap[table] == new_snap[table], f"scenario {n}: {table} differs"
        if old_lim is not None and new_lim is not None:
            assert old_lim.denied == new_lim.denied, f"scenario {n}: cap hits differ"
            seen["capped"] += old_lim.denied

        # Coverage, from the old run.
        uid = str(user.user_id)
        rows = [json.loads(s) for s in old_snap["climb_segment"]]
        flags = [json.loads(s) for s in old_snap["fraud_flag"]]
        mine = [r for r in rows if r["user_id"] == uid]
        seen["verified"] += len(old_result["accepted"])
        seen["halved"] += sum(r["status"] == "verified" and r["points"] < r["steps"] for r in mine)
        for reason in ("rate_limit", "overlap"):
            stored = sum(r["reject_reason"] == reason for r in mine)
            flagged = sum(f["user_id"] == uid and f["rule"] == reason for f in flags)
            seen[f"{reason}_flagged"] += flagged
            seen[f"{reason}_unflagged"] += stored - flagged
        answered = Counter(a["id"] for a in old_result["accepted"])
        answered.update(r["id"] for r in old_result["rejected"])
        by_id = {r["id"]: r["reason"] for r in old_result["rejected"]}
        for item_id, ks in kinds.items():
            if len(ks) > 1:
                seen["in_batch_dup"] += answered[item_id] >= 2
            if any(k.startswith("other") for k in ks) and by_id.get(item_id) == "no_checkin":
                seen["id_taken_no_checkin"] += 1
            if "resend" in ks and answered[item_id]:
                seen["resend"] += 1

    print(f"\nseed={SEED} scenarios={SCENARIOS} coverage={dict(seen)}")
    for key in (
        "verified",
        "rate_limit_flagged",
        "rate_limit_unflagged",
        "overlap_flagged",
        "overlap_unflagged",
        "id_taken_no_checkin",
        "resend",
        "in_batch_dup",
        "capped",
        "halved",
    ):
        assert seen[key] > 0, f"never exercised: {key} ({dict(seen)})"
