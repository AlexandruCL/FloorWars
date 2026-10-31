"""Access-token JWTs (EdDSA). No database needed."""

import hashlib
import json
import uuid
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.auth.tokens import AccessTokens, TokenError, b64url_decode, b64url_encode

SEED = bytes(range(32))  # dummy test key
OTHER_SEED = bytes(range(1, 33))
NOW = 1_800_000_000
USER = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _tokens(seed: bytes = SEED, audience: str = "floorwars-api", now: float = NOW) -> AccessTokens:
    return AccessTokens(seed, audience, 900, clock=lambda: now)


def _segment(value: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(value).encode())


def _parts(token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    header, claims, signature = token.split(".")
    return json.loads(b64url_decode(header)), json.loads(b64url_decode(claims)), signature


def test_roundtrip_and_shape() -> None:
    tokens = _tokens()
    token = tokens.issue(USER)
    header, claims, _ = _parts(token)
    public = Ed25519PrivateKey.from_private_bytes(SEED).public_key()
    raw = public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    assert header == {"alg": "EdDSA", "typ": "JWT", "kid": hashlib.sha256(raw).hexdigest()[:16]}
    assert claims == {"sub": str(USER), "iat": NOW, "exp": NOW + 900, "aud": "floorwars-api"}
    assert "=" not in token
    assert tokens.verify(token).user_id == USER


def test_bad_signature_rejected() -> None:
    header, claims, _ = _tokens().issue(USER).split(".")
    forged_claims = _segment({"sub": str(uuid.uuid4()), "iat": NOW, "exp": NOW + 900, "aud": "x"})
    _, _, signature = _tokens().issue(USER).split(".")
    with pytest.raises(TokenError, match="bad signature"):
        _tokens().verify(f"{header}.{forged_claims}.{signature}")
    # Same kid in the header, but signed by another key.
    other = _tokens(seed=OTHER_SEED).issue(USER).split(".")[2]
    with pytest.raises(TokenError, match="bad signature"):
        _tokens().verify(f"{header}.{claims}.{other}")


def test_alg_none_rejected() -> None:
    _, claims, _ = _tokens().issue(USER).split(".")
    header = _segment({"alg": "none", "typ": "JWT"})
    with pytest.raises(TokenError, match="alg"):
        _tokens().verify(f"{header}.{claims}.")


def test_other_alg_rejected() -> None:
    token = _tokens().issue(USER)
    header, _, _ = _parts(token)
    for alg in ("HS256", "ES256", "eddsa", None):
        swapped = _segment({**header, "alg": alg})
        with pytest.raises(TokenError, match="alg"):
            _tokens().verify(swapped + token[token.index(".") :])


def test_unknown_kid_rejected() -> None:
    token = _tokens(seed=OTHER_SEED).issue(USER)
    with pytest.raises(TokenError, match="kid"):
        _tokens().verify(token)


def test_wrong_audience_rejected() -> None:
    token = _tokens(audience="someone-else").issue(USER)
    with pytest.raises(TokenError, match="audience"):
        _tokens().verify(token)


def test_expired_rejected() -> None:
    token = _tokens().issue(USER)
    _tokens(now=NOW + 899).verify(token)
    with pytest.raises(TokenError, match="expired"):
        _tokens(now=NOW + 900).verify(token)


@pytest.mark.parametrize(
    "token",
    ["", "a.b", "a.b.c.d", "!!.e30.AA", "e30=.e30.AA", "e30.e30.A"],
)
def test_malformed_rejected(token: str) -> None:
    with pytest.raises(TokenError):
        _tokens().verify(token)


def test_non_canonical_base64_rejected() -> None:
    assert b64url_decode("QQ") == b"A"
    with pytest.raises(TokenError, match="non-canonical"):
        b64url_decode("QR")
