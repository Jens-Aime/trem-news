"""
Market Pulse Intelligence — Financial Calendar Dashboard
=========================================================
Professional economic calendar with live volatility monitoring.

Start command:
    cd /path/to/trem-news/backend
    streamlit run dashboard.py --server.port 8501
"""

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
    page_title="Market Pulse Intelligence",
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

/* ── Scenario analysis ── */
.sc-beat   { border-left: 2px solid #22c55e; padding-left: 11px; }
.sc-miss   { border-left: 2px solid #ef4444; padding-left: 11px; }
.sc-inline { border-left: 2px solid #374151; padding-left: 11px; }
.sc-lbl    { font-size: .6rem; font-weight: 700; letter-spacing: .12em;
             text-transform: uppercase; margin-bottom: 6px; }
.lbl-b  { color: #22c55e; }
.lbl-m  { color: #ef4444; }
.lbl-i  { color: #6b7280; }
.sc-txt { font-size: .76rem; color: #94a3b8; line-height: 1.6; }

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


# ── Scenario analysis engine ──────────────────────────────────────────────────

def _scenarios(name: str, ccy: str) -> dict[str, str]:
    n = name.lower()

    if any(k in n for k in ("nonfarm", "non-farm", "nfp", "payroll")):
        return {
            "beat":   f"Stronger-than-expected payrolls reduce recession risk and support {ccy} as labor market resilience sustains current rate expectations. USD-correlated assets may see upside pressure.",
            "miss":   f"Weaker payrolls raise probability of Fed easing, pressuring {ccy} near-term. Risk assets may rally on lower-for-longer rate expectations; duration bonds likely to outperform.",
            "inline": "In-line reading confirms trend continuation. Limited immediate market catalyst; attention shifts to the next high-impact release or Fed communication.",
        }
    if any(k in n for k in ("cpi", "consumer price", "price index", "inflation")):
        return {
            "beat":   f"Above-forecast inflation reinforces central bank hawkishness, supporting {ccy} through sustained rate expectations. Fixed income may come under renewed pressure.",
            "miss":   f"Below-forecast CPI opens the door for earlier rate reductions, softening {ccy} near-term. Bond prices likely to rally; growth-sensitive equities may benefit.",
            "inline": "Consensus print keeps policy trajectory unchanged. Limited repricing unless prior periods are revised materially upward.",
        }
    if any(k in n for k in ("gdp", "gross domestic")):
        return {
            "beat":   f"Growth beat strengthens the macro outlook for the {ccy} zone, potentially delaying rate cuts. Equity indices may rally; cyclicals and financials could outperform.",
            "miss":   f"Growth miss raises stagflation or recession risk, pressuring {ccy}. Safe-haven flows may benefit CHF and JPY; commodity currencies at heightened risk.",
            "inline": "GDP in line with consensus maintains status quo. Market focus shifts to forward guidance, revision components, and consumption sub-indices.",
        }
    if any(k in n for k in ("pce", "personal consumption", "personal spending")):
        return {
            "beat":   f"Strong PCE reinforces the Fed's cautious stance on rate reductions, underpinning {ccy}. Real yields may tick higher; growth stocks could see marginal pressure.",
            "miss":   f"Soft PCE increases confidence in the disinflation path, raising rate-cut probability. Treasuries likely to rally; {ccy} may weaken modestly.",
            "inline": "In-line PCE supports gradual normalization narrative. No immediate repricing catalyst absent material forward guidance shifts.",
        }
    if any(k in n for k in ("pmi", "purchasing managers", "ism manufacturing", "ism services", "ism non")):
        return {
            "beat":   f"Above-50 PMI beat signals expansion momentum, supporting risk appetite and {ccy}. Manufacturing or services sector equities may outperform.",
            "miss":   f"Sub-50 PMI miss signals contraction risk, weakening {ccy} and broader risk sentiment. Defensive sectors and government bonds may attract flows.",
            "inline": "PMI at consensus — expansion or contraction pace confirmed. Watch the 50 threshold as the decisive directional boundary.",
        }
    if any(k in n for k in ("rate decision", "interest rate", "fomc", "boe", "ecb", "rba", "rbnz", "boj", "boc")):
        return {
            "beat":   f"Hawkish surprise (higher rate or tighter-than-expected guidance) strengthens {ccy} materially. Short-duration assets outperform; yield curve may flatten.",
            "miss":   f"Dovish surprise (cut or softer guidance) pressures {ccy}. Equities may rally on reduced discount rates; long-duration bonds outperform.",
            "inline": "Rate held as expected — market focus shifts entirely to statement tone, forward guidance, and any revised economic projections.",
        }
    if any(k in n for k in ("retail sales", "retail")):
        return {
            "beat":   f"Strong consumer spending signals economic resilience, supporting {ccy} and modestly lifting rate expectations.",
            "miss":   f"Weak retail data raises demand concerns, softening {ccy}. Discretionary and consumer cyclical sectors most exposed.",
            "inline": "Sales in line with forecast — consumption trend confirmed. Limited immediate market impact without material revision to prior data.",
        }
    if any(k in n for k in ("unemployment", "jobless", "initial claims", "claims")):
        return {
            "beat":   f"Lower unemployment or fewer claims confirms tight labor market conditions, supporting {ccy} through sustained wage and rate expectations.",
            "miss":   f"Rising unemployment or higher claims signals labor market softening, weighing on {ccy} and strengthening rate-cut bets.",
            "inline": "Claims in line with consensus — labor market trend intact. Awaiting next primary labor data for directional signal.",
        }
    if any(k in n for k in ("trade balance", "current account", "trade deficit", "trade surplus")):
        return {
            "beat":   f"Narrowing deficit or wider surplus is {ccy}-positive, reducing external imbalance pressure and improving net foreign demand for the currency.",
            "miss":   f"Wider trade deficit pressures {ccy} as outflows may outpace inflows, raising external financing concerns.",
            "inline": "Trade balance as expected — no immediate currency repricing signal. Focus remains on broader macro drivers.",
        }
    # Generic fallback
    return {
        "beat":   f"A stronger-than-expected reading is generally {ccy}-positive, supporting the domestic macro outlook and potentially moderating rate-cut expectations.",
        "miss":   f"A weaker-than-expected reading may weigh on {ccy} by reducing growth confidence or accelerating expectations of monetary easing.",
        "inline": "Result in line with forecast — limited immediate market reaction anticipated. Revisions to the prior period figure are the key swing factor to monitor.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Volatility monitor
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("**MARKET PULSE INTELLIGENCE**")
    st.caption("Decision Support System")
    st.divider()

    alerts_df = load_alerts()
    vol_level, vol_label = _vol_status(alerts_df)

    # Animated pulsing dot + status label
    st.markdown(
        f'<div class="vol-strip">'
        f'<span class="vdot vdot-{vol_level}"></span>'
        f'<span class="vol-lbl lbl-{vol_level}">{vol_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Popover: click for detailed volatility context
    with st.popover("View Details", use_container_width=True):
        if alerts_df.empty:
            st.caption(
                "No spike alerts recorded. The volatility monitor warms up over "
                "the first 5 price samples (approx. 5 minutes) before detection activates."
            )
        else:
            latest = alerts_df.iloc[0]
            is_sim = str(latest["explanation"]).startswith("[SIM]")
            expl   = str(latest["explanation"]).removeprefix("[SIM]").strip()
            sp_col = "#22c55e" if latest["spike_type"] == "BULLISH_SURGE" else "#ef4444"
            spike_label = latest["spike_type"].replace("_", " ")

            st.markdown(
                f'<div style="font-size:.68rem;font-weight:700;letter-spacing:.08em;'
                f'text-transform:uppercase;color:{sp_col};margin-bottom:7px;">'
                f'{latest["asset"]} &mdash; {spike_label}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:.78rem;color:#94a3b8;line-height:1.6;">'
                f'{expl or "AI analysis pending."}</div>',
                unsafe_allow_html=True,
            )
            z = abs(float(latest["z_score"]))
            p = float(latest["current_price"])
            sim_note = " &nbsp;|&nbsp; Simulated data" if is_sim else ""
            st.markdown(
                f'<div style="margin-top:9px;font-size:.66rem;color:#475569;">'
                f'Z-Score: {z:.2f}&thinsp;&sigma; &nbsp;|&nbsp; Price: {p:.4f}{sim_note}</div>',
                unsafe_allow_html=True,
            )

            if len(alerts_df) > 1:
                st.divider()
                st.markdown(
                    '<div style="font-size:.58rem;font-weight:700;letter-spacing:.1em;'
                    'text-transform:uppercase;color:#334155;margin-bottom:6px;">Recent Alerts</div>',
                    unsafe_allow_html=True,
                )
                for _, row in alerts_df.head(6).iterrows():
                    c = "#22c55e" if row["spike_type"] == "BULLISH_SURGE" else "#ef4444"
                    st.markdown(
                        f'<div style="font-size:.7rem;padding:3px 0;border-bottom:1px solid #0f172a;">'
                        f'<span style="color:{c};font-weight:600;">{row["asset"]}</span>'
                        f'<span style="color:#334155;"> &nbsp;z={abs(float(row["z_score"])):.2f}&sigma;'
                        f' &nbsp;{str(row["detected_at"])[:16]}</span></div>',
                        unsafe_allow_html=True,
                    )

    st.divider()

    st.markdown('<div class="section-title">Calendar Range</div>', unsafe_allow_html=True)
    today = date.today()
    from_d = st.date_input("From", value=today,                     key="from_d", label_visibility="collapsed")
    to_d   = st.date_input("To",   value=today + timedelta(days=7), key="to_d",   label_visibility="collapsed")

    st.markdown('<div class="section-title">Impact Filter</div>', unsafe_allow_html=True)
    show_high   = st.checkbox("High",   value=True,  key="f_h")
    show_medium = st.checkbox("Medium", value=True,  key="f_m")
    show_low    = st.checkbox("Low",    value=False, key="f_l")

    st.divider()
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    key_c = "#22c55e" if FINNHUB_API_KEY else "#475569"
    key_t = "FINNHUB KEY CONFIGURED" if FINNHUB_API_KEY else "NO FINNHUB KEY"
    st.markdown(
        f'<div style="font-size:.6rem;color:{key_c};letter-spacing:.06em;text-align:center;">'
        f'{key_t}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — Economic Calendar
# ══════════════════════════════════════════════════════════════════════════════

events, _data_source = load_events(from_d, to_d)

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

active_impacts: list[str] = (
    (["high"]   if show_high   else []) +
    (["medium"] if show_medium else []) +
    (["low"]    if show_low    else [])
)
events = [e for e in events if e.get("impact_level") in active_impacts]

if not events:
    st.info(
        "No economic events found for the selected date range and filters. "
        "Configure FINNHUB_API_KEY in backend/.env to enable live calendar data."
    )
else:
    # Column header row
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

    # Group by calendar date
    by_date: dict[str, list[dict]] = {}
    for ev in events:
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

            # Scenario analysis — only for medium/high impact events
            if ev.get("impact_level") in ("high", "medium"):
                with st.expander(f"Scenario Analysis — {ev.get('event_name', '')}"):
                    sc = _scenarios(ev.get("event_name", ""), ev.get("currency", "USD"))
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(
                            f'<div class="sc-beat">'
                            f'<div class="sc-lbl lbl-b">BEAT</div>'
                            f'<div class="sc-txt">{sc["beat"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with c2:
                        st.markdown(
                            f'<div class="sc-miss">'
                            f'<div class="sc-lbl lbl-m">MISS</div>'
                            f'<div class="sc-txt">{sc["miss"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with c3:
                        st.markdown(
                            f'<div class="sc-inline">'
                            f'<div class="sc-lbl lbl-i">IN-LINE</div>'
                            f'<div class="sc-txt">{sc["inline"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    f'<div style="font-size:.58rem;color:#1e293b;letter-spacing:.06em;text-align:center;">'
    f'MARKET PULSE INTELLIGENCE &nbsp;&bull;&nbsp; DECISION SUPPORT SYSTEM &nbsp;&bull;&nbsp; '
    f'NOT INVESTMENT ADVICE &nbsp;&bull;&nbsp; DATA: FINNHUB + YFINANCE &nbsp;&bull;&nbsp; '
    f'DB: {DB_PATH.name}'
    f'</div>',
    unsafe_allow_html=True,
)
