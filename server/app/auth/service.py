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
from app.auth.ratelimit import RateLimiter, client_bucket, hashed_subject
from app.auth.schemas import OtpVerifyRequest, TokenPair
from app.auth.tokens import AccessTokens
from app.config import Settings
from app.mail import MailError, MailSender
from app.valkey import ValkeyError

logger = logging.getLogger("floorwars.auth")

HOUR_S = 3600
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


def _enforce_limits(limiter: RateLimiter | None, checks: list[tuple[str, str, int]]) -> None:
    """Take one token from each ``(name, subject, per_hour)`` bucket, in order; 429 on the first
    empty one. Fails closed: no limiter, or Valkey unavailable, gives 503."""
    if limiter is None:
        raise service_unavailable("Sign-in is temporarily unavailable.")
    try:
        for name, subject, capacity in checks:
            decision = limiter.hit(name, subject, capacity, HOUR_S)
            if not decision.allowed:
                logger.info("rate limited", extra={"limit": name})
                raise too_many_requests("Too many requests.", decision.retry_after_s)
    except ValkeyError:
        logger.error("rate limiter unavailable")
        raise service_unavailable("Sign-in is temporarily unavailable.") from None


def _store_pending_challenge(db: Session, settings: Settings, email: str, code: str) -> uuid.UUID:
    """Store the new challenge retired (not usable yet); the previous one stays active."""
    now = _now()
    salt = otp.new_salt()
    repository.delete_old_challenges(db, email, now - CHALLENGE_RETENTION)
    challenge_id = repository.add_pending_challenge(
        db, email, otp.hash_code(salt, code), salt, now + timedelta(seconds=settings.otp_ttl_s), now
    )
    db.commit()
    return challenge_id


def _activate_challenge(db: Session, email: str, challenge_id: uuid.UUID) -> None:
    """Supersede the previous active challenge with the new one (after the mail was sent)."""
    for attempt in range(2):
        try:
            repository.activate_challenge(db, email, challenge_id, _now())
            db.commit()
            return
        except IntegrityError:
            # A concurrent request for the same e-mail activated its challenge first (unique
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
    """Send a new code to ``email``.

    The new code supersedes the previous unused one only once the mail backend accepted it; if
    sending fails (503), the previous code keeps working.
    """
    domain = email.rsplit("@", 1)[1]
    if domain not in settings.allowed_email_domains:
        raise forbidden("This e-mail domain cannot sign in.", type_=DOMAIN_NOT_ALLOWED)
    _enforce_limits(
        limiter,
        [
            ("otp:ip", client_bucket(client_ip), settings.otp_rate_per_ip_per_hour),
            ("otp:email", hashed_subject(email), settings.otp_rate_per_email_per_hour),
        ],
    )

    code = otp.new_code()
    challenge_id = _store_pending_challenge(db, settings, email, code)
    try:
        mail.send_otp(email, code, settings.otp_ttl_s)
    except MailError:
        # The new challenge stays retired and the previous code (if any) stays usable.
        raise service_unavailable("The code could not be sent. Try again later.") from None
    _activate_challenge(db, email, challenge_id)


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
    db: Session,
    settings: Settings,
    tokens: AccessTokens,
    limiter: RateLimiter | None,
    body: OtpVerifyRequest,
    client_ip: str,
) -> TokenPair:
    """Check the code; on success sign in (creating the account if new) and register the device."""
    _enforce_limits(
        limiter, [("verify:ip", client_bucket(client_ip), settings.verify_rate_per_ip_per_hour)]
    )
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
        # Neutral name, never derived from the e-mail (the address is personal data).
        user = repository.add_user(db, body.email, f"Player-{secrets.token_hex(2)}", now)
        logger.info("user created", extra={"user_id": str(user.id)})

    challenge.consumed_at = now

    device = body.device
    repository.upsert_device(db, device.id, user.id, device.model, device.has_barometer, now)

    pair = _issue_pair(db, settings, tokens, user.id, uuid.uuid4(), now)
    db.commit()
    logger.info("signed in", extra={"user_id": str(user.id)})
    return pair


# POST /v1/auth/refresh


def refresh(
    db: Session,
    settings: Settings,
    tokens: AccessTokens,
    limiter: RateLimiter | None,
    raw_token: str,
    client_ip: str,
) -> TokenPair:
    """Rotate a refresh token.

    A token rotated less than ``refresh_reuse_grace_s`` ago is refused (401) without side
    effects: a client retry or two parallel refreshes, not theft. Presenting it later, or any
    revoked token, is reuse: the whole family is revoked (plan 7.9).
    """
    _enforce_limits(
        limiter, [("refresh:ip", client_bucket(client_ip), settings.refresh_rate_per_ip_per_hour)]
    )
    now = _now()
    row = repository.lock_refresh_token(db, _hash_refresh(raw_token))
    if row is None:
        db.rollback()
        raise _bad_refresh()
    if row.revoked_at is not None:
        grace = timedelta(seconds=settings.refresh_reuse_grace_s)
        if row.rotated_at is not None and now - row.rotated_at < grace:
            # A retry (lost response, parallel requests): refuse, but do not punish the family.
            db.rollback()
            logger.info("refresh token retried within grace window")
            raise _bad_refresh()
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
    row.rotated_at = now
    pair = _issue_pair(db, settings, tokens, row.user_id, row.family_id, now)
    db.commit()
    return pair
