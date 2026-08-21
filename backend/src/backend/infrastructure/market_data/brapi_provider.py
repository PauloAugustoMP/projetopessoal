"""brapi.dev adapter implementing the market_data_provider port.

Uses the provider's official SDK (`brapi`), which gives typed response models
instead of hand-mapped dictionary keys — the field names are checked at the
boundary rather than silently returning None when the API changes shape.

Everything the SDK can raise is translated into MarketDataUnavailableError, the
single failure mode the rest of the app knows about (docs/testing-strategy.md
§3). The SDK accepts an injected httpx client, so contract tests keep running
against recorded JSON with no network involved.
"""

import logging
from datetime import datetime, timezone

import httpx
from brapi import APIConnectionError, APIStatusError, Brapi, BrapiError, RateLimitError

from backend.ports.market_data_provider import (
    HistoricalPrice,
    MarketDataUnavailableError,
    Quote,
)

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
HISTORY_RANGE = "1y"
HISTORY_INTERVAL = "1d"


class BrapiProvider:
    def __init__(
        self,
        api_token: str = "",
        base_url: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        options: dict = {"api_key": api_token or None, "timeout": TIMEOUT_SECONDS}
        if base_url is not None:
            options["base_url"] = base_url
        if http_client is not None:
            options["http_client"] = http_client
        self._client = Brapi(**options)

    def _translate(self, error: Exception) -> MarketDataUnavailableError:
        if isinstance(error, RateLimitError):
            return MarketDataUnavailableError("brapi.dev rate limit reached.")
        if isinstance(error, APIConnectionError):
            return MarketDataUnavailableError(f"brapi.dev unreachable: {error}")
        if isinstance(error, APIStatusError):
            return MarketDataUnavailableError(
                f"brapi.dev returned HTTP {error.status_code}."
            )
        return MarketDataUnavailableError(f"brapi.dev request failed: {error}")

    def _results(self, response: object) -> list:
        """A 200 carrying something other than the documented payload (a captive
        portal, a maintenance page) deserializes to whatever it happens to be —
        treat that as an outage rather than letting an AttributeError escape."""
        results = getattr(response, "results", None)
        if results is None:
            raise MarketDataUnavailableError(
                "brapi.dev returned an unexpected payload without quote results."
            )
        return list(results)

    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        if not tickers:
            return {}
        try:
            response = self._client.quote.retrieve(tickers=",".join(sorted(tickers)))
        except BrapiError as error:
            raise self._translate(error) from error

        quotes: dict[str, Quote] = {}
        for result in self._results(response):
            # Unknown tickers come back without a price — skip rather than fail.
            if not result.symbol or result.regular_market_price is None:
                continue
            quotes[result.symbol] = Quote(
                ticker=result.symbol,
                price=float(result.regular_market_price),
                logo_url=result.logourl or None,
                change_percent=(
                    float(result.regular_market_change_percent)
                    if result.regular_market_change_percent is not None
                    else None
                ),
                name=(result.long_name or result.short_name or None),
            )
        return quotes

    def get_price_history(self, ticker: str, from_date: str, to_date: str) -> list[HistoricalPrice]:
        try:
            response = self._client.quote.retrieve(
                tickers=ticker, range=HISTORY_RANGE, interval=HISTORY_INTERVAL
            )
        except BrapiError as error:
            raise self._translate(error) from error

        results = self._results(response)
        if not results:
            return []

        prices: list[HistoricalPrice] = []
        for point in results[0].historical_data_price or []:
            if point.close is None or point.date is None:
                continue
            day = datetime.fromtimestamp(int(point.date), tz=timezone.utc).date().isoformat()
            if from_date <= day <= to_date:
                prices.append(HistoricalPrice(date=day, price=float(point.close)))
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
