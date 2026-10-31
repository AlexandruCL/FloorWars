"""Token-bucket rate limits in Valkey (plan 3.4 and 7.11).

A bucket holds up to ``capacity`` tokens and refills continuously, ``capacity`` tokens per
``period_s``. Each request takes one token; an empty bucket answers with the wait until the next
token. The whole check is one Lua script, so concurrent API workers cannot race, and it uses the
Valkey server clock (``TIME``), so API hosts with skewed clocks agree.

Keys: ``fw:rl:<name>:<subject>``. Subjects that are personal data (e-mail addresses) are hashed
before they become part of a key. Keys expire once the bucket would be full again.
"""

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from app.valkey import ValkeyClient

_BUCKET_SCRIPT = """
local capacity = tonumber(ARGV[1])
local period_ms = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
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
    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision: ...


def hashed_subject(value: str) -> str:
    """Stable, non-reversible key part for personal data (for example an e-mail address)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


class ValkeyRateLimiter:
    """``RateLimiter`` on Valkey. Raises ``app.valkey.ValkeyError`` when Valkey is unreachable."""

    def __init__(self, client: ValkeyClient, prefix: str = "fw:rl") -> None:
        self._client = client
        self._prefix = prefix

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        key = f"{self._prefix}:{name}:{subject}"
        reply = self._client.run_script(_BUCKET_SCRIPT, [key], [capacity, period_s * 1000])
        if not (isinstance(reply, list) and len(reply) == 2):
            raise TypeError("unexpected token bucket reply")
        allowed, wait_ms = reply
        if not (isinstance(allowed, int) and isinstance(wait_ms, int)):
            raise TypeError("unexpected token bucket reply")
        return Decision(allowed=allowed == 1, retry_after_s=math.ceil(wait_ms / 1000))
