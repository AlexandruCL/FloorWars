"""Request and response models of ``POST /v1/landing-scans`` (contract 0.9.0-draft)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app.constants import MAX_ID
from app.segments.schemas import BuildingFlip, Rfc3339Datetime

# Bounds the body only; app.qr_token refuses anything over 512 characters as malformed (403).
QR_TOKEN_MAX_LEN = 4096


class LandingScanIn(BaseModel):
    """Contract ``LandingScanRequest``."""

    model_config = ConfigDict(extra="forbid")

    qr_token: Annotated[StrictStr, Field(max_length=QR_TOKEN_MAX_LEN)]
    building_id: Annotated[int, Field(strict=True, ge=1, le=MAX_ID)]
    scanned_at: Rfc3339Datetime | None = None


class LandingScanResult(BaseModel):
    """Contract ``LandingScan``."""

    id: uuid.UUID
    building_id: int = Field(ge=1)
    points: int = Field(ge=0)
    flips: list[BuildingFlip]
