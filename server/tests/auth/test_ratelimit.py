"""Token buckets: refill and Retry-After maths with a fake clock, on a real Valkey."""

import os
from collections.abc import Iterator
from typing import Any

import pytest

from app.auth.ratelimit import ValkeyRateLimiter
from app.valkey import ValkeyClient, ValkeyError

TEST_VALKEY_URL = os.environ.get("FLOORWARS_TEST_VALKEY_URL")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def valkey_client() -> Iterator[ValkeyClient]:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    client = ValkeyClient(TEST_VALKEY_URL)
    client.execute("FLUSHDB")
    yield client
    client.close()


def test_bucket_refills_and_reports_retry_after(valkey_client: ValkeyClient) -> None:
    clock = FakeClock()
    limiter = ValkeyRateLimiter(valkey_client, clock=clock)
    # 4 tokens per hour: one token every 900 s.
    for _ in range(4):
        assert limiter.hit("t", "a", 4, 3600).allowed
    denied = limiter.hit("t", "a", 4, 3600)
    assert not denied.allowed
    assert 900 <= denied.retry_after_s <= 901  # ceil of float maths

    clock.now += 600
    later = limiter.hit("t", "a", 4, 3600)
    assert not later.allowed
    assert 300 <= later.retry_after_s <= 301

    clock.now += 301
    assert limiter.hit("t", "a", 4, 3600).allowed
    assert not limiter.hit("t", "a", 4, 3600).allowed

    # A full period refills to capacity, never above it.
    clock.now += 10 * 3600
    assert sum(limiter.hit("t", "a", 4, 3600).allowed for _ in range(6)) == 4


def test_buckets_are_independent(valkey_client: ValkeyClient) -> None:
    limiter = ValkeyRateLimiter(valkey_client, clock=FakeClock())
    assert limiter.hit("t", "a", 1, 3600).allowed
    assert not limiter.hit("t", "a", 1, 3600).allowed
    assert limiter.hit("t", "b", 1, 3600).allowed
    assert limiter.hit("u", "a", 1, 3600).allowed


def test_unreachable_valkey_raises_valkey_error() -> None:
    limiter = ValkeyRateLimiter(ValkeyClient("redis://127.0.0.1:1/0", timeout_s=0.5))
    with pytest.raises(ValkeyError):
        limiter.hit("t", "a", 1, 3600)


class _OddScript:
    def __init__(self, reply: Any) -> None:
        self.reply = reply

    def __call__(self, keys: Any, args: Any) -> Any:
        return self.reply


class _OddClient:
    def __init__(self, reply: Any) -> None:
        self.reply = reply

    def register_script(self, script: str) -> _OddScript:
        return _OddScript(self.reply)


@pytest.mark.parametrize("reply", [None, [1], [b"1", 0], "OK", [1, 2, 3]])
def test_unexpected_reply_is_valkey_error(reply: Any) -> None:
    limiter = ValkeyRateLimiter(_OddClient(reply))  # type: ignore[arg-type]
    with pytest.raises(ValkeyError):
        limiter.hit("t", "a", 1, 3600)
