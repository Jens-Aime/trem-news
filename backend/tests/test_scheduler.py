"""
Tests for Cluster 5: Autonomous Event Scheduler.

Test classes
────────────
  TestSchedulerDeduplication   — seen-cache: mark, check, clear, TTL structure
  TestPollOnce                 — _poll_once() unit tests with mocked dependencies
  TestProcessingPipeline       — new events flow end-to-end; duplicates are skipped
  TestSchedulerLifecycle       — start/stop/is_running asyncio.Task management
  TestStatsTracking            — counters increment correctly across poll cycles
  TestSchedulerRouter          — HTTP /scheduler/status + /scheduler/trigger
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app.core.ai_orchestrator import get_ai_orchestrator
from app.core.config import Settings
from app.core.scheduler import EventScheduler
from app.core.websocket_manager import ConnectionManager, get_connection_manager
from app.main import app
from app.models import AnalysisResult, RiskLevel, Sentiment
from tests.conftest import MOCK_ANALYSIS, _make_mock_orchestrator


# ─────────────────────────────────────────────────────────────────────────────
# Shared raw event fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _raw_event(event_id: str = "nfp-2026-06", **overrides) -> dict:
    base = {
        "event_id": event_id,
        "event_name": "Non-Farm Payrolls",
        "country": "US",
        "currency": "USD",
        "timestamp": datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        "impact_level": "high",
        "actual": 272.0,
        "forecast": 180.0,
        "previous": 165.0,
        "unit": "K",
        "source": "finnhub",
    }
    return {**base, **overrides}


def _make_finnhub_mock(events: list[dict]) -> MagicMock:
    client = MagicMock()
    client.fetch_economic_calendar = AsyncMock(return_value=events)
    return client


def _make_scheduler(
    events: list[dict] | None = None,
    orchestrator=None,
    manager: ConnectionManager | None = None,
    settings: Settings | None = None,
) -> tuple[EventScheduler, MagicMock, MagicMock, ConnectionManager]:
    """Helper: return (scheduler, finnhub_mock, orch_mock, manager) with shared defaults."""
    finnhub = _make_finnhub_mock(events if events is not None else [])
    orch = orchestrator or _make_mock_orchestrator()
    mgr = manager or ConnectionManager()
    cfg = settings or Settings(
        finnhub_api_key="test",
        anthropic_api_key="test",
        scheduler_poll_interval=1,
        scheduler_seen_ttl=3600,
        scheduler_seen_max=100,
    )
    scheduler = EventScheduler(
        finnhub_client=finnhub,
        orchestrator=orch,
        manager=mgr,
        settings=cfg,
    )
    return scheduler, finnhub, orch, mgr


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication cache tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerDeduplication:
    def test_new_event_is_not_seen(self):
        scheduler, *_ = _make_scheduler()
        assert scheduler.is_seen("evt-001") is False

    def test_mark_seen_marks_event(self):
        scheduler, *_ = _make_scheduler()
        scheduler.mark_seen("evt-001")
        assert scheduler.is_seen("evt-001") is True

    def test_mark_seen_is_idempotent(self):
        scheduler, *_ = _make_scheduler()
        scheduler.mark_seen("evt-001")
        scheduler.mark_seen("evt-001")
        assert scheduler.is_seen("evt-001") is True

    def test_clear_seen_removes_all(self):
        scheduler, *_ = _make_scheduler()
        scheduler.mark_seen("evt-001")
        scheduler.mark_seen("evt-002")
        scheduler.clear_seen()
        assert scheduler.is_seen("evt-001") is False
        assert scheduler.is_seen("evt-002") is False

    def test_different_events_tracked_independently(self):
        scheduler, *_ = _make_scheduler()
        scheduler.mark_seen("evt-A")
        assert scheduler.is_seen("evt-A") is True
        assert scheduler.is_seen("evt-B") is False

    def test_seen_cache_respects_maxsize(self):
        cfg = Settings(
            finnhub_api_key="test",
            scheduler_seen_max=3,
            scheduler_seen_ttl=3600,
        )
        scheduler = EventScheduler(settings=cfg)
        for i in range(5):
            scheduler.mark_seen(f"evt-{i:03d}")
        # TTLCache with maxsize=3 evicts LRU entries — total ≤ 3
        assert len(scheduler._seen) <= 3


# ─────────────────────────────────────────────────────────────────────────────
# poll_once unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPollOnce:
    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        scheduler, *_ = _make_scheduler(events=[])
        results = await scheduler.poll_now()
        assert results == []

    @pytest.mark.asyncio
    async def test_new_event_is_processed(self):
        scheduler, _, orch, _ = _make_scheduler(events=[_raw_event("nfp-01")])
        results = await scheduler.poll_now()
        assert len(results) == 1
        orch.analyze.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_result_type_is_analysis_result(self):
        scheduler, *_ = _make_scheduler(events=[_raw_event("nfp-01")])
        results = await scheduler.poll_now()
        assert isinstance(results[0], AnalysisResult)

    @pytest.mark.asyncio
    async def test_seen_event_is_skipped(self):
        scheduler, _, orch, _ = _make_scheduler(events=[_raw_event("nfp-01")])
        scheduler.mark_seen("nfp-01")
        results = await scheduler.poll_now()
        assert results == []
        orch.analyze.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_event_marked_seen_after_processing(self):
        scheduler, *_ = _make_scheduler(events=[_raw_event("nfp-01")])
        assert scheduler.is_seen("nfp-01") is False
        await scheduler.poll_now()
        assert scheduler.is_seen("nfp-01") is True

    @pytest.mark.asyncio
    async def test_finnhub_failure_returns_empty_list(self):
        scheduler, finnhub, _, _ = _make_scheduler()
        finnhub.fetch_economic_calendar = AsyncMock(
            side_effect=Exception("connection refused")
        )
        results = await scheduler.poll_now()
        assert results == []

    @pytest.mark.asyncio
    async def test_finnhub_failure_increments_error_counter(self):
        scheduler, finnhub, _, _ = _make_scheduler()
        finnhub.fetch_economic_calendar = AsyncMock(
            side_effect=Exception("timeout")
        )
        await scheduler.poll_now()
        assert scheduler.stats["errors"] >= 1

    @pytest.mark.asyncio
    async def test_orchestrator_failure_is_isolated_per_event(self):
        """If one event fails orchestration, others must still be processed."""
        events = [_raw_event("evt-A"), _raw_event("evt-B")]
        scheduler, _, orch, _ = _make_scheduler(events=events)
        call_count = 0

        async def flaky_analyze(processed_event):
            nonlocal call_count
            call_count += 1
            if processed_event.event.event_id == "evt-A":
                raise Exception("AI quota exceeded")
            return MOCK_ANALYSIS

        orch.analyze = flaky_analyze
        results = await scheduler.poll_now()

        assert len(results) == 1  # evt-B succeeded
        assert call_count == 2   # both were attempted
        assert scheduler.stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_failed_event_still_marked_seen(self):
        """A failed event must not be retried on the next poll cycle."""
        scheduler, _, orch, _ = _make_scheduler(events=[_raw_event("evt-A")])
        orch.analyze = AsyncMock(side_effect=Exception("boom"))
        await scheduler.poll_now()
        assert scheduler.is_seen("evt-A") is True


# ─────────────────────────────────────────────────────────────────────────────
# Processing pipeline tests (new vs. duplicate events)
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessingPipeline:
    @pytest.mark.asyncio
    async def test_second_poll_with_same_events_yields_no_results(self):
        """Core deduplication guarantee: same events → 0 AI calls on repeat poll."""
        events = [_raw_event("nfp-01"), _raw_event("cpi-01")]
        scheduler, _, orch, _ = _make_scheduler(events=events)

        first = await scheduler.poll_now()
        second = await scheduler.poll_now()

        assert len(first) == 2
        assert second == []
        assert orch.analyze.await_count == 2  # called only in first poll

    @pytest.mark.asyncio
    async def test_new_event_in_second_poll_is_processed(self):
        """Only the genuinely new event in poll 2 should be analysed."""
        scheduler, finnhub, orch, _ = _make_scheduler()

        # Poll 1: one event
        finnhub.fetch_economic_calendar = AsyncMock(
            return_value=[_raw_event("nfp-01")]
        )
        first = await scheduler.poll_now()

        # Poll 2: same event + one new
        finnhub.fetch_economic_calendar = AsyncMock(
            return_value=[_raw_event("nfp-01"), _raw_event("cpi-02")]
        )
        second = await scheduler.poll_now()

        assert len(first) == 1
        assert len(second) == 1
        assert orch.analyze.await_count == 2

    @pytest.mark.asyncio
    async def test_multiple_new_events_all_processed(self):
        events = [_raw_event(f"evt-{i:02d}") for i in range(5)]
        scheduler, _, orch, _ = _make_scheduler(events=events)
        results = await scheduler.poll_now()
        assert len(results) == 5
        assert orch.analyze.await_count == 5

    @pytest.mark.asyncio
    async def test_broadcast_sent_when_clients_connected(self):
        from tests.test_websocket import FakeWebSocket

        mgr = ConnectionManager()
        ws = FakeWebSocket()
        await mgr.connect(ws)

        scheduler, _, _, _ = _make_scheduler(
            events=[_raw_event("nfp-01")],
            manager=mgr,
        )
        await scheduler.poll_now()

        # ws received: the connection_ack (from manager.connect) + broadcast
        # Actually manager.connect just adds to pool; ack is sent by WS endpoint.
        # The broadcast from scheduler sends 1 message.
        broadcast_msgs = [m for m in ws.sent if m.get("type") == "analysis_result"]
        assert len(broadcast_msgs) == 1

    @pytest.mark.asyncio
    async def test_no_broadcast_when_no_clients(self):
        """Manager.broadcast is a no-op when connection_count == 0 — verify no error."""
        scheduler, _, _, mgr = _make_scheduler(events=[_raw_event("nfp-01")])
        assert mgr.connection_count() == 0
        results = await scheduler.poll_now()
        assert len(results) == 1  # processed ok, just not broadcast


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_not_running_before_start(self):
        scheduler, *_ = _make_scheduler()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_is_running_after_start(self):
        scheduler, *_ = _make_scheduler()
        await scheduler.start()
        assert scheduler.is_running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_not_running_after_stop(self):
        scheduler, *_ = _make_scheduler()
        await scheduler.start()
        await scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self):
        scheduler, *_ = _make_scheduler()
        await scheduler.stop()  # must not raise

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        scheduler, *_ = _make_scheduler()
        await scheduler.start()
        await scheduler.start()  # must not raise
        assert scheduler.is_running is True
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_task_cancelled_on_stop(self):
        scheduler, *_ = _make_scheduler()
        await scheduler.start()
        task = scheduler._task
        assert task is not None
        await scheduler.stop()
        assert task.done()

    @pytest.mark.asyncio
    async def test_poll_loop_executes_within_short_interval(self):
        """Verify the loop actually calls _poll_once within one interval."""
        scheduler, finnhub, _, _ = _make_scheduler()
        scheduler._interval = 0  # no sleep between polls

        await scheduler.start()
        await asyncio.sleep(0.05)  # allow at least one poll
        await scheduler.stop()

        assert finnhub.fetch_economic_calendar.await_count >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Stats tracking
# ─────────────────────────────────────────────────────────────────────────────

class TestStatsTracking:
    @pytest.mark.asyncio
    async def test_polls_counter_increments(self):
        scheduler, *_ = _make_scheduler(events=[])
        await scheduler.poll_now()
        await scheduler.poll_now()
        assert scheduler.stats["polls"] == 2

    @pytest.mark.asyncio
    async def test_new_events_counter_increments(self):
        scheduler, *_ = _make_scheduler(events=[_raw_event("evt-01")])
        await scheduler.poll_now()
        assert scheduler.stats["new_events"] == 1

    @pytest.mark.asyncio
    async def test_skipped_duplicate_counter_increments(self):
        scheduler, _, orch, _ = _make_scheduler(events=[_raw_event("nfp-01")])
        await scheduler.poll_now()   # processes nfp-01
        await scheduler.poll_now()   # skips nfp-01
        assert scheduler.stats["skipped_duplicate"] == 1

    @pytest.mark.asyncio
    async def test_processed_ok_counter_increments(self):
        events = [_raw_event(f"evt-{i:02d}") for i in range(3)]
        scheduler, *_ = _make_scheduler(events=events)
        await scheduler.poll_now()
        assert scheduler.stats["processed_ok"] == 3

    @pytest.mark.asyncio
    async def test_last_poll_utc_is_set(self):
        scheduler, *_ = _make_scheduler(events=[])
        assert scheduler.stats["last_poll_utc"] is None
        await scheduler.poll_now()
        assert scheduler.stats["last_poll_utc"] is not None

    @pytest.mark.asyncio
    async def test_stats_contain_is_running(self):
        scheduler, *_ = _make_scheduler()
        assert "is_running" in scheduler.stats
        await scheduler.start()
        assert scheduler.stats["is_running"] is True
        await scheduler.stop()
        assert scheduler.stats["is_running"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Scheduler HTTP router tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerRouter:
    """Integration tests hitting the HTTP endpoints via TestClient."""

    @pytest.fixture
    def scheduler_client(self):
        """
        TestClient with a fresh scheduler injected into app.state.
        Overrides AI + WS dependencies to keep the test isolated.
        """
        manager = ConnectionManager()
        mock_orch = _make_mock_orchestrator()
        app.dependency_overrides[get_connection_manager] = lambda: manager
        app.dependency_overrides[get_ai_orchestrator] = lambda: mock_orch

        with TestClient(app) as client:
            # Replace the scheduler created by lifespan with a controlled one
            scheduler, finnhub, _, _ = _make_scheduler(
                events=[_raw_event("nfp-01")],
                orchestrator=mock_orch,
                manager=manager,
            )
            client.app.state.scheduler = scheduler
            yield client, scheduler, finnhub, mock_orch

        app.dependency_overrides.clear()

    def test_status_endpoint_returns_200(self, scheduler_client):
        client, *_ = scheduler_client
        resp = client.get("/api/v1/scheduler/status")
        assert resp.status_code == 200

    def test_status_contains_expected_keys(self, scheduler_client):
        client, *_ = scheduler_client
        data = client.get("/api/v1/scheduler/status").json()
        required = {"polls", "new_events", "skipped_duplicate", "processed_ok",
                    "errors", "last_poll_utc", "is_running"}
        assert required.issubset(data.keys())

    def test_trigger_processes_new_event(self, scheduler_client):
        client, scheduler, *_ = scheduler_client
        resp = client.post("/api/v1/scheduler/trigger")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["event_id"] == "nfp-2026-06"  # from MOCK_ANALYSIS

    def test_trigger_returns_empty_on_duplicate(self, scheduler_client):
        client, scheduler, *_ = scheduler_client
        client.post("/api/v1/scheduler/trigger")  # first: processes nfp-01
        resp = client.post("/api/v1/scheduler/trigger")  # second: duplicate
        assert resp.status_code == 200
        assert resp.json() == []

    def test_trigger_increments_stats(self, scheduler_client):
        client, *_ = scheduler_client
        client.post("/api/v1/scheduler/trigger")
        stats = client.get("/api/v1/scheduler/status").json()
        assert stats["polls"] >= 1
        assert stats["processed_ok"] >= 1
