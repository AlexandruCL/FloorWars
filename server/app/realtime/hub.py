"""The process's socket hub (plan 7.2.1): one Valkey subscriber, fan-out to the local sockets.

Both API replicas publish every committed flip on ``leaderboards.EVENTS_CHANNEL``
(``publish_flip``: the event JSON plus an internal ``season_id``). Each process holds ONE
subscription, started with the app's lifespan, and puts each message into the queue of every
local socket whose user joined the event's season (``app.events.feed.visible``, the feed's rule).
``season_id`` is stripped first, so a socket gets exactly the contract's event.

The hub never awaits a socket: each socket has a bounded queue, and a socket whose queue is
full (a slow or stuck client) is closed with 1008, not waited for. At most
``MAX_SOCKETS_PER_USER`` sockets per user in this process; a new one closes the oldest with 1008.
"""

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass, field

import valkey.asyncio as avalkey

from app.events.feed import visible
from app.leaderboards import EVENTS_CHANNEL

logger = logging.getLogger(__name__)

MAX_SOCKETS_PER_USER = 3
MAX_QUEUED = 256  # live events waiting for one socket; flips are rare, so a full queue is stuck
CLOSE_POLICY = 1008
# How long ``start`` waits for the first subscription (so the first sockets miss nothing).
SUBSCRIBE_WAIT_S = 2.0
POLL_S = 1.0  # get_message wait; between waits the client's health check may ping Valkey
HEALTH_CHECK_S = 30
RETRY_MAX_S = 30.0

# A queued item: (event_id, JSON text) to send, or a close code.
Item = tuple[int, str] | int


@dataclass(eq=False)
class Connection:
    user_id: uuid.UUID
    seasons: frozenset[int]
    queue: asyncio.Queue[Item] = field(default_factory=lambda: asyncio.Queue(MAX_QUEUED))

    def kick(self, code: int) -> None:
        """Drop what is pending and ask the socket's sender to close with ``code``."""
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(code)


class Hub:
    def __init__(self, valkey_url: str | None) -> None:
        self._url = valkey_url
        self._users: dict[uuid.UUID, list[Connection]] = {}
        self._task: asyncio.Task[None] | None = None
        self.subscribed = asyncio.Event()

    async def start(self) -> None:
        """Start the subscriber (no-op without Valkey: sockets then get the replay only)."""
        if self._url is None or self._task is not None:
            return
        self._task = asyncio.create_task(self._listen(self._url))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.subscribed.wait(), SUBSCRIBE_WAIT_S)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def register(self, user_id: uuid.UUID, seasons: frozenset[int]) -> Connection:
        conns = self._users.setdefault(user_id, [])
        if len(conns) >= MAX_SOCKETS_PER_USER:
            conns.pop(0).kick(CLOSE_POLICY)
        conn = Connection(user_id, seasons)
        conns.append(conn)
        return conn

    def unregister(self, conn: Connection) -> None:
        conns = self._users.get(conn.user_id, [])
        if conn in conns:
            conns.remove(conn)
        if not conns:
            self._users.pop(conn.user_id, None)

    def count(self, user_id: uuid.UUID) -> int:
        return len(self._users.get(user_id, []))

    def dispatch(self, raw: bytes | str) -> None:
        """Fan one published message out to the local sockets that may see it."""
        try:
            event = json.loads(raw)
            season_id = event.pop("season_id", None)
            event_id = int(event["event_id"])
        except (ValueError, KeyError, TypeError, AttributeError):
            logger.warning("unreadable event on the events channel")
            return
        text = json.dumps(event, separators=(",", ":"))
        for conns in list(self._users.values()):
            for conn in list(conns):
                if not visible(season_id, conn.seasons):
                    continue
                try:
                    conn.queue.put_nowait((event_id, text))
                except asyncio.QueueFull:
                    self.unregister(conn)
                    conn.kick(CLOSE_POLICY)
                    logger.info("slow socket dropped")

    async def _listen(self, url: str) -> None:
        delay = 1.0
        while True:
            client = avalkey.Valkey.from_url(
                url,
                socket_connect_timeout=2.0,
                socket_keepalive=True,
                health_check_interval=HEALTH_CHECK_S,
            )
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.subscribe(EVENTS_CHANNEL)
                self.subscribed.set()
                delay = 1.0
                while True:
                    message = await pubsub.get_message(timeout=POLL_S)
                    if message is not None and message["type"] == "message":
                        self.dispatch(message["data"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Live delivery pauses; sockets still get the replay, phones the 15-minute poll.
                logger.warning(
                    "events subscriber down, retrying", extra={"error": type(exc).__name__}
                )
            finally:
                self.subscribed.clear()
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                with contextlib.suppress(Exception):
                    await client.aclose()
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_S)
