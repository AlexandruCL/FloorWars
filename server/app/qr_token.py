"""Signed entrance QR tokens (plan section 3.2, check-in flow).

Token format, version 1::

    fwq1.<b64url(payload)>.<b64url(HMAC-SHA256(key, payload))>

``payload`` is compact JSON with sorted keys::

    {"b":<building_id>,"exp":<unix s>,"kid":"<8 hex>","nbf":<unix s>,"v":1}

``kid`` is the first 8 hex characters of SHA-256 of the raw key bytes, so a code printed with an
old key is reported as "wrong key" rather than "bad signature". base64url has no padding.

Pure standard library; the key is passed in as bytes so this module does not depend on settings.
Verification order: prefix, two parts, base64url, JSON, ``v == 1``, ``kid``, signature
(``hmac.compare_digest``), then ``nbf <= now <= exp``.
"""

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass

PREFIX = "fwq1."
VERSION = 1
KEY_BYTES = 32


class QrTokenError(Exception):
    """Base class of all QR token verification errors."""


class QrMalformedError(QrTokenError):
    """The string is not a well-formed version 1 token."""


class QrWrongKeyError(QrTokenError):
    """The token was signed with a different key (``kid`` mismatch)."""


class QrBadSignatureError(QrTokenError):
    """The signature does not match the payload."""


class QrNotYetValidError(QrTokenError):
    """``now`` is before ``nbf``."""


class QrExpiredError(QrTokenError):
    """``now`` is after ``exp``."""


@dataclass(frozen=True, slots=True)
class QrClaims:
    """Verified claims of a token. Times are unix seconds."""

    building_id: int
    nbf: int
    exp: int
    kid: str


def key_from_hex(value: str) -> bytes:
    """Parse a 64-hex-character key into 32 bytes. Raises ValueError (message never has the key)."""
    try:
        key = bytes.fromhex(value.strip())
    except ValueError:
        raise ValueError("QR key must be 64 hexadecimal characters") from None
    if len(key) != KEY_BYTES:
        raise ValueError("QR key must be 64 hexadecimal characters")
    return key


def key_id(key: bytes) -> str:
    """Return the key id: first 8 hex characters of SHA-256 of the key bytes."""
    return hashlib.sha256(key).hexdigest()[:8]


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    if not text.isascii() or "=" in text:
        raise QrMalformedError("bad base64url")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise QrMalformedError("bad base64url") from None


def _mac(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def sign(building_id: int, key: bytes, nbf: int, exp: int) -> str:
    """Create a token for ``building_id`` valid from ``nbf`` to ``exp`` (unix seconds)."""
    if exp < nbf:
        raise ValueError("exp must not be before nbf")
    claims = {"v": VERSION, "b": building_id, "nbf": nbf, "exp": exp, "kid": key_id(key)}
    payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("ascii")
    return f"{PREFIX}{_b64e(payload)}.{_b64e(_mac(key, payload))}"


def _claim_int(data: dict[str, object], name: str) -> int:
    value = data.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise QrMalformedError("bad claim types")
    return value


def verify(token: str, key: bytes, now: int) -> QrClaims:
    """Verify ``token`` against ``key`` at ``now`` (unix seconds) and return its claims.

    Raises QrMalformedError, QrWrongKeyError, QrBadSignatureError, QrNotYetValidError or
    QrExpiredError (all subclasses of QrTokenError).
    """
    if not token.startswith(PREFIX):
        raise QrMalformedError("missing prefix")
    parts = token[len(PREFIX) :].split(".")
    if len(parts) != 2:
        raise QrMalformedError("expected two parts")
    payload = _b64d(parts[0])
    signature = _b64d(parts[1])
    try:
        data = json.loads(payload)
    except ValueError:
        raise QrMalformedError("payload is not JSON") from None
    if not isinstance(data, dict) or data.get("v") != VERSION:
        raise QrMalformedError("unsupported payload")
    building = _claim_int(data, "b")
    nbf = _claim_int(data, "nbf")
    exp = _claim_int(data, "exp")
    kid = data.get("kid")
    if not isinstance(kid, str):
        raise QrMalformedError("bad claim types")
    if kid != key_id(key):
        raise QrWrongKeyError("key id mismatch")
    if not hmac.compare_digest(signature, _mac(key, payload)):
        raise QrBadSignatureError("signature mismatch")
    if now < nbf:
        raise QrNotYetValidError("not yet valid")
    if now > exp:
        raise QrExpiredError("expired")
    return QrClaims(building_id=building, nbf=nbf, exp=exp, kid=kid)
