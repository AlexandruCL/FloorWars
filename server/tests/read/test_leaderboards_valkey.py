"""``app.leaderboards`` against the test Valkey (skipped without ``FLOORWARS_TEST_VALKEY_URL``)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app import leaderboards as lb
from app.valkey import ValkeyClient
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


def test_record_and_top(vk: ValkeyClient) -> None:
    ana, bob = uuid.uuid4(), uuid.uuid4()
    lb.record_verified(vk, 2, ana, 1, 4, 100)
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
