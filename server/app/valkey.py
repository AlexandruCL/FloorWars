"""Thin wrapper around ``valkey-py`` for the features that need Valkey (rate limits).

URL: ``redis://[[user]:password@]host[:port][/db]`` (``FLOORWARS_VALKEY_URL``). The client uses a
connection pool with 2 s connect and read timeouts, a periodic health check, and retries a
command once on a connection error or timeout.

Every failure, including a reply of an unexpected shape, is raised as ``ValkeyError``, so callers
can fail closed with one ``except``. Error messages never contain the URL (it holds the password).
"""

from collections.abc import Sequence
from typing import Any

import valkey
from valkey.backoff import NoBackoff
from valkey.exceptions import ConnectionError as ValkeyConnectionError
from valkey.exceptions import TimeoutError as ValkeyTimeoutError
from valkey.exceptions import ValkeyError as LibraryError
from valkey.retry import Retry

TIMEOUT_S = 2.0
HEALTH_CHECK_INTERVAL_S = 30
MAX_CONNECTIONS = 20


class ValkeyError(Exception):
    """Valkey is unreachable, failed, or answered something unexpected."""


class Script:
    """A Lua script registered once (``EVALSHA``, loaded again if the server lost it)."""

    def __init__(self, script: Any) -> None:
        self._script = script

    def __call__(self, keys: Sequence[str], args: Sequence[str | int]) -> Any:
        try:
            return self._script(keys=list(keys), args=list(args))
        except LibraryError as exc:
            raise ValkeyError(f"valkey script failed: {type(exc).__name__}") from None


class ValkeyClient:
    def __init__(self, url: str, timeout_s: float = TIMEOUT_S) -> None:
        try:
            self._client = valkey.Valkey.from_url(
                url,
                socket_timeout=timeout_s,
                socket_connect_timeout=timeout_s,
                health_check_interval=HEALTH_CHECK_INTERVAL_S,
                retry=Retry(NoBackoff(), 1),
                retry_on_error=[ValkeyConnectionError, ValkeyTimeoutError],
                max_connections=MAX_CONNECTIONS,
            )
        except ValueError:
            raise ValueError("invalid valkey url") from None

    def register_script(self, script: str) -> Script:
        """Register ``script``; nothing is sent until the first call."""
        return Script(self._client.register_script(script))

    def execute(self, *args: str | int) -> Any:
        """Run one raw command (tests and maintenance)."""
        try:
            return self._client.execute_command(*args)  # type: ignore[no-untyped-call]
        except LibraryError as exc:
            raise ValkeyError(f"valkey command failed: {type(exc).__name__}") from None

    def close(self) -> None:
        self._client.close()  # type: ignore[no-untyped-call]
