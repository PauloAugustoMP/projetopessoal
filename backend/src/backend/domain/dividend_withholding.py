"""Withholding tax at the source per dividend type (docs/business-rules.md §6).

Fixed-income redemptions follow the regressive schedule by holding period and
are not covered by the statement import, so they are not handled here.
"""

WITHHOLDING_RATES: dict[str, float] = {
    "dividend": 0.0,  # tax-exempt
    "jcp": 0.15,
    "reit_income": 0.0,  # tax-exempt for individuals under the usual conditions
}


def withholding_rate_for(dividend_type: str) -> float:
    if dividend_type not in WITHHOLDING_RATES:
        raise ValueError(f"No withholding rule for dividend type '{dividend_type}'.")
    return WITHHOLDING_RATES[dividend_type]


def net_value_per_share(dividend_type: str, gross_value_per_share: float) -> float:
    return gross_value_per_share * (1 - withholding_rate_for(dividend_type))
