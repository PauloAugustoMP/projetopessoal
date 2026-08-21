"""brapi.dev adapter implementing the market_data_provider port.

Contract-tested against recorded JSON fixtures (docs/testing-strategy.md §3) —
never against the live API. Provider failures surface as
MarketDataUnavailableError, a known error the application layer handles.
"""

import logging
from datetime import datetime, timezone

import httpx

from backend.ports.market_data_provider import (
    HistoricalPrice,
    MarketDataUnavailableError,
    Quote,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://brapi.dev/api"
TIMEOUT_SECONDS = 10.0


class BrapiProvider:
    def __init__(self, api_token: str = "", base_url: str = BASE_URL, client: httpx.Client | None = None) -> None:
        self._token = api_token
        self._base_url = base_url
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _get(self, path: str, params: dict) -> dict:
        if self._token:
            params = {**params, "token": self._token}
        try:
            response = self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.HTTPError as error:
            raise MarketDataUnavailableError(f"brapi.dev request failed: {error}") from error
        if response.status_code == 429:
            raise MarketDataUnavailableError("brapi.dev rate limit reached.")
        if response.status_code >= 400:
            raise MarketDataUnavailableError(
                f"brapi.dev returned HTTP {response.status_code} for {path}."
            )
        try:
            return response.json()
        except ValueError as error:
            raise MarketDataUnavailableError("brapi.dev returned a non-JSON response.") from error

    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        if not tickers:
            return {}
        payload = self._get(f"/quote/{','.join(sorted(tickers))}", params={})
        quotes: dict[str, Quote] = {}
        for result in payload.get("results", []):
            ticker = result.get("symbol")
            price = result.get("regularMarketPrice")
            if not ticker or price is None:
                # Unknown tickers come back with an error entry — just skip them.
                continue
            quotes[ticker] = Quote(
                ticker=ticker,
                price=float(price),
                logo_url=result.get("logourl") or None,
                change_percent=(
                    float(result["regularMarketChangePercent"])
                    if result.get("regularMarketChangePercent") is not None
                    else None
                ),
            )
        return quotes

    def get_price_history(self, ticker: str, from_date: str, to_date: str) -> list[HistoricalPrice]:
        payload = self._get(
            f"/quote/{ticker}", params={"range": "1y", "interval": "1d"}
        )
        results = payload.get("results", [])
        if not results:
            return []
        prices: list[HistoricalPrice] = []
        for point in results[0].get("historicalDataPrice", []):
            close = point.get("close")
            timestamp = point.get("date")
            if close is None or timestamp is None:
                continue
            day = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
            if from_date <= day <= to_date:
                prices.append(HistoricalPrice(date=day, price=float(close)))
        prices.sort(key=lambda p: p.date)
        return prices


def is_b3_market_hours(now: datetime | None = None) -> bool:
    """B3 trades 10:00–17:00 Brasília time, weekdays (docs/architecture.md §4.1)."""
    from zoneinfo import ZoneInfo

    current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Sao_Paulo"))
    if current.weekday() >= 5:
        return False
    return 10 <= current.hour < 17


def today_isoformat() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
