import pytest

from backend.domain.entities import CorporateAction, Dividend, Transaction
from backend.domain.snapshot_calculator import compute_snapshot


def _buy(ticker: str, date: str, quantity: float, price: float, fees: float = 0.0) -> Transaction:
    return Transaction(
        id=f"{ticker}-{date}", ticker=ticker, type="buy", quantity=quantity,
        price_per_share=price, date=date, fees=fees,
    )


def _sell(ticker: str, date: str, quantity: float, price: float, fees: float = 0.0) -> Transaction:
    return Transaction(
        id=f"{ticker}-{date}-s", ticker=ticker, type="sell", quantity=quantity,
        price_per_share=price, date=date, fees=fees,
    )


CATEGORIES = {"ITSA4": "stock", "MXRF11": "reit"}


def test_values_positions_at_the_given_prices_grouped_by_category():
    snapshot = compute_snapshot(
        "2026-02-01",
        [_buy("ITSA4", "2026-01-10", 100, 9.0), _buy("MXRF11", "2026-01-15", 50, 10.0)],
        [], [],
        prices={"ITSA4": 10.0, "MXRF11": 9.5},
        categories=CATEGORIES,
    )
    assert snapshot.total_value == 100 * 10.0 + 50 * 9.5
    assert snapshot.value_by_category == {"stock": 1000.0, "reit": 475.0}
    assert snapshot.cumulative_contributions == 100 * 9.0 + 50 * 10.0


def test_only_events_on_or_before_the_snapshot_date_count():
    snapshot = compute_snapshot(
        "2026-01-31",
        [_buy("ITSA4", "2026-01-10", 100, 9.0), _buy("ITSA4", "2026-02-10", 100, 11.0)],
        [], [],
        prices={"ITSA4": 10.0},
        categories=CATEGORIES,
    )
    assert snapshot.total_value == 1000.0
    assert snapshot.cumulative_contributions == 900.0


def test_sells_reduce_contributions_by_the_net_proceeds():
    snapshot = compute_snapshot(
        "2026-02-01",
        [_buy("ITSA4", "2026-01-10", 100, 9.0, fees=1.0), _sell("ITSA4", "2026-01-20", 40, 10.0, fees=2.0)],
        [], [],
        prices={"ITSA4": 10.0},
        categories=CATEGORIES,
    )
    assert snapshot.total_value == 60 * 10.0
    assert snapshot.cumulative_contributions == pytest.approx((900 + 1) - (400 - 2))


def test_corporate_actions_affect_the_valued_quantity():
    snapshot = compute_snapshot(
        "2026-03-01",
        [_buy("ITSA4", "2026-01-10", 100, 9.0)],
        [CorporateAction(id="a1", ticker="ITSA4", type="split", date="2026-02-01", factor=2)],
        [],
        prices={"ITSA4": 5.0},
        categories=CATEGORIES,
    )
    assert snapshot.total_value == 200 * 5.0


def test_a_missing_price_falls_back_to_cost_basis():
    snapshot = compute_snapshot(
        "2026-02-01",
        [_buy("ITSA4", "2026-01-10", 100, 9.0)],
        [], [],
        prices={},
        categories=CATEGORIES,
    )
    assert snapshot.total_value == 900.0


def test_only_reinvested_dividends_count_toward_the_reinvested_total():
    def dividend(id: str, reinvested: bool) -> Dividend:
        return Dividend(
            id=id, ticker="ITSA4", type="dividend", gross_value_per_share=1.0,
            ex_date=None, payment_date="2026-01-20", withholding_tax_rate=0.0,
            net_value_per_share=1.0, quantity=100, reinvested=reinvested,
        )

    snapshot = compute_snapshot(
        "2026-02-01",
        [_buy("ITSA4", "2026-01-10", 100, 9.0)],
        [],
        [dividend("d1", reinvested=True), dividend("d2", reinvested=False)],
        prices={"ITSA4": 10.0},
        categories=CATEGORIES,
    )
    assert snapshot.cumulative_reinvested_dividends == 100.0
