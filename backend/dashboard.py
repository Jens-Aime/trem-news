"""
Market Pulse Intelligence — Streamlit Dashboard
================================================
Direct SQLite access — no WebSockets, no caching issues.

Start command:
    cd /path/to/trem-news/backend
    streamlit run dashboard.py --server.port 8501
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Market Pulse Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "marketpulse.db"

SENTIMENT_ICON: dict[str, str] = {
    "bullish": "▲",
    "bearish": "▼",
    "neutral": "→",
    "mixed": "⇅",
}
RISK_ICON: dict[str, str] = {
    "low":      "🟢",
    "medium":   "🟡",
    "high":     "🟠",
    "critical": "🔴",
}

# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=10)
def load_volatility_alerts() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT id, asset, ticker, spike_type, current_price,
                   z_score, cause_found, explanation, detected_at
            FROM   volatility_alerts
            ORDER  BY detected_at DESC
            LIMIT  50
            """,
            conn,
        )


@st.cache_data(ttl=15)
def load_history() -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT
                ar.analyzed_at,
                ee.event_name,
                ee.country,
                ee.currency,
                ee.impact_level,
                ee.actual,
                ee.forecast,
                ee.surprise_pct,
                ar.sentiment,
                ar.risk_level,
                ar.confidence_score,
                ar.market_narrative,
                ar.cached
            FROM   analysis_results ar
            JOIN   economic_events ee ON ar.event_id = ee.event_id
            ORDER  BY ar.analyzed_at DESC
            LIMIT  200
            """,
            conn,
        )


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

col_title, col_btn = st.columns([9, 1])
with col_title:
    st.title("📊 Market Pulse Intelligence")
    st.caption(
        "Decision Support System · AI-powered economic event analysis · "
        f"DB: `{DB_PATH}`"
    )
with col_btn:
    st.write("")
    if st.button("⟳  Refresh", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — VOLATILITY SPIKE ALERTS
# ══════════════════════════════════════════════════════════════════════════════

st.subheader("⚡ Volatility Spike Alerts")
st.caption(
    "EUR/USD · S&P 500 · USD Index — polled every 60 s via yfinance. "
    "Auto-fallback to Brownian-motion simulation when Yahoo Finance is unreachable."
)

alerts = load_volatility_alerts()

if alerts.empty:
    st.info(
        "No spike alerts yet.  The VolatilityMonitor warms up over the first 5 minutes "
        "before spike detection activates (needs ≥ 5 price samples)."
    )
else:
    bulls  = int((alerts["spike_type"] == "BULLISH_SURGE").sum())
    bears  = int((alerts["spike_type"] == "BEARISH_DROP").sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Spike Alerts", len(alerts))
    m2.metric("▲ Bullish Surges",   bulls)
    m3.metric("▼ Bearish Drops",    bears)

    st.write("")

    for _, row in alerts.iterrows():
        bullish = row["spike_type"] == "BULLISH_SURGE"
        simulated = str(row["explanation"]).startswith("[SIM]")
        explanation = str(row["explanation"]).removeprefix("[SIM]").strip()

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2.5, 2.5, 2, 7])

            with c1:
                icon = "▲" if bullish else "▼"
                color_label = "🟢 BULLISH SURGE" if bullish else "🔴 BEARISH DROP"
                st.markdown(f"### {icon} {row['asset']}")
                st.markdown(f"**{color_label}**")
                st.caption(f"`{row['ticker']}`")
                if simulated:
                    st.caption("🧪 simulated data")

            with c2:
                price = float(row["current_price"])
                # EUR/USD and USD Index → 4 decimals; S&P 500 → 2
                fmt = ".2f" if row["ticker"] == "^GSPC" else ".4f"
                st.metric("Price", f"{price:{fmt}}")

            with c3:
                z = float(row["z_score"])
                st.metric(
                    "Z-Score",
                    f"{abs(z):.2f} σ",
                    delta=f"{z:+.2f} σ",
                    delta_color="normal",
                )

            with c4:
                st.markdown(f"**AI Explanation**")
                st.write(explanation if explanation else "—")
                st.caption(f"🕐 Detected: {row['detected_at']}")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ECONOMIC EVENTS HISTORY
# ══════════════════════════════════════════════════════════════════════════════

st.subheader("📰 Economic Events — AI Analysis History")

history = load_history()

if history.empty:
    st.info(
        "No events yet.  Set FINNHUB_API_KEY and GEMINI_API_KEY in "
        "`backend/.env` to enable the autonomous analysis pipeline."
    )
else:
    # ── Summary metrics ────────────────────────────────────────────────────
    by_sent = history["sentiment"].value_counts()
    by_risk = history["risk_level"].value_counts()
    avg_conf = history["confidence_score"].mean()

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Events",    len(history))
    m2.metric("▲ Bullish",       int(by_sent.get("bullish", 0)))
    m3.metric("▼ Bearish",       int(by_sent.get("bearish", 0)))
    m4.metric("→ Neutral/Mixed", int(by_sent.get("neutral", 0) + by_sent.get("mixed", 0)))
    m5.metric("🔴 High/Critical", int(by_risk.get("high", 0) + by_risk.get("critical", 0)))
    m6.metric("Avg Confidence",  f"{avg_conf:.0%}")

    st.write("")

    # ── Data table ─────────────────────────────────────────────────────────
    display = history.copy()
    display["Sentiment"] = display["sentiment"].map(
        lambda s: f"{SENTIMENT_ICON.get(s, '?')} {s.upper()}"
    )
    display["Risk"] = display["risk_level"].map(
        lambda r: f"{RISK_ICON.get(r, '?')} {r.upper()}"
    )
    display["Conf."] = (
        (display["confidence_score"] * 100).round(0).astype(int).astype(str) + "%"
    )
    display["Surprise%"] = display["surprise_pct"].apply(
        lambda x: f"{x:+.1f}%" if pd.notna(x) else "—"
    )
    display["Actual"]   = display["actual"].apply(lambda x: str(x) if pd.notna(x) else "—")
    display["Forecast"] = display["forecast"].apply(lambda x: str(x) if pd.notna(x) else "—")
    display["Analyzed"] = display["analyzed_at"].str[:16].str.replace("T", " ", regex=False)

    TABLE_COLS = {
        "Analyzed":     "Analyzed (UTC)",
        "event_name":   "Event",
        "country":      "Country",
        "currency":     "CCY",
        "impact_level": "Impact",
        "Actual":       "Actual",
        "Forecast":     "Forecast",
        "Surprise%":    "Surprise %",
        "Sentiment":    "Sentiment",
        "Risk":         "Risk",
        "Conf.":        "Conf.",
    }

    st.dataframe(
        display[list(TABLE_COLS)].rename(columns=TABLE_COLS),
        use_container_width=True,
        hide_index=True,
        height=440,
    )

    # ── AI narrative detail ────────────────────────────────────────────────
    st.write("")
    with st.expander("📖 Full AI Narratives — latest 20 events"):
        for _, row in history.head(20).iterrows():
            r_icon = RISK_ICON.get(row["risk_level"], "?")
            s_icon = SENTIMENT_ICON.get(row["sentiment"], "?")
            st.markdown(
                f"**{row['event_name']}** &nbsp;·&nbsp; {row['country']} {row['currency']}  "
                f"&nbsp;|&nbsp; {r_icon} `{row['risk_level'].upper()}` "
                f"&nbsp;|&nbsp; {s_icon} `{row['sentiment'].upper()}`  "
                f"&nbsp;|&nbsp; _{str(row['analyzed_at'])[:16]}_"
            )
            st.write(row["market_narrative"])
            st.markdown("---")

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Market Pulse Intelligence · Strictly a Decision Support System · "
    "Not investment advice · Data: Finnhub + yfinance · AI: Google Gemini"
)
