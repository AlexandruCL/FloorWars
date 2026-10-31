"""Sign-in flows (plan 7.9): request a code, verify it, rotate refresh tokens.

Each function owns its transaction: it commits what must persist (also before answering an
error, for example a counted attempt) and rolls back otherwise. Errors are ``ProblemError``.
Codes and tokens are never logged; log records carry ids only.

Problem types (``type`` member) a client can act on:

- ``urn:floorwars:problem:email-domain-not-allowed`` (403, ``/auth/otp``);
- ``urn:floorwars:problem:terms-required`` (403, ``/auth/verify``: a new account needs
  ``accept_terms`` and ``confirm_adult``; the challenge stays usable, so the app can resend).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.problems import forbidden, service_unavailable, too_many_requests
from app.auth import otp, repository
from app.auth.ratelimit import RateLimiter, hashed_subject
from app.config import Settings
from app.mail import MailError, MailSender
from app.valkey import ValkeyError

logger = logging.getLogger("floorwars.auth")

HOUR_S = 3600
DISPLAY_NAME_MAX = 64
# Retired challenges older than this are deleted when the same e-mail asks for a new code.
CHALLENGE_RETENTION = timedelta(days=1)

DOMAIN_NOT_ALLOWED = "urn:floorwars:problem:email-domain-not-allowed"
TERMS_REQUIRED = "urn:floorwars:problem:terms-required"


def _now() -> datetime:
    return datetime.now(UTC)


# POST /v1/auth/otp


def _check_rate_limits(
    limiter: RateLimiter | None, settings: Settings, email: str, ip: str
) -> None:
    if limiter is None:
        raise service_unavailable("Sign-in is temporarily unavailable.")
    checks = (
        ("otp:email", hashed_subject(email), settings.otp_rate_per_email_per_hour),
        ("otp:ip", ip, settings.otp_rate_per_ip_per_hour),
    )
    try:
        for name, subject, capacity in checks:
            decision = limiter.hit(name, subject, capacity, HOUR_S)
            if not decision.allowed:
                logger.info("otp rate limited", extra={"limit": name})
                raise too_many_requests("Too many code requests.", decision.retry_after_s)
    except ValkeyError:
        # Fail closed: without the limiter anyone could make us send unlimited mail.
        logger.error("rate limiter unavailable")
        raise service_unavailable("Sign-in is temporarily unavailable.") from None


def _store_challenge(db: Session, settings: Settings, email: str, code: str) -> None:
    salt = otp.new_salt()
    for attempt in range(2):
        now = _now()
        try:
            repository.supersede_active_challenge(db, email, now)
            repository.delete_old_challenges(db, email, now - CHALLENGE_RETENTION)
            repository.add_challenge(
                db,
                email,
                otp.hash_code(salt, code),
                salt,
                now + timedelta(seconds=settings.otp_ttl_s),
            )
            db.commit()
            return
        except IntegrityError:
            # A concurrent request for the same e-mail inserted its challenge first (unique
            # active challenge per e-mail). Retry once: this time it is superseded.
            db.rollback()
            if attempt == 1:
                raise


def request_otp(
    db: Session,
    settings: Settings,
    limiter: RateLimiter | None,
    mail: MailSender,
    email: str,
    client_ip: str,
) -> None:
    """Send a new code to ``email``. A new request supersedes the previous unused code."""
    domain = email.rsplit("@", 1)[1]
    if domain not in settings.allowed_email_domains:
        raise forbidden("This e-mail domain cannot sign in.", type_=DOMAIN_NOT_ALLOWED)
    _check_rate_limits(limiter, settings, email, client_ip)

    code = otp.new_code()
    _store_challenge(db, settings, email, code)
    try:
        mail.send_otp(email, code, settings.otp_ttl_s)
    except MailError:
        raise service_unavailable("The code could not be sent. Try again later.") from None


# Token pairs.


# POST /v1/auth/verify


# POST /v1/auth/refresh
