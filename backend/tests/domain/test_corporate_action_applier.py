import pytest

from backend.domain import CorporateAction, Position, UnsupportedCorporateActionError, apply_corporate_action


def action(type: str, factor: float, ticker: str = "ITSA4", date: str = "2026-01-01") -> CorporateAction:
    return CorporateAction(id="1", ticker=ticker, type=type, date=date, factor=factor)


def test_a_1_to_2_split_doubles_quantity_and_halves_average_price() -> None:
    position = Position(ticker="ITSA4", quantity=100, average_price=10)
    result = apply_corporate_action(position, action("split", 2))
    assert result.quantity == 200
    assert result.average_price == pytest.approx(5)
    assert result.quantity * result.average_price == pytest.approx(position.quantity * position.average_price)


def test_a_10_to_1_reverse_split_reduces_quantity_and_multiplies_average_price() -> None:
    position = Position(ticker="ITSA4", quantity=1000, average_price=2)
    result = apply_corporate_action(position, action("reverse_split", 0.1))
    assert result.quantity == 100
    assert result.average_price == pytest.approx(20)
    assert result.quantity * result.average_price == pytest.approx(position.quantity * position.average_price)


def test_a_10_percent_bonus_share_event_increases_quantity_preserving_total_cost() -> None:
    position = Position(ticker="ITSA4", quantity=100, average_price=10)
    result = apply_corporate_action(position, action("bonus_shares", 0.1))
    assert result.quantity == pytest.approx(110)
    assert result.quantity * result.average_price == pytest.approx(1000)


def test_leaves_a_zeroed_position_unchanged() -> None:
    position = Position(ticker="ITSA4", quantity=0, average_price=0)
    result = apply_corporate_action(position, action("split", 2))
    assert result == position


def test_rejects_subscription_rights() -> None:
    position = Position(ticker="ITSA4", quantity=100, average_price=10)
    with pytest.raises(UnsupportedCorporateActionError):
        apply_corporate_action(position, action("subscription_rights", 1))
