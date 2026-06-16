from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Optional
from datetime import datetime


class ImpactLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class EconomicEvent(BaseModel):
    """Normalized economic calendar event from any upstream provider."""

    event_id: str = Field(..., description="Unique identifier (provider-scoped)")
    event_name: str = Field(..., description="Human-readable event label")
    country: str = Field(..., description="ISO-3166 alpha-2 country code")
    currency: str = Field(..., description="Affected currency, e.g. 'USD'")
    timestamp: datetime = Field(..., description="Event release time (UTC)")
    impact_level: ImpactLevel = Field(
        ImpactLevel.UNKNOWN, description="Market impact classification"
    )
    actual: Optional[float] = Field(None, description="Released actual value")
    forecast: Optional[float] = Field(None, description="Analyst consensus estimate")
    previous: Optional[float] = Field(None, description="Prior period reading")
    unit: Optional[str] = Field(None, description="Value unit, e.g. '%', 'K', 'B'")
    source: str = Field("finnhub", description="Data provider identifier")

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper()

    @property
    def surprise(self) -> Optional[float]:
        """Deviation of actual from forecast (positive = beat, negative = miss)."""
        if self.actual is not None and self.forecast is not None:
            return round(self.actual - self.forecast, 4)
        return None

    @property
    def surprise_pct(self) -> Optional[float]:
        """Percentage surprise relative to absolute forecast value."""
        if self.surprise is not None and self.forecast and self.forecast != 0:
            return round((self.surprise / abs(self.forecast)) * 100, 2)
        return None


class ProcessedEvent(BaseModel):
    """
    Enriched event payload ready for AI inference.
    Bundles the normalised event with derived signals.
    """

    event: EconomicEvent
    impact_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Numeric impact score [0, 1] derived from impact_level + surprise",
    )
    surprise: Optional[float] = None
    surprise_pct: Optional[float] = None
    is_high_impact: bool = False
    narrative: str = Field("", description="Human-readable summary for LLM context")
    ai_payload: dict = Field(
        default_factory=dict, description="Flat dict forwarded to the AI pipeline"
    )
