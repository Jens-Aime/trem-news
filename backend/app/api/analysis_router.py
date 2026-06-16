from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.ai_orchestrator import AIAnalysisError, AIOrchestrator, get_ai_orchestrator
from app.core.event_store import get_event_store
from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)
from app.models import AnalysisResult, ProcessedEvent

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Canonical alias so existing test fixtures that import _get_orchestrator still work
_get_orchestrator = get_ai_orchestrator

OrchestratorDep = Annotated[AIOrchestrator, Depends(get_ai_orchestrator)]
ManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]


@router.post("/analyse", response_model=AnalysisResult)
async def analyse_event(
    processed_event: ProcessedEvent,
    orchestrator: OrchestratorDep,
    manager: ManagerDep,
) -> AnalysisResult:
    """
    Analyse a pre-processed economic event via the configured AI provider.

    After a successful analysis the result is automatically broadcast to all
    connected WebSocket clients so the trading UI updates in real-time.
    """
    try:
        result = await orchestrator.analyze(processed_event)
    except AIAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    get_event_store().append(result)

    # Push to all connected WS clients (fire-and-forget; never blocks the HTTP response)
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
