"""Landing scan route: ``POST /v1/landing-scans`` (contract 0.9.0-draft, ``createLandingScan``).

Thin handler: validation by ``app.landing.schemas``, the flow and problem types in
``app.landing.service``.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import AppSettings, CurrentUser, DbSession, Limiter
from app.api.problems import problem_doc
from app.landing import service
from app.landing.schemas import LandingScanIn, LandingScanResult
from app.qr_token import key_from_hex
from app.segments.service import Leaderboards, NoLeaderboards, ValkeyLeaderboards

router = APIRouter(prefix="/landing-scans", tags=["checkins"])


def _leaderboards(request: Request) -> Leaderboards:
    valkey = request.app.state.valkey
    return ValkeyLeaderboards(valkey) if valkey is not None else NoLeaderboards()


@router.post(
    "",
    status_code=201,
    response_model=LandingScanResult,
    responses={
        401: problem_doc("Missing, invalid or expired access token."),
        403: problem_doc(
            "Sticker invalid, outside its window or not for this building; or no check-in of "
            "the user at this building valid at the scan time."
        ),
        422: problem_doc("The body does not match the schema."),
        429: problem_doc("More than 1 scan per building per 10 minutes or 6 per hour."),
        503: problem_doc("Rate limiter or sticker key unavailable."),
    },
    operation_id="createLandingScan",
)
def create_landing_scan(
    body: LandingScanIn,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    limiter: Limiter,
    board: Annotated[Leaderboards, Depends(_leaderboards)],
) -> LandingScanResult:
    """Scan a stair sticker (barometer-less players); the points count like a verified climb."""
    secret = settings.qr_hmac_key
    key = key_from_hex(secret.get_secret_value()) if secret is not None else None
    return service.scan(db, user.id, body, datetime.now(UTC), key=key, limiter=limiter, board=board)
