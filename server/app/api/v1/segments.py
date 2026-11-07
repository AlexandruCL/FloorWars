"""Segment upload route: ``POST /v1/segments`` (contract 0.5.0-draft, ``uploadSegments``).

Thin handler: validation by ``app.segments.schemas``, the flow in ``app.segments.service``. The
response drops unset fields, so ``points`` is absent for a repeat while a ``from_team`` of null
stays.

Order of a request, set by FastAPI: the whole body is read and, if declared as JSON, parsed before
any dependency runs. Malformed JSON therefore answers 422 with or without a valid token, and spends
no upload token. Otherwise authentication runs (401), then the upload bucket (429), and only then
is the body validated against the schema, along with ``Idempotency-Key``: a client sending
schema-invalid batches must be signed in and still spends its tokens. An empty body or one not
declared as JSON takes this second path. The app has no body size limit; the proxy sets it.

Problem types: see ``app.segments.service``.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import CurrentUser, DbSession, Limiter
from app.api.problems import problem_doc
from app.segments import service
from app.segments.schemas import SegmentBatch, SegmentBatchResult

router = APIRouter(prefix="/segments", tags=["segments"])
logger = logging.getLogger("floorwars.segments")

IDEMPOTENCY_KEY_MAX_LEN = 255


def _upload_bucket(user: CurrentUser, limiter: Limiter) -> None:
    service.enforce_upload_limit(limiter, user.id)


def _leaderboards(request: Request) -> service.Leaderboards:
    valkey = request.app.state.valkey
    return service.ValkeyLeaderboards(valkey) if valkey is not None else service.NoLeaderboards()


@router.post(
    "",
    response_model=SegmentBatchResult,
    response_model_exclude_unset=True,
    dependencies=[Depends(_upload_bucket)],
    responses={
        401: problem_doc("Missing, invalid or expired access token."),
        403: problem_doc("device_id is not a device of the signed-in user (device-unknown)."),
        422: problem_doc("The body is not a valid batch, or Idempotency-Key is missing."),
        429: problem_doc("More than 60 uploads per hour; see Retry-After."),
        503: problem_doc("Rate limiter or database temporarily unavailable."),
    },
    operation_id="uploadSegments",
)
def upload_segments(
    batch: SegmentBatch,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LEN)
    ],
    user: CurrentUser,
    db: DbSession,
    board: Annotated[service.Leaderboards, Depends(_leaderboards)],
) -> SegmentBatchResult:
    """Upload a batch of climb segments. Each item is judged on its own; a repeat is success."""
    result = service.upload_batch(db, user.id, batch, board)
    logger.info(
        "segment batch",
        extra={
            "idempotency_key": idempotency_key,
            "accepted": len(result.accepted),
            "rejected": len(result.rejected),
            "flips": len(result.flips),
        },
    )
    return result
