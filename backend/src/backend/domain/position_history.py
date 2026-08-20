"""Replays an asset's full history — transactions AND corporate actions — in
chronological order (docs/business-rules.md §1, §2 and §5).

On the same date, transactions are applied before corporate actions: a share
bought on the ex-date of a split is bought at the pre-split price, so the event
must adjust it too. The ordering is deterministic either way.
"""

from dataclasses import dataclass

from .average_price_calculator import InsufficientPositionError, RealizedSale
from .corporate_action_applier import apply_corporate_action
from .entities import CorporateAction, Position, Transaction


@dataclass(frozen=True)
class HistoryResult:
    position: Position
    realized_sales: list[RealizedSale]


def replay_history(
    ticker: str,
    transactions: list[Transaction],
    corporate_actions: list[CorporateAction] | None = None,
) -> HistoryResult:
    actions = corporate_actions or []
    events: list[tuple[str, int, object]] = [
        (t.date, 0, t) for t in transactions if t.ticker == ticker
    ] + [(a.date, 1, a) for a in actions if a.ticker == ticker]
    events.sort(key=lambda e: (e[0], e[1], getattr(e[2], "id", "")))

    quantity = 0.0
    average_price = 0.0
    realized_sales: list[RealizedSale] = []

    for _, kind, event in events:
        if kind == 1:
            adjusted = apply_corporate_action(
                Position(ticker=ticker, quantity=quantity, average_price=average_price),
                event,  # type: ignore[arg-type]
            )
            quantity, average_price = adjusted.quantity, adjusted.average_price
            continue

        t: Transaction = event  # type: ignore[assignment]
        if t.type == "buy":
            previous_total_cost = quantity * average_price
            buy_cost = t.quantity * t.price_per_share + t.fees
            quantity += t.quantity
            average_price = 0.0 if quantity == 0 else (previous_total_cost + buy_cost) / quantity
        else:
            if t.quantity > quantity:
                raise InsufficientPositionError(ticker, quantity, t.quantity, t.date)
            realized_sales.append(
                RealizedSale(
                    transaction_id=t.id,
                    ticker=ticker,
                    date=t.date,
                    quantity=t.quantity,
                    realized_profit=t.quantity * (t.price_per_share - average_price) - t.fees,
                )
            )
            quantity -= t.quantity
            if quantity == 0:
                average_price = 0.0

    return HistoryResult(
        position=Position(ticker=ticker, quantity=quantity, average_price=average_price),
        realized_sales=realized_sales,
    )


def position_before_date(
    ticker: str,
    date: str,
    transactions: list[Transaction],
    corporate_actions: list[CorporateAction] | None = None,
) -> Position:
    """Position considering only events strictly before `date` — used to derive a
    corporate action's factor from the quantity credited/debited on the statement."""
    return replay_history(
        ticker,
        [t for t in transactions if t.date < date],
        [a for a in (corporate_actions or []) if a.date < date],
    ).position
