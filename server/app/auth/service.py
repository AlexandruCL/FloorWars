"""Sign-in flows (plan 7.9): request a code, verify it, rotate refresh tokens.

Each function owns its transaction: it commits what must persist (also before answering an
error, for example a counted attempt) and rolls back otherwise. Errors are ``ProblemError``.
Codes and tokens are never logged; log records carry ids only.

Problem types (``type`` member) a client can act on:

- ``urn:floorwars:problem:email-domain-not-allowed`` (403, ``/auth/otp``);
- ``urn:floorwars:problem:terms-required`` (403, ``/auth/verify``: a new account needs
  ``accept_terms`` and ``confirm_adult``; the challenge stays usable, so the app can resend).
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.problems import ProblemError, forbidden, service_unavailable, too_many_requests
from app.auth import otp, repository
from app.auth.ratelimit import RateLimiter, hashed_subject
from app.auth.schemas import OtpVerifyRequest, TokenPair
from app.auth.tokens import AccessTokens
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


def _wrong_code() -> ProblemError:
    return ProblemError(401, detail="Wrong or expired code.")


def _bad_refresh() -> ProblemError:
    return ProblemError(401, detail="Unknown, expired or reused refresh token.")


def _hash_refresh(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


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


def _issue_pair(
    db: Session,
    settings: Settings,
    tokens: AccessTokens,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    now: datetime,
) -> TokenPair:
    raw = secrets.token_urlsafe(32)  # 256 bits
    repository.add_refresh_token(
        db,
        user_id,
        _hash_refresh(raw),
        family_id,
        now + timedelta(seconds=settings.refresh_token_ttl_s),
    )
    return TokenPair(
        access_token=tokens.issue(user_id),
        refresh_token=raw,
        expires_in=tokens.ttl_s,
        refresh_expires_in=settings.refresh_token_ttl_s,
    )


# POST /v1/auth/verify


def verify_otp(
    db: Session, settings: Settings, tokens: AccessTokens, body: OtpVerifyRequest
) -> TokenPair:
    """Check the code; on success sign in (creating the account if new) and register the device."""
    now = _now()
    challenge = repository.lock_active_challenge(db, body.email)
    if challenge is None:
        db.rollback()
        raise _wrong_code()
    if challenge.attempts >= settings.otp_max_attempts:
        db.rollback()
        raise ProblemError(429, detail="Too many attempts for this code. Request a new one.")
    if challenge.expires_at <= now:
        db.rollback()
        raise _wrong_code()

    # Count the attempt before comparing, under the row lock, so parallel guesses cannot
    # exceed the limit.
    challenge.attempts += 1
    db.flush()
    if not otp.code_matches(challenge.salt, body.code, challenge.code_hash):
        db.commit()
        raise _wrong_code()

    user = repository.get_user_by_email(db, body.email)
    if user is None:
        if not (body.accept_terms and body.confirm_adult):
            db.commit()  # keep the counted attempt; the challenge stays active
            raise forbidden(
                "A new account must accept the terms and confirm being 18 or older.",
                type_=TERMS_REQUIRED,
            )
        local_part = body.email.split("@", 1)[0]
        user = repository.add_user(db, body.email, local_part[:DISPLAY_NAME_MAX], now)
        logger.info("user created", extra={"user_id": str(user.id)})

    challenge.consumed_at = now

    device = body.device
    previous_owner = repository.lock_device_owner(db, device.id)
    if previous_owner is not None and previous_owner != user.id:
        logger.warning(
            "device moved to another user",
            extra={
                "device_id": str(device.id),
                "from_user_id": str(previous_owner),
                "to_user_id": str(user.id),
            },
        )
    repository.upsert_device(db, device.id, user.id, device.model, device.has_barometer, now)

    pair = _issue_pair(db, settings, tokens, user.id, uuid.uuid4(), now)
    db.commit()
    logger.info("signed in", extra={"user_id": str(user.id)})
    return pair


# POST /v1/auth/refresh


def refresh(db: Session, settings: Settings, tokens: AccessTokens, raw_token: str) -> TokenPair:
    """Rotate a refresh token. Presenting a revoked (already rotated) one revokes its family."""
    now = _now()
    row = repository.lock_refresh_token(db, _hash_refresh(raw_token))
    if row is None:
        db.rollback()
        raise _bad_refresh()
    if row.revoked_at is not None:
        revoked = repository.revoke_family(db, row.family_id)
        db.commit()
        logger.warning(
            "refresh token reuse, family revoked",
            extra={"user_id": str(row.user_id), "family_id": str(row.family_id), "n": revoked},
        )
        raise _bad_refresh()
    if row.expires_at <= now:
        db.rollback()
        raise _bad_refresh()

    row.revoked_at = now
    pair = _issue_pair(db, settings, tokens, row.user_id, row.family_id, now)
    db.commit()
    return pair
