"""
Built-in economic calendar generator.

Produces a realistic upcoming event schedule from known recurring release
patterns when the Finnhub Economic Calendar endpoint is unavailable
(free-tier restriction — endpoint requires a paid subscription).

Coverage
────────
  US  : NFP, Unemployment Rate, Initial Jobless Claims, CPI, Core CPI,
        PPI, Retail Sales, Core PCE, ISM Manufacturing PMI, ISM Services
        PMI, GDP Advance Estimate, FOMC Rate Decision
  EU  : ECB Rate Decision
  UK  : BOE Rate Decision

All timestamps are UTC.  US 08:30 ET = 13:30 UTC (accounts for both
EST +5h and EDT +4h — close enough for a calendar display).
"""

from datetime import date, datetime, timedelta, timezone

# ── Known central bank meeting dates ──────────────────────────────────────────

_FOMC = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-10",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
_ECB = [
    "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05",
    "2025-07-24", "2025-09-11", "2025-10-30", "2025-12-18",
    "2026-01-22", "2026-03-12", "2026-04-30", "2026-06-04",
    "2026-07-16", "2026-09-10", "2026-10-22", "2026-12-03",
]
_BOE = [
    "2025-02-06", "2025-03-20", "2025-05-08", "2025-06-19",
    "2025-08-07", "2025-09-18", "2025-11-06", "2025-12-18",
    "2026-02-05", "2026-03-19", "2026-05-07", "2026-06-18",
    "2026-08-06", "2026-09-17", "2026-11-05", "2026-12-17",
]


# ── Calendar arithmetic helpers ───────────────────────────────────────────────

def _first_weekday(y: int, m: int, wd: int) -> date:
    """First occurrence of weekday wd (0=Mon … 6=Sun) in month y-m."""
    d = date(y, m, 1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    """n-th occurrence of weekday wd in month y-m (n starts at 1)."""
    return _first_weekday(y, m, wd) + timedelta(weeks=n - 1)


def _last_friday(y: int, m: int) -> date:
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def _nth_bizday(y: int, m: int, n: int) -> date:
    """n-th business day of month y-m (n starts at 1)."""
    d, count = date(y, m, 1), 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _ts(d: date, h: int, mi: int = 0) -> str:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=timezone.utc).isoformat()


# ── Event builders ────────────────────────────────────────────────────────────

def _months_in_range(from_d: date, to_d: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = from_d.year, from_d.month
    while date(y, m, 1) <= to_d:
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def generate_events(from_date: date, to_date: date) -> list[dict]:
    """
    Return synthetic economic events in [from_date, to_date], sorted by timestamp.
    Events carry the same field schema as Finnhub-normalised events so the rest
    of the pipeline needs no changes.
    """
    out: list[dict] = []
    seen: set[str] = set()

    def add(ev: dict) -> None:
        eid = ev["event_id"]
        if eid not in seen:
            seen.add(eid)
            out.append(ev)

    def in_range(d: date) -> bool:
        return from_date <= d <= to_date

    # ── Per-month events ──────────────────────────────────────────────────────
    for y, m in _months_in_range(from_date, to_date):

        # NFP + Unemployment — first Friday, 13:30 UTC
        nfp = _first_weekday(y, m, 4)  # 4 = Friday
        if in_range(nfp):
            add({"event_id": f"gen-nfp-{y}-{m:02d}", "event_name": "Nonfarm Payrolls",
                 "country": "US", "currency": "USD", "timestamp": _ts(nfp, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "K"})
            add({"event_id": f"gen-ue-{y}-{m:02d}", "event_name": "Unemployment Rate",
                 "country": "US", "currency": "USD", "timestamp": _ts(nfp, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

        # Initial Jobless Claims — every Thursday, 13:30 UTC
        thu = _first_weekday(y, m, 3)  # 3 = Thursday
        while thu.month == m:
            if in_range(thu):
                add({"event_id": f"gen-claims-{thu.isoformat()}", "event_name": "Initial Jobless Claims",
                     "country": "US", "currency": "USD", "timestamp": _ts(thu, 13, 30),
                     "impact_level": "medium", "actual": None, "forecast": None, "previous": None, "unit": "K"})
            thu += timedelta(weeks=1)

        # CPI + Core CPI — 2nd Wednesday, 13:30 UTC
        cpi = _nth_weekday(y, m, 2, 2)  # 2nd Wednesday
        if in_range(cpi):
            add({"event_id": f"gen-cpi-{y}-{m:02d}", "event_name": "CPI (YoY)",
                 "country": "US", "currency": "USD", "timestamp": _ts(cpi, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})
            add({"event_id": f"gen-cpi-core-{y}-{m:02d}", "event_name": "Core CPI (YoY)",
                 "country": "US", "currency": "USD", "timestamp": _ts(cpi, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

        # PPI — Thursday after CPI
        ppi = cpi + timedelta(days=1)
        while ppi.weekday() != 3:
            ppi += timedelta(days=1)
        if in_range(ppi):
            add({"event_id": f"gen-ppi-{y}-{m:02d}", "event_name": "PPI (MoM)",
                 "country": "US", "currency": "USD", "timestamp": _ts(ppi, 13, 30),
                 "impact_level": "medium", "actual": None, "forecast": None, "previous": None, "unit": "%"})

        # Retail Sales — 2nd Thursday, 13:30 UTC
        rs = _nth_weekday(y, m, 3, 2)  # 2nd Thursday
        if in_range(rs):
            add({"event_id": f"gen-rs-{y}-{m:02d}", "event_name": "Retail Sales (MoM)",
                 "country": "US", "currency": "USD", "timestamp": _ts(rs, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

        # Core PCE — last Friday, 13:30 UTC
        pce = _last_friday(y, m)
        if in_range(pce):
            add({"event_id": f"gen-pce-{y}-{m:02d}", "event_name": "Core PCE Price Index (YoY)",
                 "country": "US", "currency": "USD", "timestamp": _ts(pce, 13, 30),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

        # ISM Manufacturing — 1st business day, 15:00 UTC
        ism_mfg = _nth_bizday(y, m, 1)
        if in_range(ism_mfg):
            add({"event_id": f"gen-ism-mfg-{y}-{m:02d}", "event_name": "ISM Manufacturing PMI",
                 "country": "US", "currency": "USD", "timestamp": _ts(ism_mfg, 15, 0),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": ""})

        # ISM Services — 3rd business day, 15:00 UTC
        ism_svc = _nth_bizday(y, m, 3)
        if in_range(ism_svc):
            add({"event_id": f"gen-ism-svc-{y}-{m:02d}", "event_name": "ISM Services PMI",
                 "country": "US", "currency": "USD", "timestamp": _ts(ism_svc, 15, 0),
                 "impact_level": "medium", "actual": None, "forecast": None, "previous": None, "unit": ""})

        # GDP Advance Estimate — Q1→Apr, Q2→Jul, Q3→Oct, Q4→Jan (Thursday ≥ 25th)
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            gdp = date(y, m, 25)
            while gdp.weekday() != 3:
                gdp += timedelta(days=1)
            if in_range(gdp):
                add({"event_id": f"gen-gdp-{y}-{m:02d}",
                     "event_name": f"GDP Advance Estimate ({quarter})",
                     "country": "US", "currency": "USD", "timestamp": _ts(gdp, 13, 30),
                     "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

    # ── Central bank decisions ────────────────────────────────────────────────
    for dt_str in _FOMC:
        d = date.fromisoformat(dt_str)
        if in_range(d):
            add({"event_id": f"gen-fomc-{dt_str}", "event_name": "FOMC Interest Rate Decision",
                 "country": "US", "currency": "USD", "timestamp": _ts(d, 19, 0),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

    for dt_str in _ECB:
        d = date.fromisoformat(dt_str)
        if in_range(d):
            add({"event_id": f"gen-ecb-{dt_str}", "event_name": "ECB Interest Rate Decision",
                 "country": "EU", "currency": "EUR", "timestamp": _ts(d, 13, 15),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

    for dt_str in _BOE:
        d = date.fromisoformat(dt_str)
        if in_range(d):
            add({"event_id": f"gen-boe-{dt_str}", "event_name": "BOE Interest Rate Decision",
                 "country": "GB", "currency": "GBP", "timestamp": _ts(d, 12, 0),
                 "impact_level": "high", "actual": None, "forecast": None, "previous": None, "unit": "%"})

    out.sort(key=lambda e: e["timestamp"])
    return out
