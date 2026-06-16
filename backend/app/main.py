from fastapi import FastAPI

from app.api.analysis_router import router as analysis_router
from app.api.ingestion_router import router as ingestion_router
from app.api.ws_router import router as ws_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time decision support system for traders",
    version="0.3.0",
)

app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/ws")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
