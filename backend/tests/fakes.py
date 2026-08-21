"""Fake market data provider (docs/testing-strategy.md §2: integration tests
never depend on brapi.dev being up)."""

from backend.ports.market_data_provider import HistoricalPrice, Quote


class FakeMarketDataProvider:
    def __init__(
        self,
        quotes: dict[str, Quote] | None = None,
        histories: dict[str, list[HistoricalPrice]] | None = None,
    ) -> None:
        self.quotes = quotes or {}
        self.histories = histories or {}
        self.quote_calls: list[list[str]] = []
        self.history_calls: list[tuple[str, str, str]] = []

    def get_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        self.quote_calls.append(list(tickers))
        return {t: self.quotes[t] for t in tickers if t in self.quotes}

    def get_price_history(self, ticker: str, from_date: str, to_date: str) -> list[HistoricalPrice]:
        self.history_calls.append((ticker, from_date, to_date))
        return [p for p in self.histories.get(ticker, []) if from_date <= p.date <= to_date]
