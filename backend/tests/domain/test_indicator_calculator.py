import math

import pytest

from backend.domain import UnknownIndicatorError, bazin_ceiling_price, compute_indicator, graham_fair_price


def test_marks_a_low_pe_as_green() -> None:
    assert compute_indicator("P/E", 12).marker == "green"


def test_marks_a_mid_range_pe_as_yellow() -> None:
    assert compute_indicator("P/E", 20).marker == "yellow"


def test_marks_a_high_pe_as_red() -> None:
    assert compute_indicator("P/E", 30).marker == "red"


def test_marks_a_high_dy_as_green() -> None:
    assert compute_indicator("DY", 0.08).marker == "green"


def test_marks_a_low_dy_as_red() -> None:
    assert compute_indicator("DY", 0.02).marker == "red"


def test_includes_the_tooltip_description() -> None:
    indicator = compute_indicator("P/B", 0.9)
    assert len(indicator.description) > 0


def test_raises_for_an_unknown_indicator() -> None:
    with pytest.raises(UnknownIndicatorError):
        compute_indicator("EBITDA", 10)


def test_bazin_ceiling_price_divides_dividends_by_desired_minimum_yield() -> None:
    assert bazin_ceiling_price(0.9, 0.06) == pytest.approx(15)


def test_bazin_ceiling_price_rejects_zero_or_negative_yield() -> None:
    with pytest.raises(ValueError):
        bazin_ceiling_price(0.9, 0)
    with pytest.raises(ValueError):
        bazin_ceiling_price(0.9, -0.1)


def test_graham_fair_price_computes_using_grahams_formula() -> None:
    assert graham_fair_price(2, 8) == pytest.approx(math.sqrt(22.5 * 2 * 8))


def test_graham_fair_price_returns_none_when_eps_is_negative() -> None:
    assert graham_fair_price(-1, 8) is None


def test_graham_fair_price_returns_none_when_book_value_is_not_positive() -> None:
    assert graham_fair_price(2, 0) is None
