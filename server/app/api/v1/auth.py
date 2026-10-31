"""Auth routes: ``POST /v1/auth/otp``, ``/v1/auth/verify``, ``/v1/auth/refresh`` (contract 0.4.0).

Thin handlers: validation by the schemas, the flows in ``app.auth.service``. Every route is rate
limited per client IP (IPv6 per /64) before any database work, and fails closed (503) when the
limiter is unavailable.
"""

from fastapi import APIRouter, Request, Response

from app.api.deps import AppSettings, DbSession, Limiter, Mail, Tokens
from app.api.problems import problem_doc
from app.auth import service
from app.auth.schemas import OtpRequest, OtpVerifyRequest, RefreshRequest, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])

# Token responses must not be cached (RFC 6749 section 5.1).
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}

_422 = problem_doc("The body does not match the schema.")
_503 = problem_doc("Rate limiter, database or mail temporarily unavailable.")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post(
    "/otp",
    status_code=202,
    response_class=Response,
    responses={
        202: {"description": "The code was sent. No body."},
        403: problem_doc("The e-mail domain is not on the allow-list."),
        422: _422,
        429: problem_doc("Rate limit hit; see Retry-After."),
        503: _503,
    },
    operation_id="requestOtp",
)
def request_otp(
    body: OtpRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    mail: Mail,
    limiter: Limiter,
) -> Response:
    """Send a 6-digit code to a university e-mail address."""
    service.request_otp(db, settings, limiter, mail, body.email, _client_ip(request))
    return Response(status_code=202)


@router.post(
    "/verify",
    response_model=TokenPair,
    responses={
        401: problem_doc("Wrong or expired code."),
        403: problem_doc("A new account needs accept_terms and confirm_adult both true."),
        422: _422,
        429: problem_doc("Too many attempts for this code (more than 5), or rate limit hit."),
        503: _503,
    },
    operation_id="verifyOtp",
)
def verify_otp(
    body: OtpVerifyRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    tokens: Tokens,
    limiter: Limiter,
) -> TokenPair:
    """Exchange e-mail and code for tokens; registers the device."""
    response.headers.update(NO_STORE)
    return service.verify_otp(db, settings, tokens, limiter, body, _client_ip(request))


@router.post(
    "/refresh",
    response_model=TokenPair,
    responses={
        401: problem_doc("Unknown, expired or reused refresh token (reuse revokes the family)."),
        422: _422,
        429: problem_doc("Rate limit hit; see Retry-After."),
        503: _503,
    },
    operation_id="refreshTokens",
)
def refresh_tokens(
    body: RefreshRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    tokens: Tokens,
    limiter: Limiter,
) -> TokenPair:
    """Rotate the refresh token and return a new pair."""
    response.headers.update(NO_STORE)
    return service.refresh(db, settings, tokens, limiter, body.refresh_token, _client_ip(request))
