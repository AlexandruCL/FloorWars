"""``POST /v1/landing-scans`` (W4-4): a stair sticker scan worth ``LANDING_SCAN_POINTS``.

Order: the hourly bucket (every attempt), the sticker (``app.qr_token.verify_landing``) and its
building, then one transaction like a segment batch: lock the user, find the check-in, take the
per-building bucket, insert the scan, add to ``team_building_score``, ``claim.recompute_owner``,
commit. The leaderboards and the flip events follow after the commit, best effort, through the
segment path's ``_notify``. A scan holds the same locks in the same order as a batch (user, score
row, claim row), so the two cannot deadlock.

No idempotency key (Ionut, 2026-11-20): a retried scan meets the 10-minute bucket and gets a 429.

Problem types, all 403 unless noted:

- ``urn:floorwars:problem:sticker-invalid``: not a landing sticker, wrong key or bad signature;
- ``urn:floorwars:problem:sticker-expired``: outside the sticker's ``nbf``/``exp`` window;
- ``urn:floorwars:problem:sticker-wrong-building``: ``building_id`` is not the sticker's;
- ``urn:floorwars:problem:no-checkin``: no check-in of the user at the building at the scan time;
- ``urn:floorwars:problem:season-inactive``, ``urn:floorwars:problem:no-team``;
- 429 with ``Retry-After``; 503 when the limiter (Valkey) or the signing key is unavailable.

Tokens are never logged or stored.
"""

import logging
import uuid
from contextlib import suppress
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.api.problems import (
    ProblemError,
    forbidden,
    service_unavailable,
    too_many_requests,
    unauthorized,
)
from app.auth.ratelimit import RateLimiter
from app.landing import repository
from app.landing.schemas import LandingScanIn, LandingScanResult
from app.qr_token import QrExpiredError, QrNotYetValidError, QrTokenError, verify_landing
from app.segments import claim
from app.segments import repository as segments_repository
from app.segments.schemas import BuildingFlip
from app.segments.service import Leaderboards, NoLeaderboards, ScoredSegment, _notify
from app.valkey import ValkeyError

logger = logging.getLogger("floorwars.landing")

# Plan 15.3 accessible contribution mode: about one floor-equivalent (Ionut, 2026-11-19).
LANDING_SCAN_POINTS = 20
# A scanned_at outside [now - MAX_AGE, now + MAX_AHEAD], or none, is replaced by the server time.
SCANNED_AT_MAX_AGE = timedelta(minutes=10)
SCANNED_AT_MAX_AHEAD = timedelta(minutes=5)
# Rate limits (Ionut, 2026-11-20): matches the app's 10-minute cooldown per building.
SCANS_PER_BUILDING = 1
BUILDING_PERIOD_S = 600
SCANS_PER_HOUR = 6
HOUR_S = 3600

_P = "urn:floorwars:problem:"
STICKER_INVALID = _P + "sticker-invalid"
STICKER_EXPIRED = _P + "sticker-expired"
STICKER_WRONG_BUILDING = _P + "sticker-wrong-building"
NO_CHECKIN = _P + "no-checkin"
SEASON_INACTIVE = _P + "season-inactive"
NO_TEAM = _P + "no-team"
UNAVAILABLE = "Landing scans are temporarily unavailable."


def scan_time(scanned_at: datetime | None, now: datetime) -> datetime:
    """The scan time the server uses: the device's, unless missing or out of bounds."""
    if scanned_at is None or not (
        now - SCANNED_AT_MAX_AGE <= scanned_at <= now + SCANNED_AT_MAX_AHEAD
    ):
        return now
    return scanned_at


def user_scan_points(db: Session, user_id: uuid.UUID, season_id: int) -> int:
    """A user's landing-scan points in a season (for ``GET /me/season-stats``)."""
    return repository.scan_points(db, user_id, season_id)


def _take(limiter: RateLimiter | None, name: str, subject: str, capacity: int, period: int) -> None:
    """One token, fail closed: 503 without a limiter or when Valkey fails, 429 when empty."""
    if limiter is None:
        logger.error("rate limiter not configured")
        raise service_unavailable(UNAVAILABLE)
    try:
        decision = limiter.hit(name, subject, capacity, period)
    except ValkeyError:
        logger.error("rate limiter unavailable")
        raise service_unavailable(UNAVAILABLE) from None
    if not decision.allowed:
        logger.info("rate limited", extra={"limit": name})
        raise too_many_requests("Too many landing scans.", decision.retry_after_s)


def _sticker_problem(err: QrTokenError) -> ProblemError:
    if isinstance(err, QrExpiredError | QrNotYetValidError):
        return forbidden("This sticker has expired.", type_=STICKER_EXPIRED)
    return forbidden("This is not a valid FloorWars stair sticker.", type_=STICKER_INVALID)


def scan(
    db: Session,
    user_id: uuid.UUID,
    req: LandingScanIn,
    now: datetime,
    *,
    key: bytes | None,
    limiter: RateLimiter | None,
    board: Leaderboards | None = None,
) -> LandingScanResult:
    """Record one scan and credit its points through the claim transaction."""
    _take(limiter, "landing:user", str(user_id), SCANS_PER_HOUR, HOUR_S)
    if key is None:
        logger.error("qr key not configured")
        raise service_unavailable(UNAVAILABLE)
    try:
        claims = verify_landing(req.qr_token, key, int(now.timestamp()))
    except QrTokenError as err:
        logger.info(
            "landing scan refused", extra={"user_id": str(user_id), "reason": type(err).__name__}
        )
        raise _sticker_problem(err) from None
    if claims.building_id != req.building_id:
        raise forbidden("This sticker is not for this building.", type_=STICKER_WRONG_BUILDING)

    building_id = req.building_id
    at = scan_time(req.scanned_at, now)
    if not segments_repository.lock_user(db, user_id):
        raise unauthorized("Invalid or expired access token.")
    ctx = repository.scan_context(db, user_id, building_id, at)
    if ctx.checkin_id is None:
        raise forbidden("You are not checked in at this building.", type_=NO_CHECKIN)
    if ctx.season_id is None:
        raise forbidden("No season is running.", type_=SEASON_INACTIVE)
    if ctx.team_id is None:
        raise forbidden("Join a team to score.", type_=NO_TEAM)
    # Taken last, so a refused scan does not start the building's 10-minute cooldown.
    bucket = ("landing:building", f"{user_id}:{building_id}", SCANS_PER_BUILDING, BUILDING_PERIOD_S)
    _take(limiter, *bucket)
    points = LANDING_SCAN_POINTS
    try:
        scan_id = repository.insert_scan(db, user_id, building_id, ctx, points, at)
        segments_repository.add_score(db, ctx.season_id, building_id, ctx.team_id, points, 0)
        flip = claim.recompute_owner(db, ctx.season_id, building_id, now)
        db.commit()
    except BaseException:
        # Nothing was stored: give the cooldown back, so the app's retry is not a 429.
        if limiter is not None:
            with suppress(Exception):
                limiter.refund(*bucket)
        raise

    flips = [flip] if flip is not None else []
    scored = ScoredSegment(ctx.season_id, user_id, ctx.team_id, building_id, points, 0)
    _notify(board or NoLeaderboards(), [scored], flips)
    logger.info(
        "landing scan",
        extra={"user_id": str(user_id), "building_id": building_id, "flips": len(flips)},
    )
    return LandingScanResult(
        id=scan_id,
        building_id=building_id,
        points=points,
        flips=[
            BuildingFlip(
                building_id=f.building_id, from_team=f.from_code, to_team=f.to_code, at=f.at
            )
            for f in flips
        ],
    )
