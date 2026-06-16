import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_orchestrator import AIAnalysisError, AIOrchestrator, get_ai_orchestrator
from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)
from app.db import repository
from app.db.base import get_db
from app.models import AnalysisResult, ProcessedEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Canonical alias so existing test fixtures that import _get_orchestrator still work
_get_orchestrator = get_ai_orchestrator

OrchestratorDep = Annotated[AIOrchestrator, Depends(get_ai_orchestrator)]
ManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/analyse", response_model=AnalysisResult)
async def analyse_event(
    processed_event: ProcessedEvent,
    orchestrator: OrchestratorDep,
    manager: ManagerDep,
    session: DbDep,
) -> AnalysisResult:
    """
    Analyse a pre-processed economic event via the configured AI provider.

    Persists the result to the database and broadcasts to all connected
    WebSocket clients so the trading UI updates in real-time.
    """
    try:
        result = await orchestrator.analyze(processed_event)
    except AIAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Persist to database (best-effort — never blocks the HTTP response)
    try:
        await repository.save_analysis(session, processed_event, result)
        await session.commit()
    except Exception as exc:
        logger.warning("DB persist failed for event %s: %s", result.event_id, exc)
        await session.rollback()

    # Broadcast to all connected WS clients (fire-and-forget)
    if manager.connection_count() > 0:
        msg = WSMessage(
            type=WSMessageType.ANALYSIS_RESULT,
            data=result.model_dump(mode="json"),
        )
        await manager.broadcast_message(msg)

    return result


@router.get("/cache/info")
async def cache_info(orchestrator: OrchestratorDep) -> dict:
    return orchestrator.cache_info()


@router.delete("/cache")
async def clear_cache(orchestrator: OrchestratorDep) -> dict:
    orchestrator.clear_cache()
    return {"status": "cleared"}
