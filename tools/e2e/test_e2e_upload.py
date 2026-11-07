"""Tests of the --upload flow of e2e_check.py against an in-memory fake of the three endpoints.

Run: python -m pytest -q tools/e2e

TODO (when POST /segments is on main): point `call` at the FastAPI test app (TestClient) instead of
FakeServer, so the flow also runs against the real handlers.
"""

# Test file outside server/, so the server's per-file ignores do not apply (S101 assert).
# ruff: noqa: S101

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import e2e_check
import pytest

ACCESS = "ACCESS-TOKEN-VALUE"
DEVICE = "22222222-2222-4222-8222-222222222222"


class FakeServer:
    """Answers like the Week 3 server: scores a good segment once, rejects a bad ratio."""

    def __init__(self, *, repeat_points: bool = False, score: bool = True) -> None:
        self.requests: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.points = 0
        self.repeat_points = repeat_points
        self.score = score

    def standings(self) -> dict[str, Any]:
        teams = [{"team_id": 1, "code": "AC", "color_hex": "#112233", "points": self.points}]
        return {
            "building_id": 4,
            "season_id": 1,
            "owner": {"code": "AC"} if self.points else None,
            "claimed_at": None,
            "teams": teams if self.points else [],
        }

    def __call__(
        self,
        method: str,
        base: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        self.requests.append(
            {"method": method, "path": path, "body": body, "token": token, "headers": headers}
        )
        if path.endswith("/standings"):
            return 200, self.standings()
        assert body is not None
        seg = body["segments"][0]
        if not 4 <= seg["steps"] / seg["ascent_m"] <= 8:
            rejected = [{"id": seg["id"], "reason": "pressure_steps_mismatch"}]
            return 200, {"accepted": [], "rejected": rejected, "flips": []}
        if seg["id"] in self.seen:
            item = {"id": seg["id"], "steps_scored": seg["steps"]}
            if self.repeat_points:
                item["points"] = 5
            return 200, {"accepted": [item], "rejected": [], "flips": []}
        self.seen.add(seg["id"])
        if not self.score:
            rejected = [{"id": seg["id"], "reason": "speed"}]
            return 200, {"accepted": [], "rejected": rejected, "flips": []}
        self.points += seg["steps"]
        item = {"id": seg["id"], "steps_scored": seg["steps"], "points": seg["steps"]}
        return 200, {"accepted": [item], "rejected": [], "flips": []}


@pytest.fixture
def checkin() -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": str(uuid.uuid4()),
        "building_id": 4,
        "method": "qr",
        "valid_from": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(minutes=89)).isoformat(),
    }


def run(server: FakeServer, checkin: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> bool:
    monkeypatch.setattr(e2e_check, "call", server)
    return e2e_check.upload_checks("https://example.test/v1", ACCESS, DEVICE, checkin)


def test_the_flow_passes_against_a_correct_server(checkin, monkeypatch, capsys):
    server = FakeServer()
    assert run(server, checkin, monkeypatch)
    out = capsys.readouterr().out
    assert out.count("[OK]") == 6  # standings before, three uploads, standings after, summary
    assert "[FAIL]" not in out
    assert "AC 0 -> " in out
    assert "owner: AC" in out


def test_requests_follow_the_contract(checkin, monkeypatch):
    server = FakeServer()
    assert run(server, checkin, monkeypatch)
    posts = [r for r in server.requests if r["method"] == "POST"]
    assert [r["path"] for r in posts] == ["/segments"] * 3
    keys = [r["headers"]["Idempotency-Key"] for r in posts]
    assert len(set(keys)) == 3  # a fresh key for every request
    for r in posts:
        assert r["body"]["device_id"] == DEVICE
        assert r["token"] == ACCESS
        (seg,) = r["body"]["segments"]
        assert seg["checkin_id"] == checkin["id"]
        assert seg["building_id"] == 4
    assert posts[0]["body"]["segments"][0]["id"] == posts[1]["body"]["segments"][0]["id"]
    started = datetime.fromisoformat(posts[0]["body"]["segments"][0]["started_at"])
    assert datetime.fromisoformat(checkin["valid_from"]) <= started <= datetime.now(UTC)
    paths = [r["path"] for r in server.requests if r["method"] == "GET"]
    assert paths == ["/buildings/4/standings"] * 2


def test_secrets_are_never_printed(checkin, monkeypatch, capsys):
    run(FakeServer(), checkin, monkeypatch)
    captured = capsys.readouterr()
    assert ACCESS not in captured.out + captured.err
    assert "Bearer" not in captured.out + captured.err


def test_fails_when_a_repeat_is_scored_again(checkin, monkeypatch, capsys):
    assert not run(FakeServer(repeat_points=True), checkin, monkeypatch)
    assert "[FAIL] upload it again" in capsys.readouterr().out


def test_fails_when_the_valid_segment_is_rejected(checkin, monkeypatch, capsys):
    assert not run(FakeServer(score=False), checkin, monkeypatch)
    out = capsys.readouterr().out
    assert "[FAIL] upload a valid segment" in out
    assert "pressure_steps_mismatch" not in out  # stopped before the bad-ratio upload


def test_upload_needs_a_qr_token_file(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["e2e_check.py", "--email", "a@b.c", "--upload"])
    with pytest.raises(SystemExit) as exit_info:
        e2e_check.main()
    assert exit_info.value.code == 2
    assert "--qr-token-file" in capsys.readouterr().err
