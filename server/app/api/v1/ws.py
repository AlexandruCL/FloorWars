"""``WS /v1/ws`` (``openWebSocket``): replay from ``since``, then live events (plan 7.2.1).

- Auth on the upgrade only: ``Authorization: Bearer <token>`` or the ``access_token`` query. A
  missing, invalid or expired token, or a deleted user, gets an HTTP 401 ``Problem`` on the upgrade
  (``send_denial_response``), never 403 and never a close after accept. A token that expires
  while the socket is open does not close it (Ionut, 2026-11-20).
- Order: register with the process hub first (live events queue up), then replay
  ``events_after`` page by page, then forward the queued and new live events, dropping only the
  ids the replay sent (Ionut, 2026-11-20). A lower id that commits after the replay's query still
  arrives; anything else the client already has, it drops by ``event_id``. The set is the replay's
  ids only, so it stays bounded.
- The database is used only in thread-pool calls with their own short sessions (the user and
  joined seasons on connect, one per replay page); no connection is held while the socket is open.
- Joined seasons are read once on connect: a season joined later shows up after a reconnect.
- Client messages are read and ignored. Uvicorn sends a ping every 20 s and answers the client's.
"""

import asyncio
import contextlib
import json
import uuid
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool

from app import metrics
from app.api.problems import problem_response
from app.auth.tokens import AccessTokens, TokenError
from app.db.models import User
from app.events.feed import MAX_EVENT_ID, MAX_LIMIT, EventPage, events_after, joined_seasons
from app.realtime.hub import Connection, Hub

router = APIRouter(tags=["realtime"])

SEND_TIMEOUT_S = 10.0  # a send blocked longer than this (slow client) drops the socket


def _token(websocket: WebSocket) -> str | None:
    scheme, _, credentials = websocket.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credentials:
        return credentials.strip()
    return websocket.query_params.get("access_token") or None


def _since(raw: str | None) -> int | None:
    if raw is None:
        return 0
    if not raw.isascii() or not raw.isdigit() or len(raw) > 19:
        return None
    since = int(raw)
    return since if since <= MAX_EVENT_ID else None


def _member(factory: sessionmaker[Session], user_id: uuid.UUID) -> frozenset[int] | None:
    """The user's joined seasons, or None when the user no longer exists."""
    with factory() as db:
        if db.get(User, user_id) is None:
            return None
        return frozenset(joined_seasons(db, user_id))


def _page(factory: sessionmaker[Session], user_id: uuid.UUID, since: int) -> EventPage:
    with factory() as db:
        return events_after(db, user_id, since, MAX_LIMIT)


async def _send(websocket: WebSocket, text: str) -> None:
    await asyncio.wait_for(websocket.send_text(text), SEND_TIMEOUT_S)


async def _replay(
    websocket: WebSocket, factory: sessionmaker[Session], user_id: uuid.UUID, since: int
) -> set[int]:
    """Send every visible event after ``since``; return the ids sent."""
    sent: set[int] = set()
    while True:
        page = await run_in_threadpool(_page, factory, user_id, since)
        for item in page.items:
            await _send(websocket, _json(item))
            sent.add(cast(int, item["event_id"]))
        since = page.last_event_id
        if not page.has_more:
            return sent


def _json(item: dict[str, Any]) -> str:
    return json.dumps(item, separators=(",", ":"))


async def _forward(websocket: WebSocket, conn: Connection, replayed: set[int]) -> None:
    while True:
        item = await conn.queue.get()
        if isinstance(item, int):  # kicked by the hub (socket cap or slow client)
            await asyncio.wait_for(websocket.close(item), SEND_TIMEOUT_S)
            return
        event_id, text = item
        # Only what the replay sent is dropped: a lower id that committed after the replay's
        # query (ids are assigned before commit) is still delivered. The client dedupes the rest.
        if event_id not in replayed:
            await _send(websocket, text)


async def _until_disconnect(websocket: WebSocket) -> None:
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass


@router.websocket("/ws", name="openWebSocket")
async def open_websocket(websocket: WebSocket) -> None:
    state = websocket.app.state
    tokens: AccessTokens = state.access_tokens
    token = _token(websocket)
    seasons: frozenset[int] | None = None
    user_id: uuid.UUID | None = None
    if token is not None:
        try:
            user_id = tokens.verify(token).user_id
        except TokenError:
            user_id = None
    if user_id is not None:
        seasons = await run_in_threadpool(_member, state.sessionmaker, user_id)
    if user_id is None or seasons is None:
        detail = "Missing access token." if token is None else "Invalid or expired access token."
        await websocket.send_denial_response(
            problem_response(401, detail=detail, headers={"WWW-Authenticate": "Bearer"})
        )
        return
    since = _since(websocket.query_params.get("since"))
    if since is None:
        # 422 before accept (Ionut, 2026-11-20; contract PR #82).
        await websocket.send_denial_response(
            problem_response(422, detail="since must be an integer from 0 to 2^63-1.")
        )
        return

    hub: Hub = state.hub
    await websocket.accept()
    conn = hub.register(user_id, seasons)  # before the replay: no live event can fall between
    metrics.WS_CONNECTIONS.inc()
    try:
        replayed = await _replay(websocket, state.sessionmaker, user_id, since)
        tasks = {
            asyncio.create_task(_forward(websocket, conn, replayed)),
            asyncio.create_task(_until_disconnect(websocket)),
        }
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, TimeoutError):
                await task
    except (WebSocketDisconnect, TimeoutError):
        pass  # the client left, or a send blocked: the socket is dropped
    finally:
        metrics.WS_CONNECTIONS.dec()
        hub.unregister(conn)
