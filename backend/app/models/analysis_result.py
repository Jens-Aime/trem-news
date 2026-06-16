from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
from typing import Optional


class Sentiment(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnalysisResult(BaseModel):
    """Structured AI analysis of an economic event, ready for trader UI consumption."""

    event_id: str
    sentiment: Sentiment
    market_narrative: str = Field(
        ..., description="Concise, sober trading-desk summary (2-4 sentences)"
    )
    potential_impact_sectors: list[str] = Field(
        ..., description="Asset classes / sectors most exposed to this event"
    )
    risk_level: RiskLevel
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Model self-assessed confidence [0, 1]"
    )
    key_levels: Optional[dict[str, float]] = Field(
        None, description="Optional price / rate levels to watch (e.g. {'DXY': 104.5})"
    )
    scenario_matrix: Optional[list[dict]] = Field(
        None,
        description=(
            "Five-scenario outlook matrix for high-impact events. "
            "Ordered hawkish→dovish. Each entry: label, trigger, market_reaction, rationale."
        ),
    )

    # Metadata — populated by orchestrator, not by the LLM
    model_used: str = ""
    cached: bool = False
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
