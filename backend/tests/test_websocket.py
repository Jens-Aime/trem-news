"""
Integration & unit tests for Cluster 3: Real-Time Delivery Engine.

Test classes
────────────
  TestWSMessageModel         — Pydantic model: serialisation + defaults
  TestConnectionManagerUnit  — async unit tests with fake WebSockets
  TestWSEndpoint             — TestClient: connect/ack/status/disconnect
  TestBroadcastOnAnalysis    — Core integration: POST /analyse → WS broadcast
  TestMultiClientBroadcast   — Multiple clients all receive broadcast
  TestStaleConnectionPruning — Broken sockets removed automatically
  TestEndToEndPipeline       — NFP high-impact: ingestion → analysis → WS
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect
from starlette.testclient import TestClient

from app.api.analysis_router import _get_orchestrator
from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)
from app.ingestion.preprocessor import preprocess_event
from app.main import app
from app.models import AnalysisResult, ProcessedEvent, RiskLevel, Sentiment
from tests.conftest import MOCK_ANALYSIS, _make_mock_orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# Fake WebSocket helpers for unit tests
# ─────────────────────────────────────────────────────────────────────────────

class FakeWebSocket:
    """In-process WebSocket stand-in for ConnectionManager unit tests."""

    def __init__(self) -> None:
        self.accepted: bool = False
        self.sent: list[dict] = []
        self._broken: bool = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        if self._broken:
            raise WebSocketDisconnect(code=1001)
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        pass


class BrokenFakeWebSocket(FakeWebSocket):
    """Always raises on send — simulates a dropped connection."""

    async def send_json(self, data: dict) -> None:
        raise WebSocketDisconnect(code=1001)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: canonical processed NFP event
# ─────────────────────────────────────────────────────────────────────────────

def _nfp_event() -> ProcessedEvent:
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


# ─────────────────────────────────────────────────────────────────────────────
# WSMessage model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWSMessageModel:
    def test_timestamp_defaults_to_now(self):
        msg = WSMessage(type=WSMessageType.HEARTBEAT)
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.tzinfo is not None

    def test_serialises_to_json_cleanly(self):
        msg = WSMessage(
            type=WSMessageType.ANALYSIS_RESULT,
            data={"event_id": "nfp-2026-06", "risk_level": "high"},
            client_id="abc12345",
        )
        payload = msg.model_dump(mode="json")
        assert payload["type"] == "analysis_result"
        assert payload["data"]["risk_level"] == "high"
        assert isinstance(payload["timestamp"], str)

    def test_all_message_types_serialise(self):
        for msg_type in WSMessageType:
            msg = WSMessage(type=msg_type, message="test")
            raw = json.dumps(msg.model_dump(mode="json"))
            assert msg_type.value in raw

    def test_optional_fields_default_to_none(self):
        msg = WSMessage(type=WSMessageType.HEARTBEAT)
        assert msg.data is None
        assert msg.client_id is None
        assert msg.message is None


# ─────────────────────────────────────────────────────────────────────────────
# ConnectionManager unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConnectionManagerUnit:
    @pytest.mark.asyncio
    async def test_connect_accepts_and_returns_client_id(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        client_id = await manager.connect(ws)
        assert ws.accepted is True
        assert len(client_id) == 8
        assert manager.connection_count() == 1

    @pytest.mark.asyncio
    async def test_connect_assigns_unique_client_ids(self):
        manager = ConnectionManager()
        ids = set()
        for _ in range(10):
            ws = FakeWebSocket()
            cid = await manager.connect(ws)
            ids.add(cid)
        assert len(ids) == 10

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        cid = await manager.connect(ws)
        assert manager.connection_count() == 1
        await manager.disconnect(cid)
        assert manager.connection_count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_is_idempotent(self):
        manager = ConnectionManager()
        await manager.disconnect("nonexistent-id")  # must not raise
        assert manager.connection_count() == 0

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_clients(self):
        manager = ConnectionManager()
        ws_a, ws_b, ws_c = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()
        await manager.connect(ws_a)
        await manager.connect(ws_b)
        await manager.connect(ws_c)

        payload = {"type": "analysis_result", "data": {"risk_level": "high"}}
        stats = await manager.broadcast(payload)

        assert stats["sent"] == 3
        assert stats["failed"] == 0
        assert len(ws_a.sent) == 1
        assert ws_a.sent[0] == payload

    @pytest.mark.asyncio
    async def test_broadcast_with_no_clients(self):
        manager = ConnectionManager()
        stats = await manager.broadcast({"type": "heartbeat"})
        assert stats["sent"] == 0
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_prunes_broken_connections(self):
        manager = ConnectionManager()
        good = FakeWebSocket()
        broken = BrokenFakeWebSocket()
        cid_good = await manager.connect(good)
        cid_broken = await manager.connect(broken)

        stats = await manager.broadcast({"type": "test"})

        assert stats["sent"] == 1
        assert stats["failed"] == 1
        # Broken client was pruned
        assert cid_broken not in manager.client_ids()
        assert cid_good in manager.client_ids()

    @pytest.mark.asyncio
    async def test_send_to_specific_client(self):
        manager = ConnectionManager()
        ws_a, ws_b = FakeWebSocket(), FakeWebSocket()
        cid_a = await manager.connect(ws_a)
        await manager.connect(ws_b)

        ok = await manager.send_to(cid_a, {"msg": "direct"})
        assert ok is True
        assert len(ws_a.sent) == 1
        assert len(ws_b.sent) == 0

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_returns_false(self):
        manager = ConnectionManager()
        ok = await manager.send_to("ghost-id", {"msg": "hello"})
        assert ok is False

    @pytest.mark.asyncio
    async def test_send_to_broken_returns_false_and_prunes(self):
        manager = ConnectionManager()
        broken = BrokenFakeWebSocket()
        cid = await manager.connect(broken)

        ok = await manager.send_to(cid, {"msg": "test"})
        assert ok is False
        assert manager.connection_count() == 0

    @pytest.mark.asyncio
    async def test_broadcast_message_wsmodel(self):
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect(ws)

        msg = WSMessage(
            type=WSMessageType.ANALYSIS_RESULT,
            data={"event_id": "test-001"},
        )
        stats = await manager.broadcast_message(msg)
        assert stats["sent"] == 1
        assert ws.sent[0]["type"] == "analysis_result"

    @pytest.mark.asyncio
    async def test_client_ids_returns_all_active(self):
        manager = ConnectionManager()
        ids = set()
        for _ in range(3):
            ws = FakeWebSocket()
            cid = await manager.connect(ws)
            ids.add(cid)
        assert set(manager.client_ids()) == ids

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        manager = ConnectionManager()
        for _ in range(5):
            await manager.connect(FakeWebSocket())
        assert manager.connection_count() == 5
        await manager.disconnect_all()
        assert manager.connection_count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint tests (via TestClient)
# ─────────────────────────────────────────────────────────────────────────────

class TestWSEndpoint:
    def test_client_connects_and_receives_ack(self, ws_test_client):
        client, manager, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ack = ws.receive_json()
            assert ack["type"] == "connection_ack"
            assert "client_id" in ack
            assert ack["client_id"] is not None

    def test_ack_contains_server_message(self, ws_test_client):
        client, manager, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ack = ws.receive_json()
            assert "Market Pulse Intelligence" in ack["message"]

    def test_ack_timestamp_is_present(self, ws_test_client):
        client, manager, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ack = ws.receive_json()
            assert "timestamp" in ack
            assert ack["timestamp"] is not None

    def test_connection_increments_manager_count(self, ws_test_client):
        client, manager, _ = ws_test_client
        assert manager.connection_count() == 0
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()  # consume ack
            assert manager.connection_count() == 1
        # After context exit, the connection is closed
        # (TestClient triggers disconnect on __exit__)

    def test_ws_status_endpoint_returns_stats(self, ws_test_client):
        client, manager, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()
            status = client.get("/ws/status").json()
            assert status["active_connections"] == 1
            assert len(status["client_ids"]) == 1

    def test_ws_status_empty_when_no_clients(self, ws_test_client):
        client, manager, _ = ws_test_client
        status = client.get("/ws/status").json()
        assert status["active_connections"] == 0
        assert status["client_ids"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast-on-analysis integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBroadcastOnAnalysis:
    """
    Core integration: POST /api/v1/analysis/analyse must push an
    analysis_result frame to every connected WebSocket client.
    """

    def _processed_event_payload(self) -> dict:
        return _nfp_event().model_dump(mode="json")

    def test_analysis_broadcasts_to_connected_client(self, ws_test_client):
        client, manager, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()  # connection_ack

            resp = client.post(
                "/api/v1/analysis/analyse",
                json=self._processed_event_payload(),
            )
            assert resp.status_code == 200

            broadcast = ws.receive_json()
            assert broadcast["type"] == "analysis_result"
            assert broadcast["data"]["event_id"] == "nfp-2026-06"

    def test_broadcast_contains_correct_sentiment(self, ws_test_client):
        client, _, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()
            client.post("/api/v1/analysis/analyse", json=self._processed_event_payload())
            msg = ws.receive_json()
            assert msg["data"]["sentiment"] == Sentiment.BULLISH.value

    def test_broadcast_contains_risk_level(self, ws_test_client):
        client, _, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()
            client.post("/api/v1/analysis/analyse", json=self._processed_event_payload())
            msg = ws.receive_json()
            assert msg["data"]["risk_level"] == RiskLevel.HIGH.value

    def test_http_response_also_contains_result(self, ws_test_client):
        client, _, _ = ws_test_client
        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()
            resp = client.post(
                "/api/v1/analysis/analyse",
                json=self._processed_event_payload(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["event_id"] == "nfp-2026-06"
        assert body["sentiment"] == Sentiment.BULLISH.value

    def test_no_broadcast_when_no_clients_connected(self, ws_test_client):
        """Ensure analysis still succeeds even with zero WS clients."""
        client, manager, _ = ws_test_client
        assert manager.connection_count() == 0
        resp = client.post(
            "/api/v1/analysis/analyse",
            json=self._processed_event_payload(),
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Multiple-client broadcast tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiClientBroadcast:
    def test_two_clients_both_receive_broadcast(self, ws_test_client):
        client, _, _ = ws_test_client
        payload = _nfp_event().model_dump(mode="json")

        with client.websocket_connect("/ws/market-pulse") as ws1:
            with client.websocket_connect("/ws/market-pulse") as ws2:
                ws1.receive_json()  # ack
                ws2.receive_json()  # ack

                client.post("/api/v1/analysis/analyse", json=payload)

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()

        assert msg1["type"] == "analysis_result"
        assert msg2["type"] == "analysis_result"
        assert msg1["data"]["event_id"] == msg2["data"]["event_id"]

    def test_each_client_gets_unique_client_id(self, ws_test_client):
        client, _, _ = ws_test_client
        ids = []
        with client.websocket_connect("/ws/market-pulse") as ws1:
            with client.websocket_connect("/ws/market-pulse") as ws2:
                ids.append(ws1.receive_json()["client_id"])
                ids.append(ws2.receive_json()["client_id"])
        assert len(set(ids)) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Stale-connection pruning (end-to-end)
# ─────────────────────────────────────────────────────────────────────────────

class TestStaleConnectionPruning:
    @pytest.mark.asyncio
    async def test_broadcast_prunes_stale_on_send_failure(self):
        """Unit-level: stale FakeWebSocket is removed after failed broadcast."""
        manager = ConnectionManager()

        live = FakeWebSocket()
        stale = BrokenFakeWebSocket()
        cid_live = await manager.connect(live)
        cid_stale = await manager.connect(stale)

        assert manager.connection_count() == 2
        stats = await manager.broadcast({"type": "test"})

        assert stats["sent"] == 1
        assert stats["failed"] == 1
        assert manager.connection_count() == 1
        assert cid_stale not in manager.client_ids()
        assert cid_live in manager.client_ids()


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end pipeline simulation
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEndPipeline:
    """
    Simulates the complete real-time path:
    raw event → preprocess_event → POST /analyse → WS broadcast.
    Validates the full JSON payload received by the WS client.
    """

    def test_nfp_high_impact_full_pipeline(self, ws_test_client, capsys):
        client, _, mock_orch = ws_test_client

        # Preprocess the NFP event (as the ingestion scheduler would do)
        processed = _nfp_event()
        payload = processed.model_dump(mode="json")

        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()  # ack

            http_resp = client.post("/api/v1/analysis/analyse", json=payload)
            assert http_resp.status_code == 200

            ws_msg = ws.receive_json()

        # ── Validate WS message structure ────────────────────────────────
        assert ws_msg["type"] == "analysis_result"
        assert "timestamp" in ws_msg
        data = ws_msg["data"]

        assert data["event_id"] == "nfp-2026-06"
        assert data["sentiment"] in [s.value for s in Sentiment]
        assert data["risk_level"] in [r.value for r in RiskLevel]
        assert isinstance(data["potential_impact_sectors"], list)
        assert len(data["potential_impact_sectors"]) >= 1
        assert 0.0 <= data["confidence_score"] <= 1.0

        # ── Confirm AI was called once ───────────────────────────────────
        mock_orch.analyze.assert_awaited_once()

        # ── Print full WS payload for visual inspection ──────────────────
        print("\n" + "=" * 65)
        print("  CLUSTER 3 — WS Broadcast Payload (NFP High-Impact)")
        print("=" * 65)
        print(json.dumps(ws_msg, indent=2, default=str))
        print("=" * 65)

    def test_fomc_full_pipeline(self, ws_test_client):
        """FOMC bearish surprise → broadcast reaches WS client correctly."""
        client, _, mock_orch = ws_test_client

        fomc_analysis = AnalysisResult(
            event_id="fomc-2026-06",
            sentiment=Sentiment.BEARISH,
            market_narrative="FOMC surprise cut to 4.75%. USD bearish, bonds rally.",
            potential_impact_sectors=["USD_pairs", "US_treasuries", "gold"],
            risk_level=RiskLevel.CRITICAL,
            confidence_score=0.91,
            key_levels={"DXY": 102.0, "XAUUSD": 2400.0},
            model_used="mock-model",
        )
        mock_orch.analyze = AsyncMock(return_value=fomc_analysis)

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

        with client.websocket_connect("/ws/market-pulse") as ws:
            ws.receive_json()  # ack
            client.post("/api/v1/analysis/analyse", json=fomc_event.model_dump(mode="json"))
            msg = ws.receive_json()

        assert msg["data"]["sentiment"] == Sentiment.BEARISH.value
        assert msg["data"]["risk_level"] == RiskLevel.CRITICAL.value
        assert "XAUUSD" in msg["data"]["key_levels"]
