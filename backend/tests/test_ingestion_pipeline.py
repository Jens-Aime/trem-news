"""
Tests for the Data Ingestion Engine — Cluster 1: Data Pipeline.

Covers:
  - Pydantic model validation
  - preprocess_event() logic (impact score, surprise, narrative)
  - High-impact event simulation with full AI payload output
  - Edge cases: missing values, zero forecast, unknown impact
"""

import json
from datetime import datetime, timezone

import pytest

from app.ingestion.preprocessor import preprocess_event
from app.models import EconomicEvent, ImpactLevel, ProcessedEvent


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_raw(**overrides) -> dict:
    """Return a minimal valid raw event dict, overridable per test."""
    base = {
        "event_id": "fh-001",
        "event_name": "Non-Farm Payrolls",
        "country": "US",
        "currency": "USD",
        "timestamp": datetime(2026, 6, 6, 12, 30, 0, tzinfo=timezone.utc),
        "impact_level": "high",
        "actual": 272.0,
        "forecast": 180.0,
        "previous": 165.0,
        "unit": "K",
        "source": "finnhub",
    }
    return {**base, **overrides}


# ─────────────────────────────────────────────────────────────────────────────
# Model validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEconomicEventModel:
    def test_basic_construction(self):
        event = EconomicEvent(**_make_raw())
        assert event.event_name == "Non-Farm Payrolls"
        assert event.country == "US"
        assert event.currency == "USD"
        assert event.impact_level == ImpactLevel.HIGH

    def test_country_currency_uppercased(self):
        event = EconomicEvent(**_make_raw(country="gb", currency="gbp"))
        assert event.country == "GB"
        assert event.currency == "GBP"

    def test_surprise_computed(self):
        event = EconomicEvent(**_make_raw(actual=272.0, forecast=180.0))
        assert event.surprise == pytest.approx(92.0)
        assert event.surprise_pct == pytest.approx(51.11, abs=0.01)

    def test_surprise_none_when_forecast_missing(self):
        event = EconomicEvent(**_make_raw(forecast=None))
        assert event.surprise is None
        assert event.surprise_pct is None

    def test_surprise_none_when_actual_missing(self):
        event = EconomicEvent(**_make_raw(actual=None))
        assert event.surprise is None


# ─────────────────────────────────────────────────────────────────────────────
# Preprocessor tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPreprocessEvent:
    def test_returns_processed_event_type(self):
        result = preprocess_event(_make_raw())
        assert isinstance(result, ProcessedEvent)

    def test_impact_score_high_with_large_surprise(self):
        # NFP: actual 272K vs forecast 180K → surprise_pct ≈ 51.1 % → adj ≈ 0.20
        # base=0.8, adj≈0.20 → clamped to 1.0
        result = preprocess_event(_make_raw(actual=272.0, forecast=180.0))
        assert result.impact_score == 1.0

    def test_impact_score_high_no_surprise(self):
        # base=0.8, adj=0 → 0.8
        result = preprocess_event(_make_raw(actual=None, forecast=None))
        assert result.impact_score == pytest.approx(0.8)

    def test_impact_score_medium_baseline(self):
        result = preprocess_event(_make_raw(impact_level="medium", actual=None, forecast=None))
        assert result.impact_score == pytest.approx(0.5)

    def test_is_high_impact_flag_set(self):
        result = preprocess_event(_make_raw())
        assert result.is_high_impact is True

    def test_is_high_impact_flag_not_set_for_low(self):
        result = preprocess_event(
            _make_raw(impact_level="low", actual=1.0, forecast=1.0)
        )
        assert result.is_high_impact is False

    def test_narrative_contains_key_fields(self):
        result = preprocess_event(_make_raw())
        assert "Non-Farm Payrolls" in result.narrative
        assert "HIGH IMPACT" in result.narrative
        assert "HIGH-IMPACT EVENT" in result.narrative

    def test_ai_payload_keys_present(self):
        required_keys = {
            "event_id", "event_name", "country", "currency",
            "timestamp_utc", "impact_level", "impact_score",
            "actual", "forecast", "previous", "unit",
            "surprise", "surprise_pct", "source",
        }
        result = preprocess_event(_make_raw())
        assert required_keys.issubset(result.ai_payload.keys())

    def test_string_timestamp_coercion(self):
        result = preprocess_event(_make_raw(timestamp="2026-06-06 12:30:00"))
        assert isinstance(result.event.timestamp, datetime)

    def test_zero_forecast_no_surprise_pct(self):
        # Division by zero guard — surprise_pct should be None
        result = preprocess_event(_make_raw(actual=1.0, forecast=0.0))
        assert result.surprise_pct is None

    def test_unknown_impact_baseline_score(self):
        result = preprocess_event(
            _make_raw(impact_level="unknown", actual=None, forecast=None)
        )
        assert result.impact_score == pytest.approx(0.1)


# ─────────────────────────────────────────────────────────────────────────────
# High-impact event simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestHighImpactEventSimulation:
    """
    Simulates a major NFP release that dramatically beats expectations.
    Verifies the full data structure that would be forwarded to the AI.
    """

    def test_nfp_high_impact_simulation(self, capsys):
        """Full end-to-end simulation of a high-impact NFP event."""
        raw = {
            "event_id": "nfp-2026-06",
            "event_name": "Non-Farm Payrolls",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 6, 12, 30, 0, tzinfo=timezone.utc),
            "impact_level": "high",
            "actual": 272.0,     # strong beat
            "forecast": 180.0,
            "previous": 165.0,
            "unit": "K",
            "source": "finnhub",
        }

        result = preprocess_event(raw)

        # ── Core assertions ──────────────────────────────────────────────
        assert result.is_high_impact, "NFP beat should be flagged as high-impact"
        assert result.impact_score >= 0.9, "Score should be near maximum"
        assert result.surprise == pytest.approx(92.0)
        assert result.surprise_pct == pytest.approx(51.11, abs=0.01)

        # ── AI payload structure ─────────────────────────────────────────
        payload = result.ai_payload
        assert payload["currency"] == "USD"
        assert payload["impact_level"] == "high"
        assert payload["actual"] == 272.0
        assert payload["surprise"] == pytest.approx(92.0)

        # ── Print AI payload to stdout ───────────────────────────────────
        print("\n" + "=" * 60)
        print("  HIGH-IMPACT EVENT — AI Pipeline Payload")
        print("=" * 60)
        print(json.dumps(payload, indent=2, default=str))
        print("-" * 60)
        print(f"  Narrative:\n  {result.narrative}")
        print("=" * 60)

        captured = capsys.readouterr()
        assert "Non-Farm Payrolls" in captured.out
        assert "HIGH-IMPACT EVENT" in captured.out

    def test_fomc_rate_decision_simulation(self):
        """Simulate a Fed rate decision surprise (miss scenario)."""
        raw = {
            "event_id": "fomc-2026-06",
            "event_name": "FOMC Interest Rate Decision",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 18, 18, 0, 0, tzinfo=timezone.utc),
            "impact_level": "high",
            "actual": 4.75,      # surprise cut — market expected hold
            "forecast": 5.00,
            "previous": 5.00,
            "unit": "%",
            "source": "finnhub",
        }

        result = preprocess_event(raw)

        assert result.is_high_impact
        assert result.surprise == pytest.approx(-0.25)
        assert result.surprise_pct == pytest.approx(-5.0)
        assert "missed" in result.narrative.lower()

    def test_cpi_medium_impact_does_not_trigger_high_flag(self):
        """Medium-impact CPI in-line with expectations stays below threshold."""
        raw = {
            "event_id": "cpi-2026-06",
            "event_name": "CPI (YoY)",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 12, 12, 30, 0, tzinfo=timezone.utc),
            "impact_level": "medium",
            "actual": 3.1,
            "forecast": 3.1,
            "previous": 3.2,
            "unit": "%",
            "source": "finnhub",
        }

        result = preprocess_event(raw)

        assert not result.is_high_impact
        assert result.surprise == pytest.approx(0.0)
        assert result.impact_score == pytest.approx(0.5)
