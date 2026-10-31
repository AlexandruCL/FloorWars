"""Check-in flows (plan 3.2): by signed entrance QR token or by geofence.

Each flow resolves the building first, then runs one transaction: lock the user row, read the
database clock, end the user's active check-in at that instant, insert the new one for
``[now, now + checkin_ttl_s)``, commit. The lock serialises the check-ins of one user; the
exclusion constraint ``excl_checkin_user_overlap`` is the guarantee behind it.

Problem types (``type`` member), all 403 unless noted:

- ``urn:floorwars:problem:qr-malformed``: not a well-formed token;
- ``urn:floorwars:problem:qr-invalid``: wrong key or bad signature (deliberately one type);
- ``urn:floorwars:problem:qr-expired``, ``urn:floorwars:problem:qr-not-yet-valid``;
- ``urn:floorwars:problem:building-unknown``: a valid token for a building that does not exist;
- ``urn:floorwars:problem:qr-unavailable`` (503): no ``FLOORWARS_QR_HMAC_KEY`` configured;
- ``urn:floorwars:problem:location-inaccurate``, ``urn:floorwars:problem:outside-geofence``
  (``app.checkins.geofence``).

Tokens and coordinates are never logged, stored or echoed; log records carry ids only.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.api.problems import ProblemError, forbidden, unauthorized
from app.checkins import geofence, repository
from app.config import Settings
from app.qr_token import (
    QrBadSignatureError,
    QrExpiredError,
    QrMalformedError,
    QrNotYetValidError,
    QrTokenError,
    QrWrongKeyError,
    key_from_hex,
    verify,
)

logger = logging.getLogger("floorwars.checkins")

_P = "urn:floorwars:problem:"
QR_MALFORMED = _P + "qr-malformed"
QR_INVALID = _P + "qr-invalid"
QR_EXPIRED = _P + "qr-expired"
QR_NOT_YET_VALID = _P + "qr-not-yet-valid"
BUILDING_UNKNOWN = _P + "building-unknown"
QR_UNAVAILABLE = _P + "qr-unavailable"

# Most specific first: (error class, problem type, detail).
_QR_PROBLEMS: tuple[tuple[type[QrTokenError], str, str], ...] = (
    (QrMalformedError, QR_MALFORMED, "The QR code is not a FloorWars entrance code."),
    (QrWrongKeyError, QR_INVALID, "The QR code is not valid."),
    (QrBadSignatureError, QR_INVALID, "The QR code is not valid."),
    (QrExpiredError, QR_EXPIRED, "The QR code has expired."),
    (QrNotYetValidError, QR_NOT_YET_VALID, "The QR code is not valid yet."),
)


@dataclass(frozen=True, slots=True)
class CreatedCheckin:
    id: uuid.UUID
    building_id: int
    method: str
    valid_from: datetime
    valid_until: datetime


def _qr_problem(err: QrTokenError) -> ProblemError:
    for cls, type_, detail in _QR_PROBLEMS:
        if isinstance(err, cls):
            return forbidden(detail, type_=type_)
    return forbidden("The QR code is not valid.", type_=QR_INVALID)


def _record(
    db: Session, settings: Settings, user_id: uuid.UUID, building_id: int, method: str
) -> CreatedCheckin:
    """One transaction: lock the user, end the active check-in, insert the new one, commit."""
    if not repository.lock_user(db, user_id):
        db.rollback()
        raise unauthorized("Invalid or expired access token.")
    now = repository.db_clock(db)
    until = now + timedelta(seconds=settings.checkin_ttl_s)
    ended = repository.end_active_checkin(db, user_id, now)
    row = repository.add_checkin(db, user_id, building_id, method, now, until)
    created = CreatedCheckin(row.id, building_id, method, now, until)
    db.commit()
    logger.info(
        "checked in",
        extra={
            "user_id": str(user_id),
            "building_id": building_id,
            "method": method,
            "ended_previous": ended,
        },
    )
    return created


def checkin_by_qr(
    db: Session, settings: Settings, user_id: uuid.UUID, token: str
) -> CreatedCheckin:
    """Check in with a signed entrance QR token (``app.qr_token``), verified at the app clock."""
    if settings.qr_hmac_key is None:
        raise ProblemError(503, detail="QR check-in is not available.", type_=QR_UNAVAILABLE)
    key = key_from_hex(settings.qr_hmac_key.get_secret_value())
    try:
        claims = verify(token, key, int(time.time()))
    except QrTokenError as err:
        logger.info(
            "qr check-in refused", extra={"user_id": str(user_id), "reason": type(err).__name__}
        )
        raise _qr_problem(err) from None
    if not repository.building_exists(db, claims.building_id):
        db.rollback()
        raise forbidden("The QR code names an unknown building.", type_=BUILDING_UNKNOWN)
    return _record(db, settings, user_id, claims.building_id, "qr")


def checkin_by_geofence(
    db: Session,
    settings: Settings,
    user_id: uuid.UUID,
    latitude: float,
    longitude: float,
    accuracy_m: float | None,
) -> CreatedCheckin:
    """Check in at the nearest building within ``geofence_radius_m`` of a one-shot fix."""
    building_id = geofence.locate_building(db, settings, latitude, longitude, accuracy_m)
    return _record(db, settings, user_id, building_id, "geofence")
