import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

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
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models import VolatilityAlertORM
from app.ingestion.finnhub_client import FinnhubClient

logger = logging.getLogger(__name__)

_HEALTH_INTERVAL = 3_600  # 1 hour


async def _health_check_loop(monitor: VolatilityMonitor) -> None:
    """Emit a health summary every hour so operators can verify the system is alive."""
    while True:
        try:
            await asyncio.sleep(_HEALTH_INTERVAL)
        except asyncio.CancelledError:
            return

        try:
            asset_count = len(monitor.assets)

            minutes_since = "no alerts recorded"
            try:
                async with AsyncSessionLocal() as session:
                    latest_ts = await session.scalar(
                        select(func.max(VolatilityAlertORM.detected_at))
                    )
                if latest_ts is not None:
                    latest_aware = latest_ts.replace(tzinfo=timezone.utc)
                    delta_min = int(
                        (datetime.now(timezone.utc) - latest_aware).total_seconds() / 60
                    )
                    minutes_since = f"{delta_min} min ago"
            except Exception as db_exc:
                minutes_since = f"db error: {db_exc}"

            logger.info(
                "SYSTEM HEALTHY — Monitored assets: %d — Last volatility alert: %s",
                asset_count,
                minutes_since,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Health-check error (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    # ── Database ──────────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migration: add scenario_matrix to existing DBs
        try:
            await conn.execute(
                text("ALTER TABLE analysis_results ADD COLUMN scenario_matrix TEXT")
            )
            logger.info("Migration: added scenario_matrix column")
        except Exception:
            pass  # column already exists
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

    # ── Hourly health-check ───────────────────────────────────────────────────
    health_task = asyncio.create_task(
        _health_check_loop(monitor), name="system-health-check"
    )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    await monitor.stop()
    await scheduler.stop()
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time decision support system for traders",
    version="0.7.0",
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
