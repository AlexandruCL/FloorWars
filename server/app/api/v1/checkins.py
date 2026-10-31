"""Check-in route: ``POST /v1/checkins`` (contract 0.4.0-draft, ``createCheckin``).

Thin handler: validation by the schemas below (contract ``CheckinRequest``, a ``oneOf`` chosen by
``method``), the flows in ``app.checkins.service``. Problem types: see that module.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.api.problems import problem_doc
from app.checkins import service

router = APIRouter(prefix="/checkins", tags=["checkins"])

# Bounds the body only; app.qr_token refuses anything over 512 characters as malformed (403).
QR_TOKEN_MAX_LEN = 4096


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QrCheckinRequest(_Body):
    method: Literal["qr"]
    qr_token: Annotated[StrictStr, Field(max_length=QR_TOKEN_MAX_LEN)]


class GeofenceCheckinRequest(_Body):
    method: Literal["geofence"]
    # strict: JSON numbers only (integers allowed), no strings or booleans; no NaN or infinity.
    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)]
    accuracy_m: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)] | None = None


CheckinRequest = Annotated[QrCheckinRequest | GeofenceCheckinRequest, Field(discriminator="method")]


class Checkin(BaseModel):
    id: uuid.UUID
    building_id: int = Field(ge=1)
    method: Literal["qr", "geofence"]
    valid_from: datetime
    valid_until: datetime


@router.post(
    "",
    status_code=201,
    response_model=Checkin,
    responses={
        401: problem_doc("Missing, invalid or expired access token."),
        403: problem_doc(
            "QR code malformed, invalid, expired, not yet valid or for an unknown building; "
            "or the location fix is inaccurate or not near any building."
        ),
        422: problem_doc("The body does not match the schema."),
        503: problem_doc("QR check-in is not configured on this server."),
    },
    operation_id="createCheckin",
)
def create_checkin(
    body: Annotated[CheckinRequest, Body()],
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> Checkin:
    """Check in by signed QR token or geofence. A check-in is valid for 90 minutes."""
    if isinstance(body, QrCheckinRequest):
        created = service.checkin_by_qr(db, settings, user.id, body.qr_token)
    else:
        created = service.checkin_by_geofence(
            db, settings, user.id, body.latitude, body.longitude, body.accuracy_m
        )
    return Checkin(
        id=created.id,
        building_id=created.building_id,
        method="qr" if created.method == "qr" else "geofence",
        valid_from=created.valid_from,
        valid_until=created.valid_until,
    )
