"""
Thin async HTTP wrapper around Finnhub's Economic Calendar endpoint.

Endpoint reference:
  GET /api/v1/calendar/economic
  Params: from (YYYY-MM-DD), to (YYYY-MM-DD), token
  Docs:   https://finnhub.io/docs/api/economic-calendar
"""

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_IMPACT_MAP: dict[str, str] = {
    "1": "low",
    "2": "medium",
    "3": "high",
}


def _map_impact(raw: Any) -> str:
    return _IMPACT_MAP.get(str(raw), "unknown")


class FinnhubClient:
    """Async client for the Finnhub Economic Calendar API."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._base = self._settings.finnhub_base_url
        self._token = self._settings.finnhub_api_key
        self._timeout = self._settings.request_timeout_seconds

    async def fetch_economic_calendar(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[dict]:
        """
        Fetch economic events from Finnhub for the given date range.
        Defaults to today + 7 days when no range is specified.

        Returns raw event dicts (Finnhub schema).
        """
        today = date.today()
        from_date = from_date or today
        to_date = to_date or (today + timedelta(days=7))

        params = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": self._token,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(1, self._settings.max_retries + 1):
                try:
                    response = await client.get(
                        f"{self._base}/calendar/economic", params=params
                    )
                    response.raise_for_status()
                    data = response.json()
                    events: list[dict] = data.get("economicCalendar", [])
                    logger.info(
                        "Fetched %d events from Finnhub (%s → %s)",
                        len(events),
                        from_date,
                        to_date,
                    )
                    return self._normalize_raw(events)
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    if status in (401, 403):
                        logger.warning(
                            "Finnhub returned HTTP %s — API key not authorised. "
                            "Returning empty calendar (no retries).",
                            status,
                        )
                        return []
                    logger.warning(
                        "Attempt %d/%d failed: HTTP %s",
                        attempt,
                        self._settings.max_retries,
                        status,
                    )
                    if attempt == self._settings.max_retries:
                        raise
                except httpx.RequestError as exc:
                    logger.warning(
                        "Attempt %d/%d failed: %s", attempt, self._settings.max_retries, exc
                    )
                    if attempt == self._settings.max_retries:
                        raise
        return []

    @staticmethod
    def _normalize_raw(events: list[dict]) -> list[dict]:
        """
        Translate Finnhub field names → our internal schema field names so
        that downstream code is decoupled from the upstream API contract.
        """
        normalised = []
        for idx, raw in enumerate(events):
            normalised.append(
                {
                    "event_id": raw.get("id") or f"fh-{idx}",
                    "event_name": raw.get("event", ""),
                    "country": raw.get("country", ""),
                    "currency": raw.get("unit", "")
                    if raw.get("unit", "").isalpha() and len(raw.get("unit", "")) == 3
                    else _infer_currency(raw.get("country", "")),
                    "timestamp": raw.get("time", ""),
                    "impact_level": _map_impact(raw.get("impact")),
                    "actual": _to_float(raw.get("actual")),
                    "forecast": _to_float(raw.get("estimate")),
                    "previous": _to_float(raw.get("prev")),
                    "unit": raw.get("unit"),
                    "source": "finnhub",
                }
            )
        return normalised


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COUNTRY_CURRENCY: dict[str, str] = {
    "US": "USD",
    "GB": "GBP",
    "EU": "EUR",
    "DE": "EUR",
    "FR": "EUR",
    "JP": "JPY",
    "CA": "CAD",
    "AU": "AUD",
    "CH": "CHF",
    "CN": "CNY",
    "NZ": "NZD",
}


def _infer_currency(country_code: str) -> str:
    return _COUNTRY_CURRENCY.get(country_code.upper(), "USD")


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
