"""Stand-in used when no market data token is configured.

The app is designed to work without quotes — positions fall back to cost basis
(docs/architecture.md §4.1) — so a missing token must behave like any other
provider outage, not like a crash. Every caller already handles this error.
"""

from backend.ports.market_data_provider import (
    HistoricalPrice,
    MarketDataUnavailableError,
    Quote,
)

REASON = (
    "No market data provider configured — set BRAPI_API_TOKEN in .env to enable "
    "quotes, historical prices and logos."
)


class NullMarketDataProvider:
    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        raise MarketDataUnavailableError(REASON)

    def get_price_history(self, ticker: str, from_date: str, to_date: str) -> list[HistoricalPrice]:
        raise MarketDataUnavailableError(REASON)
