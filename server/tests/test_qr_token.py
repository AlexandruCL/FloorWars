"""Tests for the signed entrance QR token."""

import base64
import json

import pytest

from app import qr_token
from app.qr_token import (
    QrBadSignatureError,
    QrExpiredError,
    QrMalformedError,
    QrNotYetValidError,
    QrTokenError,
    QrWrongKeyError,
    key_from_hex,
    key_id,
    sign,
    verify,
)

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))
NBF, EXP = 1_800_000_000, 1_800_604_800
NOW = NBF + 100

# Fixed vector: key = bytes 0..31, building 42, nbf/exp above.
VECTOR = (
    "fwq1.eyJiIjo0MiwiZXhwIjoxODAwNjA0ODAwLCJraWQiOiI2MzBkY2QyOSIsIm5iZiI6MTgwMDAwMDAwMCwidiI6MX0"
    ".jaPsEA-VFnzOW5VrAlaJBNStbCk4qM69T-Ka4072uEI"
)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_round_trip() -> None:
    claims = verify(sign(7, KEY, NBF, EXP), KEY, NOW)
    assert (claims.building_id, claims.nbf, claims.exp) == (7, NBF, EXP)
    assert claims.kid == key_id(KEY)


def test_boundaries_are_inclusive() -> None:
    token = sign(7, KEY, NBF, EXP)
    verify(token, KEY, NBF)
    verify(token, KEY, EXP)


def test_fixed_vector() -> None:
    token = sign(42, KEY, NBF, EXP)
    assert token == VECTOR
    assert verify(VECTOR, KEY, NOW).building_id == 42


def test_tampered_payload() -> None:
    _, payload, sig = sign(7, KEY, NBF, EXP).split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["b"] = 8
    new_payload = _b64(json.dumps(forged, separators=(",", ":"), sort_keys=True).encode())
    with pytest.raises(QrBadSignatureError):
        verify(f"fwq1.{new_payload}.{sig}", KEY, NOW)


def test_tampered_signature() -> None:
    head, payload, sig = sign(7, KEY, NBF, EXP).split(".")
    bad = ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(QrBadSignatureError):
        verify(f"{head}.{payload}.{bad}", KEY, NOW)


def test_wrong_key() -> None:
    with pytest.raises(QrWrongKeyError):
        verify(sign(7, KEY, NBF, EXP), OTHER_KEY, NOW)


def test_expired_and_not_yet_valid() -> None:
    token = sign(7, KEY, NBF, EXP)
    with pytest.raises(QrExpiredError):
        verify(token, KEY, EXP + 1)
    with pytest.raises(QrNotYetValidError):
        verify(token, KEY, NBF - 1)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "fwq2.a.b",
        "fwq1.",
        "fwq1.onlyone",
        "fwq1.a.b.c",
        "fwq1.!!!.???",
        "fwq1.e30.AAAA",  # payload {} has no v
        "fwq1." + _b64(b"not json") + ".AAAA",
        "fwq1." + _b64(b'{"v":2,"b":1,"nbf":1,"exp":2,"kid":"x"}') + ".AAAA",
        "fwq1." + _b64(b'{"v":1,"b":"1","nbf":1,"exp":2,"kid":"x"}') + ".AAAA",
        "fwq1." + _b64(b"[1]") + ".AAAA",
    ],
)
def test_malformed(token: str) -> None:
    with pytest.raises(QrMalformedError):
        verify(token, KEY, NOW)


def test_errors_share_base() -> None:
    for err in (
        QrMalformedError,
        QrWrongKeyError,
        QrBadSignatureError,
        QrNotYetValidError,
        QrExpiredError,
    ):
        assert issubclass(err, QrTokenError)


def test_sign_rejects_inverted_window() -> None:
    with pytest.raises(ValueError):
        sign(1, KEY, EXP, NBF)


def test_key_from_hex() -> None:
    assert key_from_hex(KEY.hex() + "\n") == KEY
    for bad in ("", "zz" * 32, "ab" * 31):
        with pytest.raises(ValueError, match="64 hexadecimal") as exc:
            key_from_hex(bad)
        assert bad not in str(exc.value) or bad == ""


def test_prefix_constant() -> None:
    assert qr_token.PREFIX == "fwq1."


def test_deeply_nested_payload_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "fwq1." + _b64(b"[" * 5000) + ".AAAA"
    with pytest.raises(QrMalformedError, match="too long"):
        verify(token, KEY, NOW)
    # Lift the length cap to reach the JSON parser itself (RecursionError path).
    monkeypatch.setattr(qr_token, "MAX_TOKEN_LEN", 100_000)
    with pytest.raises(QrMalformedError, match="not JSON"):
        verify(token, KEY, NOW)


def test_oversized_token_is_malformed() -> None:
    with pytest.raises(QrMalformedError, match="too long"):
        verify("fwq1." + "A" * 1_000_000, KEY, NOW)
