"""Request and response models of ``POST /v1/segments`` (contract 0.6.0-draft).

The request models deliberately do **not** apply the contract's numeric bounds. A number outside
its bound, NaN or infinity must reach ``app.segments.rules`` and come back as one rejected item
(decision 4 of the Week 3 spec); 422 is only for a body that is not a valid batch.
"""

import math
import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StrictStr

from app.segments.rules import BATCH_MAX, RejectReason

CLASSIFIER_VERSION_MAX_LEN = 64
# RFC 3339 only. Pydantic alone would also read numbers and numeric strings as Unix timestamps.
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})")
# Printable text only: PostgreSQL text cannot hold NUL, and the value is stored as sent.
_PRINTABLE = r"^[^\x00-\x1f\x7f]+$"


def _json_number(value: Any) -> Any:
    """Keep an integer too large for a float a number (infinity), so a rule rejects that item."""
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf
    return value


def _rfc3339(value: Any) -> Any:
    if not (isinstance(value, str) and _RFC3339.fullmatch(value)):
        raise ValueError("must be an RFC 3339 date-time string")
    return value


# Strict: JSON numbers only, no strings or booleans. NaN and infinity are allowed on purpose.
AnyNumber = Annotated[float, BeforeValidator(_json_number), Field(strict=True)]
AnyInt = Annotated[int, Field(strict=True)]
Rfc3339Datetime = Annotated[AwareDatetime, BeforeValidator(_rfc3339)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(_Body):
    """One detected climb. The device is named once, on the batch."""

    id: uuid.UUID
    checkin_id: uuid.UUID
    started_at: Rfc3339Datetime
    building_id: AnyInt
    ascent_m: AnyNumber
    duration_s: AnyNumber
    vert_speed_mps: AnyNumber
    steps: AnyInt
    stair_prob: AnyNumber
    classifier_version: Annotated[
        StrictStr,
        Field(min_length=1, max_length=CLASSIFIER_VERSION_MAX_LEN, pattern=_PRINTABLE),
    ]


class SegmentBatch(_Body):
    device_id: uuid.UUID
    segments: Annotated[list[Segment], Field(min_length=1, max_length=BATCH_MAX)]


class AcceptedSegment(BaseModel):
    id: uuid.UUID
    steps_scored: int = Field(ge=0, le=2000)
    # Left unset for a repeat of a stored segment, and then omitted from the response.
    points: int | None = Field(default=None, ge=0)


class RejectedSegment(BaseModel):
    id: uuid.UUID
    reason: RejectReason


class BuildingFlip(BaseModel):
    building_id: int = Field(ge=1)
    from_team: str | None
    to_team: str
    at: datetime


class SegmentBatchResult(BaseModel):
    accepted: list[AcceptedSegment]
    rejected: list[RejectedSegment]
    flips: list[BuildingFlip]
