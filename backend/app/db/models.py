from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class EconomicEventORM(Base):
    __tablename__ = "economic_events"

    event_id = Column(String, primary_key=True)
    event_name = Column(String, nullable=False)
    country = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    event_timestamp = Column(DateTime, nullable=False)
    impact_level = Column(String, nullable=False)
    actual = Column(Float, nullable=True)
    forecast = Column(Float, nullable=True)
    previous = Column(Float, nullable=True)
    unit = Column(String, nullable=True)
    surprise_pct = Column(Float, nullable=True)
    source = Column(String, default="finnhub")

    analyses = relationship(
        "AnalysisResultORM",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="select",
    )


class AnalysisResultORM(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey("economic_events.event_id"), nullable=False, index=True)
    sentiment = Column(String, nullable=False)
    market_narrative = Column(Text, nullable=False)
    potential_impact_sectors = Column(JSON, nullable=False)
    risk_level = Column(String, nullable=False)
    confidence_score = Column(Float, nullable=False)
    key_levels = Column(JSON, nullable=True)
    scenario_matrix = Column(JSON, nullable=True)
    model_used = Column(String, nullable=False)
    cached = Column(Boolean, default=False)
    analyzed_at = Column(DateTime, nullable=False)

    event = relationship("EconomicEventORM", back_populates="analyses", lazy="select")


class VolatilityAlertORM(Base):
    __tablename__ = "volatility_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset = Column(String, nullable=False)       # human label, e.g. "EUR/USD"
    ticker = Column(String, nullable=False)      # yfinance ticker, e.g. "EURUSD=X"
    spike_type = Column(String, nullable=False)  # "BULLISH_SURGE" | "BEARISH_DROP"
    current_price = Column(Float, nullable=False)
    z_score = Column(Float, nullable=False)
    cause_found = Column(Boolean, nullable=False, default=False)
    explanation = Column(Text, nullable=False)
    detected_at = Column(DateTime, nullable=False)
