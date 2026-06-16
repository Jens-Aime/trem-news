from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.analysis_result import RiskLevel, Sentiment


class HistoryEntry(BaseModel):
    # Economic event fields
    event_id: str
    event_name: str
    country: str
    currency: str
    event_timestamp: str
    impact_level: str
    actual: Optional[float]
    forecast: Optional[float]
    previous: Optional[float]
    unit: Optional[str]
    surprise_pct: Optional[float]
    # Analysis fields (superset of AnalysisResult)
    sentiment: Sentiment
    market_narrative: str
    potential_impact_sectors: list[str]
    risk_level: RiskLevel
    confidence_score: float
    key_levels: Optional[dict[str, float]]
    model_used: str
    cached: bool
    analyzed_at: str


class HistoryResponse(BaseModel):
    items: list[HistoryEntry]
    total: int
    page: int
    page_size: int
    pages: int
