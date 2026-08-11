import pytest

from backend.domain import InsufficientPositionError, Transaction, calculate_position_and_realized_sales


def tx(id: str, type: str, quantity: float, price_per_share: float, date: str, ticker: str = "ITSA4", fees: float = 0.0) -> Transaction:
    return Transaction(id=id, ticker=ticker, type=type, quantity=quantity, price_per_share=price_per_share, date=date, fees=fees)


def test_returns_a_zeroed_position_with_no_transactions() -> None:
    result = calculate_position_and_realized_sales("ITSA4", [])
    assert result.position.ticker == "ITSA4"
    assert result.position.quantity == 0
    assert result.position.average_price == 0


def test_computes_the_weighted_average_price_across_successive_buys() -> None:
    transactions = [
        tx("1", "buy", 100, 10, "2026-01-01"),
        tx("2", "buy", 100, 20, "2026-02-01"),
    ]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.quantity == 200
    assert result.position.average_price == pytest.approx(15)


def test_does_not_change_the_average_price_on_a_sell_only_reduces_quantity() -> None:
    transactions = [
        tx("1", "buy", 200, 15, "2026-01-01"),
        tx("2", "sell", 50, 18, "2026-03-01"),
    ]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.quantity == 150
    assert result.position.average_price == pytest.approx(15)
    assert len(result.realized_sales) == 1
    assert result.realized_sales[0].realized_profit == pytest.approx(50 * (18 - 15))


def test_zeroes_the_average_price_once_the_position_reaches_zero_and_starts_fresh() -> None:
    transactions = [
        tx("1", "buy", 100, 10, "2026-01-01"),
        tx("2", "sell", 100, 12, "2026-02-01"),
        tx("3", "buy", 50, 30, "2026-03-01"),
    ]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.quantity == 50
    assert result.position.average_price == pytest.approx(30)


def test_processes_in_chronological_order_regardless_of_insertion_order() -> None:
    transactions = [
        tx("2", "buy", 100, 20, "2026-02-01"),
        tx("1", "buy", 100, 10, "2026-01-01"),
    ]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.average_price == pytest.approx(15)


def test_adds_fees_to_the_cost_of_a_buy() -> None:
    transactions = [tx("1", "buy", 100, 10, "2026-01-01", fees=10)]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.average_price == pytest.approx((100 * 10 + 10) / 100)


def test_rejects_a_sell_larger_than_the_position_available_on_that_date() -> None:
    transactions = [
        tx("1", "buy", 50, 10, "2026-01-01"),
        tx("2", "sell", 100, 12, "2026-02-01"),
    ]
    with pytest.raises(InsufficientPositionError):
        calculate_position_and_realized_sales("ITSA4", transactions)


def test_ignores_transactions_from_other_tickers() -> None:
    transactions = [
        tx("1", "buy", 100, 10, "2026-01-01"),
        tx("2", "buy", 100, 999, "2026-01-01", ticker="PETR4"),
    ]
    result = calculate_position_and_realized_sales("ITSA4", transactions)
    assert result.position.quantity == 100
    assert result.position.average_price == pytest.approx(10)
