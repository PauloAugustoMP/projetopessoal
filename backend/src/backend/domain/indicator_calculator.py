import math
from dataclasses import dataclass
from typing import Literal

from .entities import Indicator

Direction = Literal["lower_is_better", "higher_is_better"]


@dataclass(frozen=True)
class IndicatorDefinition:
    name: str
    direction: Direction
    green_threshold: float
    red_threshold: float
    description: str


# Single registry of indicators -- drives both the marker (color) and the tooltip text
# (docs/business-rules.md section 4). Thresholds are configurable heuristics, not
# investment advice.
INDICATOR_DEFINITIONS: dict[str, IndicatorDefinition] = {
    "P/E": IndicatorDefinition(
        name="P/E",
        direction="lower_is_better",
        green_threshold=15,
        red_threshold=25,
        description="Price divided by earnings per share. The lower, the cheaper the asset "
        "relative to the profit it generates.",
    ),
    "P/B": IndicatorDefinition(
        name="P/B",
        direction="lower_is_better",
        green_threshold=1,
        red_threshold=2,
        description="Compares price to book value per share. Below 1 may indicate an "
        "undervalued asset; above 1, trading at a premium.",
    ),
    "DY": IndicatorDefinition(
        name="DY",
        direction="higher_is_better",
        green_threshold=0.06,
        red_threshold=0.03,
        description="Dividend yield -- dividends paid over the last 12 months divided by "
        "the current price.",
    ),
    "ROE": IndicatorDefinition(
        name="ROE",
        direction="higher_is_better",
        green_threshold=0.15,
        red_threshold=0.1,
        description="Return on equity -- how efficiently the company turns shareholder "
        "capital into profit.",
    ),
}


class UnknownIndicatorError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f'Indicator "{name}" is not registered in INDICATOR_DEFINITIONS.')


def _determine_marker(definition: IndicatorDefinition, value: float) -> str:
    if definition.direction == "lower_is_better":
        if value < definition.green_threshold:
            return "green"
        if value <= definition.red_threshold:
            return "yellow"
        return "red"

    if value > definition.green_threshold:
        return "green"
    if value >= definition.red_threshold:
        return "yellow"
    return "red"


def compute_indicator(name: str, value: float) -> Indicator:
    definition = INDICATOR_DEFINITIONS.get(name)
    if definition is None:
        raise UnknownIndicatorError(name)
    return Indicator(
        name=definition.name,
        value=value,
        marker=_determine_marker(definition, value),  # type: ignore[arg-type]
        description=definition.description,
    )


def bazin_ceiling_price(trailing_dividends_12m: float, desired_minimum_yield: float) -> float:
    """Ceiling price using the Bazin Method: trailing 12-month dividends / desired minimum
    yield (default 6% for stocks, 8% for REITs -- configurable). docs/business-rules.md
    section 4.
    """
    if desired_minimum_yield <= 0:
        raise ValueError("desired_minimum_yield must be greater than zero.")
    return trailing_dividends_12m / desired_minimum_yield


def graham_fair_price(eps: float, book_value_per_share: float) -> float | None:
    """Fair price using Graham's Formula: sqrt(22.5 x EPS x BVPS). Only applies to stocks;
    undefined (returns None) when EPS or BVPS is not positive. docs/business-rules.md
    section 4.
    """
    if eps <= 0 or book_value_per_share <= 0:
        return None
    return math.sqrt(22.5 * eps * book_value_per_share)
