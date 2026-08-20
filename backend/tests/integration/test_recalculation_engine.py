"""The recalculation engine running against the real database (docs/business-rules.md §2):
idempotency and full-history replay, independent of the API layer."""

import uuid
from datetime import date

from sqlalchemy import select

from backend.application.recalculation import recalculate_position
from backend.infrastructure.persistence.database import get_engine, get_session_factory
from backend.infrastructure.persistence.models import PositionModel, TransactionModel


def _insert_transactions(rows: list[dict]) -> None:
    factory = get_session_factory()
    with factory() as session:
        for row in rows:
            session.add(
                TransactionModel(
                    id=uuid.uuid4(),
                    ticker=row["ticker"],
                    type=row["type"],
                    quantity=row["quantity"],
                    price_per_share=row["price"],
                    date=date.fromisoformat(row["date"]),
                    fees=row.get("fees", 0),
                    source="manual",
                )
            )
        session.commit()


def _position(ticker: str) -> tuple[float, float] | None:
    factory = get_session_factory()
    with factory() as session:
        row = session.scalars(
            select(PositionModel).where(PositionModel.ticker == ticker)
        ).one_or_none()
        if row is None:
            return None
        return float(row.quantity), float(row.average_price)


def test_running_the_engine_twice_produces_the_same_final_state():
    _insert_transactions(
        [
            {"ticker": "VALE3", "type": "buy", "quantity": 100, "price": 60, "date": "2026-01-05"},
            {"ticker": "VALE3", "type": "buy", "quantity": 50, "price": 66, "date": "2026-02-05"},
            {"ticker": "VALE3", "type": "sell", "quantity": 30, "price": 70, "date": "2026-03-05"},
        ]
    )
    factory = get_session_factory()

    recalculate_position(factory, "VALE3")
    first = _position("VALE3")

    recalculate_position(factory, "VALE3")
    second = _position("VALE3")

    assert first == second
    assert first is not None
    quantity, average_price = first
    assert quantity == 120
    assert average_price == (100 * 60 + 50 * 66) / 150  # sells never change the average


def test_the_engine_replays_history_chronologically_regardless_of_insertion_order():
    # Inserted out of order on purpose — the engine must sort by date.
    _insert_transactions(
        [
            {"ticker": "PETR4", "type": "buy", "quantity": 100, "price": 40, "date": "2026-03-01"},
            {"ticker": "PETR4", "type": "buy", "quantity": 100, "price": 20, "date": "2026-01-01"},
        ]
    )
    recalculate_position(get_session_factory(), "PETR4")
    assert _position("PETR4") == (200, 30)


def test_the_engine_removes_the_position_when_no_transactions_remain():
    _insert_transactions(
        [{"ticker": "BBAS3", "type": "buy", "quantity": 10, "price": 25, "date": "2026-01-05"}]
    )
    factory = get_session_factory()
    recalculate_position(factory, "BBAS3")
    assert _position("BBAS3") is not None

    with get_engine().begin() as connection:
        connection.execute(
            TransactionModel.__table__.delete().where(TransactionModel.ticker == "BBAS3")
        )
    recalculate_position(factory, "BBAS3")
    assert _position("BBAS3") is None
