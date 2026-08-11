from dataclasses import dataclass

from .entities import Position, Transaction


class InsufficientPositionError(Exception):
    def __init__(self, ticker: str, available_quantity: float, sold_quantity: float, date: str) -> None:
        super().__init__(
            f"Selling {sold_quantity} units of {ticker} on {date} exceeds the "
            f"available position ({available_quantity})."
        )


@dataclass(frozen=True)
class RealizedSale:
    transaction_id: str
    ticker: str
    date: str
    quantity: float
    realized_profit: float


@dataclass(frozen=True)
class CalculationResult:
    position: Position
    realized_sales: list[RealizedSale]


def _sort_chronologically(transactions: list[Transaction]) -> list[Transaction]:
    return sorted(transactions, key=lambda t: (t.date, t.id))


def calculate_position_and_realized_sales(ticker: str, transactions: list[Transaction]) -> CalculationResult:
    """Recalculates position and average price by walking the ENTIRE history in
    chronological order -- never incrementally -- to support backdated entries
    (docs/business-rules.md sections 1-2).
    """
    ordered = _sort_chronologically([t for t in transactions if t.ticker == ticker])

    quantity = 0.0
    average_price = 0.0
    realized_sales: list[RealizedSale] = []

    for t in ordered:
        if t.type == "buy":
            previous_total_cost = quantity * average_price
            buy_cost = t.quantity * t.price_per_share + t.fees
            quantity += t.quantity
            average_price = 0.0 if quantity == 0 else (previous_total_cost + buy_cost) / quantity
        else:
            if t.quantity > quantity:
                raise InsufficientPositionError(ticker, quantity, t.quantity, t.date)
            realized_profit = t.quantity * (t.price_per_share - average_price) - t.fees
            realized_sales.append(
                RealizedSale(
                    transaction_id=t.id,
                    ticker=ticker,
                    date=t.date,
                    quantity=t.quantity,
                    realized_profit=realized_profit,
                )
            )
            quantity -= t.quantity
            if quantity == 0:
                average_price = 0.0

    return CalculationResult(
        position=Position(ticker=ticker, quantity=quantity, average_price=average_price),
        realized_sales=realized_sales,
    )
