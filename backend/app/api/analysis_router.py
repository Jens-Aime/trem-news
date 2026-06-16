from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.ai_orchestrator import AIAnalysisError, AIOrchestrator
from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)
from app.models import AnalysisResult, ProcessedEvent

router = APIRouter(prefix="/analysis", tags=["analysis"])


@lru_cache(maxsize=1)
def _get_orchestrator() -> AIOrchestrator:
    return AIOrchestrator()


OrchestratorDep = Annotated[AIOrchestrator, Depends(_get_orchestrator)]
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
