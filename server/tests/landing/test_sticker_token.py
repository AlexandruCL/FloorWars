"""Landing sticker tokens (``fwl1.``, ``kind: "landing"`` inside the signed payload)."""

import pytest

from app.qr_token import (
    LANDING_PREFIX,
    MAX_TOKEN_LEN,
    PREFIX,
    QrBadSignatureError,
    QrExpiredError,
    QrMalformedError,
    sign,
    verify,
    verify_landing,
)

KEY = bytes(range(32))
NBF, EXP = 1_800_000_000, 1_800_000_000 + 31 * 86400
NOW = NBF + 100


def test_sticker_round_trip() -> None:
    token = sign(7, KEY, NBF, EXP, landing=True)
    assert token.startswith(LANDING_PREFIX)
    assert len(token) <= MAX_TOKEN_LEN
    assert verify_landing(token, KEY, NOW).building_id == 7


def test_entrance_code_is_not_a_sticker() -> None:
    with pytest.raises(QrMalformedError):
        verify_landing(sign(7, KEY, NBF, EXP), KEY, NOW)


def test_sticker_is_not_an_entrance_code() -> None:
    with pytest.raises(QrMalformedError):
        verify(sign(7, KEY, NBF, EXP, landing=True), KEY, NOW)


def test_sticker_with_entrance_prefix_is_refused() -> None:
    """The prefix is not signed: only the kind claim keeps a sticker from checking in."""
    token = sign(7, KEY, NBF, EXP, landing=True)
    with pytest.raises(QrMalformedError, match="entrance"):
        verify(PREFIX + token[len(LANDING_PREFIX) :], KEY, NOW)


def test_entrance_code_with_sticker_prefix_is_refused() -> None:
    token = sign(7, KEY, NBF, EXP)
    with pytest.raises(QrMalformedError, match="landing"):
        verify_landing(LANDING_PREFIX + token[len(PREFIX) :], KEY, NOW)


def test_tampered_sticker() -> None:
    token = sign(7, KEY, NBF, EXP, landing=True)
    other = sign(8, KEY, NBF, EXP, landing=True)
    forged = token.split(".")[0] + "." + other.split(".")[1] + "." + token.split(".")[2]
    with pytest.raises(QrBadSignatureError):
        verify_landing(forged, KEY, NOW)


def test_expired_sticker() -> None:
    with pytest.raises(QrExpiredError):
        verify_landing(sign(7, KEY, NBF, EXP, landing=True), KEY, EXP + 1)
