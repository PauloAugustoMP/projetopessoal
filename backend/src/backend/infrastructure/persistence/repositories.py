from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.entities import Transaction

from .models import PositionModel, TransactionModel


def to_domain_transaction(model: TransactionModel) -> Transaction:
    return Transaction(
        id=str(model.id),
        ticker=model.ticker,
        type=model.type,  # type: ignore[arg-type]
        quantity=float(model.quantity),
        price_per_share=float(model.price_per_share),
        date=model.date.isoformat(),
        fees=float(model.fees),
    )


class SqlAlchemyTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_ticker(self, ticker: str) -> list[Transaction]:
        rows = self._session.scalars(
            select(TransactionModel).where(TransactionModel.ticker == ticker)
        ).all()
        return [to_domain_transaction(row) for row in rows]


class SqlAlchemyPositionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, ticker: str, quantity: float, average_price: float) -> None:
        position = self._session.get(PositionModel, ticker)
        if position is None:
            position = PositionModel(ticker=ticker, quantity=quantity, average_price=average_price)
            self._session.add(position)
        else:
            position.quantity = quantity
            position.average_price = average_price

    def delete(self, ticker: str) -> None:
        position = self._session.get(PositionModel, ticker)
        if position is not None:
            self._session.delete(position)
