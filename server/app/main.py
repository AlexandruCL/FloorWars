"""FastAPI application factory.

Run locally from ``server/``: ``uvicorn app.main:app --reload``.
"""

import logging

from fastapi import APIRouter, FastAPI
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.logging_config import configure_logging

logger = logging.getLogger("floorwars")

# Versioned API routes (plan section 6) are added to this router in later branches.
api_v1 = APIRouter(prefix="/v1")

# STUB (replace in Week 5): real Prometheus metrics (request rate, error rate, latency
# histograms, segments accepted vs rejected; plan section 7.8) via a client library.
METRICS_STUB = (
    "# HELP floorwars_up Whether the FloorWars API process is up (stub).\n"
    "# TYPE floorwars_up gauge\n"
    "floorwars_up 1\n"
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="FloorWars API", version="0.1.0")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        """Liveness probe for Docker, Caddy and uptime checks. No auth, no DB access."""
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
    def metrics() -> PlainTextResponse:
        """Prometheus scrape endpoint. Stub until Week 5."""
        return PlainTextResponse(METRICS_STUB, media_type="text/plain; version=0.0.4")

    app.include_router(api_v1)

    logger.info("app created", extra={"env": settings.env})
    return app


app = create_app()
