"""Port for external market data (docs/architecture.md §3): the domain and
application layers depend on this contract, never on brapi.dev directly."""

from dataclasses import dataclass
from typing import Optional, Protocol


class MarketDataUnavailableError(Exception):
    """Raised when the provider is down, rate-limited, or returned garbage —
    callers decide whether to fall back to cached data or surface the error."""


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: float
    logo_url: Optional[str] = None
    change_percent: Optional[float] = None  # daily variation reported by the provider
    name: Optional[str] = None  # provider's display name, used to enrich the catalog


@dataclass(frozen=True)
class HistoricalPrice:
    date: str  # ISO
    price: float


class MarketDataProvider(Protocol):
    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        """Latest quotes for the given tickers. Missing/unknown tickers are simply
        absent from the result — never an error."""
        ...

    def get_price_history(self, ticker: str, from_date: str, to_date: str) -> list[HistoricalPrice]:
        """Daily closing prices within the range (inclusive). Weekends/holidays
        are naturally absent."""
        ...
