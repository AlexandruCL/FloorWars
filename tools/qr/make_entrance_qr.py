"""Create signed entrance QR codes (one SVG per building).

The key (64 hex characters) is read from ``--key-file`` or the ``FLOORWARS_QR_HMAC_KEY``
environment variable; it is never taken as a command-line value and never printed.

Examples::

    python tools/qr/make_entrance_qr.py --key-file key.txt --out out \
        --building-id 1 --name "Library" --building-id 2 --name "Lab"
    python tools/qr/make_entrance_qr.py --key-file key.txt --out out --from-db

Per building it writes ``<id>.svg`` (QR plus name and validity dates) and ``<id>.token.txt``
(the token string embedded in the QR).
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.svg import SvgPathImage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

from app.qr_token import key_from_hex, sign

KEY_ENV = "FLOORWARS_QR_HMAC_KEY"
DB_ENV = "FLOORWARS_DATABASE_URL"
CAPTION_HEIGHT = 7  # in QR modules


def load_key(key_file: str | None) -> bytes:
    """Read the key from a file, else from the environment. Error messages never contain it."""
    if key_file:
        raw = Path(key_file).read_text(encoding="ascii")
    else:
        raw = os.environ.get(KEY_ENV, "")
        if not raw:
            raise SystemExit(f"error: give --key-file or set {KEY_ENV}")
    try:
        return key_from_hex(raw)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None


def buildings_from_db() -> list[tuple[int, str]]:
    from sqlalchemy import create_engine, text

    url = os.environ.get(DB_ENV)
    if not url:
        raise SystemExit(f"error: {DB_ENV} is not set")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name FROM building ORDER BY id")).all()
    finally:
        engine.dispose()
    return [(int(r[0]), str(r[1])) for r in rows]


def render_svg(token: str, name: str, nbf: int, exp: int) -> str:
    """QR for ``token`` with the building name and validity dates as text underneath."""
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=4)
    qr.add_data(token)
    qr.make(fit=True)
    raw = qr.make_image(image_factory=SvgPathImage).to_string().decode("utf-8")
    size = int(raw.split('viewBox="0 0 ')[1].split(" ")[0])
    inner = raw[raw.index(">") + 1 : raw.rindex("</svg>")]
    first = datetime.fromtimestamp(nbf, UTC).strftime("%Y-%m-%d")
    last = datetime.fromtimestamp(exp, UTC).strftime("%Y-%m-%d")
    height = size + CAPTION_HEIGHT
    mid = size / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{size}mm" '
        f'height="{height}mm" viewBox="0 0 {size} {height}">'
        f'<rect width="{size}" height="{height}" fill="#fff"/>'
        f"{inner}"
        f'<text x="{mid}" y="{size}" text-anchor="middle" font-family="sans-serif" '
        f'font-size="1.8" font-weight="bold">{escape(name)}</text>'
        f'<text x="{mid}" y="{size + 2.6}" text-anchor="middle" font-family="sans-serif" '
        f'font-size="1.3">Valid {first} to {last} (UTC)</text>'
        "</svg>\n"
    )


def generate(
    buildings: list[tuple[int, str]],
    key: bytes,
    days: int,
    out: Path,
    now: int | None = None,
) -> list[Path]:
    """Write ``<id>.svg`` and ``<id>.token.txt`` per building; return the SVG paths."""
    start = int(time.time()) if now is None else now
    end = start + days * 86400
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for building_id, name in buildings:
        token = sign(building_id, key, start, end)
        svg_path = out / f"{building_id}.svg"
        svg_path.write_text(render_svg(token, name, start, end), encoding="utf-8")
        (out / f"{building_id}.token.txt").write_text(token + "\n", encoding="ascii")
        written.append(svg_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create signed entrance QR codes (SVG)."
    )
    parser.add_argument("--key-file", help="file holding the 64-hex-character key")
    parser.add_argument("--building-id", type=int, action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument(
        "--from-db", action="store_true", help=f"read buildings via {DB_ENV}"
    )
    parser.add_argument(
        "--days", type=int, default=7, help="validity in days (default 7)"
    )
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    if args.days < 1:
        parser.error("--days must be at least 1")
    if args.from_db:
        if args.building_id or args.name:
            parser.error("--from-db cannot be combined with --building-id/--name")
        buildings = buildings_from_db()
    else:
        if not args.building_id or len(args.building_id) != len(args.name):
            parser.error("give matching --building-id and --name pairs, or --from-db")
        buildings = list(zip(args.building_id, args.name, strict=True))
    if not buildings:
        parser.error("no buildings")

    key = load_key(args.key_file)
    for path in generate(buildings, key, args.days, Path(args.out)):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
