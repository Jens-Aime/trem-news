"""
Built-in economic calendar generator — comprehensive G10 coverage.

Covers all major central bank decisions and data releases for USD, EUR, GBP,
JPY, CAD, AUD, NZD, CHF. Dates are exact for central bank meetings and
calculated from known release patterns for recurring data.
"""

from datetime import date, datetime, timedelta, timezone

# ══════════════════════════════════════════════════════════════════════════════
# KNOWN CENTRAL BANK MEETING DATES (exact, published in advance)
# ══════════════════════════════════════════════════════════════════════════════

_FOMC = [
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-10",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]
_FOMC_MINUTES = [
    "2025-02-19", "2025-04-09", "2025-05-28", "2025-07-09",
    "2025-08-20", "2025-10-08", "2025-11-19", "2026-01-07",
    "2026-02-18", "2026-04-08", "2026-05-20", "2026-06-24",
]
_ECB = [
    "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05",
    "2025-07-24", "2025-09-11", "2025-10-30", "2025-12-18",
    "2026-01-22", "2026-03-12", "2026-04-30", "2026-06-04",
    "2026-07-16", "2026-09-10", "2026-10-22", "2026-12-03",
]
_ECB_MINUTES = [
    "2025-02-27", "2025-04-03", "2025-05-15", "2025-07-03",
    "2025-08-21", "2025-10-09", "2025-11-27", "2026-01-15",
]
_BOE = [
    "2025-02-06", "2025-03-20", "2025-05-08", "2025-06-19",
    "2025-08-07", "2025-09-18", "2025-11-06", "2025-12-18",
    "2026-02-05", "2026-03-19", "2026-05-07", "2026-06-18",
    "2026-08-06", "2026-09-17", "2026-11-05", "2026-12-17",
]
_BOJ = [
    "2025-01-24", "2025-03-19", "2025-05-01", "2025-06-17",
    "2025-07-31", "2025-09-22", "2025-10-29", "2025-12-19",
    "2026-01-23", "2026-03-18", "2026-04-30", "2026-06-16",
    "2026-07-30", "2026-09-17", "2026-10-29", "2026-12-18",
]
_RBA = [
    "2025-02-18", "2025-04-01", "2025-05-20", "2025-07-08",
    "2025-08-05", "2025-09-30", "2025-11-04", "2025-12-09",
    "2026-02-17", "2026-04-07", "2026-05-19", "2026-07-07",
    "2026-08-04", "2026-09-29", "2026-11-03", "2026-12-08",
]
_RBNZ = [
    "2025-02-19", "2025-04-09", "2025-05-28", "2025-07-09",
    "2025-08-27", "2025-10-08", "2025-11-19",
    "2026-02-25", "2026-04-08", "2026-05-27", "2026-07-08",
    "2026-08-26", "2026-10-07", "2026-11-18",
]
_BOC = [
    "2025-01-29", "2025-03-12", "2025-04-16", "2025-06-04",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-04", "2026-04-15", "2026-06-03",
    "2026-07-15", "2026-09-09", "2026-10-21", "2026-12-09",
]
_SNB = [
    "2025-03-20", "2025-06-19", "2025-09-25", "2025-12-11",
    "2026-03-19", "2026-06-18", "2026-09-24", "2026-12-10",
]

# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR ARITHMETIC
# ══════════════════════════════════════════════════════════════════════════════

def _first_weekday(y: int, m: int, wd: int) -> date:
    d = date(y, m, 1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


def _nth_weekday(y: int, m: int, wd: int, n: int) -> date:
    return _first_weekday(y, m, wd) + timedelta(weeks=n - 1)


def _last_weekday(y: int, m: int, wd: int) -> date:
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() != wd:
        d -= timedelta(days=1)
    return d


def _nth_bizday(y: int, m: int, n: int) -> date:
    d, count = date(y, m, 1), 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)


def _ts(d: date, h: int, mi: int = 0) -> str:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=timezone.utc).isoformat()


def _months_in_range(from_d: date, to_d: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = from_d.year, from_d.month
    while date(y, m, 1) <= to_d:
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


# ══════════════════════════════════════════════════════════════════════════════
# REFERENCE BASELINES  (previous, forecast) — mid-2025 reference values
# ══════════════════════════════════════════════════════════════════════════════

_BASELINES: dict[str, tuple[object, object]] = {
    # ── USA ─────────────────────────────────────────────────────────────────
    "Nonfarm Payrolls":                         (139,    160),
    "Unemployment Rate":                        (4.2,    4.2),
    "Average Hourly Earnings (MoM)":            (0.2,    0.3),
    "ADP Non-Farm Employment Change":           (152,    155),
    "JOLTS Job Openings":                       (7.19,   7.30),
    "Initial Jobless Claims":                   (229,    225),
    "Continuing Jobless Claims":                (1881,   1870),
    "CPI (YoY)":                                (2.3,    2.4),
    "CPI (MoM)":                                (0.2,    0.3),
    "Core CPI (YoY)":                           (2.8,    2.7),
    "PPI (MoM)":                                (0.2,    0.2),
    "Core PPI (MoM)":                           (0.4,    0.3),
    "Retail Sales (MoM)":                       (-0.9,   0.3),
    "Retail Sales ex-Autos (MoM)":              (-0.5,   0.3),
    "Core PCE Price Index (YoY)":               (2.6,    2.6),
    "Personal Income (MoM)":                    (0.5,    0.4),
    "Personal Spending (MoM)":                  (0.7,    0.3),
    "ISM Manufacturing PMI":                    (48.7,   49.5),
    "ISM Services PMI":                         (51.6,   51.5),
    "S&P Global Manufacturing PMI (Flash)":     (50.2,   50.4),
    "S&P Global Services PMI (Flash)":          (52.3,   52.5),
    "Consumer Confidence (CB)":                 (98.3,   100.0),
    "UoM Consumer Sentiment (Prelim)":          (52.2,   54.0),
    "Philadelphia Fed Manufacturing Index":     (-26.4,  -15.0),
    "Empire State Manufacturing Index":         (-20.1,  -15.0),
    "Durable Goods Orders (MoM)":               (-6.3,   7.8),
    "Core Durable Goods Orders (MoM)":          (-0.2,   0.3),
    "Housing Starts":                           (1.361,  1.370),
    "Building Permits":                         (1.419,  1.400),
    "Existing Home Sales":                      (3.98,   4.10),
    "New Home Sales":                           (681,    700),
    "Trade Balance":                            (-140.5, -135.0),
    "GDP Advance Estimate (Q1)":                (2.4,    -0.3),
    "GDP Advance Estimate (Q2)":                (-0.3,   1.8),
    "GDP Advance Estimate (Q3)":                (1.8,    2.2),
    "GDP Advance Estimate (Q4)":                (2.4,    2.1),
    "GDP Second Estimate (Q1)":                 (-0.3,   -0.3),
    "GDP Second Estimate (Q2)":                 (1.8,    1.8),
    "GDP Second Estimate (Q3)":                 (2.2,    2.2),
    "GDP Second Estimate (Q4)":                 (2.1,    2.4),
    "Current Account":                          (-303.9, -310.0),
    "FOMC Interest Rate Decision":              (4.50,   4.50),
    "FOMC Meeting Minutes":                     (None,   None),
    # ── Eurozone / Germany ───────────────────────────────────────────────────
    "Eurozone CPI Flash Estimate (YoY)":        (2.2,    2.3),
    "Eurozone Core CPI Flash Estimate (YoY)":   (2.7,    2.8),
    "Eurozone Unemployment Rate":               (6.2,    6.2),
    "Eurozone Manufacturing PMI (Flash)":       (49.4,   49.6),
    "Eurozone Services PMI (Flash)":            (50.1,   50.3),
    "German Manufacturing PMI (Flash)":         (48.4,   48.8),
    "German Services PMI (Flash)":              (47.2,   47.5),
    "German ZEW Economic Sentiment":            (-14.1,  -12.0),
    "German IFO Business Climate":              (86.9,   87.5),
    "German CPI (YoY) Prelim":                  (2.2,    2.3),
    "German Retail Sales (MoM)":                (-0.4,   0.3),
    "German Unemployment Change":               (-2,     -5),
    "Eurozone GDP Flash Estimate (Q4)":         (0.1,    0.1),
    "Eurozone GDP Flash Estimate (Q1)":         (0.4,    0.3),
    "Eurozone GDP Flash Estimate (Q2)":         (0.3,    0.3),
    "Eurozone GDP Flash Estimate (Q3)":         (0.3,    0.4),
    "Eurozone Retail Sales (MoM)":              (1.5,    0.3),
    "Eurozone Trade Balance":                   (36.1,   34.0),
    "ECB Interest Rate Decision":               (2.25,   2.25),
    "ECB Monetary Policy Meeting Accounts":     (None,   None),
    # ── UK ───────────────────────────────────────────────────────────────────
    "UK CPI (YoY)":                             (3.5,    3.3),
    "UK CPI (MoM)":                             (0.3,    0.4),
    "UK Core CPI (YoY)":                        (3.8,    3.7),
    "UK Manufacturing PMI (Flash)":             (45.4,   45.8),
    "UK Services PMI (Flash)":                  (50.0,   50.3),
    "UK Retail Sales (MoM)":                    (0.0,    0.2),
    "UK Unemployment Rate":                     (4.5,    4.5),
    "UK Average Earnings Index (3M/YoY)":       (5.6,    5.5),
    "UK GDP (MoM)":                             (0.5,    0.1),
    "UK GDP (Q4) Preliminary":                  (0.1,    0.1),
    "UK GDP (Q1) Preliminary":                  (0.7,    0.3),
    "UK GDP (Q2) Preliminary":                  (0.3,    0.3),
    "UK GDP (Q3) Preliminary":                  (0.3,    0.3),
    "UK Trade Balance":                         (-7.9,   -8.0),
    "BOE Interest Rate Decision":               (4.25,   4.25),
    # ── Japan ────────────────────────────────────────────────────────────────
    "Japan CPI (YoY)":                          (3.5,    3.4),
    "Japan Core CPI (YoY)":                     (3.0,    3.1),
    "Japan Manufacturing PMI (Flash)":          (49.0,   49.3),
    "Japan Industrial Production (MoM)":        (0.2,   -0.4),
    "Japan Retail Sales (YoY)":                 (3.5,    3.3),
    "Japan Unemployment Rate":                  (2.5,    2.5),
    "Japan Trade Balance":                      (-115.8, -200.0),
    "Tankan Large Manufacturers Index (Q4)":    (14,     12),
    "Tankan Large Manufacturers Index (Q1)":    (12,     11),
    "Tankan Large Manufacturers Index (Q2)":    (11,     10),
    "Tankan Large Manufacturers Index (Q3)":    (10,     10),
    "Japan GDP (Q4) Preliminary":               (-0.4,  -0.4),
    "Japan GDP (Q1) Preliminary":               (-0.7,  -0.4),
    "Japan GDP (Q2) Preliminary":               (-0.4,   0.3),
    "Japan GDP (Q3) Preliminary":               (0.3,    0.4),
    "Japan Current Account":                    (3.41,   3.20),
    "BOJ Interest Rate Decision":               (0.50,   0.50),
    # ── Canada ───────────────────────────────────────────────────────────────
    "Canada Employment Change":                 (-33,    10),
    "Canada Unemployment Rate":                 (6.9,    6.9),
    "Canada CPI (YoY)":                         (1.7,    1.8),
    "Canada CPI (MoM)":                         (-0.1,   0.4),
    "Canada Retail Sales (MoM)":                (-0.4,   0.3),
    "Canada Trade Balance":                     (-0.7,  -0.5),
    "Canada GDP (MoM)":                         (0.3,    0.3),
    "Canada Manufacturing PMI":                 (45.3,   46.0),
    "BOC Interest Rate Decision":               (2.75,   2.75),
    # ── Australia ────────────────────────────────────────────────────────────
    "Australia Employment Change":              (38.5,   22.0),
    "Australia Unemployment Rate":              (4.1,    4.2),
    "Australia CPI (QoQ) (Q4)":                (0.2,    0.3),
    "Australia CPI (QoQ) (Q1)":                (0.2,    0.7),
    "Australia CPI (QoQ) (Q2)":                (0.7,    0.7),
    "Australia CPI (QoQ) (Q3)":                (0.7,    0.7),
    "Australia Retail Sales (MoM)":             (0.3,    0.4),
    "Australia Trade Balance":                  (6.9,    6.5),
    "Australia GDP (QoQ) (Q4)":                (0.6,    0.5),
    "Australia GDP (QoQ) (Q1)":                (0.6,    0.6),
    "Australia GDP (QoQ) (Q2)":                (0.6,    0.6),
    "Australia GDP (QoQ) (Q3)":                (0.6,    0.6),
    "Australia Manufacturing PMI":              (51.7,   51.5),
    "RBA Interest Rate Decision":               (4.10,   4.10),
    # ── New Zealand ──────────────────────────────────────────────────────────
    "New Zealand CPI (QoQ) (Q4)":              (0.5,    0.5),
    "New Zealand CPI (QoQ) (Q1)":              (0.5,    0.6),
    "New Zealand CPI (QoQ) (Q2)":              (0.6,    0.6),
    "New Zealand CPI (QoQ) (Q3)":              (0.6,    0.6),
    "New Zealand Employment Change (Q4)":       (0.1,   -0.2),
    "New Zealand Employment Change (Q1)":       (-0.2,  -0.3),
    "New Zealand Employment Change (Q2)":       (-0.3,  -0.1),
    "New Zealand Employment Change (Q3)":       (-0.1,   0.1),
    "New Zealand Unemployment Rate (Q4)":       (5.1,    5.2),
    "New Zealand Unemployment Rate (Q1)":       (5.1,    5.3),
    "New Zealand Unemployment Rate (Q2)":       (5.3,    5.4),
    "New Zealand Unemployment Rate (Q3)":       (5.4,    5.3),
    "New Zealand Trade Balance":                (-1.4,  -1.5),
    "New Zealand Business Confidence (ANZ)":    (49.3,   50.0),
    "RBNZ Interest Rate Decision":              (3.50,   3.50),
    # ── Switzerland ──────────────────────────────────────────────────────────
    "Switzerland CPI (YoY)":                    (0.0,    0.0),
    "Switzerland Trade Balance":                (5.2,    5.0),
    "Switzerland GDP (QoQ) (Q4)":              (0.4,    0.3),
    "Switzerland GDP (QoQ) (Q1)":              (0.3,    0.3),
    "Switzerland GDP (QoQ) (Q2)":              (0.3,    0.3),
    "Switzerland GDP (QoQ) (Q3)":              (0.3,    0.3),
    "Switzerland KOF Leading Indicators":       (101.5,  101.0),
    "SNB Interest Rate Decision":               (0.25,   0.25),
}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_events(from_date: date, to_date: date) -> list[dict]:
    """
    Return synthetic economic events in [from_date, to_date], sorted ascending.
    Schema matches Finnhub-normalised events so no pipeline changes are needed.
    """
    out: list[dict] = []
    seen: set[str] = set()

    def add(ev: dict) -> None:
        if ev["event_id"] not in seen:
            seen.add(ev["event_id"])
            out.append(ev)

    def in_range(d: date) -> bool:
        return from_date <= d <= to_date

    def ev(eid: str, name: str, country: str, ccy: str,
           d: date, h: int, mi: int, impact: str, unit: str = "") -> None:
        if in_range(d):
            _prev, _fcast = _BASELINES.get(name, (None, None))
            add({
                "event_id": eid, "event_name": name,
                "country": country, "currency": ccy,
                "timestamp": _ts(d, h, mi),
                "impact_level": impact,
                "actual": None, "forecast": _fcast, "previous": _prev, "unit": unit,
            })

    for y, m in _months_in_range(from_date, to_date):

        # ── USA ────────────────────────────────────────────────────────────────

        # NFP + Unemployment Rate + Average Hourly Earnings — first Friday, 13:30 UTC
        nfp = _first_weekday(y, m, 4)
        ev(f"gen-nfp-{y}-{m:02d}",    "Nonfarm Payrolls",                  "US", "USD", nfp, 13, 30, "high",   "K")
        ev(f"gen-ue-{y}-{m:02d}",     "Unemployment Rate",                 "US", "USD", nfp, 13, 30, "high",   "%")
        ev(f"gen-ahe-{y}-{m:02d}",    "Average Hourly Earnings (MoM)",     "US", "USD", nfp, 13, 30, "high",   "%")

        # ADP — Wednesday before NFP
        adp = nfp - timedelta(days=2)
        while adp.weekday() != 2:
            adp -= timedelta(days=1)
        ev(f"gen-adp-{y}-{m:02d}",    "ADP Non-Farm Employment Change",    "US", "USD", adp, 13, 15, "high",   "K")

        # JOLTS — 2nd Tuesday, 15:00 UTC
        jolts = _nth_weekday(y, m, 1, 2)
        ev(f"gen-jolts-{y}-{m:02d}",  "JOLTS Job Openings",                "US", "USD", jolts, 15, 0, "medium", "M")

        # Initial + Continuing Claims — every Thursday, 13:30 UTC
        thu = _first_weekday(y, m, 3)
        while thu.month == m:
            ev(f"gen-claims-{thu}",      "Initial Jobless Claims",          "US", "USD", thu, 13, 30, "medium", "K")
            ev(f"gen-cont-{thu}",        "Continuing Jobless Claims",       "US", "USD", thu, 13, 30, "low",    "K")
            thu += timedelta(weeks=1)

        # CPI — 2nd Wednesday, 13:30 UTC
        cpi = _nth_weekday(y, m, 2, 2)
        ev(f"gen-cpi-{y}-{m:02d}",    "CPI (YoY)",                         "US", "USD", cpi, 13, 30, "high",   "%")
        ev(f"gen-cpi-mom-{y}-{m:02d}","CPI (MoM)",                         "US", "USD", cpi, 13, 30, "high",   "%")
        ev(f"gen-cpi-core-{y}-{m:02d}","Core CPI (YoY)",                   "US", "USD", cpi, 13, 30, "high",   "%")

        # PPI — Thursday after CPI
        ppi = cpi + timedelta(days=1)
        while ppi.weekday() != 3:
            ppi += timedelta(days=1)
        ev(f"gen-ppi-{y}-{m:02d}",    "PPI (MoM)",                         "US", "USD", ppi, 13, 30, "medium", "%")
        ev(f"gen-ppi-core-{y}-{m:02d}","Core PPI (MoM)",                   "US", "USD", ppi, 13, 30, "medium", "%")

        # Retail Sales — 2nd Thursday, 13:30 UTC
        rs = _nth_weekday(y, m, 3, 2)
        ev(f"gen-rs-{y}-{m:02d}",     "Retail Sales (MoM)",                "US", "USD", rs, 13, 30, "high",   "%")
        ev(f"gen-rs-ex-{y}-{m:02d}",  "Retail Sales ex-Autos (MoM)",       "US", "USD", rs, 13, 30, "medium", "%")

        # Core PCE + Personal Income/Spending — last Friday, 13:30 UTC
        pce_d = _last_weekday(y, m, 4)
        ev(f"gen-pce-{y}-{m:02d}",    "Core PCE Price Index (YoY)",        "US", "USD", pce_d, 13, 30, "high",   "%")
        ev(f"gen-pce-mom-{y}-{m:02d}","Personal Income (MoM)",             "US", "USD", pce_d, 13, 30, "medium", "%")
        ev(f"gen-pce-sp-{y}-{m:02d}", "Personal Spending (MoM)",           "US", "USD", pce_d, 13, 30, "medium", "%")

        # ISM Manufacturing — 1st business day, 15:00 UTC
        ism_mfg = _nth_bizday(y, m, 1)
        ev(f"gen-ism-mfg-{y}-{m:02d}","ISM Manufacturing PMI",             "US", "USD", ism_mfg, 15, 0, "high")

        # ISM Services — 3rd business day, 15:00 UTC
        ism_svc = _nth_bizday(y, m, 3)
        ev(f"gen-ism-svc-{y}-{m:02d}","ISM Services PMI",                  "US", "USD", ism_svc, 15, 0, "high")

        # S&P Global Flash PMIs — 3rd Friday, 14:45 UTC
        sp_pmi = _nth_weekday(y, m, 4, 3)
        ev(f"gen-sp-mfg-{y}-{m:02d}", "S&P Global Manufacturing PMI (Flash)","US","USD", sp_pmi, 14, 45, "medium")
        ev(f"gen-sp-svc-{y}-{m:02d}", "S&P Global Services PMI (Flash)",   "US", "USD", sp_pmi, 14, 45, "medium")

        # Consumer Confidence (Conference Board) — last Tuesday, 15:00 UTC
        cc = _last_weekday(y, m, 1)
        ev(f"gen-cc-{y}-{m:02d}",     "Consumer Confidence (CB)",          "US", "USD", cc, 15, 0, "high")

        # University of Michigan Sentiment — 2nd Friday (prelim), 15:00 UTC
        umich = _nth_weekday(y, m, 4, 2)
        ev(f"gen-umich-{y}-{m:02d}",  "UoM Consumer Sentiment (Prelim)",   "US", "USD", umich, 15, 0, "medium")

        # Philadelphia Fed — 3rd Thursday, 13:30 UTC
        philly = _nth_weekday(y, m, 3, 3)
        ev(f"gen-philly-{y}-{m:02d}", "Philadelphia Fed Manufacturing Index","US","USD", philly, 13, 30, "medium")

        # Empire State — ~15th of month (next business day), 13:30 UTC
        empire_d = date(y, m, 15)
        while empire_d.weekday() >= 5:
            empire_d += timedelta(days=1)
        ev(f"gen-empire-{y}-{m:02d}", "Empire State Manufacturing Index",  "US", "USD", empire_d, 13, 30, "medium")

        # Durable Goods — 4th Thursday, 13:30 UTC
        dg = _nth_weekday(y, m, 3, 4)
        ev(f"gen-dg-{y}-{m:02d}",     "Durable Goods Orders (MoM)",        "US", "USD", dg, 13, 30, "medium", "%")
        ev(f"gen-dg-ex-{y}-{m:02d}",  "Core Durable Goods Orders (MoM)",   "US", "USD", dg, 13, 30, "medium", "%")

        # Housing Starts + Building Permits — 3rd Wednesday, 13:30 UTC
        housing = _nth_weekday(y, m, 2, 3)
        ev(f"gen-hs-{y}-{m:02d}",     "Housing Starts",                    "US", "USD", housing, 13, 30, "medium", "M")
        ev(f"gen-bp-{y}-{m:02d}",     "Building Permits",                  "US", "USD", housing, 13, 30, "medium", "M")

        # Existing Home Sales — 4th Wednesday, 15:00 UTC
        ehs = _nth_weekday(y, m, 2, 4)
        ev(f"gen-ehs-{y}-{m:02d}",    "Existing Home Sales",               "US", "USD", ehs, 15, 0, "medium", "M")

        # New Home Sales — last Tuesday, 15:00 UTC
        nhs = _last_weekday(y, m, 1)
        ev(f"gen-nhs-{y}-{m:02d}",    "New Home Sales",                    "US", "USD", nhs, 15, 0, "medium", "K")

        # Trade Balance — 1st Wednesday, 13:30 UTC
        tb_us = _nth_weekday(y, m, 2, 1)
        ev(f"gen-tb-us-{y}-{m:02d}",  "Trade Balance",                     "US", "USD", tb_us, 13, 30, "medium", "B")

        # GDP Advance — Q1→Apr, Q2→Jul, Q3→Oct, Q4→Jan (Thursday ≥ 25th)
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            gdp_d = date(y, m, 25)
            while gdp_d.weekday() != 3:
                gdp_d += timedelta(days=1)
            ev(f"gen-gdp-{y}-{m:02d}", f"GDP Advance Estimate ({quarter})", "US", "USD", gdp_d, 13, 30, "high", "%")

        # GDP Second Estimate — following month
        if m in (2, 5, 8, 11):
            quarter = {2: "Q4", 5: "Q1", 8: "Q2", 11: "Q3"}[m]
            gdp2 = date(y, m, 27)
            while gdp2.weekday() != 3:
                gdp2 += timedelta(days=1)
            ev(f"gen-gdp2-{y}-{m:02d}", f"GDP Second Estimate ({quarter})", "US", "USD", gdp2, 13, 30, "high", "%")

        # Current Account — quarterly (Q1→Jun, Q2→Sep, Q3→Dec, Q4→Mar)
        if m in (3, 6, 9, 12):
            ca_d = _nth_weekday(y, m, 3, 4)
            ev(f"gen-ca-us-{y}-{m:02d}", "Current Account",                "US", "USD", ca_d, 13, 30, "medium", "B")

        # ── EUROZONE / GERMANY ────────────────────────────────────────────────

        # Eurozone CPI Flash — last Thursday of month, 10:00 UTC
        ez_cpi = _last_weekday(y, m, 3)
        ev(f"gen-ez-cpi-{y}-{m:02d}",     "Eurozone CPI Flash Estimate (YoY)",      "EU", "EUR", ez_cpi, 10, 0, "high",   "%")
        ev(f"gen-ez-cpi-core-{y}-{m:02d}","Eurozone Core CPI Flash Estimate (YoY)", "EU", "EUR", ez_cpi, 10, 0, "high",   "%")

        # Eurozone Unemployment — ~25th, 09:00 UTC
        ez_ue = date(y, m, 25)
        while ez_ue.weekday() >= 5:
            ez_ue += timedelta(days=1)
        ev(f"gen-ez-ue-{y}-{m:02d}",      "Eurozone Unemployment Rate",             "EU", "EUR", ez_ue, 9, 0, "medium", "%")

        # Eurozone Flash PMIs — 3rd Friday, 09:00 UTC
        ez_pmi = _nth_weekday(y, m, 4, 3)
        ev(f"gen-ez-pmi-mfg-{y}-{m:02d}", "Eurozone Manufacturing PMI (Flash)",     "EU", "EUR", ez_pmi, 9, 0, "high")
        ev(f"gen-ez-pmi-svc-{y}-{m:02d}", "Eurozone Services PMI (Flash)",          "EU", "EUR", ez_pmi, 9, 0, "high")
        ev(f"gen-de-pmi-mfg-{y}-{m:02d}", "German Manufacturing PMI (Flash)",       "DE", "EUR", ez_pmi, 8, 30, "high")
        ev(f"gen-de-pmi-svc-{y}-{m:02d}", "German Services PMI (Flash)",            "DE", "EUR", ez_pmi, 8, 30, "medium")

        # German ZEW — 2nd Tuesday, 10:00 UTC
        zew = _nth_weekday(y, m, 1, 2)
        ev(f"gen-zew-{y}-{m:02d}",        "German ZEW Economic Sentiment",          "DE", "EUR", zew, 10, 0, "high")

        # German IFO — 4th business day, 09:00 UTC
        ifo_d = _nth_bizday(y, m, 4)
        ev(f"gen-ifo-{y}-{m:02d}",        "German IFO Business Climate",            "DE", "EUR", ifo_d, 9, 0, "high")

        # German CPI Prelim — last Thursday, 13:00 UTC
        de_cpi = _last_weekday(y, m, 3)
        ev(f"gen-de-cpi-{y}-{m:02d}",     "German CPI (YoY) Prelim",                "DE", "EUR", de_cpi, 13, 0, "high",   "%")

        # German Retail Sales — 2nd Thursday, 07:00 UTC
        de_rs = _nth_weekday(y, m, 3, 2)
        ev(f"gen-de-rs-{y}-{m:02d}",      "German Retail Sales (MoM)",              "DE", "EUR", de_rs, 7, 0, "medium", "%")

        # German Unemployment — last Wednesday, 08:55 UTC
        de_ue = _last_weekday(y, m, 2)
        ev(f"gen-de-ue-{y}-{m:02d}",      "German Unemployment Change",             "DE", "EUR", de_ue, 8, 55, "medium", "K")

        # Eurozone Flash GDP — quarterly
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            ez_gdp = date(y, m, 25)
            while ez_gdp.weekday() >= 5:
                ez_gdp += timedelta(days=1)
            ev(f"gen-ez-gdp-{y}-{m:02d}", f"Eurozone GDP Flash Estimate ({quarter})", "EU", "EUR", ez_gdp, 10, 0, "high", "%")

        # Eurozone Retail Sales — 2nd Wednesday, 10:00 UTC
        ez_rs = _nth_weekday(y, m, 2, 2)
        ev(f"gen-ez-rs-{y}-{m:02d}",      "Eurozone Retail Sales (MoM)",            "EU", "EUR", ez_rs, 10, 0, "medium", "%")

        # Eurozone Trade Balance — 3rd Tuesday, 10:00 UTC
        ez_tb = _nth_weekday(y, m, 1, 3)
        ev(f"gen-ez-tb-{y}-{m:02d}",      "Eurozone Trade Balance",                 "EU", "EUR", ez_tb, 10, 0, "low",    "B")

        # ── UK ────────────────────────────────────────────────────────────────

        # UK CPI — 3rd Wednesday, 07:00 UTC
        uk_cpi = _nth_weekday(y, m, 2, 3)
        ev(f"gen-uk-cpi-{y}-{m:02d}",     "UK CPI (YoY)",                           "GB", "GBP", uk_cpi, 7, 0, "high",   "%")
        ev(f"gen-uk-cpi-mom-{y}-{m:02d}", "UK CPI (MoM)",                           "GB", "GBP", uk_cpi, 7, 0, "high",   "%")
        ev(f"gen-uk-cpi-core-{y}-{m:02d}","UK Core CPI (YoY)",                      "GB", "GBP", uk_cpi, 7, 0, "high",   "%")

        # UK Flash PMIs — 3rd Friday, 09:30 UTC
        uk_pmi = _nth_weekday(y, m, 4, 3)
        ev(f"gen-uk-pmi-mfg-{y}-{m:02d}", "UK Manufacturing PMI (Flash)",           "GB", "GBP", uk_pmi, 9, 30, "medium")
        ev(f"gen-uk-pmi-svc-{y}-{m:02d}", "UK Services PMI (Flash)",                "GB", "GBP", uk_pmi, 9, 30, "high")

        # UK Retail Sales — 4th Friday, 07:00 UTC
        uk_rs = _nth_weekday(y, m, 4, 4)
        ev(f"gen-uk-rs-{y}-{m:02d}",      "UK Retail Sales (MoM)",                  "GB", "GBP", uk_rs, 7, 0, "high",   "%")

        # UK Labour Market (Unemployment + Earnings) — 3rd Tuesday, 07:00 UTC
        uk_ue = _nth_weekday(y, m, 1, 3)
        ev(f"gen-uk-ue-{y}-{m:02d}",      "UK Unemployment Rate",                   "GB", "GBP", uk_ue, 7, 0, "medium", "%")
        ev(f"gen-uk-earn-{y}-{m:02d}",    "UK Average Earnings Index (3M/YoY)",     "GB", "GBP", uk_ue, 7, 0, "high",   "%")

        # UK GDP Monthly — last Wednesday, 07:00 UTC
        uk_gdp_m = _last_weekday(y, m, 2)
        ev(f"gen-uk-gdp-{y}-{m:02d}",     "UK GDP (MoM)",                           "GB", "GBP", uk_gdp_m, 7, 0, "high",   "%")

        # UK Quarterly GDP — Feb, May, Aug, Nov (preliminary)
        if m in (2, 5, 8, 11):
            quarter = {2: "Q4", 5: "Q1", 8: "Q2", 11: "Q3"}[m]
            uk_gdp_q = _nth_weekday(y, m, 4, 2)
            ev(f"gen-uk-gdp-q-{y}-{m:02d}", f"UK GDP ({quarter}) Preliminary",      "GB", "GBP", uk_gdp_q, 7, 0, "high", "%")

        # UK Trade Balance — 4th Thursday, 07:00 UTC
        uk_tb = _nth_weekday(y, m, 3, 4)
        ev(f"gen-uk-tb-{y}-{m:02d}",      "UK Trade Balance",                       "GB", "GBP", uk_tb, 7, 0, "medium", "B")

        # ── JAPAN ────────────────────────────────────────────────────────────

        # Japan CPI — 3rd Friday, 23:30 UTC (overnight in UTC, JST = UTC+9)
        jp_cpi = _nth_weekday(y, m, 4, 3)
        ev(f"gen-jp-cpi-{y}-{m:02d}",     "Japan CPI (YoY)",                        "JP", "JPY", jp_cpi, 23, 30, "high",   "%")
        ev(f"gen-jp-cpi-core-{y}-{m:02d}","Japan Core CPI (YoY)",                   "JP", "JPY", jp_cpi, 23, 30, "high",   "%")

        # Japan Flash PMI — 1st business day, 00:30 UTC
        jp_pmi = _nth_bizday(y, m, 1)
        ev(f"gen-jp-pmi-mfg-{y}-{m:02d}", "Japan Manufacturing PMI (Flash)",        "JP", "JPY", jp_pmi, 0, 30, "medium")

        # Japan Industrial Production — last Thursday, 23:50 UTC
        jp_ip = _last_weekday(y, m, 3)
        ev(f"gen-jp-ip-{y}-{m:02d}",      "Japan Industrial Production (MoM)",      "JP", "JPY", jp_ip, 23, 50, "medium", "%")

        # Japan Retail Sales — last Tuesday, 23:50 UTC
        jp_rs = _last_weekday(y, m, 1)
        ev(f"gen-jp-rs-{y}-{m:02d}",      "Japan Retail Sales (YoY)",               "JP", "JPY", jp_rs, 23, 50, "medium", "%")

        # Japan Unemployment — last Tuesday, 23:30 UTC
        ev(f"gen-jp-ue-{y}-{m:02d}",      "Japan Unemployment Rate",                "JP", "JPY", jp_rs, 23, 30, "medium", "%")

        # Japan Trade Balance — 3rd Wednesday, 23:50 UTC
        jp_tb = _nth_weekday(y, m, 2, 3)
        ev(f"gen-jp-tb-{y}-{m:02d}",      "Japan Trade Balance",                    "JP", "JPY", jp_tb, 23, 50, "medium", "T")

        # Tankan Survey — quarterly (Q4→Jan, Q1→Apr, Q2→Jul, Q3→Oct), 23:50 UTC
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            tankan_d = _nth_bizday(y, m, 1)
            ev(f"gen-tankan-{y}-{m:02d}", f"Tankan Large Manufacturers Index ({quarter})", "JP", "JPY", tankan_d, 23, 50, "high")

        # Japan GDP Preliminary — quarterly (Feb, May, Aug, Nov)
        if m in (2, 5, 8, 11):
            quarter = {2: "Q4", 5: "Q1", 8: "Q2", 11: "Q3"}[m]
            jp_gdp = date(y, m, 15)
            while jp_gdp.weekday() >= 5:
                jp_gdp += timedelta(days=1)
            ev(f"gen-jp-gdp-{y}-{m:02d}", f"Japan GDP ({quarter}) Preliminary",     "JP", "JPY", jp_gdp, 23, 50, "high",   "%")

        # Japan Current Account — ~10th of month, 23:50 UTC
        jp_ca = date(y, m, 10)
        while jp_ca.weekday() >= 5:
            jp_ca += timedelta(days=1)
        ev(f"gen-jp-ca-{y}-{m:02d}",      "Japan Current Account",                  "JP", "JPY", jp_ca, 23, 50, "low",    "T")

        # ── CANADA ───────────────────────────────────────────────────────────

        # Canada Employment + Unemployment — 2nd Friday, 13:30 UTC
        ca_emp = _nth_weekday(y, m, 4, 2)
        ev(f"gen-ca-emp-{y}-{m:02d}",     "Canada Employment Change",               "CA", "CAD", ca_emp, 13, 30, "high",   "K")
        ev(f"gen-ca-ue-{y}-{m:02d}",      "Canada Unemployment Rate",               "CA", "CAD", ca_emp, 13, 30, "high",   "%")

        # Canada CPI — 3rd Tuesday, 13:30 UTC
        ca_cpi = _nth_weekday(y, m, 1, 3)
        ev(f"gen-ca-cpi-{y}-{m:02d}",     "Canada CPI (YoY)",                       "CA", "CAD", ca_cpi, 13, 30, "high",   "%")
        ev(f"gen-ca-cpi-mom-{y}-{m:02d}", "Canada CPI (MoM)",                       "CA", "CAD", ca_cpi, 13, 30, "high",   "%")

        # Canada Retail Sales — 3rd Friday, 13:30 UTC
        ca_rs = _nth_weekday(y, m, 4, 3)
        ev(f"gen-ca-rs-{y}-{m:02d}",      "Canada Retail Sales (MoM)",              "CA", "CAD", ca_rs, 13, 30, "medium", "%")

        # Canada Trade Balance — 3rd Wednesday, 13:30 UTC
        ca_tb = _nth_weekday(y, m, 2, 3)
        ev(f"gen-ca-tb-{y}-{m:02d}",      "Canada Trade Balance",                   "CA", "CAD", ca_tb, 13, 30, "medium", "B")

        # Canada GDP Monthly — last Wednesday, 13:30 UTC
        ca_gdp = _last_weekday(y, m, 2)
        ev(f"gen-ca-gdp-{y}-{m:02d}",     "Canada GDP (MoM)",                       "CA", "CAD", ca_gdp, 13, 30, "medium", "%")

        # Canada Manufacturing PMI — 1st business day, 14:30 UTC
        ca_pmi = _nth_bizday(y, m, 1)
        ev(f"gen-ca-pmi-{y}-{m:02d}",     "Canada Manufacturing PMI",               "CA", "CAD", ca_pmi, 14, 30, "medium")

        # ── AUSTRALIA ────────────────────────────────────────────────────────

        # Australia Employment — 2nd Thursday, 01:30 UTC
        au_emp = _nth_weekday(y, m, 3, 2)
        ev(f"gen-au-emp-{y}-{m:02d}",     "Australia Employment Change",            "AU", "AUD", au_emp, 1, 30, "high",   "K")
        ev(f"gen-au-ue-{y}-{m:02d}",      "Australia Unemployment Rate",            "AU", "AUD", au_emp, 1, 30, "high",   "%")

        # Australia CPI — quarterly (Q1→Apr, Q2→Jul, Q3→Oct, Q4→Jan)
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            au_cpi = _nth_weekday(y, m, 2, 4)
            ev(f"gen-au-cpi-{y}-{m:02d}", f"Australia CPI (QoQ) ({quarter})",       "AU", "AUD", au_cpi, 1, 30, "high",   "%")

        # Australia Retail Sales — 1st Wednesday, 01:30 UTC
        au_rs = _nth_weekday(y, m, 2, 1)
        ev(f"gen-au-rs-{y}-{m:02d}",      "Australia Retail Sales (MoM)",           "AU", "AUD", au_rs, 1, 30, "medium", "%")

        # Australia Trade Balance — 2nd Thursday + 1 week, 01:30 UTC
        au_tb = au_emp + timedelta(weeks=1)
        ev(f"gen-au-tb-{y}-{m:02d}",      "Australia Trade Balance",                "AU", "AUD", au_tb, 1, 30, "medium", "B")

        # Australia GDP — quarterly (Mar, Jun, Sep, Dec)
        if m in (3, 6, 9, 12):
            quarter = {3: "Q4", 6: "Q1", 9: "Q2", 12: "Q3"}[m]
            au_gdp = _nth_weekday(y, m, 2, 2)
            ev(f"gen-au-gdp-{y}-{m:02d}", f"Australia GDP (QoQ) ({quarter})",       "AU", "AUD", au_gdp, 1, 30, "high",   "%")

        # Australia Manufacturing PMI — 1st business day, 23:00 UTC (prev day)
        au_pmi = _nth_bizday(y, m, 1)
        ev(f"gen-au-pmi-{y}-{m:02d}",     "Australia Manufacturing PMI",            "AU", "AUD", au_pmi, 23, 0, "medium")

        # ── NEW ZEALAND ───────────────────────────────────────────────────────

        # NZ CPI — quarterly (Q1→Apr, Q2→Jul, Q3→Oct, Q4→Jan)
        if m in (1, 4, 7, 10):
            quarter = {1: "Q4", 4: "Q1", 7: "Q2", 10: "Q3"}[m]
            nz_cpi = _nth_weekday(y, m, 2, 3)
            ev(f"gen-nz-cpi-{y}-{m:02d}", f"New Zealand CPI (QoQ) ({quarter})",     "NZ", "NZD", nz_cpi, 21, 45, "high",   "%")

        # NZ Employment — quarterly (Feb, May, Aug, Nov)
        if m in (2, 5, 8, 11):
            quarter = {2: "Q4", 5: "Q1", 8: "Q2", 11: "Q3"}[m]
            nz_emp = _nth_weekday(y, m, 2, 1)
            ev(f"gen-nz-emp-{y}-{m:02d}", f"New Zealand Employment Change ({quarter})","NZ","NZD", nz_emp, 21, 45, "high", "%")
            ev(f"gen-nz-ue-{y}-{m:02d}",  f"New Zealand Unemployment Rate ({quarter})","NZ","NZD", nz_emp, 21, 45, "high", "%")

        # NZ Trade Balance — monthly, last Wednesday, 21:45 UTC
        nz_tb = _last_weekday(y, m, 2)
        ev(f"gen-nz-tb-{y}-{m:02d}",      "New Zealand Trade Balance",              "NZ", "NZD", nz_tb, 21, 45, "medium", "B")

        # NZ Business Confidence — last Tuesday, 03:00 UTC
        nz_bc = _last_weekday(y, m, 1)
        ev(f"gen-nz-bc-{y}-{m:02d}",      "New Zealand Business Confidence (ANZ)",  "NZ", "NZD", nz_bc, 3, 0, "medium")

        # ── SWITZERLAND ───────────────────────────────────────────────────────

        # Swiss CPI — 1st Wednesday, 07:30 UTC
        ch_cpi = _nth_weekday(y, m, 2, 1)
        ev(f"gen-ch-cpi-{y}-{m:02d}",     "Switzerland CPI (YoY)",                  "CH", "CHF", ch_cpi, 7, 30, "medium", "%")

        # Swiss Trade Balance — last Wednesday, 07:00 UTC
        ch_tb = _last_weekday(y, m, 2)
        ev(f"gen-ch-tb-{y}-{m:02d}",      "Switzerland Trade Balance",              "CH", "CHF", ch_tb, 7, 0, "low",    "B")

        # Swiss GDP — quarterly (Mar, Jun, Sep, Dec)
        if m in (3, 6, 9, 12):
            quarter = {3: "Q4", 6: "Q1", 9: "Q2", 12: "Q3"}[m]
            ch_gdp = _nth_weekday(y, m, 3, 4)
            ev(f"gen-ch-gdp-{y}-{m:02d}", f"Switzerland GDP (QoQ) ({quarter})",     "CH", "CHF", ch_gdp, 7, 30, "medium", "%")

        # Swiss KOF Leading Indicator — last business day, 09:30 UTC
        ch_kof = _nth_bizday(y, m, 20 - date(y, m, 1).weekday())  # approx last biz
        # Use last weekday(Friday) instead as a safe approximation
        ch_kof = _last_weekday(y, m, 4)
        ev(f"gen-ch-kof-{y}-{m:02d}",     "Switzerland KOF Leading Indicators",     "CH", "CHF", ch_kof, 9, 30, "medium")

    # ── CENTRAL BANK DECISIONS (exact dates) ─────────────────────────────────

    for dt_str in _FOMC:
        d = date.fromisoformat(dt_str)
        ev(f"gen-fomc-{dt_str}",     "FOMC Interest Rate Decision",               "US", "USD", d, 19, 0,  "high",   "%")

    for dt_str in _FOMC_MINUTES:
        d = date.fromisoformat(dt_str)
        ev(f"gen-fomc-min-{dt_str}", "FOMC Meeting Minutes",                      "US", "USD", d, 19, 0,  "medium")

    for dt_str in _ECB:
        d = date.fromisoformat(dt_str)
        ev(f"gen-ecb-{dt_str}",      "ECB Interest Rate Decision",                "EU", "EUR", d, 13, 15, "high",   "%")

    for dt_str in _ECB_MINUTES:
        d = date.fromisoformat(dt_str)
        ev(f"gen-ecb-min-{dt_str}",  "ECB Monetary Policy Meeting Accounts",      "EU", "EUR", d, 12, 30, "medium")

    for dt_str in _BOE:
        d = date.fromisoformat(dt_str)
        ev(f"gen-boe-{dt_str}",      "BOE Interest Rate Decision",                "GB", "GBP", d, 12, 0,  "high",   "%")

    for dt_str in _BOJ:
        d = date.fromisoformat(dt_str)
        ev(f"gen-boj-{dt_str}",      "BOJ Interest Rate Decision",                "JP", "JPY", d, 3, 0,   "high",   "%")

    for dt_str in _RBA:
        d = date.fromisoformat(dt_str)
        ev(f"gen-rba-{dt_str}",      "RBA Interest Rate Decision",                "AU", "AUD", d, 3, 30,  "high",   "%")

    for dt_str in _RBNZ:
        d = date.fromisoformat(dt_str)
        ev(f"gen-rbnz-{dt_str}",     "RBNZ Interest Rate Decision",               "NZ", "NZD", d, 2, 0,   "high",   "%")

    for dt_str in _BOC:
        d = date.fromisoformat(dt_str)
        ev(f"gen-boc-{dt_str}",      "BOC Interest Rate Decision",                "CA", "CAD", d, 15, 0,  "high",   "%")

    for dt_str in _SNB:
        d = date.fromisoformat(dt_str)
        ev(f"gen-snb-{dt_str}",      "SNB Interest Rate Decision",                "CH", "CHF", d, 9, 30,  "high",   "%")

    out.sort(key=lambda e: e["timestamp"])
    return out
