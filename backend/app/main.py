import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis_router import router as analysis_router
from app.api.ingestion_router import router as ingestion_router
from app.api.scheduler_router import router as scheduler_router
from app.api.ws_router import router as ws_router
from app.core.ai_orchestrator import get_ai_orchestrator
from app.core.config import get_settings
from app.core.event_store import get_event_store
from app.core.scheduler import EventScheduler
from app.core.websocket_manager import get_connection_manager
from app.ingestion.finnhub_client import FinnhubClient
from app.models import AnalysisResult

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan manager.

    Startup:  initialise the EventScheduler and start it if the Finnhub API
              key is present and scheduler_enabled is True.
    Shutdown: cleanly cancel the background polling task.
    """
    settings = get_settings()

    scheduler = EventScheduler(
        finnhub_client=FinnhubClient(),
        orchestrator=get_ai_orchestrator(),
        manager=get_connection_manager(),
        settings=settings,
    )
    app.state.scheduler = scheduler

    if settings.scheduler_enabled and settings.finnhub_api_key:
        await scheduler.start()
        logger.info(
            "Autonomous engine started — polling Finnhub every %ds",
            settings.scheduler_poll_interval,
        )
    else:
        logger.info(
            "Scheduler not started "
            "(scheduler_enabled=%s, finnhub_api_key_set=%s)",
            settings.scheduler_enabled,
            bool(settings.finnhub_api_key),
        )

    yield

    await scheduler.stop()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time decision support system for traders",
    version="0.4.0",
    lifespan=lifespan,
)

# Allow cross-origin fetch from the Next.js frontend (needed in Codespaces
# where the frontend and backend run on different subdomains).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(scheduler_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/v1/latest-events", response_model=list[AnalysisResult])
async def latest_events() -> list[AnalysisResult]:
    """Return the 5 most recent analysis results for HTTP polling clients."""
    return get_event_store().latest(5)
