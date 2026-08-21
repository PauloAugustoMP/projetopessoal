from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.entities import CorporateAction, Dividend, Transaction
from backend.ports.market_data_provider import HistoricalPrice

from .models import (
    CorporateActionModel,
    DividendModel,
    PositionModel,
    PriceHistoryModel,
    SystemStateModel,
    TransactionModel,
)


def to_domain_dividend(model: DividendModel) -> Dividend:
    return Dividend(
        id=str(model.id),
        ticker=model.ticker,
        type=model.type,  # type: ignore[arg-type]
        gross_value_per_share=float(model.gross_value_per_share),
        ex_date=model.ex_date.isoformat() if model.ex_date else None,
        payment_date=model.payment_date.isoformat(),
        withholding_tax_rate=float(model.withholding_tax_rate),
        net_value_per_share=float(model.net_value_per_share),
        quantity=float(model.quantity),
        reinvested=model.reinvested,
    )


def to_domain_corporate_action(model: CorporateActionModel) -> CorporateAction:
    return CorporateAction(
        id=str(model.id),
        ticker=model.ticker,
        type=model.type,  # type: ignore[arg-type]
        date=model.date.isoformat(),
        factor=float(model.factor),
    )


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


class SqlAlchemyCorporateActionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_ticker(self, ticker: str) -> list[CorporateAction]:
        rows = self._session.scalars(
            select(CorporateActionModel).where(CorporateActionModel.ticker == ticker)
        ).all()
        return [to_domain_corporate_action(row) for row in rows]


class SqlAlchemyPriceHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_prices(self, ticker: str, prices: list[HistoricalPrice]) -> None:
        for point in prices:
            day = date_type.fromisoformat(point.date)
            existing = self._session.get(PriceHistoryModel, (ticker, day))
            if existing is None:
                self._session.add(PriceHistoryModel(ticker=ticker, date=day, price=point.price))
            else:
                existing.price = point.price

    def latest_date(self, ticker: str) -> str | None:
        row = self._session.scalars(
            select(PriceHistoryModel)
            .where(PriceHistoryModel.ticker == ticker)
            .order_by(PriceHistoryModel.date.desc())
            .limit(1)
        ).first()
        return row.date.isoformat() if row is not None else None

    def latest_price_on_or_before(self, ticker: str, date: str) -> float | None:
        row = self._session.scalars(
            select(PriceHistoryModel)
            .where(
                PriceHistoryModel.ticker == ticker,
                PriceHistoryModel.date <= date_type.fromisoformat(date),
            )
            .order_by(PriceHistoryModel.date.desc())
            .limit(1)
        ).first()
        return float(row.price) if row is not None else None


class SystemStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> str | None:
        row = self._session.get(SystemStateModel, key)
        return row.value if row is not None else None

    def set(self, key: str, value: str) -> None:
        row = self._session.get(SystemStateModel, key)
        if row is None:
            self._session.add(SystemStateModel(key=key, value=value))
        else:
            row.value = value


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
