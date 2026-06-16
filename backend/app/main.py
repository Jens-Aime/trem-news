from fastapi import FastAPI

from app.api.ingestion_router import router as ingestion_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Real-time decision support system for traders",
    version="0.1.0",
)

app.include_router(ingestion_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
