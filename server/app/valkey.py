"""Minimal synchronous Valkey client (RESP2 over TCP), enough for rate-limit scripts.

Why our own: the approved dependency list for Week 2 has no Valkey/Redis client, and the
features need only ``EVALSHA``/``EVAL`` (plus ``AUTH``/``SELECT`` on connect). Swapping this for
``valkey-py`` later touches this module and ``app/auth/ratelimit.py`` only.

URL: ``redis://[[user]:password@]host[:port][/db]`` (``FLOORWARS_VALKEY_URL``). TLS (``rediss``)
is not supported: Valkey is reached on the internal Compose network only.

Thread safety: one connection guarded by a lock (route handlers run in a thread pool). On any
I/O or protocol error the connection is dropped and the next call reconnects.
"""

import contextlib
import hashlib
import socket
import threading
from urllib.parse import unquote, urlsplit

type RespValue = int | bytes | str | list[RespValue] | None

DEFAULT_TIMEOUT_S = 2.0


class ValkeyError(Exception):
    """Connection, protocol or server error. Never carries the URL (it holds the password)."""


class _ServerError(ValkeyError):
    pass


def _encode(args: tuple[str | bytes | int, ...]) -> bytes:
    out = [f"*{len(args)}\r\n".encode()]
    for arg in args:
        data = arg if isinstance(arg, bytes) else str(arg).encode()
        out.append(b"$%d\r\n%s\r\n" % (len(data), data))
    return b"".join(out)


class ValkeyClient:
    def __init__(self, url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        parts = urlsplit(url)
        if parts.scheme != "redis":
            raise ValueError("valkey url must start with redis:// (no TLS on the internal network)")
        self._host = parts.hostname or "localhost"
        self._port = parts.port or 6379
        self._username = unquote(parts.username) if parts.username else None
        self._password = unquote(parts.password) if parts.password else None
        path = parts.path.lstrip("/")
        self._db = int(path) if path else 0
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._buffer = b""
        self._scripts: dict[str, str] = {}

    # Connection handling.

    def _connect(self) -> None:
        sock = socket.create_connection((self._host, self._port), timeout=self._timeout_s)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self._buffer = b""
        try:
            if self._password is not None:
                auth: tuple[str, ...] = (
                    ("AUTH", self._username, self._password)
                    if self._username
                    else ("AUTH", self._password)
                )
                self._roundtrip(auth)
            if self._db:
                self._roundtrip(("SELECT", self._db))
        except _ServerError as exc:
            # Plain ValkeyError, so execute() drops the half-open connection.
            raise ValkeyError(f"valkey handshake failed: {str(exc).split(' ', 1)[0]}") from None

    def close(self) -> None:
        with self._lock:
            self._drop()

    def _drop(self) -> None:
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
        self._sock = None
        self._buffer = b""

    # RESP2 parsing.

    def _read_line(self) -> bytes:
        assert self._sock is not None  # noqa: S101 (internal invariant)
        while b"\r\n" not in self._buffer:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ValkeyError("connection closed")
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\r\n", 1)
        return line

    def _read_exact(self, n: int) -> bytes:
        assert self._sock is not None  # noqa: S101 (internal invariant)
        while len(self._buffer) < n + 2:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ValkeyError("connection closed")
            self._buffer += chunk
        data, self._buffer = self._buffer[:n], self._buffer[n + 2 :]
        return data

    def _read_reply(self) -> RespValue:
        line = self._read_line()
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode()
        if kind == b"-":
            raise _ServerError(rest.decode(errors="replace"))
        if kind == b":":
            return int(rest)
        if kind == b"$":
            n = int(rest)
            return None if n < 0 else self._read_exact(n)
        if kind == b"*":
            n = int(rest)
            return None if n < 0 else [self._read_reply() for _ in range(n)]
        raise ValkeyError("unexpected reply type")

    def _roundtrip(self, args: tuple[str | bytes | int, ...]) -> RespValue:
        assert self._sock is not None  # noqa: S101 (internal invariant)
        self._sock.sendall(_encode(args))
        return self._read_reply()

    # Public API.

    def execute(self, *args: str | bytes | int) -> RespValue:
        """Send one command and return its reply. Raises ``ValkeyError``."""
        with self._lock:
            try:
                if self._sock is None:
                    self._connect()
                return self._roundtrip(args)
            except _ServerError:
                raise
            except (OSError, ValueError, ValkeyError) as exc:
                self._drop()
                raise ValkeyError(f"valkey unavailable: {type(exc).__name__}") from None

    def run_script(self, script: str, keys: list[str], args: list[str | int]) -> RespValue:
        """``EVALSHA`` with a fallback to ``EVAL`` when the server does not know the script."""
        sha = self._scripts.get(script)
        if sha is None:
            sha = hashlib.sha1(script.encode(), usedforsecurity=False).hexdigest()
            self._scripts[script] = sha
        try:
            return self.execute("EVALSHA", sha, len(keys), *keys, *args)
        except _ServerError as exc:
            if not str(exc).startswith("NOSCRIPT"):
                raise
        return self.execute("EVAL", script, len(keys), *keys, *args)
