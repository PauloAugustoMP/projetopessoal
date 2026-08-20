from typing import Protocol

from backend.domain.entities import Transaction


class TransactionRepository(Protocol):
    def list_by_ticker(self, ticker: str) -> list[Transaction]: ...


class PositionRepository(Protocol):
    def upsert(self, ticker: str, quantity: float, average_price: float) -> None: ...

    def delete(self, ticker: str) -> None: ...
