"""Token-bucket rate limits in Valkey (plan 3.4 and 7.11).

A bucket holds up to ``capacity`` tokens and refills continuously, ``capacity`` tokens per
``period_s``. Each request takes one token; an empty bucket answers with the wait until the next
token. The whole check is one Lua script, so concurrent API workers cannot race. The time comes
from the API process (``clock``, injectable for tests); there is a single API host, and a clock
step backwards only delays the refill.

Keys: ``fw:rl:<name>:<subject>``. Subjects that are personal data (e-mail addresses) are hashed
before they become part of a key. Keys expire once the bucket would be full again.
"""

import hashlib
import ipaddress
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.valkey import ValkeyClient, ValkeyError

_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local period_ms = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now
end
local rate = capacity / period_ms
tokens = math.min(capacity, tokens + math.max(0, now - ts) * rate)
local allowed = 0
local wait_ms = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait_ms = math.ceil((1 - tokens) / rate)
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity - tokens) / rate) + 1000)
return {allowed, wait_ms}
"""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after_s: int  # 0 when allowed


class RateLimiter(Protocol):
    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        """Take one token. Raises ``app.valkey.ValkeyError`` when the limiter cannot answer."""
        ...


def client_bucket(ip: str) -> str:
    """Rate-limit subject for a client address: IPv4 per address, IPv6 per /64 network.

    One IPv6 host usually controls a whole /64, so per-address buckets would be trivial to
    escape. IPv4-mapped IPv6 addresses count as their IPv4 address. Anything that is not an IP
    (for example the test client's host name) is used as is.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, 64), strict=False))
    return str(address)


def hashed_subject(value: str) -> str:
    """Stable, non-reversible key part for personal data (for example an e-mail address)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


class ValkeyRateLimiter:
    """``RateLimiter`` on Valkey. Any Valkey problem raises ``ValkeyError`` (fail closed)."""

    def __init__(
        self,
        client: ValkeyClient,
        prefix: str = "fw:rl",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._script = client.register_script(_BUCKET_SCRIPT)
        self._prefix = prefix
        self._clock = clock

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        key = f"{self._prefix}:{name}:{subject}"
        now_ms = int(self._clock() * 1000)
        reply = self._script([key], [capacity, period_s * 1000, now_ms])
        if not (isinstance(reply, list) and len(reply) == 2):
            raise ValkeyError("unexpected token bucket reply")
        allowed, wait_ms = reply
        if not (isinstance(allowed, int) and isinstance(wait_ms, int)):
            raise ValkeyError("unexpected token bucket reply")
        return Decision(allowed=allowed == 1, retry_after_s=math.ceil(wait_ms / 1000))
