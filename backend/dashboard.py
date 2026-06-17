"""
Trem News — Financial Calendar Dashboard
=========================================================
Professional economic calendar with live volatility monitoring.

Start command:
    cd /path/to/trem-news/backend
    streamlit run dashboard.py --server.port 8501
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st

# Allow importing from the backend app package when running as a script
_BACKEND = Path(__file__).parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Trem News",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH      = Path(__file__).parent / "marketpulse.db"
ENV_PATH     = Path(__file__).parent / ".env"
FINNHUB_BASE = "https://finnhub.io/api/v1"

_IMPACT_MAP: dict[str, str] = {"1": "low", "2": "medium", "3": "high"}
_CCY_MAP: dict[str, str] = {
    "US": "USD", "GB": "GBP", "EU": "EUR", "DE": "EUR", "FR": "EUR",
    "JP": "JPY", "CA": "CAD", "AU": "AUD", "CH": "CHF", "CN": "CNY", "NZ": "NZD",
}

# ── CSS injection ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Volatility dot animations ── */
@keyframes pulse-green {
    0%   { box-shadow: 0 0 0 0 rgba(34,197,94,.8); }
    70%  { box-shadow: 0 0 0 9px rgba(34,197,94,0); }
    100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}
@keyframes pulse-amber {
    0%   { box-shadow: 0 0 0 0 rgba(245,158,11,.9); }
    70%  { box-shadow: 0 0 0 11px rgba(245,158,11,0); }
    100% { box-shadow: 0 0 0 0 rgba(245,158,11,0); }
}
@keyframes pulse-red {
    0%   { box-shadow: 0 0 0 0 rgba(239,68,68,1); }
    70%  { box-shadow: 0 0 0 14px rgba(239,68,68,0); }
    100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
}
.vdot {
    display: inline-block;
    width: 9px; height: 9px;
    border-radius: 50%;
    vertical-align: middle;
    flex-shrink: 0;
}
.vdot-normal   { background: #22c55e; animation: pulse-green 2.2s ease-in-out infinite; }
.vdot-elevated { background: #f59e0b; animation: pulse-amber 1.4s ease-in-out infinite; }
.vdot-critical { background: #ef4444; animation: pulse-red   .9s ease-in-out infinite; }

.vol-strip {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 8px 0 10px;
}
.vol-lbl {
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .1em;
    text-transform: uppercase;
}
.lbl-normal   { color: #22c55e; }
.lbl-elevated { color: #f59e0b; }
.lbl-critical { color: #ef4444; }

/* ── Section titles ── */
.section-title {
    font-size: .65rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: #475569;
    margin: 14px 0 5px;
}

/* ── Impact badges ── */
.ib-high   { color: #ef4444; font-size: .65rem; font-weight: 700; letter-spacing: .06em; }
.ib-medium { color: #f59e0b; font-size: .65rem; font-weight: 600; letter-spacing: .06em; }
.ib-low    { color: #4b5563; font-size: .65rem; font-weight: 500; letter-spacing: .06em; }

/* ── Calendar table ── */
.cal-hdr {
    display: grid;
    grid-template-columns: 70px 1fr 58px 72px 90px 90px 90px 94px;
    padding: 6px 10px;
    border-bottom: 1px solid #1e293b;
    font-size: .6rem;
    font-weight: 700;
    color: #334155;
    letter-spacing: .1em;
    text-transform: uppercase;
}
.cal-row {
    display: grid;
    grid-template-columns: 70px 1fr 58px 72px 90px 90px 90px 94px;
    padding: 10px 10px;
    border-bottom: 1px solid #0f172a;
    font-size: .78rem;
    align-items: center;
    transition: background .12s;
}
.cal-row:hover { background: rgba(255,255,255,.025); }
.cal-row-past  { opacity: .5; }

.c-time  { color: #475569; font-variant-numeric: tabular-nums; font-size: .73rem; }
.c-event { color: #cbd5e1; font-weight: 500; }
.c-ccy   { color: #475569; font-size: .7rem; font-weight: 700; letter-spacing: .05em; }
.c-act   { color: #22c55e; font-weight: 700; font-variant-numeric: tabular-nums; }
.c-fct   { color: #94a3b8; font-variant-numeric: tabular-nums; }
.c-prv   { color: #4b5563; font-variant-numeric: tabular-nums; }
.c-na    { color: #1e293b; }
.s-sched { color: #3b82f6; font-size: .6rem; font-weight: 700; letter-spacing: .08em; }
.s-rel   { color: #374151; font-size: .6rem; font-weight: 700; letter-spacing: .08em; }

/* ── Date group header ── */
.date-grp {
    padding: 12px 10px 4px;
    font-size: .6rem;
    font-weight: 700;
    color: #374151;
    letter-spacing: .14em;
    text-transform: uppercase;
    border-top: 1px solid #1e293b;
    margin-top: 6px;
}
.date-grp:first-of-type { border-top: none; margin-top: 0; }

/* ── Scenario matrix table ── */
.sc-tbl { width: 100%; border-collapse: collapse; }
.sc-tbl th {
    text-align: left; padding: 6px 8px;
    font-size: .58rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
    color: #334155; border-bottom: 1px solid #1e293b;
}
.sc-tbl td { padding: 8px 8px; vertical-align: top; line-height: 1.55; border-bottom: 1px solid #0f172a; }
.sc-tbl td:first-child { padding-left: 12px; }
.sc-cell-label { font-size: .7rem; font-weight: 700; }
.sc-cell-trigger  { font-size: .73rem; color: #94a3b8; }
.sc-cell-reaction { font-size: .73rem; color: #cbd5e1; font-weight: 500; }
.sc-cell-rationale { font-size: .71rem; color: #64748b; }
.sc-hdr-lbl { font-size: .58rem; font-weight: 700; letter-spacing: .12em;
              text-transform: uppercase; color: #334155;
              padding: 8px 0 5px; margin-bottom: 4px; }

/* ── Page header ── */
.pg-header {
    font-size: .8rem;
    font-weight: 700;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: #64748b;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 10px;
    margin-bottom: 14px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_ENV = _load_env()
FINNHUB_API_KEY: str = _ENV.get("FINNHUB_API_KEY", "")

_ASSETS_YAML = Path(__file__).parent / "assets.yaml"

_DEFAULT_WATCHED: list[dict] = [
    {"name": "EUR/USD",   "ticker": "EURUSD=X",  "class": "forex"},
    {"name": "S&P 500",   "ticker": "^GSPC",      "class": "index"},
    {"name": "USD Index", "ticker": "DX-Y.NYB",   "class": "index"},
    {"name": "Bitcoin",   "ticker": "BTC-USD",    "class": "crypto"},
    {"name": "Gold",      "ticker": "GC=F",       "class": "commodity"},
]


@st.cache_data(ttl=60)
def _load_watched_assets() -> list[dict]:
    """Read assets.yaml; return defaults if the file is absent or malformed."""
    try:
        import yaml
        with open(_ASSETS_YAML) as fh:
            data = yaml.safe_load(fh)
        assets = data.get("assets", [])
        return assets if assets else _DEFAULT_WATCHED
    except Exception:
        return _DEFAULT_WATCHED


def _tofloat(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_time(ts: str) -> str:
    try:
        return pd.Timestamp(ts).strftime("%H:%M")
    except Exception:
        return (ts[:5] if len(ts) >= 5 else ts) if ts else "—"


def _parse_date(ts: str) -> str:
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return (ts[:10] if len(ts) >= 10 else ts) if ts else "—"


def _fmt(v: float | None, unit: str | None = None) -> str:
    if v is None:
        return '<span class="c-na">—</span>'
    u = (unit or "").strip()
    if "%" in u or u.lower() in ("pct", "percent"):
        return f"{v:+.1f}%"
    av = abs(v)
    if av >= 1_000_000:
        return f"{v / 1_000_000:.3f}M"
    if av >= 1_000:
        return f"{v:,.1f}K"
    return f"{v:.2f}"


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "N/A"
    av = abs(v)
    if av >= 10_000:
        return f"{v:,.0f}"
    if av >= 1_000:
        return f"{v:,.2f}"
    if av >= 100:
        return f"{v:.4f}"
    if av >= 1:
        return f"{v:.5f}"
    return f"{v:.6f}"


def _impact_html(level: str) -> str:
    cls = {"high": "ib-high", "medium": "ib-medium"}.get(level, "ib-low")
    return f'<span class="{cls}">{level.upper()}</span>'


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_events(from_d: date, to_d: date) -> tuple[list[dict], str]:
    """
    Return (events, source_label).

    Priority:
      1. Finnhub API — live data with actual/forecast values (requires Premium key)
      2. Local SQLite DB — previously ingested events
      3. Built-in calendar generator — recurring schedule, always available
    """
    # ── 1. Finnhub (live) ──────────────────────────────────────────────────────
    if FINNHUB_API_KEY:
        try:
            r = httpx.get(
                f"{FINNHUB_BASE}/calendar/economic",
                params={"from": str(from_d), "to": str(to_d), "token": FINNHUB_API_KEY},
                timeout=10,
            )
            if r.status_code in (401, 403):
                pass  # free-tier restriction — fall through silently
            else:
                r.raise_for_status()
                raw: list[dict] = r.json().get("economicCalendar", [])
                if raw:
                    return _normalize_finnhub(raw), "LIVE — Finnhub API"
        except Exception:
            pass

    # ── 2. Local DB ────────────────────────────────────────────────────────────
    db_events = _events_from_db(str(from_d), str(to_d))
    if db_events:
        return db_events, "LOCAL DB"

    # ── 3. Built-in calendar generator ────────────────────────────────────────
    try:
        from app.ingestion.calendar_generator import generate_events
        return generate_events(from_d, to_d), "GENERATED SCHEDULE"
    except Exception:
        return [], "NO DATA"


def _normalize_finnhub(raw: list[dict]) -> list[dict]:
    out = []
    for idx, r in enumerate(raw):
        u = r.get("unit", "")
        ccy = u if (u and u.isalpha() and len(u) == 3) else _CCY_MAP.get(
            r.get("country", "").upper(), "USD"
        )
        out.append({
            "event_id":     r.get("id") or f"fh-{idx}",
            "event_name":   r.get("event", ""),
            "country":      r.get("country", ""),
            "currency":     ccy,
            "timestamp":    r.get("time", ""),
            "impact_level": _IMPACT_MAP.get(str(r.get("impact", "")), "low"),
            "actual":       _tofloat(r.get("actual")),
            "forecast":     _tofloat(r.get("estimate")),
            "previous":     _tofloat(r.get("prev")),
            "unit":         u,
        })
    return out


def _events_from_db(from_d: str, to_d: str) -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                """
                SELECT event_id, event_name, country, currency,
                       event_timestamp AS timestamp,
                       impact_level, actual, forecast, previous, unit
                FROM   economic_events
                WHERE  date(event_timestamp) BETWEEN ? AND ?
                ORDER  BY event_timestamp
                """,
                (from_d, to_d),
            ).fetchall()
        cols = [
            "event_id", "event_name", "country", "currency", "timestamp",
            "impact_level", "actual", "forecast", "previous", "unit",
        ]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


@st.cache_data(ttl=1800)
def load_asset_intelligence(ticker: str) -> dict:
    """Fetch yfinance market data and analyst info. Returns {error: ...} on failure."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}

        recs_df = None
        try:
            r = t.recommendations
            if r is not None and not r.empty:
                recs_df = r.head(8)
        except Exception:
            pass

        return {
            "name":         info.get("longName") or info.get("shortName", ticker),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "prev_close":   info.get("previousClose") or info.get("regularMarketPreviousClose"),
            "week52_high":  info.get("fiftyTwoWeekHigh"),
            "week52_low":   info.get("fiftyTwoWeekLow"),
            "target_mean":  info.get("targetMeanPrice"),
            "target_high":  info.get("targetHighPrice"),
            "target_low":   info.get("targetLowPrice"),
            "rec_key":      (info.get("recommendationKey") or "").upper().replace("_", " "),
            "rec_mean":     info.get("recommendationMean"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "sector":       info.get("sector") or "",
            "industry":     info.get("industry") or "",
            "recommendations": recs_df,
            "error":        None,
        }
    except Exception as exc:
        return {"error": str(exc)}


@st.cache_data(ttl=10)
def load_alerts() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql_query(
                """
                SELECT id, asset, ticker, spike_type, current_price,
                       z_score, cause_found, explanation, detected_at
                FROM   volatility_alerts
                ORDER  BY detected_at DESC
                LIMIT  20
                """,
                conn,
            )
    except Exception:
        return pd.DataFrame()


# ── Volatility classification ─────────────────────────────────────────────────

def _vol_status(df: pd.DataFrame) -> tuple[str, str]:
    """Return (css_level, display_label) from recent spike data."""
    if df.empty:
        return "normal", "NORMAL VOLATILITY"
    try:
        cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(hours=1)
        recent = df[pd.to_datetime(df["detected_at"]) > cutoff]
    except Exception:
        recent = df.head(3)
    if recent.empty:
        return "normal", "NORMAL VOLATILITY"
    max_z = float(recent["z_score"].abs().max())
    if max_z >= 4.0:
        return "critical", "CRITICAL SPIKE DETECTED"
    return "elevated", "ELEVATED VOLATILITY"


# ── Scenario matrix engine ────────────────────────────────────────────────────
# Five scenarios per event type, ordered hawkish → dovish.
# Fields: label | trigger | market_reaction | rationale
# Prohibited: buy / sell / long / short / enter / exit / recommend.

_SC_LABELS = [
    "Extreme Hawkish Surprise",
    "Hawkish / Slight Beat",
    "Consensus / In-Line",
    "Dovish / Slight Miss",
    "Extreme Dovish Surprise",
]

def _scenario_matrix(name: str, ccy: str) -> list[dict]:
    """Return a 5-scenario matrix for the given event + currency."""
    n = name.lower()

    # ── NFP / Payrolls ────────────────────────────────────────────────────────
    if any(k in n for k in ("nonfarm", "non-farm", "nfp", "payroll")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": f"Print ≥ +100K above forecast (e.g. +350K vs +250K consensus)",
             "market_reaction": f"{ccy} sharply higher across G10; US Treasury 2Y yield surges; equities retreat on rate concerns; gold under pressure",
             "rationale": "A large beat compresses unemployment toward NAIRU, eliminating the precondition for rate cuts. Yield differential widens via uncovered interest-rate parity; carry inflows amplify the currency move."},
            {"label": _SC_LABELS[1],
             "trigger": "+25K to +100K above forecast",
             "market_reaction": f"{ccy} modestly higher; 2Y–10Y spread compresses (flattening); equities mixed; rate-cut pricing pushed further out",
             "rationale": "Moderate labor outperformance sustains the 'higher-for-longer' Fed narrative. Taylor Rule residuals remain positive, reducing near-term rate-cut probability without triggering a major repricing."},
            {"label": _SC_LABELS[2],
             "trigger": "Print within ±25K of forecast",
             "market_reaction": "Limited immediate repricing; attention shifts to the wages sub-component and unemployment rate",
             "rationale": "An in-line print confirms the existing trajectory without forcing a policy reassessment. Markets are likely to fade any initial volatility and await the next CPI or FOMC signal."},
            {"label": _SC_LABELS[3],
             "trigger": "-25K to -100K below forecast",
             "market_reaction": f"{ccy} lower; rate-cut expectations advance; equities may strengthen on easing outlook; Treasuries rally",
             "rationale": "Below-trend employment shifts Fed reaction function via the dual mandate. Real yield differential narrows versus G10 peers; risk premium on duration falls, supporting longer-dated bonds."},
            {"label": _SC_LABELS[4],
             "trigger": "Print ≥ -100K below forecast or outright negative job losses",
             "market_reaction": f"{ccy} sharply lower; Treasury curve steepens; equities volatile (stagflation risk); gold and JPY as safe-haven flows",
             "rationale": "A contractionary print signals recessionary labor dynamics, forcing the Fed to abandon the restrictive stance. Competing inflation pressures may, however, cap the extent of any bond rally, creating cross-asset dislocation."},
        ]

    # ── CPI / Inflation ───────────────────────────────────────────────────────
    if any(k in n for k in ("cpi", "consumer price", "price index", "pce", "personal consumption", "inflation")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "MoM print ≥ +0.4pp above forecast (e.g. +0.6% vs +0.2% expected)",
             "market_reaction": f"{ccy} sharply higher; short-end yields spike; equities under pressure; inflation breakevens widen; gold mixed",
             "rationale": "A large inflation surprise forces a hawkish repricing of the entire rate path. Real yields rise as the market prices in delayed cuts or additional hikes; equity discount rates increase simultaneously."},
            {"label": _SC_LABELS[1],
             "trigger": "+0.1pp to +0.4pp above forecast",
             "market_reaction": f"{ccy} higher; 2Y yields rise; curve flattens; equities mixed; rate-cut pricing recedes by 1–2 meetings",
             "rationale": "A moderate beat extends the 'stickier inflation' narrative, keeping the central bank on hold longer. Market inflation expectations reset slightly higher, sustaining the yield differential advantage."},
            {"label": _SC_LABELS[2],
             "trigger": "Within ±0.1pp of forecast on both headline and core",
             "market_reaction": "Muted initial move; markets assess sub-components (services, shelter, energy ex-food)",
             "rationale": "An in-line print neither accelerates cuts nor triggers hike fears. Attention shifts immediately to the next data point in the rate-decision sequence (PCE, wages, or the FOMC meeting itself)."},
            {"label": _SC_LABELS[3],
             "trigger": "-0.1pp to -0.3pp below forecast",
             "market_reaction": f"{ccy} lower; rate-cut probability advances; Treasuries rally; equities benefit from lower discount-rate expectations",
             "rationale": "Disinflation progress reduces the cost of easing. The Fed's real rate rises mechanically as nominal inflation falls, creating room to cut without losing policy credibility."},
            {"label": _SC_LABELS[4],
             "trigger": "Print ≥ -0.3pp below forecast or outright deflation signal",
             "market_reaction": f"{ccy} sharply lower; front-end yields collapse; equities volatile (growth fears dominate); gold higher; deflation hedges outperform",
             "rationale": "Deflation risk triggers a fundamental regime shift — central banks lose the 'inflation as cover' argument. Fisher equation dynamics push real rates higher even as nominal rates are cut, risking a liquidity trap."},
        ]

    # ── Rate Decisions (FOMC / ECB / BOE / BOJ / RBA) ────────────────────────
    if any(k in n for k in ("rate decision", "interest rate", "fomc", "boe", "ecb", "rba", "rbnz", "boj", "boc")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "Unexpected rate hike, or hike of double the expected increment (e.g. +50bp vs +25bp priced)",
             "market_reaction": f"{ccy} surges; short-end yields spike sharply; yield curve flattens aggressively; equities under pressure; carry-funded currencies weaken",
             "rationale": "A hawkish surprise causes an immediate upward shift in the entire rate path. Carry traders rebalance toward the higher-yielding currency; equity duration premium rises as the risk-free rate jumps."},
            {"label": _SC_LABELS[1],
             "trigger": "Rate held with materially hawkish statement — fewer cuts signaled, dot plot shifted up, or explicit rate-hike bias added",
             "market_reaction": f"{ccy} higher; 2Y yield rises; curve flattens; equities mixed; commodity currencies affected via USD strength",
             "rationale": "Forward guidance is as powerful as the rate decision itself. A hawkish hold removes near-term cut probability from the OIS strip, sustaining the yield differential that supports the currency."},
            {"label": _SC_LABELS[2],
             "trigger": "Rate held with statement language unchanged — dot plot in line, neutral tone",
             "market_reaction": "Limited directional move; attention focused on press conference tone and Q&A",
             "rationale": "A fully-priced hold with no guidance change provides no new information. Markets look for any deviation in language as the primary signal; statement word-for-word comparison drives algos."},
            {"label": _SC_LABELS[3],
             "trigger": "Rate held with dovish tilt — more cuts signaled, lower terminal rate, downgraded economic projections",
             "market_reaction": f"{ccy} lower; front-end yields fall; curve steepens; equities potentially higher on easing expectations; gold supported",
             "rationale": "Forward guidance shifts market pricing on the OIS curve immediately. Lower expected rates reduce the currency's yield advantage and compress the carry premium; bonds rally as duration risk is repriced."},
            {"label": _SC_LABELS[4],
             "trigger": "Unexpected rate cut, or emergency inter-meeting cut",
             "market_reaction": f"{ccy} sharply lower; front-end yields collapse; yield curve steepens dramatically; equities volatile; safe havens (JPY, CHF, gold) strengthen",
             "rationale": "An emergency or unscheduled cut signals that the central bank sees a material deterioration in the economic outlook not previously communicated. The surprise triggers a broad risk-off repricing and calls into question the stability of the economic outlook."},
        ]

    # ── GDP ───────────────────────────────────────────────────────────────────
    if any(k in n for k in ("gdp", "gross domestic")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "Growth ≥ +1.0pp annualised above forecast (e.g. +3.5% vs +2.5% expected)",
             "market_reaction": f"{ccy} higher; equities advance; cyclicals and financials outperform defensives; rate-cut timeline pushed out",
             "rationale": "Strong growth reduces the probability of policy easing and supports the currency via higher expected rates. The wealth effect and stronger earnings outlook lift equities, particularly cyclical sectors sensitive to the growth cycle."},
            {"label": _SC_LABELS[1],
             "trigger": "+0.3pp to +1.0pp above forecast",
             "market_reaction": f"{ccy} modestly higher; growth-sensitive equities outperform; yield curve flattens slightly",
             "rationale": "A moderate growth beat extends the expansion without triggering inflation fears. The Taylor Rule leans hawkish at the margin; the yield differential advantage for the currency persists."},
            {"label": _SC_LABELS[2],
             "trigger": "Within ±0.3pp of forecast",
             "market_reaction": "Limited repricing; focus shifts to sub-components (consumption, investment, inventories) and the next quarter's outlook",
             "rationale": "An in-line GDP print confirms the existing consensus trajectory. Markets assess whether the composition of growth (consumption vs. investment) has any implications for future quarters."},
            {"label": _SC_LABELS[3],
             "trigger": "-0.3pp to -1.0pp below forecast",
             "market_reaction": f"{ccy} lower; defensive sectors outperform; rate-cut expectations advance; Treasuries rally; commodity currencies most exposed",
             "rationale": "A growth miss signals that the demand side of the economy is softening, reducing the central bank's ability to maintain restrictive rates. The output gap widens, exerting disinflationary pressure."},
            {"label": _SC_LABELS[4],
             "trigger": "Contraction or ≥ -1.0pp below forecast; recession risk confirmed",
             "market_reaction": f"{ccy} sharply lower; safe havens (JPY, CHF, Treasuries, gold) strengthen; equities retreat; credit spreads widen",
             "rationale": "A recessionary print forces an immediate reassessment of the rate path and corporate earnings outlook. Flight-to-quality flows dominate; the central bank faces pressure to cut aggressively, compressing the currency's yield advantage to zero or negative."},
        ]

    # ── PMI / ISM ─────────────────────────────────────────────────────────────
    if any(k in n for k in ("pmi", "purchasing managers", "ism manufacturing", "ism services", "ism non")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "Reading ≥ 55 and ≥ 2.5 points above forecast",
             "market_reaction": f"{ccy} higher; cyclical equities outperform; industrial commodities (copper, oil) strengthen; risk-on tone",
             "rationale": "A strong PMI beat signals robust expansion momentum, reducing the probability of a policy error (premature easing). The procyclical currency benefits via improved growth expectations; commodity-linked assets respond to demand signals."},
            {"label": _SC_LABELS[1],
             "trigger": "Reading above 50 and +1 to +2.5 points above forecast",
             "market_reaction": f"{ccy} modestly higher; equities mixed but cyclicals supported; risk appetite improves at the margin",
             "rationale": "A moderate expansion beat confirms recovery without triggering inflation concerns. The yield differential for the currency is marginally supported; sector rotation into cyclicals may occur."},
            {"label": _SC_LABELS[2],
             "trigger": "Reading within ±1 point of forecast, near the 50 expansion/contraction boundary",
             "market_reaction": "Limited immediate move; absolute level relative to 50 is the primary signal",
             "rationale": "An in-line PMI provides no new directional information. Traders monitor whether the absolute reading confirms expansion (>50) or contraction (<50), which carries more weight than the surprise component alone."},
            {"label": _SC_LABELS[3],
             "trigger": "Reading below forecast by 1–2.5 points, or dipping toward 50",
             "market_reaction": f"{ccy} lower; defensive sectors (utilities, healthcare) outperform; rate-cut expectations advance marginally",
             "rationale": "A miss signals that expansion momentum is fading. The growth-sensitive currency weakens as traders price in a softer economic trajectory and a more accommodative monetary policy response."},
            {"label": _SC_LABELS[4],
             "trigger": "Reading below 50 (contraction territory) and/or ≥ 2.5 points below forecast",
             "market_reaction": f"{ccy} sharply lower; equities retreat (especially industrials); safe havens strengthen; bond yields fall",
             "rationale": "A contractionary PMI reading signals that the manufacturing or services sector is shrinking. This strengthens the case for rate cuts, compressing the yield advantage of the domestic currency and triggering risk-off repositioning."},
        ]

    # ── Retail Sales ──────────────────────────────────────────────────────────
    if any(k in n for k in ("retail sales", "retail")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "MoM print ≥ +0.5pp above forecast (e.g. +1.2% vs +0.7% expected)",
             "market_reaction": f"{ccy} higher; consumer discretionary equities outperform; Treasuries weaken as rate-cut timeline extends",
             "rationale": "Strong consumer spending validates the 'soft landing' scenario, reducing pressure on the central bank to ease. Robust demand supports the inflation outlook, keeping rates elevated and the yield differential in the currency's favour."},
            {"label": _SC_LABELS[1],
             "trigger": "+0.1pp to +0.5pp above forecast",
             "market_reaction": f"{ccy} modestly higher; risk-on sentiment supported; discretionary outperforms staples",
             "rationale": "A moderate retail beat signals consumer resilience without signalling overheating. This narrows but does not eliminate the possibility of near-term rate cuts, providing a mild positive for the currency."},
            {"label": _SC_LABELS[2],
             "trigger": "Within ±0.1pp of forecast",
             "market_reaction": "Limited reaction; focus on core retail sales (ex-autos) and revision to prior month",
             "rationale": "Consensus print confirms spending trajectory. The more informative sub-components (control group, ex-autos/gas) and any prior-month revision are the key takeaways."},
            {"label": _SC_LABELS[3],
             "trigger": "-0.1pp to -0.5pp below forecast",
             "market_reaction": f"{ccy} lower; consumer discretionary equities lag; Treasuries rally on rate-cut expectations",
             "rationale": "Weaker consumer spending signals that demand-side pressures are abating, increasing the probability of central bank easing. The domestic currency weakens as the expected rate premium is reduced."},
            {"label": _SC_LABELS[4],
             "trigger": "Print ≥ -0.5pp below forecast or negative reading",
             "market_reaction": f"{ccy} sharply lower; defensives and Treasuries rally strongly; discretionary equities under pressure",
             "rationale": "A large miss in consumer spending raises recession risk. GDP models are revised lower; central bank rate-cut pricing accelerates. The currency loses its yield advantage as the policy rate path shifts materially downward."},
        ]

    # ── Unemployment / Jobless Claims ──────────────────────────────────────────
    if any(k in n for k in ("unemployment", "jobless", "initial claims", "claims")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "Claims below consensus by ≥ 20K, or unemployment rate 0.2pp below forecast",
             "market_reaction": f"{ccy} higher; rate-cut expectations pushed out; equities mixed; short-end yields rise",
             "rationale": "A tight labour market reduces the Fed's urgency to ease. Below-NAIRU unemployment maintains wage pressure, sustaining the inflation outlook and the 'higher for longer' rate narrative."},
            {"label": _SC_LABELS[1],
             "trigger": "Claims below consensus by 5K–20K, or unemployment 0.1pp lower than expected",
             "market_reaction": f"{ccy} modestly supported; curve flattens marginally; market OIS pricing adjusts slightly hawkish",
             "rationale": "A moderate labour market beat confirms resilience without triggering aggressive policy repricing. The employment pillar of the dual mandate remains satisfied, reducing political pressure on the central bank to ease."},
            {"label": _SC_LABELS[2],
             "trigger": "Within ±5K of forecast (initial claims) or ±0.1pp (unemployment rate)",
             "market_reaction": "Muted; focus shifts to wage data and the broader employment trend",
             "rationale": "In-line claims data confirms the existing trend without providing a new directional signal. The market awaits the NFP release for a more complete picture of labour market conditions."},
            {"label": _SC_LABELS[3],
             "trigger": "Claims above consensus by 5K–20K, or unemployment 0.1pp higher than expected",
             "market_reaction": f"{ccy} modestly weaker; rate-cut probability advances slightly; Treasuries marginally bid",
             "rationale": "A moderate softening in labour conditions shifts the dual mandate balance modestly toward the employment side. The market begins to price a marginally earlier easing cycle without a dramatic repricing."},
            {"label": _SC_LABELS[4],
             "trigger": "Claims ≥ 20K above consensus or unemployment rate 0.2pp+ above forecast",
             "market_reaction": f"{ccy} lower; rate-cut expectations accelerate significantly; equities volatile; Treasuries rally",
             "rationale": "A material weakening in employment is a leading recession indicator. The Taylor Rule shifts decisively toward easing; inflation concerns recede relative to growth concerns, reducing the yield premium for the domestic currency."},
        ]

    # ── PPI ───────────────────────────────────────────────────────────────────
    if any(k in n for k in ("ppi", "producer price", "producer")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "MoM PPI ≥ +0.5pp above forecast",
             "market_reaction": f"{ccy} higher as pipeline inflation signals; equities mixed; longer-dated bond yields rise",
             "rationale": "PPI is a leading indicator for CPI — upstream price pressure tends to flow through to consumer prices with a 2–3 month lag, adding to the case for sustained monetary tightening."},
            {"label": _SC_LABELS[1],
             "trigger": "+0.1pp to +0.5pp above forecast",
             "market_reaction": f"{ccy} modestly higher; inflation breakevens widen slightly; equities mixed",
             "rationale": "A moderate PPI beat reinforces the 'sticky inflation' narrative and keeps rate-cut expectations in check, providing a marginal positive for the currency's yield differential."},
            {"label": _SC_LABELS[2],
             "trigger": "Within ±0.1pp of forecast",
             "market_reaction": "Muted; headline CPI impact expected to be limited; attention on core components",
             "rationale": "An in-line PPI confirms disinflation or stable inflation dynamics at the producer level, consistent with the central bank's existing policy stance."},
            {"label": _SC_LABELS[3],
             "trigger": "-0.1pp to -0.4pp below forecast",
             "market_reaction": f"{ccy} lower; Treasuries bid; rate-cut timeline advances marginally",
             "rationale": "Below-expected producer prices signal easing pipeline inflation pressures, supporting the disinflation narrative and potentially bringing forward the rate-cut timeline."},
            {"label": _SC_LABELS[4],
             "trigger": "PPI ≥ -0.4pp below forecast or negative producer deflation",
             "market_reaction": f"{ccy} sharply lower; bonds rally strongly; deflation fears emerge; equities uncertain",
             "rationale": "Producer deflation signals a significant demand-side contraction or commodity-driven price collapse. Transmitted to consumer prices, this could accelerate the central bank's easing cycle and push the yield differential sharply negative."},
        ]

    # ── Trade Balance ─────────────────────────────────────────────────────────
    if any(k in n for k in ("trade balance", "current account", "trade deficit", "trade surplus")):
        return [
            {"label": _SC_LABELS[0],
             "trigger": "Surplus materially wider than expected, or deficit narrows by ≥ 10% vs forecast",
             "market_reaction": f"{ccy} higher; external demand for the currency increases; current account surplus reduces external financing risk",
             "rationale": "A better trade balance reduces the structural selling pressure on the currency from import payments. A surplus implies net foreign demand for domestic currency; improving external accounts reduce current account vulnerability."},
            {"label": _SC_LABELS[1],
             "trigger": "Slight improvement versus forecast",
             "market_reaction": f"{ccy} mildly supported; limited market impact absent structural implications",
             "rationale": "A marginal improvement in trade flows provides a small fundamental tailwind for the currency, though the FX impact is typically muted unless the change is large relative to GDP."},
            {"label": _SC_LABELS[2],
             "trigger": "In line with consensus",
             "market_reaction": "No immediate repricing; attention turns to sub-components (goods vs services, key trading partner flows)",
             "rationale": "Consensus trade data provides no new information about external demand conditions. The currency impact depends on whether the composition reveals shifts in key trading relationships."},
            {"label": _SC_LABELS[3],
             "trigger": "Slight deterioration versus forecast",
             "market_reaction": f"{ccy} mildly lower; external deficit concerns marginal",
             "rationale": "A slightly wider deficit increases the theoretical supply of the domestic currency to fund imports, but the FX impact is typically minimal unless it represents a structural trend deterioration."},
            {"label": _SC_LABELS[4],
             "trigger": "Deficit significantly wider than expected or structural deterioration confirmed",
             "market_reaction": f"{ccy} lower; current account vulnerability narrative intensifies; sovereign CDS spreads may widen",
             "rationale": "A large deficit implies persistent outflows to fund imports, creating structural downward pressure on the currency. External financing requirement rises, increasing vulnerability to shifts in capital flow sentiment."},
        ]

    # ── Generic fallback ──────────────────────────────────────────────────────
    return [
        {"label": _SC_LABELS[0],
         "trigger": "Print significantly above forecast — magnitude depends on event unit",
         "market_reaction": f"{ccy} higher; risk assets potentially supported; rate-cut expectations reduced",
         "rationale": "A strong beat typically strengthens the domestic macro outlook, sustaining the central bank's restrictive stance and maintaining the currency's yield advantage via interest rate parity."},
        {"label": _SC_LABELS[1],
         "trigger": "Print modestly above forecast",
         "market_reaction": f"{ccy} modestly higher; limited repricing of rate expectations",
         "rationale": "A moderate beat confirms positive trend without forcing a material policy reassessment. The marginal improvement in the macro outlook provides a mild positive for the currency."},
        {"label": _SC_LABELS[2],
         "trigger": "Print within a narrow band of the forecast",
         "market_reaction": "Muted reaction; markets await next data point",
         "rationale": "An in-line print provides no new directional signal. Attention shifts to the next high-impact release or central bank communication."},
        {"label": _SC_LABELS[3],
         "trigger": "Print modestly below forecast",
         "market_reaction": f"{ccy} modestly lower; marginal advance in rate-cut pricing",
         "rationale": "A moderate miss softens the domestic macro outlook marginally, reducing the currency's yield advantage and increasing the probability of an earlier easing cycle."},
        {"label": _SC_LABELS[4],
         "trigger": "Print significantly below forecast",
         "market_reaction": f"{ccy} lower; Treasuries/Bunds rally; safe-haven currencies (JPY, CHF) strengthen",
         "rationale": "A large miss raises growth or policy concerns, forcing a reassessment of the rate path. The currency loses its yield advantage as easing expectations bring forward the projected rate-cut cycle."},
    ]


# Colour coding for each scenario row (hawkish → dovish)
_SC_ROW_STYLES = [
    {"border": "#14532d", "text": "#4ade80",  "arrow": "▲▲"},  # extreme hawkish
    {"border": "#166534", "text": "#86efac",  "arrow": "▲"},   # hawkish beat
    {"border": "#374151", "text": "#94a3b8",  "arrow": "→"},   # consensus
    {"border": "#78350f", "text": "#fbbf24",  "arrow": "▼"},   # dovish miss
    {"border": "#7f1d1d", "text": "#f87171",  "arrow": "▼▼"},  # extreme dovish
]


def _render_scenario_matrix(matrix: list[dict]) -> None:
    """Render the 5-scenario matrix as a styled HTML table."""
    hdr = (
        '<table class="sc-tbl">'
        "<thead><tr>"
        '<th style="width:16%;">Scenario</th>'
        '<th style="width:20%;">Trigger Condition</th>'
        '<th style="width:24%;">Market Reaction</th>'
        '<th>Expert Rationale</th>'
        "</tr></thead><tbody>"
    )
    rows = ""
    for i, sc in enumerate(matrix[:5]):
        sty = _SC_ROW_STYLES[i]   # 'sty' — never shadows the streamlit 'st' module
        rows += (
            f'<tr style="border-left:3px solid {sty["border"]};">'
            f'<td class="sc-cell-label" style="color:{sty["text"]};">'
            f'{sty["arrow"]}&nbsp;{sc.get("label","")}</td>'
            f'<td class="sc-cell-trigger">{sc.get("trigger","")}</td>'
            f'<td class="sc-cell-reaction">{sc.get("market_reaction", sc.get("reaction",""))}</td>'
            f'<td class="sc-cell-rationale">{sc.get("rationale","")}</td>'
            f"</tr>"
        )
    st_html(hdr + rows + "</tbody></table>")


def _render_event_terminal(ev: dict) -> None:
    """Institutional-style scenario terminal for a single calendar event."""
    if st.button("← Back to Calendar", key="terminal_back"):
        st.session_state.event_page = None
        st.rerun()

    ev_name   = ev.get("event_name", "")
    ev_ccy    = ev.get("currency", "USD")
    ev_impact = ev.get("impact_level", "low")
    ev_time   = _parse_time(str(ev.get("timestamp", "")))
    ev_date   = _parse_date(str(ev.get("timestamp", "")))
    ev_actual = ev.get("actual")
    ev_fcast  = ev.get("forecast")
    ev_prev   = ev.get("previous")
    ev_unit   = ev.get("unit") or ""

    _impact_color = {"high": "#ef4444", "medium": "#f59e0b"}.get(ev_impact, "#4b5563")
    _status   = "RELEASED" if ev_actual is not None else "SCHEDULED"
    _status_c = "#334155" if ev_actual is not None else "#3b82f6"

    st.markdown(
        f'<div style="background:#111827;border:1px solid #1e293b;border-left:4px solid {_impact_color};'
        f'border-radius:6px;padding:16px 20px;margin:8px 0 16px;">'
        f'<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:10px;">'
        f'<div>'
        f'<div style="font-size:.55rem;color:#334155;letter-spacing:.14em;text-transform:uppercase;margin-bottom:5px;">'
        f'SCENARIO TERMINAL &nbsp;&middot;&nbsp; {ev_date}</div>'
        f'<div style="font-size:1.25rem;font-weight:700;color:#f1f5f9;letter-spacing:.01em;">{ev_name}</div>'
        f'</div>'
        f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding-top:2px;">'
        f'<span style="font-size:.72rem;font-weight:700;color:{_impact_color};letter-spacing:.08em;">'
        f'&#9632; {ev_impact.upper()} IMPACT</span>'
        f'<span style="font-size:.72rem;color:#475569;font-family:monospace;font-weight:700;">{ev_ccy}</span>'
        f'<span style="font-size:.7rem;color:#334155;font-family:monospace;">{ev_time} UTC</span>'
        f'<span style="font-size:.68rem;font-weight:700;color:{_status_c};letter-spacing:.06em;">{_status}</span>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    _dc1, _dc2, _dc3 = st.columns(3)
    with _dc1:
        _act_v = f"{ev_actual:g}" if ev_actual is not None else "Pending"
        st.metric("Actual", _act_v)
    with _dc2:
        _fct_v = f"{ev_fcast:g}" if ev_fcast is not None else "—"
        st.metric("Forecast", _fct_v)
    with _dc3:
        _prv_v = f"{ev_prev:g}" if ev_prev is not None else "—"
        st.metric("Previous", _prv_v)

    st.markdown(
        '<div style="margin:18px 0 6px;font-size:.58rem;font-weight:700;letter-spacing:.14em;'
        'text-transform:uppercase;color:#334155;border-bottom:1px solid #1e293b;padding-bottom:6px;">'
        'SCENARIO ANALYSIS</div>',
        unsafe_allow_html=True,
    )

    _matrix = _scenario_matrix(ev_name, ev_ccy)
    _sc_tabs = st.tabs([
        "▲▲ Extreme Hawkish",
        "▲ Hawkish",
        "→ Consensus",
        "▼ Dovish",
        "▼▼ Extreme Dovish",
        "≡ Full Table",
    ])

    for _i, (_sc_tab, _sc) in enumerate(zip(_sc_tabs[:5], _matrix[:5])):
        with _sc_tab:
            _sty = _SC_ROW_STYLES[_i]
            st.markdown(
                f'<div style="background:#0d1117;border:1px solid #1e293b;'
                f'border-left:4px solid {_sty["border"]};border-radius:6px;'
                f'padding:22px 26px;margin-top:10px;">'
                f'<div style="font-size:.62rem;font-weight:700;letter-spacing:.1em;'
                f'text-transform:uppercase;color:{_sty["text"]};margin-bottom:16px;">'
                f'{_sty["arrow"]} {_sc.get("label","")}</div>'
                f'<div style="margin-bottom:16px;">'
                f'<div style="font-size:.53rem;font-weight:700;letter-spacing:.12em;'
                f'text-transform:uppercase;color:#334155;margin-bottom:6px;">TRIGGER CONDITION</div>'
                f'<div style="font-size:.82rem;color:#94a3b8;line-height:1.7;">'
                f'{_sc.get("trigger","")}</div>'
                f'</div>'
                f'<div style="margin-bottom:16px;">'
                f'<div style="font-size:.53rem;font-weight:700;letter-spacing:.12em;'
                f'text-transform:uppercase;color:#334155;margin-bottom:6px;">MARKET REACTION</div>'
                f'<div style="font-size:.82rem;color:#cbd5e1;font-weight:500;line-height:1.7;">'
                f'{_sc.get("market_reaction", _sc.get("reaction",""))}</div>'
                f'</div>'
                f'<div>'
                f'<div style="font-size:.53rem;font-weight:700;letter-spacing:.12em;'
                f'text-transform:uppercase;color:#334155;margin-bottom:6px;">EXPERT RATIONALE</div>'
                f'<div style="font-size:.78rem;color:#64748b;line-height:1.75;">'
                f'{_sc.get("rationale","")}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    with _sc_tabs[5]:
        st.markdown('<div style="margin-top:10px;"></div>', unsafe_allow_html=True)
        _render_scenario_matrix(_matrix)


def st_html(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


# ── Session state (alert detection across reruns) ─────────────────────────────

if "last_alert_ts" not in st.session_state:
    st.session_state.last_alert_ts = None
if "event_page" not in st.session_state:
    st.session_state.event_page = None

_ALL_CCYS = sorted(["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "NZD", "CNY"])

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Volatility status + interactive filters
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("**TREM NEWS**")
    st.caption("Decision Support System")
    st.divider()

    # Unfiltered alerts for system-wide vol status
    _sb_alerts = load_alerts()
    vol_level, vol_label = _vol_status(_sb_alerts)

    st.markdown(
        f'<div class="vol-strip">'
        f'<span class="vdot vdot-{vol_level}"></span>'
        f'<span class="vol-lbl lbl-{vol_level}">{vol_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.popover("View Details", use_container_width=True):
        if _sb_alerts.empty:
            st.caption(
                "No spike alerts recorded. The volatility monitor warms up over "
                "the first 5 price samples (approx. 5 minutes) before detection activates."
            )
        else:
            _sb_lat = _sb_alerts.iloc[0]
            _sb_sim = str(_sb_lat["explanation"]).startswith("[SIM]")
            _sb_expl = str(_sb_lat["explanation"]).removeprefix("[SIM]").strip()
            _sb_col  = "#22c55e" if _sb_lat["spike_type"] == "BULLISH_SURGE" else "#ef4444"
            st.markdown(
                f'<div style="font-size:.68rem;font-weight:700;letter-spacing:.08em;'
                f'text-transform:uppercase;color:{_sb_col};margin-bottom:7px;">'
                f'{_sb_lat["asset"]} &mdash; {_sb_lat["spike_type"].replace("_"," ")}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:.78rem;color:#94a3b8;line-height:1.6;">'
                f'{_sb_expl or "AI analysis pending."}</div>',
                unsafe_allow_html=True,
            )
            _sb_z = abs(float(_sb_lat["z_score"]))
            _sb_p = float(_sb_lat["current_price"])
            _sb_sn = " &nbsp;|&nbsp; Simulated data" if _sb_sim else ""
            st.markdown(
                f'<div style="margin-top:9px;font-size:.66rem;color:#475569;">'
                f'Z-Score: {_sb_z:.2f}&thinsp;&sigma; &nbsp;|&nbsp; Price: {_sb_p:.4f}{_sb_sn}</div>',
                unsafe_allow_html=True,
            )
            if len(_sb_alerts) > 1:
                st.divider()
                st.markdown(
                    '<div style="font-size:.58rem;font-weight:700;letter-spacing:.1em;'
                    'text-transform:uppercase;color:#334155;margin-bottom:6px;">Recent Alerts</div>',
                    unsafe_allow_html=True,
                )
                for _, _sb_row in _sb_alerts.head(6).iterrows():
                    _sb_rc = "#22c55e" if _sb_row["spike_type"] == "BULLISH_SURGE" else "#ef4444"
                    st.markdown(
                        f'<div style="font-size:.7rem;padding:3px 0;border-bottom:1px solid #0f172a;">'
                        f'<span style="color:{_sb_rc};font-weight:600;">{_sb_row["asset"]}</span>'
                        f'<span style="color:#334155;"> &nbsp;z={abs(float(_sb_row["z_score"])):.2f}'
                        f'&sigma; &nbsp;{str(_sb_row["detected_at"])[:16]}</span></div>',
                        unsafe_allow_html=True,
                    )

    st.divider()

    # ── Time Range ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Time Range</div>', unsafe_allow_html=True)
    _today = date.today()
    _t_mode = st.radio(
        "Period",
        ["Today", "This Week", "This Month", "Custom"],
        index=1,
        key="t_mode",
        label_visibility="collapsed",
    )
    if _t_mode == "Today":
        from_d = to_d = _today
    elif _t_mode == "This Week":
        from_d = _today - timedelta(days=_today.weekday())
        to_d   = from_d + timedelta(days=6)
    elif _t_mode == "This Month":
        from_d = date(_today.year, _today.month, 1)
        to_d   = _today
    else:
        from_d = st.date_input("From", value=_today,                     key="from_d", label_visibility="collapsed")
        to_d   = st.date_input("To",   value=_today + timedelta(days=7), key="to_d",   label_visibility="collapsed")

    # ── Currency Filter ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Currency Filter</div>', unsafe_allow_html=True)
    _sel_ccys: list[str] = st.multiselect(
        "Currencies",
        options=_ALL_CCYS,
        default=_ALL_CCYS,
        key="f_ccy",
        label_visibility="collapsed",
    )

    # ── Impact Filter ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Impact Filter</div>', unsafe_allow_html=True)
    show_high   = st.checkbox("High",   value=True,  key="f_h")
    show_medium = st.checkbox("Medium", value=True,  key="f_m")
    show_low    = st.checkbox("Low",    value=False, key="f_l")

    # ── Alert Asset Filter ─────────────────────────────────────────────────
    _watched_assets = _load_watched_assets()
    _all_asset_names = [a["name"] for a in _watched_assets]
    st.markdown('<div class="section-title">Alert Assets</div>', unsafe_allow_html=True)
    _sel_assets: list[str] = st.multiselect(
        "Assets",
        options=_all_asset_names,
        default=_all_asset_names,
        key="f_assets",
        label_visibility="collapsed",
    )

    st.divider()
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # ── Monitored assets panel ─────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">Monitored Assets</div>', unsafe_allow_html=True)
    _class_colors = {
        "forex":     "#3b82f6",
        "index":     "#8b5cf6",
        "crypto":    "#f59e0b",
        "commodity": "#22c55e",
        "equity":    "#64748b",
    }
    for _a in _watched_assets:
        _c = _class_colors.get(_a.get("class", ""), "#475569")
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:7px;'
            f'padding:4px 0;border-bottom:1px solid #0f172a;">'
            f'<span style="width:6px;height:6px;border-radius:50%;'
            f'background:{_c};flex-shrink:0;display:inline-block;"></span>'
            f'<span style="font-size:.72rem;color:#94a3b8;flex:1;">{_a.get("name","")}</span>'
            f'<span style="font-size:.62rem;color:#475569;font-family:monospace;">'
            f'{_a.get("ticker","")}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div style="font-size:.58rem;color:#334155;padding-top:5px;">'
        'Edit backend/assets.yaml to add or remove tickers.</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    _key_c = "#22c55e" if FINNHUB_API_KEY else "#475569"
    _key_t = "FINNHUB KEY CONFIGURED" if FINNHUB_API_KEY else "NO FINNHUB KEY"
    st.markdown(
        f'<div style="font-size:.6rem;color:{_key_c};letter-spacing:.06em;text-align:center;">'
        f'{_key_t}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# POST-SIDEBAR: alert detection, filtered data, auto-refresh
# ══════════════════════════════════════════════════════════════════════════════

alerts_df = load_alerts()

# Apply asset filter
if _sel_assets and not alerts_df.empty:
    alerts_df = alerts_df[alerts_df["asset"].isin(_sel_assets)].reset_index(drop=True)

# Detect new spike → toast + audio ping
if not alerts_df.empty:
    _cur_ts = str(alerts_df.iloc[0]["detected_at"])
    if st.session_state.last_alert_ts is not None and _cur_ts != st.session_state.last_alert_ts:
        _al = alerts_df.iloc[0]
        st.toast(
            f"Spike detected: {_al['asset']} — {_al['spike_type'].replace('_', ' ')}",
            icon="🚨",
        )
        # Web Audio API beep (880 Hz, 0.5 s) — works after first user interaction
        st_html(
            "<script>"
            "(function(){"
            "try{"
            "var c=new(window.AudioContext||window.webkitAudioContext)();"
            "var o=c.createOscillator();"
            "var g=c.createGain();"
            "o.connect(g);g.connect(c.destination);"
            "o.type='sine';o.frequency.value=880;"
            "g.gain.setValueAtTime(0.2,c.currentTime);"
            "g.gain.exponentialRampToValueAtTime(0.001,c.currentTime+0.5);"
            "o.start(c.currentTime);o.stop(c.currentTime+0.5);"
            "}catch(e){}"
            "})();"
            "</script>"
        )
    st.session_state.last_alert_ts = _cur_ts

# Auto-refresh every 30 s — keeps alert detection live between user interactions
st_html("<script>setTimeout(function(){window.location.reload();},30000);</script>")

# ── Filtered events (shared between Calendar tab and Export tab) ───────────────

_raw_events, _data_source = load_events(from_d, to_d)

_active_impacts: list[str] = (
    (["high"]   if show_high   else []) +
    (["medium"] if show_medium else []) +
    (["low"]    if show_low    else [])
)
_active_ccys = set(_sel_ccys) if _sel_ccys else set(_ALL_CCYS)

filtered_events: list[dict] = [
    e for e in _raw_events
    if e.get("impact_level") in _active_impacts
    and e.get("currency") in _active_ccys
]

# ══════════════════════════════════════════════════════════════════════════════
# MAIN — Tabs
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("event_page") is not None:
    _render_event_terminal(st.session_state.event_page)
    st.stop()

tab_cal, tab_ai, tab_export = st.tabs(
    ["Economic Calendar", "Asset Intelligence", "Export"]
)

# ── Tab 1: Economic Calendar ──────────────────────────────────────────────────

with tab_cal:
    _src_colors = {
        "LIVE — Finnhub API":   "#22c55e",
        "LOCAL DB":             "#3b82f6",
        "GENERATED SCHEDULE":   "#f59e0b",
        "NO DATA":              "#ef4444",
    }
    _src_c = _src_colors.get(_data_source, "#475569")

    st.markdown(
        f'<div class="pg-header" style="display:flex;align-items:baseline;gap:14px;">'
        f'<span>Economic Calendar</span>'
        f'<span style="font-size:.58rem;color:{_src_c};letter-spacing:.1em;">'
        f'DATA SOURCE: {_data_source}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not filtered_events:
        st.info(
            "No economic events match the current filters. "
            "Try widening the time range, impact filter, or currency selection."
        )
    else:
        st.markdown(
            '<div class="cal-hdr">'
            '<span>TIME (UTC)</span>'
            '<span>EVENT</span>'
            '<span>CCY</span>'
            '<span>IMPACT</span>'
            '<span>ACTUAL</span>'
            '<span>FORECAST</span>'
            '<span>PREVIOUS</span>'
            '<span>STATUS</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        by_date: dict[str, list[dict]] = {}
        for ev in filtered_events:
            d = _parse_date(str(ev.get("timestamp", "")))
            by_date.setdefault(d, []).append(ev)

        for day, day_evs in sorted(by_date.items()):
            try:
                day_label = pd.Timestamp(day).strftime("%A, %d %B %Y").upper()
            except Exception:
                day_label = day

            st.markdown(f'<div class="date-grp">{day_label}</div>', unsafe_allow_html=True)

            for ev in day_evs:
                has_actual = ev.get("actual") is not None
                row_cls    = "cal-row cal-row-past" if has_actual else "cal-row"
                status_html = (
                    '<span class="s-rel">RELEASED</span>'
                    if has_actual
                    else '<span class="s-sched">SCHEDULED</span>'
                )
                unit = ev.get("unit") or ""

                st.markdown(
                    f'<div class="{row_cls}">'
                    f'<span class="c-time">{_parse_time(str(ev.get("timestamp", "")))}</span>'
                    f'<span class="c-event">{ev.get("event_name", "")}</span>'
                    f'<span class="c-ccy">{ev.get("currency", "")}</span>'
                    f'{_impact_html(ev.get("impact_level", "low"))}'
                    f'<span class="c-act">{_fmt(ev.get("actual"),   unit)}</span>'
                    f'<span class="c-fct">{_fmt(ev.get("forecast"), unit)}</span>'
                    f'<span class="c-prv">{_fmt(ev.get("previous"), unit)}</span>'
                    f'{status_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                if ev.get("impact_level") in ("high", "medium"):
                    if st.button(
                        "→ Scenario Terminal",
                        key=f"evt_{ev.get('event_id', '')}_{ev.get('timestamp', '')}",
                        help=f"Open scenario terminal for {ev.get('event_name', '')}",
                    ):
                        st.session_state.event_page = ev
                        st.rerun()

# ── Tab 2: Asset Intelligence ─────────────────────────────────────────────────

with tab_ai:
    _ai_assets  = _load_watched_assets()
    _ai_options = {a["name"]: a for a in _ai_assets}

    st.markdown(
        '<div class="pg-header">Asset Intelligence</div>',
        unsafe_allow_html=True,
    )

    _sel_name = st.selectbox(
        "Select asset",
        options=list(_ai_options.keys()),
        label_visibility="collapsed",
    )

    if _sel_name:
        _sel    = _ai_options[_sel_name]
        _ticker = _sel["ticker"]
        _aclass = _sel.get("class", "")

        with st.spinner(f"Loading market data for {_sel_name}…"):
            _intel = load_asset_intelligence(_ticker)

        if _intel.get("error"):
            st.warning(
                f"Market data unavailable for **{_sel_name}** (`{_ticker}`). "
                f"This is expected when the environment blocks outbound finance APIs. "
                f"Error: `{_intel['error']}`"
            )
        else:
            _price   = _intel.get("current_price")
            _prev    = _intel.get("prev_close")
            _hi52    = _intel.get("week52_high")
            _lo52    = _intel.get("week52_low")

            _chg_pct: float | None = None
            if _price is not None and _prev is not None and _prev != 0:
                _chg_pct = (_price - _prev) / _prev * 100

            # Metric cards
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.metric(
                    "Current Price",
                    _fmt_price(_price),
                )
            with mc2:
                st.metric(
                    "Daily Change",
                    f"{_chg_pct:+.2f}%" if _chg_pct is not None else "N/A",
                    delta=f"{_chg_pct:+.2f}%" if _chg_pct is not None else None,
                )
            with mc3:
                st.metric("52W High", _fmt_price(_hi52))
            with mc4:
                st.metric("52W Low",  _fmt_price(_lo52))

            # 52-week range progress bar
            if _price is not None and _hi52 is not None and _lo52 is not None and _hi52 > _lo52:
                _pct_pos = max(0.0, min(100.0, (_price - _lo52) / (_hi52 - _lo52) * 100))
                st.markdown(
                    f'<div style="margin:12px 0 16px;">'
                    f'<div style="font-size:.58rem;color:#334155;letter-spacing:.1em;'
                    f'text-transform:uppercase;margin-bottom:5px;">52-Week Position</div>'
                    f'<div style="background:#1e293b;border-radius:4px;height:6px;position:relative;">'
                    f'<div style="position:absolute;left:0;top:0;height:100%;'
                    f'width:{_pct_pos:.1f}%;background:#3b82f6;border-radius:4px;"></div>'
                    f'<div style="position:absolute;left:{_pct_pos:.1f}%;top:-3px;'
                    f'transform:translateX(-50%);width:12px;height:12px;border-radius:50%;'
                    f'background:#60a5fa;border:2px solid #0b0f19;"></div>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'font-size:.62rem;color:#475569;margin-top:5px;">'
                    f'<span>{_fmt_price(_lo52)} (Low)</span>'
                    f'<span style="color:#3b82f6;">{_pct_pos:.0f}% of range</span>'
                    f'<span>{_fmt_price(_hi52)} (High)</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

            # Analyst consensus — only available for equities
            _target_mean  = _intel.get("target_mean")
            _rec_key      = _intel.get("rec_key", "")
            _analyst_cnt  = _intel.get("analyst_count")
            _recs_df      = _intel.get("recommendations")

            if _target_mean is not None or _rec_key:
                st.markdown('<div class="section-title">Analyst Consensus</div>', unsafe_allow_html=True)

                _rec_colors = {
                    "STRONG BUY":   "#16a34a",
                    "BUY":          "#22c55e",
                    "HOLD":         "#f59e0b",
                    "UNDERPERFORM": "#ef4444",
                    "SELL":         "#dc2626",
                    "STRONG SELL":  "#991b1b",
                }
                _rc = _rec_colors.get(_rec_key, "#64748b")
                _cnt_str = f"{_analyst_cnt} analysts" if _analyst_cnt else ""

                ac1, ac2, ac3 = st.columns(3)
                with ac1:
                    st.markdown(
                        f'<div style="padding:14px;background:#111827;border-radius:6px;'
                        f'border-left:3px solid {_rc};height:100%;">'
                        f'<div style="font-size:.55rem;color:#334155;letter-spacing:.1em;'
                        f'text-transform:uppercase;margin-bottom:6px;">Consensus Rating</div>'
                        f'<div style="font-size:1.15rem;font-weight:700;color:{_rc};">'
                        f'{_rec_key or "N/A"}</div>'
                        f'<div style="font-size:.62rem;color:#475569;margin-top:4px;">'
                        f'{_cnt_str}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with ac2:
                    if _target_mean is not None:
                        _upside: float | None = None
                        if _price is not None and _price != 0:
                            _upside = (_target_mean - _price) / _price * 100
                        _up_str = f" ({_upside:+.1f}%)" if _upside is not None else ""
                        _up_col = "#22c55e" if (_upside or 0) >= 0 else "#ef4444"
                        st.markdown(
                            f'<div style="padding:14px;background:#111827;border-radius:6px;height:100%;">'
                            f'<div style="font-size:.55rem;color:#334155;letter-spacing:.1em;'
                            f'text-transform:uppercase;margin-bottom:6px;">Price Target (Mean)</div>'
                            f'<div style="font-size:1.15rem;font-weight:700;color:#cbd5e1;">'
                            f'{_fmt_price(_target_mean)}</div>'
                            f'<div style="font-size:.62rem;color:{_up_col};margin-top:4px;">'
                            f'{_up_str.strip()}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                with ac3:
                    _thi = _intel.get("target_high")
                    _tlo = _intel.get("target_low")
                    if _thi is not None or _tlo is not None:
                        st.markdown(
                            f'<div style="padding:14px;background:#111827;border-radius:6px;height:100%;">'
                            f'<div style="font-size:.55rem;color:#334155;letter-spacing:.1em;'
                            f'text-transform:uppercase;margin-bottom:6px;">Target Range</div>'
                            f'<div style="font-size:.9rem;font-weight:600;">'
                            f'<span style="color:#22c55e">{_fmt_price(_thi) if _thi else "—"}</span>'
                            f'<span style="color:#334155;margin:0 5px;">/</span>'
                            f'<span style="color:#ef4444">{_fmt_price(_tlo) if _tlo else "—"}</span>'
                            f'</div>'
                            f'<div style="font-size:.58rem;color:#334155;margin-top:5px;">High / Low</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                if _recs_df is not None and not _recs_df.empty:
                    st.markdown(
                        '<div class="section-title" style="margin-top:14px;">Recent Analyst Ratings</div>',
                        unsafe_allow_html=True,
                    )
                    try:
                        _disp = _recs_df.reset_index()
                        _cols = [c for c in _disp.columns if c not in ("index",)]
                        st.dataframe(_disp[_cols], use_container_width=True, hide_index=True)
                    except Exception:
                        st.dataframe(_recs_df, use_container_width=True)
            else:
                _class_labels = {
                    "forex": "currency pair",
                    "crypto": "cryptocurrency",
                    "commodity": "commodity",
                    "index": "market index",
                }
                _cl = _class_labels.get(_aclass, "instrument")
                st.markdown(
                    f'<div style="padding:14px 16px;background:#111827;border-radius:6px;'
                    f'border-left:3px solid #1e293b;margin-top:8px;">'
                    f'<div style="font-size:.7rem;color:#64748b;line-height:1.7;">'
                    f'Sell-side analyst consensus is not published for this {_cl}. '
                    f'Price metrics and 52-week range are shown above.<br>'
                    f'To see equity-level analyst data, add stock tickers '
                    f'(e.g. <code>AAPL</code>, <code>MSFT</code>) to '
                    f'<code>backend/assets.yaml</code>.'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )


# ── Tab 3: Export ─────────────────────────────────────────────────────────────

with tab_export:
    st.markdown('<div class="pg-header">Export</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:.72rem;color:#64748b;margin-bottom:18px;">'
        'Downloads reflect the currently active filters '
        '(time range, currency, impact level, asset selection).'
        '</div>',
        unsafe_allow_html=True,
    )

    exp_c1, exp_c2 = st.columns(2)

    # ── Events CSV ────────────────────────────────────────────────────────
    with exp_c1:
        st.markdown(
            '<div class="section-title">Economic Events</div>',
            unsafe_allow_html=True,
        )
        if filtered_events:
            _ev_rows = []
            for _ev in filtered_events:
                _sc = _scenario_matrix(_ev.get("event_name", ""), _ev.get("currency", "USD"))
                _ev_rows.append({
                    "Timestamp (UTC)":    _ev.get("timestamp", ""),
                    "Event":              _ev.get("event_name", ""),
                    "Country":            _ev.get("country", ""),
                    "Currency":           _ev.get("currency", ""),
                    "Impact":             _ev.get("impact_level", ""),
                    "Actual":             _ev.get("actual", ""),
                    "Forecast":           _ev.get("forecast", ""),
                    "Previous":           _ev.get("previous", ""),
                    "Unit":               _ev.get("unit", ""),
                    "SC1_Label":          _sc[0]["label"] if len(_sc) > 0 else "",
                    "SC1_Trigger":        _sc[0]["trigger"] if len(_sc) > 0 else "",
                    "SC1_Reaction":       _sc[0]["market_reaction"] if len(_sc) > 0 else "",
                    "SC3_Label":          _sc[2]["label"] if len(_sc) > 2 else "",
                    "SC3_Trigger":        _sc[2]["trigger"] if len(_sc) > 2 else "",
                    "SC3_Reaction":       _sc[2]["market_reaction"] if len(_sc) > 2 else "",
                    "SC5_Label":          _sc[4]["label"] if len(_sc) > 4 else "",
                    "SC5_Trigger":        _sc[4]["trigger"] if len(_sc) > 4 else "",
                    "SC5_Reaction":       _sc[4]["market_reaction"] if len(_sc) > 4 else "",
                })
            _ev_df = pd.DataFrame(_ev_rows)
            st.markdown(
                f'<div style="font-size:.65rem;color:#475569;margin-bottom:8px;">'
                f'{len(filtered_events)} event(s) — {from_d} to {to_d}</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                label="Download Events (CSV)",
                data=_ev_df.to_csv(index=False),
                file_name=f"trem_news_events_{from_d}_{to_d}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No events match current filters.")

    # ── Alerts CSV ────────────────────────────────────────────────────────
    with exp_c2:
        st.markdown(
            '<div class="section-title">Volatility Alerts</div>',
            unsafe_allow_html=True,
        )
        if not alerts_df.empty:
            st.markdown(
                f'<div style="font-size:.65rem;color:#475569;margin-bottom:8px;">'
                f'{len(alerts_df)} alert(s) — most recent {len(alerts_df)}</div>',
                unsafe_allow_html=True,
            )
            _al_export = alerts_df.copy()
            _al_export.columns = [c.replace("_", " ").title() for c in _al_export.columns]
            st.download_button(
                label="Download Alerts (CSV)",
                data=_al_export.to_csv(index=False),
                file_name="trem_news_alerts.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("No alerts match current filters.")

    st.divider()
    st.markdown(
        '<div style="font-size:.65rem;color:#334155;line-height:1.8;">'
        '<strong>Events CSV columns:</strong> timestamp, event, country, currency, impact, '
        'actual, forecast, previous, unit, plus scenario-matrix fields for the Extreme Hawkish, '
        'Consensus, and Extreme Dovish cases (label, trigger, market reaction).<br>'
        '<strong>Alerts CSV columns:</strong> id, asset, ticker, spike type, current price, '
        'z-score, cause found, AI explanation, detected at.'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    f'<div style="font-size:.58rem;color:#1e293b;letter-spacing:.06em;text-align:center;">'
    f'TREM NEWS &nbsp;&bull;&nbsp; DECISION SUPPORT SYSTEM &nbsp;&bull;&nbsp; '
    f'NOT INVESTMENT ADVICE &nbsp;&bull;&nbsp; DATA: FINNHUB + YFINANCE &nbsp;&bull;&nbsp; '
    f'DB: {DB_PATH.name}'
    f'</div>',
    unsafe_allow_html=True,
)
