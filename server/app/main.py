"""FastAPI application factory.

Run locally from ``server/``: ``uvicorn app.main:app --reload``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response

from app import metrics
from app.api import v1
from app.api.problems import install_problem_handlers
from app.auth.ratelimit import ValkeyRateLimiter
from app.auth.tokens import build_access_tokens
from app.config import Settings, check_api_settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.logging_config import configure_logging
from app.mail import build_mail_sender
from app.realtime.hub import Hub
from app.valkey import ValkeyClient

logger = logging.getLogger("floorwars")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Shared resources live on ``app.state`` and are read by ``app.api.deps``."""
    settings = settings or get_settings()
    check_api_settings(settings)  # refuses to start with an unusable configuration
    configure_logging(settings.log_level)

    engine = (
        make_engine(settings.database_url.get_secret_value()) if settings.database_url else None
    )
    valkey = ValkeyClient(settings.valkey_url.get_secret_value()) if settings.valkey_url else None
    # The socket hub's own Valkey subscriber (one per process, plan 7.2.1).
    hub = Hub(settings.valkey_url.get_secret_value() if settings.valkey_url else None)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await hub.start()
        yield
        await hub.stop()
        if engine is not None:
            engine.dispose()
        if valkey is not None:
            valkey.close()

    app = FastAPI(title="FloorWars API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(engine) if engine is not None else None
    app.state.access_tokens = build_access_tokens(settings)
    app.state.mail_sender = build_mail_sender(settings)
    # None without FLOORWARS_VALKEY_URL: POST /v1/auth/otp then answers 503 (fails closed).
    app.state.valkey = valkey
    app.state.hub = hub
    app.state.rate_limiter = ValkeyRateLimiter(valkey) if valkey is not None else None
    install_problem_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        """Liveness probe for Docker, Caddy and uptime checks. No auth, no DB access."""
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def scrape() -> Response:
        """Prometheus scrape endpoint. Internal network only: Caddy answers 404 for /metrics."""
        return Response(metrics.render(app.state.sessionmaker), media_type=metrics.CONTENT_TYPE)

    app.add_middleware(metrics.MetricsMiddleware)

    app.include_router(v1.router)

    logger.info("app created", extra={"env": settings.env})
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """``app.main:app`` for uvicorn, built on first access (PEP 562).

    Lazy, so importing ``create_app`` (tests, tools) does not build an app from the process
    environment, which fails the startup checks unless the environment is complete.
    """
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        _app = create_app()
    return _app
