from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import repository
from app.db.base import get_db
from app.models import VolatilityAlertsResponse

router = APIRouter(tags=["volatility"])


@router.get("/volatility-alerts", response_model=VolatilityAlertsResponse)
async def get_volatility_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> VolatilityAlertsResponse:
    """Return the most recent volatility spike alerts (newest first)."""
    items, total = await repository.get_volatility_alerts(session, limit=limit)
    return VolatilityAlertsResponse(items=items, total=total)
