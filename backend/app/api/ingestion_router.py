from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.ingestion import FinnhubClient, preprocess_event
from app.models import ProcessedEvent

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/economic-calendar", response_model=list[ProcessedEvent])
async def get_economic_calendar(
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Fetch, normalize and preprocess economic calendar events from Finnhub.
    Returns enriched ProcessedEvent objects ready for AI analysis.
    """
    client = FinnhubClient()
    try:
        raw_events = await client.fetch_economic_calendar(from_date, to_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc

    return [preprocess_event(e) for e in raw_events]
