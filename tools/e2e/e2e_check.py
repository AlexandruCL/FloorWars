"""End-to-end check of the Week 2 flow against a running server, with no phone.

    python tools/e2e/e2e_check.py --base-url https://api.floorwars.me --email you@student.upt.ro \
        --qr-token-file tools/qr/out/1.token.txt

Steps: request the sign-in code, read it from the e-mail (you type it, hidden), sign in with a
device, list the teams, read the active season, join a team (an existing membership is fine),
check in with the entrance QR token, then refresh the tokens and test reuse detection (takes
about 25 s). Standard library only. Tokens and the code are never printed. It creates or
updates a real account, so use your own e-mail address.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

TIMEOUT_S = 20


def call(
    method: str,
    base: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any]:
    if not base.startswith(("http://", "https://")):
        raise SystemExit("error: --base-url must start with http:// or https://")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method)  # noqa: S310
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, None


def problem(payload: Any) -> str:
    if isinstance(payload, dict):
        return f"{payload.get('type', '?')} - {payload.get('detail') or payload.get('title') or ''}"
    return "no body"


def step(ok: bool, name: str, detail: str = "") -> bool:
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="https://api.floorwars.me")
    parser.add_argument("--email", required=True)
    parser.add_argument("--qr-token-file", type=Path, help="a tools/qr/out/<id>.token.txt file")
    parser.add_argument("--team-id", type=int, help="team to join (default: the first team)")
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/v1"

    status, _ = call("POST", base, "/auth/otp", {"email": args.email})
    if not step(status == 202, "request sign-in code", f"HTTP {status}"):
        return 1
    code = getpass.getpass("6-digit code from the e-mail: ").strip()

    device = {"id": str(uuid.uuid4()), "model": "e2e-check", "has_barometer": False}
    status, tokens = call(
        "POST",
        base,
        "/auth/verify",
        {
            "email": args.email,
            "code": code,
            "device": device,
            "accept_terms": True,
            "confirm_adult": True,
        },
    )
    if not step(
        status == 200,
        "sign in",
        f"HTTP {status}" + ("" if status == 200 else f" {problem(tokens)}"),
    ):
        return 1
    access = tokens["access_token"]

    status, teams = call("GET", base, "/teams")
    if not step(status == 200 and bool(teams), "list teams", f"{len(teams or [])} teams"):
        return 1
    status, season = call("GET", base, "/seasons/active")
    if not step(
        status == 200,
        "active season",
        f"id {season.get('id')}" if status == 200 else problem(season),
    ):
        return 1

    team_id = args.team_id or teams[0]["id"]
    status, joined = call(
        "POST", base, f"/seasons/{season['id']}/join", {"team_id": team_id}, access
    )
    already = status == 409
    if not step(
        status == 201 or already, "join team", "already a member" if already else f"HTTP {status}"
    ):
        print("      " + problem(joined))
        return 1

    if args.qr_token_file:
        token = args.qr_token_file.read_text(encoding="utf-8").strip()
        status, checkin = call(
            "POST", base, "/checkins", {"method": "qr", "qr_token": token}, access
        )
        if not step(
            status == 201,
            "check in with the QR token",
            f"building {checkin.get('building_id')}, valid until {checkin.get('valid_until')}"
            if status == 201
            else f"HTTP {status} {problem(checkin)}",
        ):
            return 1

    status, rotated = call(
        "POST", base, "/auth/refresh", {"refresh_token": tokens["refresh_token"]}
    )
    if not step(status == 200, "refresh tokens", f"HTTP {status}"):
        return 1
    # A token reused within the grace window (20 s by default) is refused without revoking the
    # family, so a retried request does not sign the user out. Wait it out to test real reuse.
    print("      waiting 22 s, past the refresh grace window ...")
    time.sleep(22)
    status, _ = call("POST", base, "/auth/refresh", {"refresh_token": tokens["refresh_token"]})
    step(status == 401, "reusing the old refresh token is refused", f"HTTP {status}")
    status, _ = call("POST", base, "/auth/refresh", {"refresh_token": rotated["refresh_token"]})
    step(status == 401, "...and the whole family is revoked", f"HTTP {status}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
