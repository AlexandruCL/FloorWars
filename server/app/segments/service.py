"""The upload of a segment batch (Week 3 spec section 5).

One transaction per batch: lock the user, check the device, handle the items in ascending
``started_at``, recompute the owner of each affected building in ascending order, commit. Only then
the leaderboards are told, best effort: they can be rebuilt from the database, so a Valkey error
never fails the request.

Problem types: ``urn:floorwars:problem:device-unknown`` (403).

``Idempotency-Key`` is informational. Duplicates are decided per segment by ``segment_receipt``.
"""

import logging
import uuid
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from app import leaderboards
from app.api.problems import forbidden, service_unavailable, too_many_requests, unauthorized
from app.auth.ratelimit import RateLimiter
from app.segments import claim, repository, rules
from app.segments.models import (
    STATUS_REJECTED,
    STATUS_VERIFIED,
    Flip,
    ItemContext,
    Receipt,
    SegmentRow,
    VerifiedClimb,
)
from app.segments.schemas import (
    AcceptedSegment,
    BuildingFlip,
    RejectedSegment,
    Segment,
    SegmentBatch,
    SegmentBatchResult,
)
from app.valkey import ValkeyError

logger = logging.getLogger("floorwars.segments")

DEVICE_UNKNOWN = "urn:floorwars:problem:device-unknown"
HOUR_S = 3600
HOUR = timedelta(hours=1)
# Answer for a segment id that is already taken: by a receipt of another user on this device id, or
# by a stored row of any user. Only the caller's receipt is added. It shows nothing of the other
# upload, but it does tell someone holding the id, and its exact ``started_at`` for a stored row,
# that the id is taken.
ID_TAKEN_REASON: rules.RejectReason = "no_checkin"


@dataclass(frozen=True, slots=True)
class ScoredSegment:
    """What the leaderboards need to know about one newly verified segment."""

    season_id: int
    user_id: uuid.UUID
    team_id: int
    building_id: int
    points: int
    steps: int


class Leaderboards(Protocol):
    """Post-commit notifications. May raise ``ValkeyError``."""

    def record_verified(self, scored: ScoredSegment) -> None: ...

    def publish_flip(self, flip: Flip) -> None: ...

    def mark_stale(self, season_id: int) -> None: ...


class NoLeaderboards:
    """Default when Valkey is not configured."""

    def record_verified(self, scored: ScoredSegment) -> None:
        pass

    def publish_flip(self, flip: Flip) -> None:
        pass

    def mark_stale(self, season_id: int) -> None:
        pass


class ValkeyLeaderboards:
    """The boards and the flip events of ``app.leaderboards``."""

    def __init__(self, valkey: leaderboards.Commands) -> None:
        self._valkey = valkey

    def record_verified(self, scored: ScoredSegment) -> None:
        leaderboards.record_verified(
            self._valkey,
            scored.season_id,
            scored.user_id,
            scored.team_id,
            scored.building_id,
            scored.points,
        )

    def publish_flip(self, flip: Flip) -> None:
        leaderboards.publish_flip(self._valkey, flip)

    def mark_stale(self, season_id: int) -> None:
        leaderboards.mark_stale(self._valkey, season_id)


def enforce_upload_limit(limiter: RateLimiter | None, user_id: uuid.UUID) -> None:
    """One token from the user's upload bucket: 429 when empty, 503 without a limiter (fail
    closed: without it a client could upload without any limit)."""
    if limiter is None:
        logger.error("rate limiter not configured")
        raise service_unavailable("Uploads are temporarily unavailable.")
    try:
        decision = limiter.hit("seg:user", str(user_id), rules.UPLOADS_PER_HOUR, HOUR_S)
    except ValkeyError:
        logger.error("rate limiter unavailable")
        raise service_unavailable("Uploads are temporarily unavailable.") from None
    if not decision.allowed:
        logger.info("rate limited", extra={"limit": "seg:user"})
        raise too_many_requests("Too many uploads.", decision.retry_after_s)


class _RejectionBudget:
    """The user's ``seg:rej`` bucket for one batch. ``take()`` False means: answer the rejection
    but write nothing. After the first Valkey failure it stops calling Valkey (the batch holds the
    user's row lock) and answers False, so storage fails closed and a 503 cannot drop the verified
    items of the batch. ``limiter=None`` (direct callers; the route always passes one) is
    uncapped."""

    def __init__(self, limiter: RateLimiter | None, user_id: uuid.UUID) -> None:
        self._limiter = limiter
        self._subject = str(user_id)
        self._down = False
        self.capped = 0

    def take(self) -> bool:
        if self._limiter is None:
            return True
        allowed = False
        if not self._down:
            try:
                decision = self._limiter.hit(
                    "seg:rej", self._subject, rules.REJECTED_STORED_PER_HOUR, HOUR_S
                )
                allowed = decision.allowed
            except ValkeyError:
                self._down = True
                logger.error("rejection limiter unavailable")
        if not allowed:
            self.capped += 1
        return allowed


def _from_receipt(receipt: Receipt, user_id: uuid.UUID, result: SegmentBatchResult) -> None:
    """Answer a repeat from its stored outcome. A receipt of another user is not shown."""
    if receipt.user_id != user_id:
        result.rejected.append(RejectedSegment(id=receipt.id, reason=ID_TAKEN_REASON))
    elif receipt.status == STATUS_VERIFIED:
        result.accepted.append(AcceptedSegment(id=receipt.id, steps_scored=receipt.steps_scored))
    else:
        # A stored reason always comes from rules.check_item, so it is a valid RejectReason.
        result.rejected.append(
            RejectedSegment.model_validate({"id": receipt.id, "reason": receipt.reject_reason})
        )


def _row(
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: ItemContext,
    reason: rules.RejectReason | None,
    points: int,
) -> SegmentRow:
    # The rules passed 3 and 4 before any row is built, so the team and season exist.
    if ctx.team_id is None or ctx.season_id is None:
        raise RuntimeError("segment row without a team or season")
    return SegmentRow(
        id=item.id,
        device_id=device_id,
        user_id=user_id,
        team_id=ctx.team_id,
        season_id=ctx.season_id,
        checkin_id=item.checkin_id,
        building_id=item.building_id,
        status=STATUS_REJECTED if reason else STATUS_VERIFIED,
        reject_reason=reason,
        steps=item.steps,
        steps_scored=0 if reason else item.steps,
        points=points,
        ascent_m=item.ascent_m,
        duration_s=item.duration_s,
        vert_speed_mps=rules.storable_real(item.vert_speed_mps),
        stair_prob=rules.storable_real(item.stair_prob),
        classifier_version=item.classifier_version,
        started_at=item.started_at,
    )


def _answer(
    receipts: dict[uuid.UUID, Receipt],
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
    reason: rules.RejectReason | None,
    steps_scored: int,
) -> None:
    """Record a receipt for the one insert after the loop. The first answer for an id stays, as
    with ``ON CONFLICT DO NOTHING``; a repeat of the id later in the batch is answered from it."""
    receipts.setdefault(item.id, Receipt(device_id, item.id, user_id, status, reason, steps_scored))


def _id_taken(
    receipts: dict[uuid.UUID, Receipt],
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    result: SegmentBatchResult,
    store: bool = True,
) -> None:
    if store:
        _answer(receipts, item, device_id, user_id, STATUS_REJECTED, ID_TAKEN_REASON, 0)
    result.rejected.append(RejectedSegment(id=item.id, reason=ID_TAKEN_REASON))


def _hour(at: datetime) -> datetime:
    return at.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


class _Climbs:
    """The user's verified climbs that the batch reads, plus those it accepts. Each method answers
    what the repository function of the same name would, with the same bounds. Safe because only
    this user's batches write these rows, and they hold the user lock."""

    def __init__(self, climbs: list[VerifiedClimb]) -> None:
        self._climbs = climbs

    def add(self, climb: VerifiedClimb) -> None:
        self._climbs.append(climb)

    def _steps(self, low: datetime, high: datetime, *, from_low: bool = False) -> int:
        return sum(
            c.steps_scored
            for c in self._climbs
            if (c.started_at >= low if from_low else c.started_at > low) and c.started_at < high
        )

    def verified_steps_around(self, at: datetime) -> int:
        return self._steps(at - rules.RATE_WINDOW, at + rules.RATE_WINDOW)

    def verified_steps_before(self, at: datetime) -> int:
        return self._steps(at - rules.RATE_WINDOW, at)

    def verified_steps_in_hour(self, at: datetime) -> int:
        start = _hour(at)
        return self._steps(start, start + HOUR, from_low=True)

    def overlaps_verified(self, item: Segment, device_id: uuid.UUID | None = None) -> bool:
        end = item.started_at + timedelta(seconds=item.duration_s)
        return any(
            c.started_at > item.started_at - timedelta(seconds=rules.DURATION_MAX_S)
            and c.started_at < end - rules.OVERLAP_TOLERANCE
            and c.ends_at > item.started_at + rules.OVERLAP_TOLERANCE
            and (device_id is None or c.device_id == device_id)
            for c in self._climbs
        )


def _reads(item: Segment) -> tuple[datetime, datetime]:
    """The closed range of ``started_at`` that ``_Climbs`` reads for ``item``."""
    start = item.started_at
    hour = _hour(start)
    return (
        min(start - rules.RATE_WINDOW, start - timedelta(seconds=rules.DURATION_MAX_S), hour),
        max(start + rules.RATE_WINDOW, start + timedelta(seconds=item.duration_s), hour + HOUR),
    )


def _merged(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for low, high in sorted(ranges):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


_Check = tuple[rules.RejectReason | None, ItemContext | None]


def _check_rules(
    db: Session, items: dict[int, Segment], user_id: uuid.UUID, now: datetime
) -> dict[int, _Check]:
    """Rules 1 to 7 of each new item, with one context query. Bounds first: ``started_at`` is
    unsafe for date arithmetic until then. A reason of None means the item passed rules 1 to 7 (its
    context is then set); rules 8 and 9 need the user's climbs and run in the loop. Check-ins do not
    change during the batch (written under the user lock); a team join can (spec 5a)."""
    checks: dict[int, _Check] = {
        n: (rules.check_bounds(item, now), None) for n, item in items.items()
    }
    in_bounds = [n for n, (reason, _) in checks.items() if reason is None]
    contexts = repository.load_contexts(
        db, user_id, [(items[n].checkin_id, items[n].started_at) for n in in_bounds]
    )
    for n, ctx in zip(in_bounds, contexts, strict=True):
        checks[n] = (rules.check_state_and_physics(items[n], ctx, user_id), ctx)
    return checks


def _is_flagged(
    climbs: _Climbs, item: Segment, device_id: uuid.UUID, reason: rules.RejectReason
) -> bool:
    """Whether a rejection goes to review. Two reasons often hit honest users, so they are flagged
    only in their more suspicious case: climbs that started earlier already fill the cap, or one
    device recorded both overlapping climbs. A late upload and a second phone are rejected without
    a flag. Interim: a client that uploads newest first or uses a second device id also avoids the
    flag (it still scores nothing)."""
    if reason in rules.NOT_FRAUD:
        return False
    if reason == "rate_limit":
        return rules.over_step_cap(item, climbs.verified_steps_before(item.started_at))
    if reason == "overlap":
        return climbs.overlaps_verified(item, device_id)
    return True


def _reject(
    db: Session,
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: rules.RejectReason,
    ctx: ItemContext | None,
    result: SegmentBatchResult,
    budget: _RejectionBudget,
    climbs: _Climbs,
    receipts: dict[uuid.UUID, Receipt],
) -> None:
    if not budget.take():
        result.rejected.append(RejectedSegment(id=item.id, reason=reason))
        return
    if ctx is not None and reason not in rules.RECEIPT_ONLY:
        row = _row(item, device_id, user_id, ctx, reason, 0)
        if repository.insert_segment(db, row) is None:  # a concurrent upload stored this id first
            _id_taken(receipts, item, device_id, user_id, result)
            return
    if _is_flagged(climbs, item, device_id, reason):
        repository.add_fraud_flag(db, item.id, item.started_at, user_id, reason)
    _answer(receipts, item, device_id, user_id, STATUS_REJECTED, reason, 0)
    result.rejected.append(RejectedSegment(id=item.id, reason=reason))


def _accept(
    db: Session,
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: ItemContext,
    result: SegmentBatchResult,
    climbs: _Climbs,
    receipts: dict[uuid.UUID, Receipt],
) -> ScoredSegment | None:
    """Store and score a verified item. None when a concurrent upload stored this segment first:
    ``repository.stored_segments`` runs earlier, but holds no lock against other users."""
    points = claim.points_for(item.steps, climbs.verified_steps_in_hour(item.started_at))
    row = _row(item, device_id, user_id, ctx, None, points)
    ends_at = repository.insert_segment(db, row)
    if ends_at is None:
        _id_taken(receipts, item, device_id, user_id, result)
        return None
    climbs.add(VerifiedClimb(item.started_at, ends_at, item.steps, device_id))
    _answer(receipts, item, device_id, user_id, STATUS_VERIFIED, None, item.steps)
    result.accepted.append(AcceptedSegment(id=item.id, steps_scored=item.steps, points=points))
    return ScoredSegment(row.season_id, user_id, row.team_id, row.building_id, points, item.steps)


def _add_scores(db: Session, scored: list[ScoredSegment]) -> None:
    """One ``add_score`` per team and building, in ascending order, after all items.

    Teammates uploading at once lock the same score rows: taken item by item, in ``started_at``
    order, two batches could wait on each other (a deadlock would lose one batch). All score locks
    in one global order, before all claim locks, leave no cycle.
    """
    totals: defaultdict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0])
    for segment in scored:
        total = totals[(segment.season_id, segment.building_id, segment.team_id)]
        total[0] += segment.points
        total[1] += segment.steps
    for (season_id, building_id, team_id), (points, steps) in sorted(totals.items()):
        repository.add_score(db, season_id, building_id, team_id, points, steps)


def _notify(board: Leaderboards, scored: list[ScoredSegment], flips: list[Flip]) -> None:
    """Best effort: each loop stops at its first error, so a dead Valkey costs a few timeouts, not
    a hundred. A failed board update marks every season of the batch stale, so the next read
    rebuilds them."""
    try:
        for segment in scored:
            board.record_verified(segment)
    except Exception:
        logger.exception("leaderboard update failed", extra={"flips": len(flips)})
        for season_id in sorted({s.season_id for s in scored}):
            with suppress(Exception):  # unreachable: the marker's expiry bounds the drift
                board.mark_stale(season_id)
    try:
        for flip in flips:
            board.publish_flip(flip)
    except Exception:
        logger.exception("flip publish failed", extra={"flips": len(flips)})


def upload_batch(
    db: Session,
    user_id: uuid.UUID,
    batch: SegmentBatch,
    board: Leaderboards | None = None,
    now: datetime | None = None,
    limiter: RateLimiter | None = None,
) -> SegmentBatchResult:
    """Process one batch in one transaction and answer per item. ``limiter`` caps how many
    rejections are stored per user and hour; verified items never touch it. A rejection past the
    cap has no receipt, so a resend is judged again (it can change if the user's state did)."""
    now = now or datetime.now(UTC)
    if not repository.lock_user(db, user_id):
        raise unauthorized("Invalid or expired access token.")
    if not repository.device_belongs(db, user_id, batch.device_id):
        raise forbidden("This device is not registered to you.", type_=DEVICE_UNKNOWN)

    budget = _RejectionBudget(limiter, user_id)
    result = SegmentBatchResult(accepted=[], rejected=[], flips=[])
    scored: list[ScoredSegment] = []
    device_id = batch.device_id
    # A full order: two batches holding the same items lock their rows in the same order.
    items = sorted(batch.segments, key=lambda s: (s.started_at, s.id))
    # All reads happen here, once per batch (spec 5a); the loop below only writes.
    receipts = repository.get_receipts(db, device_id, {item.id for item in items})
    known = set(receipts)
    stored = repository.stored_segments(
        db, {(item.id, item.started_at) for item in items if item.id not in known}
    )
    checks = _check_rules(
        db,
        {
            n: item
            for n, item in enumerate(items)
            if item.id not in known and (item.id, item.started_at) not in stored
        },
        user_id,
        now,
    )
    passed = [_reads(items[n]) for n, (reason, _) in checks.items() if reason is None]
    # Only items that passed rules 1 to 7 read the user's climbs (spec section 5).
    climbs = _Climbs(repository.verified_climbs(db, user_id, _merged(passed)) if passed else [])

    for n, item in enumerate(items):
        receipt = receipts.get(item.id)
        if receipt is not None:  # stored before, or an earlier item of this batch with this id
            _from_receipt(receipt, user_id, result)
            continue
        # Before the rules: a resend of a stored segment is not a new climb, so it must not be
        # judged, flagged or counted against itself.
        if (item.id, item.started_at) in stored:
            _id_taken(receipts, item, device_id, user_id, result, budget.take())
            continue
        reason, ctx = checks[n]
        if reason is None:
            reason = rules.check_limits(
                item,
                recent_verified_steps=climbs.verified_steps_around(item.started_at),
                overlaps_verified=climbs.overlaps_verified(item),
            )
        if reason is not None:
            _reject(db, item, device_id, user_id, reason, ctx, result, budget, climbs, receipts)
            continue
        if ctx is None:
            raise RuntimeError("verified segment without a context")
        segment = _accept(db, item, device_id, user_id, ctx, result, climbs, receipts)
        if segment is not None:
            scored.append(segment)
    repository.insert_receipts(db, [r for i, r in receipts.items() if i not in known])

    if budget.capped:
        logger.warning(
            "rejection cap reached",
            extra={"limit": "seg:rej", "user_id": str(user_id), "capped": budget.capped},
        )
    _add_scores(db, scored)
    flips: list[Flip] = []
    for season_id, building_id in sorted({(s.season_id, s.building_id) for s in scored}):
        flip = claim.recompute_owner(db, season_id, building_id, now)
        if flip is not None:
            flips.append(flip)
    db.commit()

    _notify(board or NoLeaderboards(), scored, flips)
    result.flips = [
        BuildingFlip(building_id=f.building_id, from_team=f.from_code, to_team=f.to_code, at=f.at)
        for f in flips
    ]
    return result
