"""GDPR access and erasure: ``GET /v1/me/export`` and ``DELETE /v1/me`` (plan 8, Q6, Q6b, Q15).

Export: the caller's rows of every user-owned table, as ``MyDataExport``. Token hashes and
sign-in code hashes are never read (``refresh_token`` and ``otp_challenge`` are not exported).

Delete, in one transaction: lock the user, subtract the user's points and steps from
``team_building_score`` (score rows in the claim path's sorted order), delete the user (the
``ON DELETE CASCADE`` keys remove the owned rows), then recompute the owner of every building the
user scored in (``claim.recompute_owner``, after the delete, so the user's points no longer count).
After the commit, best effort: publish the flips, drop the user from the boards
(``leaderboards.remove_user``) and close the user's sockets in every process
(``hub.CLOSE_CHANNEL``).

TODO(W5-4, Blocked on Ionut): seasons already closed (``season.closed_at``, ``0009_w5_jobs``) are
treated like open ones; the recommendation is to skip their score and owner changes.
TODO(W5-4, Blocked on Ionut): ``otp_challenge`` rows of the user's e-mail survive the delete
(no foreign key); the recommendation is to delete them by e-mail in the same transaction.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app import leaderboards
from app.api.problems import service_unavailable, too_many_requests, unauthorized
from app.auth.ratelimit import RateLimiter, hashed_subject
from app.db.base import Base
from app.db.models import (
    Checkin,
    ClimbSegment,
    Device,
    FraudFlag,
    LandingScan,
    RefreshToken,
    SegmentReceipt,
    TeamBuildingScore,
    TeamMembership,
    User,
)
from app.realtime.hub import CLOSE_CHANNEL
from app.segments import claim
from app.segments.models import Flip
from app.segments.repository import lock_user
from app.valkey import ValkeyError

logger = logging.getLogger(__name__)

EXPORTS_PER_HOUR = 3  # Q15
HOUR_S = 3600

# MyDataExport section -> table; each row is the caller's, keyed by ``user_id``.
SECTIONS: dict[str, type[Base]] = {
    "devices": Device,
    "memberships": TeamMembership,
    "checkins": Checkin,
    "segments": ClimbSegment,
    "landing_scans": LandingScan,
    "fraud_flags": FraudFlag,
}
# TODO(W5-4): fraud_flags gain resolution_note (0008_w5_admin) by themselves: _row writes every
# stored column.
# Every table with ``ForeignKey("user.id", ondelete="CASCADE")``: counted for the delete log line.
CASCADED: tuple[type[Base], ...] = (
    *SECTIONS.values(),
    RefreshToken,
    SegmentReceipt,
)

# What the user added to each team's season totals: verified segments add points and steps,
# landing scans points only (as ``segments.service._add_scores`` and ``landing.service.scan``).
_USER_SCORES = text(
    """
    SELECT season_id, building_id, team_id, sum(points)::int AS points, sum(steps)::int AS steps
    FROM (
        SELECT season_id, building_id, team_id, points, steps FROM climb_segment
        WHERE user_id = :u AND status = 'verified'
        UNION ALL
        SELECT season_id, building_id, team_id, points, 0 FROM landing_scan WHERE user_id = :u
    ) AS scored
    GROUP BY season_id, building_id, team_id
    ORDER BY season_id, building_id, team_id
    """
)


def take_export_token(limiter: RateLimiter | None, user_id: uuid.UUID) -> None:
    """3 exports per user per hour, fail closed: 429 with ``Retry-After``, 503 without Valkey."""
    unavailable = "Data export is temporarily unavailable."
    if limiter is None:
        logger.error("rate limiter not configured")
        raise service_unavailable(unavailable)
    try:
        decision = limiter.hit("me:export", str(user_id), EXPORTS_PER_HOUR, HOUR_S)
    except ValkeyError:
        logger.error("rate limiter unavailable")
        raise service_unavailable(unavailable) from None
    if not decision.allowed:
        logger.info("rate limited", extra={"limit": "me:export"})
        raise too_many_requests("Too many data exports.", decision.retry_after_s)


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _row(model: type[Base], row: Base) -> dict[str, Any]:
    """Stored columns of ``row`` but ``user_id``; a range becomes ``valid_from``/``valid_to``."""
    out: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.key == "user_id":
            continue
        value = getattr(row, column.key)
        if isinstance(value, Range):
            out["valid_from"], out["valid_to"] = _value(value.lower), _value(value.upper)
        else:
            out[column.key] = _value(value)
    return out


def export_user(db: Session, user_id: uuid.UUID) -> dict[str, object]:
    """Everything stored about the user (contract ``MyDataExport``)."""
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid or expired access token.")
    out: dict[str, object] = {
        "exported_at": _value(datetime.now(UTC)),
        "user": _row(User, user),
    }
    for section, model in SECTIONS.items():
        rows = db.scalars(
            select(model)
            .where(model.__table__.c.user_id == user_id)
            .order_by(*inspect(model).primary_key)
        )
        out[section] = [_row(model, r) for r in rows]
    return out


def delete_user(
    db: Session, valkey: leaderboards.Commands | None, user_id: uuid.UUID, now: datetime
) -> None:
    """Delete the user and take their points out of the game (module docstring). Commits."""
    if not lock_user(db, user_id):
        raise unauthorized("Invalid or expired access token.")  # deleted meanwhile
    scores = db.execute(_USER_SCORES, {"u": user_id}).all()
    for s in scores:  # sorted: the same lock order as the claim path's ``_add_scores``
        db.execute(
            update(TeamBuildingScore)
            .where(
                TeamBuildingScore.season_id == s.season_id,
                TeamBuildingScore.building_id == s.building_id,
                TeamBuildingScore.team_id == s.team_id,
            )
            .values(
                points=TeamBuildingScore.points - s.points,
                steps=TeamBuildingScore.steps - s.steps,
            )
        )
    counts = {
        m.__tablename__: db.scalar(
            select(func.count()).select_from(m).where(m.__table__.c.user_id == user_id)
        )
        for m in CASCADED
    }
    db.execute(delete(User).where(User.id == user_id))
    flips: list[Flip] = []
    for season_id, building_id in sorted({(s.season_id, s.building_id) for s in scores}):
        flip = claim.recompute_owner(db, season_id, building_id, now)
        if flip is not None:
            flips.append(flip)
    db.commit()
    logger.info(
        "account deleted",
        extra={"user": hashed_subject(str(user_id)), "rows": counts, "flips": len(flips)},
    )
    if valkey is not None:
        _after_commit(valkey, user_id, sorted({s.season_id for s in scores}), flips)


def _after_commit(
    valkey: leaderboards.Commands, user_id: uuid.UUID, seasons: list[int], flips: list[Flip]
) -> None:
    """Best effort, like the claim path's ``_notify``: the database is already right. A failed
    board cleanup is repaired when the built marker expires (``BUILT_TTL_S``)."""
    try:
        for flip in flips:
            leaderboards.publish_flip(valkey, flip)
    except Exception as exc:
        _failed("flip publish", exc)
    try:
        for season_id in seasons:
            leaderboards.remove_user(valkey, season_id, user_id)
    except Exception as exc:
        _failed("board cleanup", exc)
    try:
        valkey.execute("PUBLISH", CLOSE_CHANNEL, str(user_id))
    except Exception as exc:
        _failed("socket close", exc)


def _failed(step: str, exc: Exception) -> None:
    logger.warning(
        "account deletion follow-up failed", extra={"step": step, "error": type(exc).__name__}
    )
