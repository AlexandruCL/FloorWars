"""``ValkeyRateLimiter.refund``: gives one token back, never above capacity."""

import uuid
from collections.abc import Iterator

import pytest

from app.auth.ratelimit import ValkeyRateLimiter
from app.valkey import ValkeyClient
from tests.helpers import TEST_VALKEY_URL


@pytest.fixture
def limiter() -> Iterator[ValkeyRateLimiter]:
    if not TEST_VALKEY_URL:
        pytest.skip("FLOORWARS_TEST_VALKEY_URL not set")
    client = ValkeyClient(TEST_VALKEY_URL)
    try:
        yield ValkeyRateLimiter(client, prefix=f"fw:test:{uuid.uuid4().hex}", clock=lambda: 1000.0)
    finally:
        client.close()


def test_refund_returns_the_token(limiter: ValkeyRateLimiter) -> None:
    assert limiter.hit("b", "s", 1, 600).allowed
    assert not limiter.hit("b", "s", 1, 600).allowed
    limiter.refund("b", "s", 1, 600)
    assert limiter.hit("b", "s", 1, 600).allowed
    assert not limiter.hit("b", "s", 1, 600).allowed


def test_refund_never_exceeds_capacity(limiter: ValkeyRateLimiter) -> None:
    limiter.refund("b", "new", 1, 600)  # no bucket yet: nothing to give back
    assert limiter.hit("b", "s", 2, 600).allowed
    limiter.refund("b", "s", 2, 600)
    limiter.refund("b", "s", 2, 600)
    assert [limiter.hit("b", "s", 2, 600).allowed for _ in range(3)] == [True, True, False]
