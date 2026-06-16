import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis_router import router as analysis_router
from app.api.history_router import router as history_router
from app.api.ingestion_router import router as ingestion_router
from app.api.scheduler_router import router as scheduler_router
from app.api.volatility_router import router as volatility_router
from app.api.ws_router import router as ws_router
from app.core.ai_orchestrator import get_ai_orchestrator
from app.core.config import get_settings
from app.core.scheduler import EventScheduler
from app.core.volatility_monitor import VolatilityMonitor
from app.core.websocket_manager import get_connection_manager
from app.db.base import engine, Base
from app.ingestion.finnhub_client import FinnhubClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # ── Database ──────────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # ── Event scheduler (Finnhub → AI → DB) ──────────────────────────────────
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
            "EventScheduler started — polling Finnhub every %ds",
            settings.scheduler_poll_interval,
        )
    else:
        logger.info(
            "EventScheduler not started "
            "(scheduler_enabled=%s, finnhub_api_key_set=%s)",
            settings.scheduler_enabled,
            bool(settings.finnhub_api_key),
        )

    # ── Volatility monitor (yfinance → spike detection → AI → DB) ────────────
    monitor = VolatilityMonitor(orchestrator=get_ai_orchestrator())
    app.state.volatility_monitor = monitor
    await monitor.start()

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    await monitor.stop()
    await scheduler.stop()
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time decision support system for traders",
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(scheduler_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(volatility_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
