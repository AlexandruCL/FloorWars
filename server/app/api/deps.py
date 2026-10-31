"""Dependencies shared by the ``/v1`` routes.

Use the ``Annotated`` aliases in route signatures::

    from app.api.deps import CurrentUser, DbSession

    @router.post("/seasons/{id}/join")
    def join(id: int, user: CurrentUser, db: DbSession) -> ...: ...

- ``CurrentUser``: the signed-in ``app.db.models.User``. Verifies the ``Authorization: Bearer``
  access token (EdDSA JWT, ``app.auth.tokens``) and loads the user; answers 401 ``Problem`` with
  ``WWW-Authenticate: Bearer`` when the token is missing, invalid, expired or the user is gone.
- ``DbSession``: the request's sync SQLAlchemy ``Session``.
- ``AppSettings``: the ``Settings`` the app was created with.
- ``Tokens`` (``AccessTokens``), ``Mail`` (``MailSender``), ``Limiter`` (``RateLimiter | None``):
  app-wide resources from ``app.state``, built by ``create_app``.

Route handlers are plain ``def`` (FastAPI runs them in its thread pool). The session does not
commit by itself: the service that changes data calls ``db.commit()``; anything left uncommitted
is rolled back when the request ends.

Tests get a valid access token with ``app.state.access_tokens.issue(user_id)``; see
``tests/helpers.py`` (``auth_headers``) and the fixtures in ``tests/conftest.py``.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.api.problems import unauthorized
from app.auth.ratelimit import RateLimiter
from app.auth.tokens import AccessTokens, TokenError
from app.config import Settings
from app.db.models import User
from app.mail import MailSender


def get_app_settings(request: Request) -> Settings:
    """The settings the app was created with (``create_app(settings)``)."""
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    """One database session per request, closed (and rolled back if uncommitted) at the end."""
    factory: sessionmaker[Session] | None = request.app.state.sessionmaker
    if factory is None:
        raise RuntimeError("FLOORWARS_DATABASE_URL is not set")
    with factory() as session:
        yield session


def get_access_tokens(request: Request) -> AccessTokens:
    """The app's access-token issuer and verifier."""
    tokens: AccessTokens = request.app.state.access_tokens
    return tokens


def get_mail_sender(request: Request) -> MailSender:
    """The sign-in mail backend (``FLOORWARS_MAIL_BACKEND``)."""
    sender: MailSender = request.app.state.mail_sender
    return sender


def get_rate_limiter(request: Request) -> RateLimiter | None:
    """The Valkey token-bucket limiter, or None without ``FLOORWARS_VALKEY_URL`` (fail closed)."""
    limiter: RateLimiter | None = request.app.state.rate_limiter
    return limiter


AppSettings = Annotated[Settings, Depends(get_app_settings)]
DbSession = Annotated[Session, Depends(get_db)]
Tokens = Annotated[AccessTokens, Depends(get_access_tokens)]
Mail = Annotated[MailSender, Depends(get_mail_sender)]
Limiter = Annotated[RateLimiter | None, Depends(get_rate_limiter)]

# auto_error=False: a missing header must give our 401 Problem, not FastAPI's 403.
# scheme_name matches the contract's security scheme (components.securitySchemes.bearerAuth).
_bearer = HTTPBearer(
    scheme_name="bearerAuth",
    auto_error=False,
    description="Access token from POST /v1/auth/verify.",
)


def current_user(
    db: DbSession,
    tokens: Tokens,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The user named by a valid Bearer access token, or 401 ``Problem``."""
    if credentials is None:
        raise unauthorized("Missing access token.")
    try:
        claims = tokens.verify(credentials.credentials)
    except TokenError:
        raise unauthorized("Invalid or expired access token.") from None
    user = db.get(User, claims.user_id)
    if user is None:
        raise unauthorized("Invalid or expired access token.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
