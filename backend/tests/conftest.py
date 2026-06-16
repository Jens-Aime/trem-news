"""
Shared pytest fixtures for the Market Pulse Intelligence test suite.

WebSocket + Lifespan isolation
──────────────────────────────
FastAPI's app.dependency_overrides injects fresh instances of:
  • ConnectionManager  — prevents WS state leaking across tests
  • AIOrchestrator     — prevents real AI calls; returns MOCK_ANALYSIS

The lifespan (main.py) creates an EventScheduler but ONLY starts it when
FINNHUB_API_KEY is set.  In the test environment the key is always empty,
so the scheduler is dormant and does not interfere with any test.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

# Canonical override key — imported from the module that owns get_ai_orchestrator
from app.core.ai_orchestrator import get_ai_orchestrator
from app.core.websocket_manager import ConnectionManager, get_connection_manager
from app.main import app
from app.models import AnalysisResult, RiskLevel, Sentiment

# Backward-compatible alias so any existing test that imports _get_orchestrator
# from conftest still resolves to the right override key.
_get_orchestrator = get_ai_orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# Canonical mock AnalysisResult (reused across WS + analysis + scheduler tests)
# ─────────────────────────────────────────────────────────────────────────────

MOCK_ANALYSIS = AnalysisResult(
    event_id="nfp-2026-06",
    sentiment=Sentiment.BULLISH,
    market_narrative=(
        "Non-Farm Payrolls printed 272K vs 180K expected — a 51% beat. "
        "Labour market strength delays rate cut expectations. USD bullish."
    ),
    potential_impact_sectors=["USD_pairs", "US_equities", "US_treasuries", "gold"],
    risk_level=RiskLevel.HIGH,
    confidence_score=0.88,
    key_levels={"DXY": 104.5, "US10Y": 4.45},
    model_used="mock-model",
    cached=False,
    analyzed_at=datetime(2026, 6, 6, 12, 31, 0, tzinfo=timezone.utc),
)


def _make_mock_orchestrator(result: AnalysisResult = MOCK_ANALYSIS) -> MagicMock:
    """Return a mock AIOrchestrator whose analyze() always returns the given result."""
    orch = MagicMock()
    orch.analyze = AsyncMock(return_value=result)
    orch.cache_info = MagicMock(return_value={"size": 0, "maxsize": 512, "ttl_seconds": 3600})
    orch.clear_cache = MagicMock()
    return orch


# ─────────────────────────────────────────────────────────────────────────────
# Core fixture: isolated TestClient with fresh manager + mocked orchestrator
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ws_test_client():
    """
    Yield (TestClient, ConnectionManager, mock_orchestrator) with dependency
    overrides active.  Both the WS router and the analysis router share the
    same fresh ConnectionManager, which is required for the broadcast tests.
    """
    manager = ConnectionManager()
    mock_orch = _make_mock_orchestrator()

    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[get_ai_orchestrator] = lambda: mock_orch

    with TestClient(app) as client:
        yield client, manager, mock_orch

    app.dependency_overrides.clear()


@pytest.fixture
def ws_test_client_no_orch_override():
    """
    TestClient with only the manager overridden.
    Caller is responsible for mocking the orchestrator independently.
    """
    manager = ConnectionManager()
    app.dependency_overrides[get_connection_manager] = lambda: manager

    with TestClient(app) as client:
        yield client, manager

    app.dependency_overrides.clear()
