"""FastAPI application factory.

Run locally from ``server/``: ``uvicorn app.main:app --reload``.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.api import v1
from app.api.problems import install_problem_handlers
from app.auth.tokens import build_access_tokens
from app.config import Settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.logging_config import configure_logging

logger = logging.getLogger("floorwars")

# STUB (replace in Week 5): real Prometheus metrics (request rate, error rate, latency
# histograms, segments accepted vs rejected; plan section 7.8) via a client library.
METRICS_STUB = (
    "# HELP floorwars_up Whether the FloorWars API process is up (stub).\n"
    "# TYPE floorwars_up gauge\n"
    "floorwars_up 1\n"
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Shared resources live on ``app.state`` and are read by ``app.api.deps``."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    engine = (
        make_engine(settings.database_url.get_secret_value()) if settings.database_url else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="FloorWars API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessionmaker = make_sessionmaker(engine) if engine is not None else None
    app.state.access_tokens = build_access_tokens(settings)
    install_problem_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        """Liveness probe for Docker, Caddy and uptime checks. No auth, no DB access."""
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
    def metrics() -> PlainTextResponse:
        """Prometheus scrape endpoint. Stub until Week 5."""
        return PlainTextResponse(METRICS_STUB, media_type="text/plain; version=0.0.4")

    app.include_router(v1.router)

    logger.info("app created", extra={"env": settings.env})
    return app


app = create_app()
