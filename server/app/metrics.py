"""The one Prometheus registry (plan 7.8). Other modules import the helpers here and never create
their own metrics. No label holds a user id, e-mail, device id, token or coordinate: labels are a
route template, a method, a status code, a reject reason or a flag rule (all from fixed sets).
"""

import logging
import time
from collections.abc import Iterable
from datetime import UTC, datetime

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client import generate_latest as _generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("floorwars.metrics")

REGISTRY = CollectorRegistry()
CONTENT_TYPE = CONTENT_TYPE_LATEST

HTTP_REQUESTS = Counter(
    "floorwars_http_requests_total",
    "HTTP requests by route template, method and status code.",
    ["route", "method", "status"],
    registry=REGISTRY,
)
HTTP_SECONDS = Histogram(
    "floorwars_http_request_duration_seconds",
    "HTTP request duration by route template and method.",
    ["route", "method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
SEGMENTS_ACCEPTED = Counter(
    "floorwars_segments_accepted_total", "Verified segments stored.", registry=REGISTRY
)
SEGMENTS_REJECTED = Counter(
    "floorwars_segments_rejected_total",
    "Segments rejected, by reject reason.",
    ["reason"],
    registry=REGISTRY,
)
DETECTION_SECONDS = Histogram(
    "floorwars_detection_latency_seconds",
    "Segment started_at to server accept.",
    buckets=(5, 15, 30, 60, 300, 900, 3600, 6 * 3600, 24 * 3600, 7 * 24 * 3600),
    registry=REGISTRY,
)
FRAUD_FLAGS = Counter(
    "floorwars_fraud_flags_total", "Fraud flags raised, by rule.", ["rule"], registry=REGISTRY
)
WS_CONNECTIONS = Gauge(
    "floorwars_websocket_connections", "Open WebSocket connections.", registry=REGISTRY
)
ACTIVE_USERS = Gauge(
    "floorwars_active_users",
    "Distinct users with an upload in the last 15 minutes (the same value on every replica).",
    registry=REGISTRY,
)

ACTIVE_WINDOW = "15 minutes"


def record_accepted(started_at: datetime) -> None:
    SEGMENTS_ACCEPTED.inc()
    DETECTION_SECONDS.observe(max(0.0, (datetime.now(UTC) - started_at).total_seconds()))


def record_rejected(reason: str) -> None:
    SEGMENTS_REJECTED.labels(reason).inc()


def record_flags(rules: Iterable[str]) -> None:
    for rule in rules:
        FRAUD_FLAGS.labels(rule).inc()


def render(factory: sessionmaker[Session] | None) -> bytes:
    """The scrape body. The active-user gauge is read from the database at scrape time."""
    if factory is not None:
        try:
            with factory() as db:
                ACTIVE_USERS.set(
                    db.execute(
                        text(
                            "SELECT count(DISTINCT user_id) FROM segment_receipt "
                            "WHERE created_at > now() - CAST(:w AS interval)"
                        ),
                        {"w": ACTIVE_WINDOW},
                    ).scalar_one()
                )
        except Exception:  # a database error must not fail the scrape: keep the last value
            logger.warning("active users query failed", exc_info=True)
    return _generate_latest(REGISTRY)


class MetricsMiddleware:
    """Pure ASGI middleware: request count and latency per route template (never the raw path)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        status = 500
        start = time.perf_counter()

        async def wrapped(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            route = _template(scope)
            method = scope["method"]
            HTTP_REQUESTS.labels(route, method, str(status)).inc()
            HTTP_SECONDS.labels(route, method).observe(time.perf_counter() - start)


def _template(scope: Scope) -> str:
    """The matched route's path template; one fixed label for unmatched paths (no cardinality
    from scanners)."""
    route = scope.get("route")
    if route is not None:
        return str(route.path)
    for candidate in scope["app"].router.routes:
        if candidate.matches(scope)[0] == Match.FULL:
            return str(getattr(candidate, "path", "unmatched"))
    return "unmatched"
