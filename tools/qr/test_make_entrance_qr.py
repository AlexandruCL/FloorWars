"""Tests for the entrance QR tool (no database needed)."""

import time
from pathlib import Path

import make_entrance_qr
import pytest
from app.qr_token import QrExpiredError, key_from_hex, verify

KEY_HEX = "00112233445566778899aabbccddeeff" * 2
BUILDINGS = [(1, "Library & Lab"), (2, "Aula")]


def _run(tmp_path: Path, *extra: str) -> list[str]:
    key_file = tmp_path / "key.txt"
    key_file.write_text(KEY_HEX + "\n", encoding="ascii")
    args = ["--key-file", str(key_file), "--out", str(tmp_path / "out"), *extra]
    for building_id, name in BUILDINGS:
        args += ["--building-id", str(building_id), "--name", name]
    assert make_entrance_qr.main(args) == 0
    return sorted(p.name for p in (tmp_path / "out").iterdir())


def test_one_svg_per_building_with_verifiable_token(tmp_path: Path) -> None:
    files = _run(tmp_path)
    assert files == ["1.svg", "1.token.txt", "2.svg", "2.token.txt"]
    out = tmp_path / "out"
    key = key_from_hex(KEY_HEX)
    for building_id, name in BUILDINGS:
        svg = (out / f"{building_id}.svg").read_text(encoding="utf-8")
        assert svg.startswith("<svg")
        assert name.replace("&", "&amp;") in svg
        token = (out / f"{building_id}.token.txt").read_text(encoding="ascii").strip()
        claims = verify(token, key, int(time.time()))
        assert claims.building_id == building_id
        assert claims.exp - claims.nbf == 7 * 86400


def test_days_option(tmp_path: Path) -> None:
    _run(tmp_path, "--days", "2")
    token = (tmp_path / "out" / "1.token.txt").read_text(encoding="ascii").strip()
    key = key_from_hex(KEY_HEX)
    assert verify(token, key, int(time.time())).building_id == 1
    with pytest.raises(QrExpiredError):
        verify(token, key, int(time.time()) + 3 * 86400)


def test_key_never_printed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run(tmp_path)
    captured = capsys.readouterr()
    assert KEY_HEX not in captured.out + captured.err


def test_key_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOORWARS_QR_HMAC_KEY", KEY_HEX)
    args = ["--out", str(tmp_path), "--building-id", "5", "--name", "X"]
    assert make_entrance_qr.main(args) == 0
    assert (tmp_path / "5.svg").exists()


def test_bad_key_exits_without_leaking(tmp_path: Path) -> None:
    key_file = tmp_path / "key.txt"
    key_file.write_text("abcd", encoding="ascii")
    with pytest.raises(SystemExit) as exc:
        make_entrance_qr.main(
            [
                "--key-file",
                str(key_file),
                "--out",
                str(tmp_path),
                "--building-id",
                "1",
                "--name",
                "X",
            ]
        )
    assert "abcd" not in str(exc.value)
