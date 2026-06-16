"""
Shared pytest fixtures for the Market Pulse Intelligence test suite.

WebSocket test isolation
────────────────────────
FastAPI's app.dependency_overrides is used to inject a fresh ConnectionManager
per test. Without this, the lru_cache singleton would leak connection state
across tests (e.g., a WS connected in test A appearing in test B's broadcast).

Usage in test files:
    def test_something(ws_test_client):
        client, manager = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ...
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from app.api.analysis_router import _get_orchestrator
from app.core.websocket_manager import ConnectionManager, get_connection_manager
from app.main import app
from app.models import AnalysisResult, RiskLevel, Sentiment


# ─────────────────────────────────────────────────────────────────────────────
# Canonical mock AnalysisResult (reused across WS + analysis tests)
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
    Yield (TestClient, ConnectionManager) with dependency overrides in effect.

    Both the WebSocket router and the analysis router will share the same fresh
    ConnectionManager — necessary for the broadcast integration tests.
    """
    manager = ConnectionManager()
    mock_orch = _make_mock_orchestrator()

    app.dependency_overrides[get_connection_manager] = lambda: manager
    app.dependency_overrides[_get_orchestrator] = lambda: mock_orch

    with TestClient(app) as client:
        yield client, manager, mock_orch

    app.dependency_overrides.clear()


@pytest.fixture
def ws_test_client_no_orch_override():
    """
    TestClient with only the manager overridden (orchestrator stays mocked at
    the class level by the caller). Used for tests that need a custom orchestrator.
    """
    manager = ConnectionManager()
    app.dependency_overrides[get_connection_manager] = lambda: manager

    with TestClient(app) as client:
        yield client, manager

    app.dependency_overrides.clear()
