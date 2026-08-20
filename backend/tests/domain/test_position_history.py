import pytest

from backend.domain.average_price_calculator import InsufficientPositionError
from backend.domain.entities import CorporateAction, Transaction
from backend.domain.position_history import position_before_date, replay_history


def _buy(id: str, date: str, quantity: float, price: float) -> Transaction:
    return Transaction(id=id, ticker="ITSA4", type="buy", quantity=quantity, price_per_share=price, date=date)


def _sell(id: str, date: str, quantity: float, price: float) -> Transaction:
    return Transaction(id=id, ticker="ITSA4", type="sell", quantity=quantity, price_per_share=price, date=date)


def _action(id: str, date: str, type_: str, factor: float) -> CorporateAction:
    return CorporateAction(id=id, ticker="ITSA4", type=type_, date=date, factor=factor)  # type: ignore[arg-type]


def test_a_split_doubles_the_quantity_and_halves_the_average_price():
    result = replay_history(
        "ITSA4",
        [_buy("t1", "2026-01-10", 100, 10)],
        [_action("a1", "2026-02-01", "split", 2)],
    )
    assert result.position.quantity == 200
    assert result.position.average_price == 5


def test_events_are_interleaved_chronologically():
    # buy 100@10 -> split x2 (200@5) -> buy 100@8 -> avg = (1000+800)/300 = 6
    result = replay_history(
        "ITSA4",
        [_buy("t1", "2026-01-10", 100, 10), _buy("t2", "2026-03-10", 100, 8)],
        [_action("a1", "2026-02-01", "split", 2)],
    )
    assert result.position.quantity == 300
    assert result.position.average_price == pytest.approx(6)


def test_a_sale_after_a_split_can_exceed_the_pre_split_quantity():
    result = replay_history(
        "ITSA4",
        [_buy("t1", "2026-01-10", 100, 10), _sell("t2", "2026-03-10", 150, 6)],
        [_action("a1", "2026-02-01", "split", 2)],
    )
    assert result.position.quantity == 50
    assert result.position.average_price == 5


def test_a_sale_exceeding_the_position_on_that_date_still_raises():
    with pytest.raises(InsufficientPositionError):
        replay_history(
            "ITSA4",
            # The sell happens BEFORE the split, so only 100 shares exist then.
            [_buy("t1", "2026-01-10", 100, 10), _sell("t2", "2026-01-20", 150, 6)],
            [_action("a1", "2026-02-01", "split", 2)],
        )


def test_on_the_same_date_transactions_apply_before_corporate_actions():
    # buy 100@10 on the split date -> split doubles it to 200@5
    result = replay_history(
        "ITSA4",
        [_buy("t1", "2026-02-01", 100, 10)],
        [_action("a1", "2026-02-01", "split", 2)],
    )
    assert result.position.quantity == 200
    assert result.position.average_price == 5


def test_a_reverse_split_preserves_the_total_cost():
    result = replay_history(
        "ITSA4",
        [_buy("t1", "2026-01-10", 100, 10)],
        [_action("a1", "2026-02-01", "reverse_split", 0.1)],
    )
    assert result.position.quantity == 10
    assert result.position.average_price == 100


def test_position_before_date_ignores_later_events():
    position = position_before_date(
        "ITSA4",
        "2026-02-01",
        [_buy("t1", "2026-01-10", 100, 10), _buy("t2", "2026-02-10", 100, 8)],
        [_action("a1", "2026-02-05", "split", 2)],
    )
    assert position.quantity == 100
    assert position.average_price == 10
