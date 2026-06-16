from pydantic import BaseModel


class VolatilityAlert(BaseModel):
    id: int
    asset: str
    ticker: str
    spike_type: str          # "BULLISH_SURGE" | "BEARISH_DROP"
    current_price: float
    z_score: float
    cause_found: bool
    explanation: str
    detected_at: str         # ISO-8601


class VolatilityAlertsResponse(BaseModel):
    items: list[VolatilityAlert]
    total: int
