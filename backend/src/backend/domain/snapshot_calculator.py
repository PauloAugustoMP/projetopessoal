"""Computes one day's PortfolioSnapshot from raw history (docs/business-rules.md §8).

Pure: prices are handed in by the caller (application layer resolves them from
the provider/cache). Only events dated on or before the snapshot date count.

Cumulative contributions are the net external cash flow: buys (cost including
fees) minus sell proceeds (net of fees). Buys made through the dividend
reinvestment flow (§9) are not contributions — that money never left the
portfolio — so they enter through cumulative_reinvested_dividends instead.
"""

from .entities import CorporateAction, Dividend, PortfolioSnapshot, Transaction
from .position_history import replay_history


def compute_snapshot(
    snapshot_date: str,
    transactions: list[Transaction],
    corporate_actions: list[CorporateAction],
    dividends: list[Dividend],
    prices: dict[str, float],
    categories: dict[str, str],
) -> PortfolioSnapshot:
    up_to_transactions = [t for t in transactions if t.date <= snapshot_date]
    up_to_actions = [a for a in corporate_actions if a.date <= snapshot_date]

    total_value = 0.0
    value_by_category: dict[str, float] = {}
    for ticker in sorted({t.ticker for t in up_to_transactions}):
        position = replay_history(ticker, up_to_transactions, up_to_actions).position
        if position.quantity <= 0:
            continue
        price = prices.get(ticker)
        if price is None:
            # Without a price the position can't be valued; the caller is expected
            # to resolve every held ticker — missing ones fall back to cost.
            price = position.average_price
        value = position.quantity * price
        total_value += value
        category = categories.get(ticker, "stock")
        value_by_category[category] = value_by_category.get(category, 0.0) + value

    contributions = 0.0
    for t in up_to_transactions:
        if t.type == "buy":
            contributions += t.quantity * t.price_per_share + t.fees
        else:
            contributions -= t.quantity * t.price_per_share - t.fees

    reinvested = sum(
        d.net_value_per_share * d.quantity
        for d in dividends
        if d.reinvested and d.payment_date <= snapshot_date
    )

    return PortfolioSnapshot(
        date=snapshot_date,
        total_value=total_value,
        value_by_category=value_by_category,
        cumulative_contributions=contributions,
        cumulative_reinvested_dividends=reinvested,
    )
