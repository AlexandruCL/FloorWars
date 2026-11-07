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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

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
# Answer for a segment id that is already taken by a receipt of another user, or by a stored row
# of another device. It says nothing about the other upload and changes nothing.
ID_TAKEN_REASON: rules.RejectReason = "no_checkin"


@dataclass(frozen=True, slots=True)
class ScoredSegment:
    """What the leaderboards need to know about one newly verified segment."""

    season_id: int
    user_id: uuid.UUID
    team_id: int
    building_id: int
    points: int


class Leaderboards(Protocol):
    """Post-commit notifications. May raise ``ValkeyError``."""

    def record_verified(self, scored: ScoredSegment) -> None: ...

    def publish_flip(self, flip: Flip) -> None: ...


class NoLeaderboards:
    """Default when Valkey is not configured."""

    def record_verified(self, scored: ScoredSegment) -> None:
        pass

    def publish_flip(self, flip: Flip) -> None:
        pass


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
        stair_prob=item.stair_prob,
        classifier_version=item.classifier_version,
        started_at=item.started_at,
    )


def _check(
    db: Session, item: Segment, user_id: uuid.UUID, now: datetime
) -> tuple[rules.RejectReason | None, ItemContext | None]:
    """The rule outcome. Bounds first: ``started_at`` is unsafe for date arithmetic until then."""
    reason = rules.check_bounds(item, now)
    if reason is not None:
        return reason, None
    ctx = repository.load_context(db, user_id, item.checkin_id, item.started_at)
    recent = repository.verified_steps_between(
        db, user_id, item.started_at - rules.RATE_WINDOW, item.started_at
    )
    reason = rules.check_item(item, ctx, user_id=user_id, now=now, recent_verified_steps=recent)
    return reason, ctx


def _reject(
    db: Session,
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: rules.RejectReason,
    ctx: ItemContext | None,
    result: SegmentBatchResult,
) -> None:
    if ctx is not None and reason not in rules.RECEIPT_ONLY:
        repository.insert_segment(db, _row(item, device_id, user_id, ctx, reason, 0))
    if reason not in rules.NOT_FRAUD:
        repository.add_fraud_flag(db, item.id, item.started_at, user_id, reason)
    repository.insert_receipt(db, device_id, item.id, user_id, STATUS_REJECTED, reason, 0)
    result.rejected.append(RejectedSegment(id=item.id, reason=reason))


def _accept(
    db: Session,
    item: Segment,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: ItemContext,
    result: SegmentBatchResult,
) -> ScoredSegment | None:
    """Store and score a verified item. None when another device already stored this segment."""
    prior = repository.verified_steps_between(
        db, user_id, item.started_at - rules.POINTS_WINDOW, item.started_at
    )
    points = claim.points_for(item.steps, prior)
    row = _row(item, device_id, user_id, ctx, None, points)
    if not repository.insert_segment(db, row):
        repository.insert_receipt(
            db, device_id, item.id, user_id, STATUS_REJECTED, ID_TAKEN_REASON, 0
        )
        result.rejected.append(RejectedSegment(id=item.id, reason=ID_TAKEN_REASON))
        return None
    repository.add_score(db, row.season_id, row.building_id, row.team_id, points, item.steps)
    repository.insert_receipt(db, device_id, item.id, user_id, STATUS_VERIFIED, None, item.steps)
    result.accepted.append(AcceptedSegment(id=item.id, steps_scored=item.steps, points=points))
    return ScoredSegment(row.season_id, user_id, row.team_id, row.building_id, points)


def _notify(board: Leaderboards, scored: list[ScoredSegment], flips: list[Flip]) -> None:
    """Best effort: stop at the first error, so a dead Valkey costs one timeout, not a hundred."""
    try:
        for segment in scored:
            board.record_verified(segment)
        for flip in flips:
            board.publish_flip(flip)
    except ValkeyError:
        logger.warning("leaderboard update failed", extra={"flips": len(flips)})


def upload_batch(
    db: Session,
    user_id: uuid.UUID,
    batch: SegmentBatch,
    board: Leaderboards | None = None,
    now: datetime | None = None,
) -> SegmentBatchResult:
    """Process one batch in one transaction and answer per item."""
    now = now or datetime.now(UTC)
    if not repository.lock_user(db, user_id):
        raise unauthorized("Invalid or expired access token.")
    if not repository.device_belongs(db, user_id, batch.device_id):
        raise forbidden("This device is not registered to you.", type_=DEVICE_UNKNOWN)

    result = SegmentBatchResult(accepted=[], rejected=[], flips=[])
    scored: list[ScoredSegment] = []
    for item in sorted(batch.segments, key=lambda s: s.started_at):
        receipt = repository.get_receipt(db, batch.device_id, item.id)
        if receipt is not None:
            _from_receipt(receipt, user_id, result)
            continue
        reason, ctx = _check(db, item, user_id, now)
        if reason is not None:
            _reject(db, item, batch.device_id, user_id, reason, ctx, result)
            continue
        if ctx is None:
            raise RuntimeError("verified segment without a context")
        segment = _accept(db, item, batch.device_id, user_id, ctx, result)
        if segment is not None:
            scored.append(segment)

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
