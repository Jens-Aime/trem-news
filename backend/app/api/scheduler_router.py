"""
Scheduler control router — ops endpoints for the autonomous polling engine.

Endpoints
─────────
  GET  /api/v1/scheduler/status    Live stats (polls, processed, errors, etc.)
  POST /api/v1/scheduler/trigger   Immediately run one poll cycle
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.core.scheduler import EventScheduler
from app.models import AnalysisResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _get_scheduler(request: Request) -> EventScheduler:
    scheduler: EventScheduler | None = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not initialised")
    return scheduler


@router.get("/status")
async def scheduler_status(request: Request) -> dict[str, Any]:
    """Return live scheduler stats and running state."""
    return _get_scheduler(request).stats


@router.post("/trigger", response_model=list[AnalysisResult])
async def scheduler_trigger(request: Request) -> list[AnalysisResult]:
    """
    Trigger one poll cycle immediately.

    Returns the list of AnalysisResult objects produced for newly-seen events.
    Returns an empty list if no new events were found.
    """
    scheduler = _get_scheduler(request)
    try:
        return await scheduler.poll_now()
    except Exception as exc:
        logger.error("Manual trigger failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
