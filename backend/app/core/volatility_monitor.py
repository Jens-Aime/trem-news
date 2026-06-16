"""
VolatilityMonitor — background asyncio.Task that watches key USD-correlated
assets for abnormal price moves and fires AI-powered spike explanations.

Data sources
────────────
  Primary  : yfinance (Yahoo Finance) via a thread executor (sync library)
  Fallback : built-in Brownian-motion simulator — activates automatically
             after FAIL_THRESHOLD consecutive fetch failures per asset.
             Simulator injects controlled spikes so the full pipeline can be
             exercised in network-restricted environments (e.g. Codespaces).
             Simulated alerts are labelled "[SIM]" in logs and explanations.

Spike detection
───────────────
  Rolling price window (deque, maxlen=WINDOW_SIZE) per asset.
  Z-Score = (current_price - window_mean) / window_std.
  |z| ≥ SPIKE_THRESHOLD (2.0 σ) → spike declared.
  SPIKE_COOLDOWN (300 s) prevents alert storms on sustained moves.

Architecture
────────────
  On spike:
    1. AIOrchestrator.explain_volatility_spike()  — LLM context
    2. repository.save_volatility_alert()         — DB persistence
"""

import asyncio
import logging
import random
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.core.ai_orchestrator import AIOrchestrator, get_ai_orchestrator
from app.db import repository
from app.db.base import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Tunable constants ──────────────────────────────────────────────────────────

POLL_INTERVAL = 60        # seconds between price checks
WINDOW_SIZE = 15          # rolling window depth (one sample per poll)
MIN_SAMPLES = 5           # minimum samples before spike detection is active
SPIKE_THRESHOLD = 2.0     # |z-score| that declares a spike
SPIKE_COOLDOWN = 300      # seconds before re-alerting the same asset
FAIL_THRESHOLD = 3        # consecutive fetch failures before sim-mode activates

ASSETS: list[dict[str, str]] = [
    {"name": "EUR/USD",   "ticker": "EURUSD=X"},
    {"name": "S&P 500",   "ticker": "^GSPC"},
    {"name": "USD Index", "ticker": "DX-Y.NYB"},
]

# ── Simulation parameters (Brownian motion) ───────────────────────────────────

_SIM_BASE: dict[str, float] = {
    "EURUSD=X": 1.0850,
    "^GSPC":    5300.0,
    "DX-Y.NYB": 104.5,
}
# Typical 1-minute standard deviation per asset
_SIM_VOL: dict[str, float] = {
    "EURUSD=X": 0.0003,   # ~3 pips
    "^GSPC":    8.0,       # ~8 S&P points
    "DX-Y.NYB": 0.07,     # ~7 cents
}
# Stagger spike injection so not all assets fire at once
_SIM_SPIKE_OFFSET: dict[str, int] = {
    "EURUSD=X": 0,
    "^GSPC":    5,
    "DX-Y.NYB": 10,
}
SIM_SPIKE_PERIOD = 20     # inject a spike every N steps (after warmup)


# ── yfinance price fetch (sync — runs in executor) ────────────────────────────

def _fetch_price(ticker: str) -> float | None:
    """Return the latest market price via yfinance, or None on any error."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed")
        return None

    try:
        hist = yf.Ticker(ticker).history(period="60m", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception as exc:
        logger.debug("yfinance fetch error for %s: %s", ticker, exc)
        return None


# ── Monitor class ─────────────────────────────────────────────────────────────

class VolatilityMonitor:
    def __init__(self, orchestrator: AIOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or get_ai_orchestrator()

        # Rolling price windows
        self._windows: dict[str, deque[float]] = {
            a["ticker"]: deque(maxlen=WINDOW_SIZE) for a in ASSETS
        }
        # Cooldown: epoch timestamp of last spike per ticker
        self._last_spike: dict[str, float] = {}
        # Consecutive fetch failures per ticker
        self._failures: dict[str, int] = {a["ticker"]: 0 for a in ASSETS}
        # Simulation state
        self._sim_prices: dict[str, float] = {k: v for k, v in _SIM_BASE.items()}
        self._sim_steps: dict[str, int] = {k: 0 for k in _SIM_BASE}

        self._task: asyncio.Task[Any] | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._loop(), name="volatility-monitor"
        )
        logger.info(
            "VolatilityMonitor started (poll=%ds, threshold=%.1fσ, cooldown=%ds)",
            POLL_INTERVAL, SPIKE_THRESHOLD, SPIKE_COOLDOWN,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("VolatilityMonitor stopped")

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_all_assets()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("VolatilityMonitor loop error: %s", exc, exc_info=True)
            try:
                await asyncio.sleep(POLL_INTERVAL)
            except asyncio.CancelledError:
                raise

    async def _check_all_assets(self) -> None:
        loop = asyncio.get_event_loop()
        for asset in ASSETS:
            ticker = asset["ticker"]
            try:
                price = await loop.run_in_executor(None, _fetch_price, ticker)
                if price is None:
                    self._failures[ticker] += 1
                    if self._failures[ticker] >= FAIL_THRESHOLD:
                        price = self._next_sim_price(ticker)
                        logger.debug("[SIM] %s → %.5f", ticker, price)
                else:
                    self._failures[ticker] = 0

                if price is not None:
                    await self._process_price(asset, price)
            except Exception as exc:
                logger.warning("Asset check failed for %s: %s", ticker, exc)

    def _next_sim_price(self, ticker: str) -> float:
        """Advance the Brownian-motion simulator one step; inject spikes periodically."""
        current = self._sim_prices[ticker]
        base = _SIM_BASE[ticker]
        vol = _SIM_VOL[ticker]
        step = self._sim_steps[ticker]
        offset = _SIM_SPIKE_OFFSET.get(ticker, 0)
        self._sim_steps[ticker] = step + 1

        # Gentle mean-reversion towards base price
        reversion = 0.05 * (base - current)
        noise = random.gauss(0, vol)

        # Spike injection: first spike after (MIN_SAMPLES + 2 + offset) steps,
        # then every SIM_SPIKE_PERIOD steps
        effective_step = step - (MIN_SAMPLES + 2 + offset)
        if effective_step >= 0 and effective_step % SIM_SPIKE_PERIOD == 0:
            direction = random.choice([-1, 1])
            noise += direction * vol * 9   # ~9σ — well above SPIKE_THRESHOLD
            logger.info("[SIM] Spike injected for %s at step %d", ticker, step)

        new_price = current + reversion + noise
        self._sim_prices[ticker] = new_price
        return new_price

    async def _process_price(self, asset: dict[str, str], price: float) -> None:
        ticker = asset["ticker"]
        window = self._windows[ticker]
        window.append(price)

        n = len(window)
        if n < MIN_SAMPLES:
            logger.debug("%s warming up (%d/%d samples)", ticker, n, MIN_SAMPLES)
            return

        mean = sum(window) / n
        variance = sum((p - mean) ** 2 for p in window) / n
        std = variance ** 0.5

        if std < 1e-10:
            return  # flat price — no meaningful variance

        z_score = (price - mean) / std
        logger.debug(
            "%s price=%.5f mean=%.5f std=%.5f z=%.2f",
            ticker, price, mean, std, z_score,
        )

        if abs(z_score) < SPIKE_THRESHOLD:
            return

        # Cooldown guard
        now = datetime.now(timezone.utc).timestamp()
        if now - self._last_spike.get(ticker, 0) < SPIKE_COOLDOWN:
            logger.debug("%s spike suppressed (cooldown)", ticker)
            return

        self._last_spike[ticker] = now
        spike_type = "BULLISH_SURGE" if z_score > 0 else "BEARISH_DROP"
        simulated = self._failures.get(ticker, 0) >= FAIL_THRESHOLD

        logger.info(
            "SPIKE %s %s — z=%.2f price=%.5f%s",
            asset["name"], spike_type, z_score, price,
            " [SIMULATED]" if simulated else "",
        )
        await self._handle_spike(asset, price, z_score, spike_type, simulated)

    async def _handle_spike(
        self,
        asset: dict[str, str],
        price: float,
        z_score: float,
        spike_type: str,
        simulated: bool,
    ) -> None:
        # ── 1. Recent economic events for AI context ───────────────────────
        recent_events: list[dict] = []
        try:
            async with AsyncSessionLocal() as session:
                recent_events = await repository.get_recent_events(session, limit=5)
        except Exception as exc:
            logger.warning("Could not load recent events for context: %s", exc)

        # ── 2. AI explanation ──────────────────────────────────────────────
        explanation: dict = {
            "asset": asset["name"],
            "spike_type": spike_type,
            "cause_found": False,
            "explanation": "AI analysis pending.",
        }
        try:
            explanation = await self._orchestrator.explain_volatility_spike(
                asset_name=asset["name"],
                spike_type=spike_type,
                z_score=z_score,
                current_price=price,
                recent_events=recent_events,
            )
        except Exception as exc:
            logger.error("AI spike explanation failed: %s", exc)
            explanation["explanation"] = f"AI unavailable: {exc}"

        if simulated:
            explanation["explanation"] = (
                "[SIM] " + str(explanation.get("explanation", ""))
            )

        # ── 3. Persist ─────────────────────────────────────────────────────
        try:
            async with AsyncSessionLocal() as session:
                await repository.save_volatility_alert(
                    session,
                    asset_name=asset["name"],
                    ticker=asset["ticker"],
                    spike_type=spike_type,
                    current_price=price,
                    z_score=round(z_score, 4),
                    cause_found=bool(explanation.get("cause_found", False)),
                    explanation=str(explanation.get("explanation", "")),
                )
                await session.commit()
            logger.info("Volatility alert persisted for %s", asset["name"])
        except Exception as exc:
            logger.error("Failed to persist volatility alert: %s", exc)


# ── Singleton ─────────────────────────────────────────────────────────────────

_monitor: VolatilityMonitor | None = None


def get_volatility_monitor() -> VolatilityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = VolatilityMonitor()
    return _monitor
