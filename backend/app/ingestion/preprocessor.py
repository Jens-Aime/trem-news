"""
preprocess_event — transforms a normalized raw dict into a ProcessedEvent
that is ready to be forwarded to the AI analysis pipeline.

Impact score formula
────────────────────
  base_score   = {low: 0.2, medium: 0.5, high: 0.8, unknown: 0.1}
  surprise_adj = clamp(abs(surprise_pct) / 50, 0, 0.2)   (max +0.20)
  final_score  = clamp(base_score + surprise_adj, 0, 1)
"""

from datetime import datetime, timezone
from typing import Any

from app.models import EconomicEvent, ImpactLevel, ProcessedEvent

_BASE_SCORE: dict[ImpactLevel, float] = {
    ImpactLevel.LOW: 0.2,
    ImpactLevel.MEDIUM: 0.5,
    ImpactLevel.HIGH: 0.8,
    ImpactLevel.UNKNOWN: 0.1,
}

_HIGH_IMPACT_THRESHOLD = 0.65


def preprocess_event(data: dict[str, Any]) -> ProcessedEvent:
    """
    Validate, enrich and package a single economic event for AI consumption.

    Parameters
    ----------
    data : dict
        Normalised event dict as produced by FinnhubClient._normalize_raw.

    Returns
    -------
    ProcessedEvent
        Enriched event with impact_score, surprise metrics, narrative text,
        and a flat ai_payload dict ready for LLM context injection.
    """
    # ── 1. Validate + parse into domain model ──────────────────────────────
    if isinstance(data.get("timestamp"), str):
        data = _coerce_timestamp(data)

    event = EconomicEvent(**data)

    # ── 2. Compute derived signals ─────────────────────────────────────────
    surprise = event.surprise
    surprise_pct = event.surprise_pct
    base = _BASE_SCORE[event.impact_level]

    surprise_adj = 0.0
    if surprise_pct is not None:
        surprise_adj = min(abs(surprise_pct) / 50.0, 0.20)

    impact_score = round(min(base + surprise_adj, 1.0), 4)
    is_high_impact = impact_score >= _HIGH_IMPACT_THRESHOLD

    # ── 3. Build human-readable narrative ─────────────────────────────────
    narrative = _build_narrative(event, surprise, surprise_pct, is_high_impact)

    # ── 4. Flat AI payload ─────────────────────────────────────────────────
    ai_payload = _build_ai_payload(event, impact_score, surprise, surprise_pct)

    return ProcessedEvent(
        event=event,
        impact_score=impact_score,
        surprise=surprise,
        surprise_pct=surprise_pct,
        is_high_impact=is_high_impact,
        narrative=narrative,
        ai_payload=ai_payload,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _coerce_timestamp(data: dict) -> dict:
    """Attempt to parse various ISO-8601 / Unix timestamp strings."""
    raw_ts = data["timestamp"]
    parsed: datetime | None = None

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(raw_ts, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue

    if parsed is None:
        # Fallback: try Unix epoch as string
        try:
            parsed = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            parsed = datetime.now(tz=timezone.utc)

    return {**data, "timestamp": parsed}


def _build_narrative(
    event: EconomicEvent,
    surprise: float | None,
    surprise_pct: float | None,
    is_high_impact: bool,
) -> str:
    parts = [
        f"[{event.impact_level.value.upper()} IMPACT]",
        f"{event.event_name} ({event.currency})",
        f"released at {event.timestamp.strftime('%Y-%m-%d %H:%M UTC')}.",
    ]

    if event.actual is not None:
        unit = f" {event.unit}" if event.unit else ""
        parts.append(f"Actual: {event.actual}{unit}.")

    if event.forecast is not None:
        unit = f" {event.unit}" if event.unit else ""
        parts.append(f"Forecast: {event.forecast}{unit}.")

    if surprise is not None:
        direction = "beat" if surprise > 0 else "missed"
        parts.append(
            f"Result {direction} expectations by {abs(surprise):.4f}"
            + (f" ({surprise_pct:+.1f}%)" if surprise_pct is not None else "") + "."
        )

    if is_high_impact:
        parts.append("⚠ HIGH-IMPACT EVENT — immediate market reaction likely.")

    return " ".join(parts)


def _build_ai_payload(
    event: EconomicEvent,
    impact_score: float,
    surprise: float | None,
    surprise_pct: float | None,
) -> dict:
    return {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "country": event.country,
        "currency": event.currency,
        "timestamp_utc": event.timestamp.isoformat(),
        "impact_level": event.impact_level.value,
        "impact_score": impact_score,
        "actual": event.actual,
        "forecast": event.forecast,
        "previous": event.previous,
        "unit": event.unit,
        "surprise": surprise,
        "surprise_pct": surprise_pct,
        "source": event.source,
    }
