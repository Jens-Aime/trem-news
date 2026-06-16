"""
Integration tests for Cluster 2: AI Analysis Module.

Strategy
────────
All external AI API calls are mocked at the provider-client level
so tests are fast, deterministic, and require no API keys.

Coverage
────────
  - Anthropic path: full pipeline ProcessedEvent → AnalysisResult
  - OpenAI path:    full pipeline with alternate mock
  - Caching:        second call returns cached result (no duplicate AI calls)
  - Stampede guard: concurrent calls for same key trigger only one AI request
  - JSON extraction: prose-wrapped, fenced, and clean JSON responses
  - Error paths:    invalid JSON, schema validation failures
  - Prompt content: system prompt and user prompt structure validation
  - High-impact NFP end-to-end simulation
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ai_orchestrator import AIAnalysisError, AIOrchestrator
from app.core.config import Settings
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ingestion.preprocessor import preprocess_event
from app.models import AnalysisResult, RiskLevel, Sentiment


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_settings(**overrides) -> Settings:
    base = dict(
        finnhub_api_key="test",
        anthropic_api_key="test-anthropic-key",
        openai_api_key="test-openai-key",
        ai_provider="anthropic",
        ai_cache_ttl_seconds=60,
        ai_cache_max_size=64,
    )
    return Settings(**{**base, **overrides})


def _nfp_processed_event():
    """High-impact NFP beat — the canonical test event from Cluster 1."""
    return preprocess_event({
        "event_id": "nfp-2026-06",
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
    })


_VALID_AI_JSON = {
    "sentiment": "bullish",
    "market_narrative": (
        "Non-Farm Payrolls printed 272K vs 180K expected, a 51% beat. "
        "Labour market strength reduces near-term rate cut probability. "
        "USD likely to firm across G10; watch DXY 104.5 resistance. "
        "US equity futures may rally on growth narrative."
    ),
    "potential_impact_sectors": [
        "USD_pairs", "US_equities", "US_treasuries", "gold", "EUR_pairs"
    ],
    "risk_level": "high",
    "confidence_score": 0.88,
    "key_levels": {"DXY": 104.5, "US10Y": 4.45},
}


def _make_anthropic_mock(response_json: dict | None = None) -> MagicMock:
    """Return a mock of anthropic.AsyncAnthropic that yields the given JSON."""
    payload = response_json or _VALID_AI_JSON
    # Anthropic prefill path: response text does NOT contain the leading "{"
    # because the orchestrator prepends it.
    response_text = json.dumps(payload)[1:]  # strip leading "{"

    content_block = MagicMock()
    content_block.text = response_text

    message = MagicMock()
    message.content = [content_block]

    client = MagicMock()
    client.messages.create = AsyncMock(return_value=message)

    anthropic_module = MagicMock()
    anthropic_module.AsyncAnthropic.return_value = client
    return anthropic_module


def _make_openai_mock(response_json: dict | None = None) -> MagicMock:
    payload = response_json or _VALID_AI_JSON

    choice = MagicMock()
    choice.message.content = json.dumps(payload)

    completion = MagicMock()
    completion.choices = [choice]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)

    openai_module = MagicMock()
    openai_module.AsyncOpenAI.return_value = client
    return openai_module


# ─────────────────────────────────────────────────────────────────────────────
# Prompt structure tests (no I/O)
# ─────────────────────────────────────────────────────────────────────────────

class TestPrompts:
    def test_system_prompt_contains_json_contract(self):
        assert "STRICT OUTPUT CONTRACT" in SYSTEM_PROMPT
        assert '"sentiment"' in SYSTEM_PROMPT
        assert '"market_narrative"' in SYSTEM_PROMPT
        assert '"potential_impact_sectors"' in SYSTEM_PROMPT
        assert '"risk_level"' in SYSTEM_PROMPT
        assert '"confidence_score"' in SYSTEM_PROMPT

    def test_system_prompt_enumerates_all_sentiment_values(self):
        for val in ("bullish", "bearish", "neutral", "mixed"):
            assert val in SYSTEM_PROMPT

    def test_system_prompt_enumerates_all_risk_levels(self):
        for val in ("low", "medium", "high", "critical"):
            assert val in SYSTEM_PROMPT

    def test_user_prompt_contains_event_data(self):
        event = _nfp_processed_event()
        prompt = build_user_prompt(event)
        assert "Non-Farm Payrolls" in prompt
        assert "272" in prompt        # actual
        assert "180" in prompt        # forecast
        assert "BEAT" in prompt       # surprise direction
        assert "51.1%" in prompt      # surprise_pct
        assert "HIGH" in prompt       # impact level
        assert "YES" in prompt        # is_high_impact flag

    def test_user_prompt_handles_missing_actual(self):
        event = preprocess_event({
            "event_id": "evt-001",
            "event_name": "GDP Growth",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            "impact_level": "medium",
            "actual": None,
            "forecast": 2.0,
            "previous": 1.8,
            "unit": "%",
        })
        prompt = build_user_prompt(event)
        assert "N/A (not yet released)" in prompt
        assert "N/A" in prompt  # surprise also N/A


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction tests
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonExtraction:
    def setup_method(self):
        self.orch = AIOrchestrator(_make_settings())

    def test_clean_json(self):
        raw = json.dumps(_VALID_AI_JSON)
        result = self.orch._extract_json(raw)
        assert result["sentiment"] == "bullish"

    def test_fenced_json(self):
        raw = f"```json\n{json.dumps(_VALID_AI_JSON)}\n```"
        result = self.orch._extract_json(raw)
        assert result is not None
        assert result["risk_level"] == "high"

    def test_prose_wrapped_json(self):
        raw = f"Here is my analysis:\n{json.dumps(_VALID_AI_JSON)}\nEnd of analysis."
        result = self.orch._extract_json(raw)
        assert result is not None

    def test_invalid_json_returns_none(self):
        assert self.orch._extract_json("this is not json at all") is None

    def test_partial_json_returns_none(self):
        assert self.orch._extract_json('{"sentiment": "bullish"') is None


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic provider tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_returns_analysis_result(self):
        settings = _make_settings(ai_provider="anthropic")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            result = await orch.analyze(event)

        assert isinstance(result, AnalysisResult)
        assert result.sentiment == Sentiment.BULLISH
        assert result.risk_level == RiskLevel.HIGH
        assert result.cached is False
        assert "claude" in result.model_used.lower()

    @pytest.mark.asyncio
    async def test_model_used_matches_config(self):
        settings = _make_settings(ai_provider="anthropic", anthropic_model="claude-test-model")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            result = await orch.analyze(event)

        assert result.model_used == "claude-test-model"

    @pytest.mark.asyncio
    async def test_all_required_fields_populated(self):
        settings = _make_settings(ai_provider="anthropic")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            result = await orch.analyze(event)

        assert result.event_id == "nfp-2026-06"
        assert len(result.potential_impact_sectors) >= 2
        assert 0.0 <= result.confidence_score <= 1.0
        assert result.market_narrative != ""
        assert isinstance(result.analyzed_at, datetime)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI provider tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_returns_analysis_result(self):
        settings = _make_settings(ai_provider="openai")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"openai": _make_openai_mock()}):
            result = await orch.analyze(event)

        assert isinstance(result, AnalysisResult)
        assert result.sentiment == Sentiment.BULLISH
        assert result.cached is False

    @pytest.mark.asyncio
    async def test_model_used_matches_config(self):
        settings = _make_settings(ai_provider="openai", openai_model="gpt-test")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"openai": _make_openai_mock()}):
            result = await orch.analyze(event)

        assert result.model_used == "gpt-test"


# ─────────────────────────────────────────────────────────────────────────────
# Caching tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCaching:
    @pytest.mark.asyncio
    async def test_second_call_returns_cached_result(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        mock_module = _make_anthropic_mock()
        with patch.dict("sys.modules", {"anthropic": mock_module}):
            first = await orch.analyze(event)
            second = await orch.analyze(event)

        # AI was called exactly once
        client = mock_module.AsyncAnthropic.return_value
        assert client.messages.create.call_count == 1

        assert first.cached is False
        assert second.cached is True

    @pytest.mark.asyncio
    async def test_different_actual_bypasses_cache(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)

        raw_base = {
            "event_id": "nfp-2026-06",
            "event_name": "Non-Farm Payrolls",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 6, 12, 30, 0, tzinfo=timezone.utc),
            "impact_level": "high",
            "actual": 272.0,
            "forecast": 180.0,
            "previous": 165.0,
            "unit": "K",
        }
        event_a = preprocess_event(raw_base)
        event_b = preprocess_event({**raw_base, "actual": 150.0})  # miss instead of beat

        mock_module = _make_anthropic_mock()
        with patch.dict("sys.modules", {"anthropic": mock_module}):
            await orch.analyze(event_a)
            await orch.analyze(event_b)

        client = mock_module.AsyncAnthropic.return_value
        assert client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_info_reflects_entries(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        assert orch.cache_info()["size"] == 0

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            await orch.analyze(event)

        assert orch.cache_info()["size"] == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            await orch.analyze(event)

        orch.clear_cache()
        assert orch.cache_info()["size"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_calls_trigger_single_ai_request(self):
        """Stampede guard: N concurrent calls for the same uncached event → 1 AI call."""
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        mock_module = _make_anthropic_mock()

        # Add a slight delay so coroutines truly overlap
        original_create = mock_module.AsyncAnthropic.return_value.messages.create

        async def slow_create(*args, **kwargs):
            await asyncio.sleep(0.05)
            return await original_create(*args, **kwargs)

        mock_module.AsyncAnthropic.return_value.messages.create = slow_create

        with patch.dict("sys.modules", {"anthropic": mock_module}):
            results = await asyncio.gather(*[orch.analyze(event) for _ in range(5)])

        # Only one result should be non-cached (the one that triggered the call)
        non_cached = [r for r in results if not r.cached]
        assert len(non_cached) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Error handling tests
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_invalid_json_raises_analysis_error(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        bad_mock = _make_anthropic_mock()
        bad_mock.AsyncAnthropic.return_value.messages.create = AsyncMock(
            return_value=MagicMock(content=[MagicMock(text="not json at all")])
        )

        with patch.dict("sys.modules", {"anthropic": bad_mock}):
            with pytest.raises(AIAnalysisError, match="Could not extract JSON"):
                await orch.analyze(event)

    @pytest.mark.asyncio
    async def test_invalid_schema_raises_analysis_error(self):
        settings = _make_settings()
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        # Valid JSON but missing required fields
        broken_payload = {"sentiment": "bullish"}
        bad_mock = _make_anthropic_mock(response_json=broken_payload)

        with patch.dict("sys.modules", {"anthropic": bad_mock}):
            with pytest.raises(AIAnalysisError, match="validation failed"):
                await orch.analyze(event)

    @pytest.mark.asyncio
    async def test_missing_anthropic_package_raises_error(self):
        settings = _make_settings(ai_provider="anthropic")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises((AIAnalysisError, ImportError)):
                await orch.analyze(event)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end high-impact simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestHighImpactSimulation:
    """
    Full pipeline: raw event dict → preprocess_event → AIOrchestrator → AnalysisResult.
    Simulates exactly what happens at runtime for a major NFP release.
    """

    @pytest.mark.asyncio
    async def test_nfp_full_pipeline(self, capsys):
        settings = _make_settings(ai_provider="anthropic")
        orch = AIOrchestrator(settings)
        event = _nfp_processed_event()

        with patch.dict("sys.modules", {"anthropic": _make_anthropic_mock()}):
            result = await orch.analyze(event)

        # ── Structural assertions ────────────────────────────────────────
        assert isinstance(result, AnalysisResult)
        assert result.event_id == "nfp-2026-06"
        assert result.sentiment in list(Sentiment)
        assert result.risk_level in list(RiskLevel)
        assert len(result.potential_impact_sectors) >= 2
        assert 0.0 <= result.confidence_score <= 1.0
        assert result.model_used != ""
        assert isinstance(result.analyzed_at, datetime)

        # ── High-impact event must be high or critical risk ──────────────
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL), (
            f"NFP 51% beat should be HIGH or CRITICAL, got {result.risk_level}"
        )

        # ── Print the AI payload for visual inspection ───────────────────
        import json as _json
        print("\n" + "=" * 65)
        print("  CLUSTER 2 — AI ANALYSIS RESULT")
        print("=" * 65)
        print(_json.dumps(result.model_dump(mode="json"), indent=2, default=str))
        print("=" * 65)

        captured = capsys.readouterr()
        assert "Non-Farm Payrolls" in captured.out or "nfp-2026-06" in captured.out

    @pytest.mark.asyncio
    async def test_fomc_full_pipeline(self):
        settings = _make_settings(ai_provider="openai")
        orch = AIOrchestrator(settings)

        fomc_event = preprocess_event({
            "event_id": "fomc-2026-06",
            "event_name": "FOMC Interest Rate Decision",
            "country": "US",
            "currency": "USD",
            "timestamp": datetime(2026, 6, 18, 18, 0, 0, tzinfo=timezone.utc),
            "impact_level": "high",
            "actual": 4.75,
            "forecast": 5.00,
            "previous": 5.00,
            "unit": "%",
        })

        fomc_ai_response = {
            "sentiment": "bearish",
            "market_narrative": (
                "FOMC delivered an unexpected 25bp cut to 4.75% against a 5.00% consensus. "
                "Dovish pivot signals growth concerns outweigh inflation stickiness. "
                "USD likely to weaken broadly; bonds rally on rate expectations repricing. "
                "Watch for Fed Chair guidance on pace of future cuts."
            ),
            "potential_impact_sectors": [
                "USD_pairs", "US_treasuries", "gold", "real_estate", "financials"
            ],
            "risk_level": "critical",
            "confidence_score": 0.91,
            "key_levels": {"DXY": 102.0, "US10Y": 4.1, "XAUUSD": 2400.0},
        }

        with patch.dict("sys.modules", {"openai": _make_openai_mock(fomc_ai_response)}):
            result = await orch.analyze(fomc_event)

        assert result.sentiment == Sentiment.BEARISH
        assert result.risk_level == RiskLevel.CRITICAL
        assert "USD_pairs" in result.potential_impact_sectors
        assert result.key_levels is not None
        assert "US10Y" in result.key_levels
