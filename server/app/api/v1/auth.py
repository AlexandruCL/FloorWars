"""Auth routes: ``POST /v1/auth/otp``, ``/v1/auth/verify``, ``/v1/auth/refresh`` (contract 0.4.0).

Thin handlers: validation by the schemas, the flows in ``app.auth.service``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import AppSettings, DbSession, get_access_tokens
from app.api.problems import problem_doc
from app.auth import service
from app.auth.ratelimit import RateLimiter
from app.auth.schemas import OtpRequest
from app.auth.tokens import AccessTokens
from app.mail import MailSender

router = APIRouter(prefix="/auth", tags=["auth"])

# Token responses must not be cached (RFC 6749 section 5.1).
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def get_mail_sender(request: Request) -> MailSender:
    sender: MailSender = request.app.state.mail_sender
    return sender


def get_rate_limiter(request: Request) -> RateLimiter | None:
    limiter: RateLimiter | None = request.app.state.rate_limiter
    return limiter


Tokens = Annotated[AccessTokens, Depends(get_access_tokens)]


@router.post(
    "/otp",
    status_code=202,
    response_class=Response,
    responses={
        202: {"description": "The code was sent. No body."},
        403: problem_doc("The e-mail domain is not on the allow-list."),
        422: problem_doc("The body does not match the schema."),
        429: problem_doc("Rate limit hit; see Retry-After."),
        503: problem_doc("Mail or rate limiter unavailable."),
    },
    operation_id="requestOtp",
)
def request_otp(
    body: OtpRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    mail: Annotated[MailSender, Depends(get_mail_sender)],
    limiter: Annotated[RateLimiter | None, Depends(get_rate_limiter)],
) -> Response:
    """Send a 6-digit code to a university e-mail address."""
    client_ip = request.client.host if request.client else "unknown"
    service.request_otp(db, settings, limiter, mail, body.email, client_ip)
    return Response(status_code=202)
