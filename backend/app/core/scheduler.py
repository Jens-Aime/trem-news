"""
EventScheduler — autonomous polling engine for Market Pulse Intelligence.

Responsibility
──────────────
  Periodically calls the Finnhub Economic Calendar API, deduplicates results
  against a TTL-bounded seen-event cache, preprocesses new events, runs them
  through the AIOrchestrator, and broadcasts the analysis to all connected
  WebSocket clients.

Architecture
────────────
  • Pure asyncio: a single asyncio.Task runs the poll loop — no extra libs.
  • Deduplication: cachetools.TTLCache keyed by event_id.
      - TTL = 24 h (re-processes an event only if it hasn't been seen for a day)
      - maxsize = 5 000 (LRU eviction beyond the cap)
      - Events are marked seen BEFORE async I/O to prevent concurrent reprocessing.
  • Error isolation: per-event failures are logged and counted but don't crash
    the loop or prevent other events from processing.
  • Lifecycle: start() → asyncio.Task → cancel() in stop() — clean shutdown.

Scheduler is disabled when either:
  • settings.finnhub_api_key is empty  (test environments)
  • settings.scheduler_enabled is False (explicit opt-out)
The lifespan in main.py enforces this guard.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from cachetools import TTLCache

from app.core.ai_orchestrator import AIOrchestrator, get_ai_orchestrator
from app.core.config import Settings, get_settings
from app.core.event_store import get_event_store
from app.core.websocket_manager import (
    ConnectionManager,
    WSMessage,
    WSMessageType,
    get_connection_manager,
)
from app.ingestion.finnhub_client import FinnhubClient
from app.ingestion.preprocessor import preprocess_event
from app.models import AnalysisResult

logger = logging.getLogger(__name__)


class EventScheduler:
    """
    Background polling engine that autonomously drives the full
    ingestion → analysis → broadcast pipeline.
    """

    def __init__(
        self,
        finnhub_client: FinnhubClient | None = None,
        orchestrator: AIOrchestrator | None = None,
        manager: ConnectionManager | None = None,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._finnhub = finnhub_client or FinnhubClient()
        self._orchestrator = orchestrator or get_ai_orchestrator()
        self._manager = manager or get_connection_manager()
        self._interval = cfg.scheduler_poll_interval

        self._seen: TTLCache = TTLCache(
            maxsize=cfg.scheduler_seen_max,
            ttl=cfg.scheduler_seen_ttl,
        )
        self._task: asyncio.Task | None = None
        self._running = False
        self._stats: dict[str, Any] = {
            "polls": 0,
            "new_events": 0,
            "skipped_duplicate": 0,
            "processed_ok": 0,
            "errors": 0,
            "last_poll_utc": None,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the background polling loop."""
        if self._running:
            logger.warning("EventScheduler already running — ignoring start()")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="market-pulse-scheduler")
        logger.info(
            "EventScheduler started (poll_interval=%ds)", self._interval
        )

    async def stop(self) -> None:
        """Cancel the polling loop and wait for it to finish."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("EventScheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    # ── Public API ────────────────────────────────────────────────────────────

    async def poll_now(self) -> list[AnalysisResult]:
        """
        Trigger one poll cycle immediately (outside the regular interval).
        Useful for admin endpoints and integration tests.
        """
        return await self._poll_once()

    @property
    def stats(self) -> dict[str, Any]:
        return {**self._stats, "is_running": self.is_running}

    def is_seen(self, event_id: str) -> bool:
        """Return True if this event_id has already been processed."""
        return event_id in self._seen

    def mark_seen(self, event_id: str) -> None:
        """Manually mark an event_id as seen (used in tests)."""
        self._seen[event_id] = True

    def clear_seen(self) -> None:
        """Flush the deduplication cache (used in tests)."""
        self._seen.clear()

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Main scheduling loop: poll → sleep → poll …"""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Scheduler poll error: %s", exc, exc_info=True)
                self._stats["errors"] += 1
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                raise

    async def _poll_once(self) -> list[AnalysisResult]:
        """
        One full poll cycle:
          1. Fetch calendar events from Finnhub
          2. Skip already-seen event_ids
          3. preprocess_event() for each new event
          4. AIOrchestrator.analyze()
          5. Broadcast to WebSocket clients
        """
        self._stats["polls"] += 1
        self._stats["last_poll_utc"] = datetime.now(timezone.utc).isoformat()

        # ── 1. Fetch ───────────────────────────────────────────────────────
        try:
            raw_events: list[dict] = await self._finnhub.fetch_economic_calendar()
        except Exception as exc:
            logger.warning("Finnhub fetch failed: %s", exc)
            self._stats["errors"] += 1
            return []

        if not raw_events:
            logger.debug("No events returned from Finnhub")
            return []

        # ── 2. Deduplicate ────────────────────────────────────────────────
        new_events = [
            e for e in raw_events if not self.is_seen(str(e.get("event_id", "")))
        ]
        skipped = len(raw_events) - len(new_events)
        self._stats["skipped_duplicate"] += skipped

        if not new_events:
            logger.debug("All %d events already seen", len(raw_events))
            return []

        logger.info(
            "Poll: %d total events — %d new, %d duplicate",
            len(raw_events), len(new_events), skipped,
        )
        self._stats["new_events"] += len(new_events)

        # ── 3-5. Preprocess → Analyse → Broadcast (per event) ────────────
        results: list[AnalysisResult] = []
        for raw in new_events:
            event_id = str(raw.get("event_id", ""))

            # Mark seen BEFORE async I/O — prevents double-processing on
            # concurrent polls or if the event appears again mid-loop.
            self.mark_seen(event_id)

            try:
                processed = preprocess_event(raw)
                result = await self._orchestrator.analyze(processed)
                get_event_store().append(result)

                if self._manager.connection_count() > 0:
                    msg = WSMessage(
                        type=WSMessageType.ANALYSIS_RESULT,
                        data=result.model_dump(mode="json"),
                    )
                    await self._manager.broadcast_message(msg)

                results.append(result)
                self._stats["processed_ok"] += 1
                logger.info(
                    "Processed event %s → %s / %s",
                    event_id, result.sentiment.value, result.risk_level.value,
                )

            except Exception as exc:
                logger.error("Failed processing event %s: %s", event_id, exc)
                self._stats["errors"] += 1

        return results
