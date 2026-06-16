from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.ai_orchestrator import AIAnalysisError, AIOrchestrator
from app.ingestion import preprocess_event
from app.models import AnalysisResult, ProcessedEvent

router = APIRouter(prefix="/analysis", tags=["analysis"])


@lru_cache
def _get_orchestrator() -> AIOrchestrator:
    return AIOrchestrator()


OrchestratorDep = Annotated[AIOrchestrator, Depends(_get_orchestrator)]


@router.post("/analyse", response_model=AnalysisResult)
async def analyse_event(
    processed_event: ProcessedEvent,
    orchestrator: OrchestratorDep,
) -> AnalysisResult:
    """Analyse a pre-processed economic event via the configured AI provider."""
    try:
        return await orchestrator.analyze(processed_event)
    except AIAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/cache/info")
async def cache_info(orchestrator: OrchestratorDep) -> dict:
    return orchestrator.cache_info()


@router.delete("/cache")
async def clear_cache(orchestrator: OrchestratorDep) -> dict:
    orchestrator.clear_cache()
    return {"status": "cleared"}
