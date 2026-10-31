"""Access tokens: compact JWS (JWT) signed with Ed25519 ("EdDSA"), written by us (plan 7.9).

Only the Ed25519 primitive comes from ``cryptography``. Format:

- header ``{"alg":"EdDSA","typ":"JWT","kid":<first 16 hex of SHA-256(raw public key)>}``;
- claims ``sub`` (user id), ``iat``, ``exp``, ``aud``;
- base64url without padding, ``<header>.<claims>.<signature>``.

``verify`` rejects anything else: another ``alg`` (including ``none``), an unknown ``kid``, a
``crit`` header, a bad signature, a wrong ``aud``, an expired token, a non-canonical encoding.
Rotation (each semester, plan 7.5): put the previous key's public key (``public_key_hex``) in
``FLOORWARS_JWT_PREVIOUS_PUBLIC_KEYS`` for the overlap (at least the access-token lifetime); only
the current key signs.
"""

import base64
import binascii
import hashlib
import json
import logging
import re
import secrets
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.config import Settings

logger = logging.getLogger("floorwars.auth")

ALG = "EdDSA"
MAX_TOKEN_LENGTH = 4096
# Clock skew tolerated for ``iat`` in the future (seconds). ``exp`` has no leeway.
IAT_LEEWAY_S = 60
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")


class TokenError(Exception):
    """The token is not a valid access token. The message is for logs, never shown to clients."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    issued_at: int
    expires_at: int


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(segment: str) -> bytes:
    """Strict base64url without padding: alphabet checked and the encoding must be canonical."""
    if not _B64URL.fullmatch(segment) or len(segment) % 4 == 1:
        raise TokenError("bad base64url")
    try:
        data = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError):
        raise TokenError("bad base64url") from None
    if b64url_encode(data) != segment:
        raise TokenError("non-canonical base64url")
    return data


def key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def _json_segment(value: Mapping[str, Any]) -> str:
    return b64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _json_object(segment: str) -> dict[str, Any]:
    try:
        value = json.loads(b64url_decode(segment))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TokenError("bad json") from None
    if not isinstance(value, dict):
        raise TokenError("not a json object")
    return value


def _int_claim(claims: Mapping[str, Any], name: str) -> int:
    value = claims.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TokenError(f"bad {name}")
    return value


class AccessTokens:
    """Issues and verifies access tokens. One instance per app (``app.state.access_tokens``)."""

    def __init__(
        self,
        seed: bytes,
        audience: str,
        ttl_s: int,
        *,
        extra_verify_keys: Mapping[str, Ed25519PublicKey] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._private = Ed25519PrivateKey.from_private_bytes(seed)
        public = self._private.public_key()
        self.kid = key_id(public)
        self._verify_keys = {**(extra_verify_keys or {}), self.kid: public}
        self.audience = audience
        self.ttl_s = ttl_s
        self._clock = clock

    def issue(self, user_id: uuid.UUID) -> str:
        """A signed access token for ``user_id``, valid for ``ttl_s`` seconds."""
        now = int(self._clock())
        header = {"alg": ALG, "typ": "JWT", "kid": self.kid}
        claims = {"sub": str(user_id), "iat": now, "exp": now + self.ttl_s, "aud": self.audience}
        signing_input = f"{_json_segment(header)}.{_json_segment(claims)}"
        signature = self._private.sign(signing_input.encode("ascii"))
        return f"{signing_input}.{b64url_encode(signature)}"

    def verify(self, token: str) -> AccessClaims:
        """Return the claims of a valid token or raise ``TokenError``."""
        if len(token) > MAX_TOKEN_LENGTH:
            raise TokenError("too long")
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenError("not a compact JWS")
        header_b64, claims_b64, signature_b64 = parts

        header = _json_object(header_b64)
        if header.get("alg") != ALG:
            raise TokenError("unexpected alg")
        if "crit" in header:
            raise TokenError("crit not supported")
        if header.get("typ", "JWT") != "JWT":
            raise TokenError("unexpected typ")
        kid = header.get("kid")
        public = self._verify_keys.get(kid) if isinstance(kid, str) else None
        if public is None:
            raise TokenError("unknown kid")

        # Parsed before the signature check (it validates the segment), trusted only after it.
        claims = _json_object(claims_b64)
        signature = b64url_decode(signature_b64)
        if len(signature) != 64:
            raise TokenError("bad signature length")
        try:
            public.verify(signature, f"{header_b64}.{claims_b64}".encode("ascii"))
        except InvalidSignature:
            raise TokenError("bad signature") from None

        if claims.get("aud") != self.audience:
            raise TokenError("wrong audience")
        now = int(self._clock())
        expires_at = _int_claim(claims, "exp")
        issued_at = _int_claim(claims, "iat")
        if now >= expires_at:
            raise TokenError("expired")
        if issued_at > now + IAT_LEEWAY_S:
            raise TokenError("issued in the future")
        sub = claims.get("sub")
        try:
            user_id = uuid.UUID(sub) if isinstance(sub, str) else None
        except ValueError:
            user_id = None
        if user_id is None:
            raise TokenError("bad sub")
        return AccessClaims(user_id=user_id, issued_at=issued_at, expires_at=expires_at)


def build_access_tokens(settings: Settings) -> AccessTokens:
    """From ``jwt_signing_key``; in ``dev`` without one, a random key for this process only."""
    if settings.jwt_signing_key is not None:
        seed = bytes.fromhex(settings.jwt_signing_key.get_secret_value())
    elif settings.env == "dev":
        logger.warning(
            "SECURITY WARNING: FLOORWARS_JWT_SIGNING_KEY is unset; using a random signing key "
            "for this process only (dev). Tokens stop working on restart. Never run like this "
            "outside local development."
        )
        seed = secrets.token_bytes(32)
    else:  # Settings already refuses this; kept as a guard.
        raise RuntimeError("FLOORWARS_JWT_SIGNING_KEY is required outside dev")
    previous = {}
    for hex_key in settings.jwt_previous_public_keys:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(hex_key))
        previous[key_id(public)] = public
    return AccessTokens(
        seed, settings.jwt_audience, settings.access_token_ttl_s, extra_verify_keys=previous
    )


def public_key_hex(seed: bytes) -> str:
    """Raw public key (hex) of a signing seed, for ``FLOORWARS_JWT_PREVIOUS_PUBLIC_KEYS``."""
    public = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    return public.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
