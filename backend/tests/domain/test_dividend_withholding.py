import pytest

from backend.domain.dividend_withholding import net_value_per_share, withholding_rate_for


def test_stock_dividends_and_reit_income_are_tax_exempt():
    assert withholding_rate_for("dividend") == 0
    assert withholding_rate_for("reit_income") == 0
    assert net_value_per_share("dividend", 1.0) == 1.0


def test_jcp_withholds_fifteen_percent_at_the_source():
    assert withholding_rate_for("jcp") == 0.15
    assert net_value_per_share("jcp", 1.0) == pytest.approx(0.85)


def test_an_unknown_dividend_type_is_rejected():
    with pytest.raises(ValueError):
        withholding_rate_for("fixed_income_redemption")
