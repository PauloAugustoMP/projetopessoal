from typing import Protocol

from backend.ports.market_data_provider import HistoricalPrice


class PriceHistoryRepository(Protocol):
    def save_prices(self, ticker: str, prices: list[HistoricalPrice]) -> None: ...

    def latest_price_on_or_before(self, ticker: str, date: str) -> float | None: ...
