"""Pure helpers of ``app.leaderboards`` with a fake client (no Valkey needed)."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app import leaderboards as lb
from app.segments import service
from app.valkey import ValkeyError


class FakeClient:
    """Implements only the commands ``app.leaderboards`` sends."""

    def __init__(self) -> None:
        self.sets: dict[str, dict[str, float]] = {}
        self.published: list[tuple[str, str]] = []

    def execute(self, *args: str | int) -> Any:
        cmd, *rest = args
        if cmd == "ZINCRBY":
            key, inc, member = str(rest[0]), float(rest[1]), str(rest[2])
            z = self.sets.setdefault(key, {})
            z[member] = z.get(member, 0.0) + inc
            return str(z[member])
        if cmd == "ZREVRANGE":
            z = self.sets.get(str(rest[0]), {})
            items = sorted(z.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
            stop = int(rest[2])
            items = items[: stop + 1]
            return [x for member, score in items for x in (member, str(score))]
        if cmd == "EXISTS":
            return int(str(rest[0]) in self.sets)
        if cmd == "PUBLISH":
            self.published.append((str(rest[0]), str(rest[1])))
            return 0
        raise AssertionError(f"unexpected command {cmd}")


@dataclass(frozen=True)
class Flip:
    building_id: int
    event_id: int
    from_code: str | None
    to_code: str
    at: datetime


def test_keys() -> None:
    assert lb.users_key(3) == "fw:lb:s3:users"
    assert lb.teams_key(3) == "fw:lb:s3:teams"
    assert lb.building_key(3, 9) == "fw:lb:s3:b9:teams"
    assert lb.built_key(3) == "fw:lb:s3:built"


class Failing:
    """Board updates fail. ``mark_stale`` calls are recorded (by marker key); the first
    ``failed_marks`` of them fail too."""

    def __init__(self, failed_marks: int = 0) -> None:
        self.failed_marks = failed_marks
        self.marked: list[object] = []

    def execute(self, *args: str | int) -> Any:
        if args[:2] == ("EVAL", lb._STALE):
            self.marked.append(args[4])
            if len(self.marked) <= self.failed_marks:
                raise ValkeyError("down")
            return None
        raise ValkeyError("down")


def _scored(season_id: int) -> service.ScoredSegment:
    return service.ScoredSegment(season_id, uuid.uuid4(), 7, 4, 60, 60)


def test_a_failed_update_marks_every_season_of_the_batch_stale() -> None:
    vk = Failing()
    service._notify(service.ValkeyLeaderboards(vk), [_scored(1), _scored(2), _scored(1)], [])
    assert vk.marked == ["fw:lb:s1:built", "fw:lb:s2:built"]


def test_a_failed_mark_does_not_stop_the_next_season() -> None:
    vk = Failing(failed_marks=1)
    service._notify(service.ValkeyLeaderboards(vk), [_scored(1), _scored(2)], [])
    assert vk.marked == ["fw:lb:s1:built", "fw:lb:s2:built"]


def test_a_failed_update_and_a_failed_mark_still_return(caplog: pytest.LogCaptureFixture) -> None:
    service._notify(service.ValkeyLeaderboards(Failing(failed_marks=9)), [_scored(1)], [])
    assert any(r.message == "leaderboard update failed" for r in caplog.records)


def test_record_verified_ignores_zero_points() -> None:
    vk = FakeClient()
    assert not lb.record_verified(vk, 1, uuid.uuid4(), 7, 4, 0)
    assert vk.sets == {}


def test_top_orders_and_limits() -> None:
    vk = FakeClient()
    for team, pts in (("1", 10), ("2", 30), ("3", 20)):
        vk.execute("ZINCRBY", "k", pts, team)
    assert lb.top(vk, "k", 2) == [("2", 30), ("3", 20)]


def test_top_missing_key_is_none() -> None:
    assert lb.top(FakeClient(), "nope", 5) is None


def test_top_rejects_odd_reply() -> None:
    class Bad:
        def execute(self, *args: str | int) -> Any:
            return "oops"

    with pytest.raises(ValkeyError):
        lb.top(Bad(), "k", 5)


def test_publish_flip_message() -> None:
    vk = FakeClient()
    at = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)
    lb.publish_flip(vk, Flip(4, 12, None, "AC", at))
    channel, message = vk.published[0]
    assert channel == "fw:events"
    assert json.loads(message) == {
        "type": "building_flipped",
        "event_id": 12,
        "building_id": 4,
        "from_team": None,
        "to_team": "AC",
        "at": at.isoformat(),
    }
