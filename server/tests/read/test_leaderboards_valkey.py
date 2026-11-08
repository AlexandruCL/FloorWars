"""``app.leaderboards`` against the test Valkey (skipped without ``FLOORWARS_TEST_VALKEY_URL``)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app import leaderboards as lb
from app.valkey import ValkeyClient, ValkeyError
from tests.helpers import TEST_VALKEY_URL


@pytest.fixture
def vk() -> Iterator[ValkeyClient]:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    client = ValkeyClient(TEST_VALKEY_URL)
    client.execute("FLUSHDB")
    yield client
    client.execute("FLUSHDB")
    client.close()


@dataclass(frozen=True)
class Flip:
    building_id: int = 4
    event_id: int = 1
    from_code: str | None = "AC"
    to_code: str = "ETC"
    at: datetime = datetime(2026, 11, 7, tzinfo=UTC)


def test_record_skips_a_season_that_is_not_built(vk: ValkeyClient) -> None:
    assert not lb.record_verified(vk, 2, uuid.uuid4(), 1, 4, 100)
    assert vk.execute("EXISTS", lb.users_key(2), lb.teams_key(2), lb.building_key(2, 4)) == 0


def test_record_during_a_rebuild_skips_and_marks_the_lock_dirty(vk: ValkeyClient) -> None:
    vk.execute("SET", lb.lock_key(2), "tok")
    vk.execute("SET", lb.built_key(2), 1)
    assert not lb.record_verified(vk, 2, uuid.uuid4(), 1, 4, 100)
    assert vk.execute("GET", lb.lock_key(2)) == b"tok:dirty"
    assert vk.execute("EXISTS", lb.users_key(2), lb.teams_key(2), lb.building_key(2, 4)) == 0


def _finish(vk: ValkeyClient, token: str, expiry: int = lb.BUILT_TTL_S) -> object:
    return vk.execute("EVAL", lb._FINISH, 2, lb.lock_key(2), lb.built_key(2), token, expiry)


def test_finish_of_a_dirty_rebuild_deletes_the_marker(vk: ValkeyClient) -> None:
    vk.execute("SET", lb.lock_key(2), "tok:dirty")
    vk.execute("SET", lb.built_key(2), 1)
    assert _finish(vk, "tok") == 0
    assert vk.execute("EXISTS", lb.lock_key(2), lb.built_key(2)) == 0


def test_finish_without_the_lock_keeps_the_other_lock_and_drops_the_marker(
    vk: ValkeyClient,
) -> None:
    vk.execute("SET", lb.lock_key(2), "other")
    vk.execute("SET", lb.built_key(2), 1)
    assert _finish(vk, "tok") == 0
    assert vk.execute("GET", lb.lock_key(2)) == b"other"
    assert vk.execute("EXISTS", lb.built_key(2)) == 0


def test_mark_stale_during_a_rebuild_keeps_that_rebuild_from_setting_the_marker(
    vk: ValkeyClient,
) -> None:
    vk.execute("SET", lb.lock_key(2), "tok")
    lb.mark_stale(vk, 2)
    assert vk.execute("GET", lb.lock_key(2)).endswith(b":dirty")
    assert _finish(vk, "tok") == 0
    assert vk.execute("EXISTS", lb.lock_key(2), lb.built_key(2)) == 0


def test_a_replace_past_the_deadline_stops_inside_its_chunks(
    vk: ValkeyClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[None] = []

    def clock() -> float:  # the first chunk in time, the second one late
        calls.append(None)
        return 0.0 if len(calls) == 1 else 1000.0

    monkeypatch.setattr(lb, "time", SimpleNamespace(monotonic=clock))
    with pytest.raises(ValkeyError):
        lb._replace(vk, "k", {str(i): i + 1 for i in range(501)}, "tok", 15.0)
    assert len(calls) == 2
    assert vk.execute("EXISTS", "k", "k:rebuild:tok") == 0


def test_clean_finish_sets_the_marker_and_releases(vk: ValkeyClient) -> None:
    vk.execute("SET", lb.lock_key(2), "tok")
    assert _finish(vk, "tok") == 1
    assert vk.execute("EXISTS", lb.lock_key(2)) == 0
    assert 0 < vk.execute("TTL", lb.built_key(2)) <= lb.BUILT_TTL_S


def test_record_and_top(vk: ValkeyClient) -> None:
    ana, bob = uuid.uuid4(), uuid.uuid4()
    vk.execute("SET", lb.built_key(2), 1)
    assert lb.record_verified(vk, 2, ana, 1, 4, 100)
    lb.record_verified(vk, 2, bob, 2, 4, 250)
    lb.record_verified(vk, 2, ana, 1, 5, 20)
    assert lb.top(vk, lb.users_key(2), 10) == [(str(bob), 250), (str(ana), 120)]
    assert lb.top(vk, lb.teams_key(2), 1) == [("2", 250)]
    assert lb.top(vk, lb.building_key(2, 4), 10) == [("2", 250), ("1", 100)]
    assert lb.top(vk, lb.building_key(2, 99), 10) is None


def test_publish_flip_reaches_subscriber(vk: ValkeyClient) -> None:
    sub = vk._client.pubsub()
    sub.subscribe(lb.EVENTS_CHANNEL)
    sub.get_message(timeout=1)  # subscribe confirmation
    lb.publish_flip(vk, Flip())
    message = sub.get_message(timeout=2)
    sub.close()
    assert message is not None
    assert b'"building_flipped"' in message["data"]
