"""Signed QR tokens: entrance codes (plan section 3.2, check-in flow) and landing stickers.

Token format, version 1::

    fwq1.<b64url(payload)>.<b64url(HMAC-SHA256(key, payload))>

``payload`` is compact JSON with sorted keys::

    {"b":<building_id>,"exp":<unix s>,"kid":"<8 hex>","nbf":<unix s>,"v":1}

``kid`` is the first 8 hex characters of SHA-256 of the raw key bytes, so a code printed with an
old key is reported as "wrong key" rather than "bad signature". base64url has no padding.

Landing stickers (W4-4, barometer-less scans) use the same scheme and key with the prefix
``fwl1.`` and ``"kind":"landing"`` inside the signed payload. The entrance verifier refuses any
token with a ``kind`` claim and the landing verifier requires ``kind == "landing"``, so a sticker
never checks in and an entrance code never scores, even with its prefix swapped.

Pure standard library; the key is passed in as bytes so this module does not depend on settings.
Verification order: prefix, two parts, base64url, JSON, ``v == 1``, ``kid``, signature
(``hmac.compare_digest``), then ``nbf <= now <= exp``.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass

PREFIX = "fwq1."
LANDING_PREFIX = "fwl1."
KIND_LANDING = "landing"
VERSION = 1
KEY_BYTES = 32
MAX_TOKEN_LEN = 512
_HEX_KEY = re.compile(r"[0-9a-fA-F]{64}")
_B64_ALPHABET = re.compile(r"[A-Za-z0-9_-]*")


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
    text = value.strip()
    if not _HEX_KEY.fullmatch(text):
        raise ValueError("QR key must be 64 hexadecimal characters")
    return bytes.fromhex(text)


def _check_key(key: bytes) -> None:
    if len(key) != KEY_BYTES:
        raise ValueError(f"QR key must be {KEY_BYTES} bytes")


def key_id(key: bytes) -> str:
    """Return the key id: first 8 hex characters of SHA-256 of the key bytes."""
    return hashlib.sha256(key).hexdigest()[:8]


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    """Strict, canonical base64url decode: no padding, no foreign characters, no spare bits."""
    if not _B64_ALPHABET.fullmatch(text):
        raise QrMalformedError("bad base64url")
    try:
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise QrMalformedError("bad base64url") from None
    if _b64e(decoded) != text:
        raise QrMalformedError("non-canonical base64url")
    return decoded


def _mac(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def sign(building_id: int, key: bytes, nbf: int, exp: int, *, landing: bool = False) -> str:
    """Create a token for ``building_id`` valid from ``nbf`` to ``exp`` (unix seconds).

    ``landing=True`` makes a landing sticker (``fwl1.``, ``kind`` claim), not an entrance code.
    """
    _check_key(key)
    if isinstance(building_id, bool) or building_id < 0 or nbf < 0 or exp < nbf:
        raise ValueError("building_id and nbf must be non-negative and exp must not precede nbf")
    claims: dict[str, object] = {
        "v": VERSION,
        "b": building_id,
        "nbf": nbf,
        "exp": exp,
        "kid": key_id(key),
    }
    if landing:
        claims["kind"] = KIND_LANDING
    payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("ascii")
    prefix = LANDING_PREFIX if landing else PREFIX
    return f"{prefix}{_b64e(payload)}.{_b64e(_mac(key, payload))}"


def _claim_int(data: dict[str, object], name: str) -> int:
    value = data.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise QrMalformedError("bad claim types")
    return value


def verify(token: str, key: bytes, now: int) -> QrClaims:
    """Verify an entrance ``token`` against ``key`` at ``now`` (unix seconds) and return its claims.

    Raises QrMalformedError, QrWrongKeyError, QrBadSignatureError, QrNotYetValidError or
    QrExpiredError (all subclasses of QrTokenError). A landing sticker is malformed here.
    """
    return _verify(token, key, now, PREFIX, None)


def verify_landing(token: str, key: bytes, now: int) -> QrClaims:
    """``verify`` for a landing sticker; an entrance code is malformed here."""
    return _verify(token, key, now, LANDING_PREFIX, KIND_LANDING)


def _verify(token: str, key: bytes, now: int, prefix: str, kind: str | None) -> QrClaims:
    _check_key(key)
    if len(token) > MAX_TOKEN_LEN:
        raise QrMalformedError("token too long")
    if not token.startswith(prefix):
        raise QrMalformedError("missing prefix")
    parts = token[len(prefix) :].split(".")
    if len(parts) != 2:
        raise QrMalformedError("expected two parts")
    payload = _b64d(parts[0])
    signature = _b64d(parts[1])
    try:
        data = json.loads(payload)
    except (ValueError, RecursionError):
        raise QrMalformedError("payload is not JSON") from None
    if not isinstance(data, dict) or _claim_int(data, "v") != VERSION:
        raise QrMalformedError("unsupported payload")
    # The kind is signed, the prefix is not: this check is what keeps the two codes apart.
    if kind is None:
        if "kind" in data:
            raise QrMalformedError("not an entrance token")
    elif data.get("kind") != kind:
        raise QrMalformedError("not a landing token")
    building = _claim_int(data, "b")
    nbf = _claim_int(data, "nbf")
    exp = _claim_int(data, "exp")
    kid = data.get("kid")
    if not isinstance(kid, str):
        raise QrMalformedError("bad claim types")
    if building < 0 or nbf < 0 or exp < nbf:
        raise QrMalformedError("bad claim values")
    if kid != key_id(key):
        raise QrWrongKeyError("key id mismatch")
    if not hmac.compare_digest(signature, _mac(key, payload)):
        raise QrBadSignatureError("signature mismatch")
    if now < nbf:
        raise QrNotYetValidError("not yet valid")
    if now > exp:
        raise QrExpiredError("expired")
    return QrClaims(building_id=building, nbf=nbf, exp=exp, kid=kid)
