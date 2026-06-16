from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisResultORM, EconomicEventORM
from app.models import AnalysisResult, ProcessedEvent


async def save_analysis(
    session: AsyncSession,
    processed_event: ProcessedEvent,
    result: AnalysisResult,
) -> None:
    """Upsert the economic event and append an analysis result row."""
    e = processed_event.event

    orm_event = EconomicEventORM(
        event_id=e.event_id,
        event_name=e.event_name,
        country=e.country,
        currency=e.currency,
        event_timestamp=e.timestamp,
        impact_level=e.impact_level.value,
        actual=e.actual,
        forecast=e.forecast,
        previous=e.previous,
        unit=e.unit,
        surprise_pct=processed_event.surprise_pct,
        source=e.source,
    )
    await session.merge(orm_event)

    orm_result = AnalysisResultORM(
        event_id=result.event_id,
        sentiment=result.sentiment.value,
        market_narrative=result.market_narrative,
        potential_impact_sectors=list(result.potential_impact_sectors),
        risk_level=result.risk_level.value,
        confidence_score=result.confidence_score,
        key_levels=result.key_levels,
        model_used=result.model_used,
        cached=result.cached,
        analyzed_at=result.analyzed_at,
    )
    session.add(orm_result)


async def get_history(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Return paginated analysis history joined with event metadata (newest first)."""
    offset = (page - 1) * page_size

    total: int = await session.scalar(
        select(func.count(AnalysisResultORM.id))
    ) or 0

    rows = await session.execute(
        select(AnalysisResultORM, EconomicEventORM)
        .join(EconomicEventORM, AnalysisResultORM.event_id == EconomicEventORM.event_id)
        .order_by(AnalysisResultORM.analyzed_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    items = []
    for analysis, event in rows:
        items.append(
            {
                "event_id": analysis.event_id,
                "event_name": event.event_name,
                "country": event.country,
                "currency": event.currency,
                "event_timestamp": event.event_timestamp.isoformat(),
                "impact_level": event.impact_level,
                "actual": event.actual,
                "forecast": event.forecast,
                "previous": event.previous,
                "unit": event.unit,
                "surprise_pct": event.surprise_pct,
                "sentiment": analysis.sentiment,
                "market_narrative": analysis.market_narrative,
                "potential_impact_sectors": analysis.potential_impact_sectors or [],
                "risk_level": analysis.risk_level,
                "confidence_score": analysis.confidence_score,
                "key_levels": analysis.key_levels,
                "model_used": analysis.model_used,
                "cached": analysis.cached,
                "analyzed_at": analysis.analyzed_at.isoformat(),
            }
        )

    return items, total
