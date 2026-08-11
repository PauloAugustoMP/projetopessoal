from dataclasses import dataclass

from .entities import AllocationTarget

_EPSILON = 1e-6


class InvalidAllocationTargetsError(Exception):
    pass


class MissingPriceError(Exception):
    def __init__(self, ticker: str) -> None:
        super().__init__(f"Current price unavailable for {ticker} -- cannot simulate the contribution.")


@dataclass(frozen=True)
class TargetPercentage:
    ticker: str
    final_percentage: float


@dataclass(frozen=True)
class RebalanceItem:
    ticker: str
    current_percentage: float
    target_percentage: float
    suggested_value: float
    suggested_quantity: int


@dataclass(frozen=True)
class RebalanceSuggestion:
    contribution_amount: float
    items: list[RebalanceItem]
    unallocated_value: float


def validate_allocation_targets(targets: list[AllocationTarget]) -> None:
    """Validates that category percentages add up to 100% (docs/business-rules.md section 3)."""
    total = sum(t.percentage for t in targets)
    if abs(total - 1) > _EPSILON:
        raise InvalidAllocationTargetsError(
            f"Category percentages must add up to 100% (received {total * 100:.2f}%)."
        )


def resolve_target_percentages(targets: list[AllocationTarget]) -> list[TargetPercentage]:
    """Resolves each asset's final target percentage = category percentage x weight within
    the category. Assets without an explicit weight split whatever remains after explicit
    weights equally among themselves (docs/business-rules.md section 3).
    """
    result: list[TargetPercentage] = []

    for target in targets:
        explicit = [a for a in target.assets if a.weight_in_category is not None]
        implicit = [a for a in target.assets if a.weight_in_category is None]
        explicit_sum = sum(a.weight_in_category or 0 for a in explicit)
        remaining = max(0.0, 1 - explicit_sum)
        implicit_weight = remaining / len(implicit) if implicit else 0.0

        for asset in target.assets:
            weight = asset.weight_in_category if asset.weight_in_category is not None else implicit_weight
            result.append(TargetPercentage(ticker=asset.ticker, final_percentage=target.percentage * weight))

    return result


def simulate_contribution(
    targets: list[AllocationTarget],
    current_total_value: float,
    current_value_by_asset: dict[str, float],
    current_price_by_asset: dict[str, float],
    contribution_amount: float,
) -> RebalanceSuggestion:
    """Contribution / rebalancing simulator (docs/business-rules.md section 3). Never
    suggests selling.
    """
    validate_allocation_targets(targets)
    percentages = resolve_target_percentages(targets)
    total_with_contribution = current_total_value + contribution_amount

    gaps = []
    for percentage in percentages:
        current_value = current_value_by_asset.get(percentage.ticker, 0.0)
        target_value = percentage.final_percentage * total_with_contribution
        gap = max(0.0, target_value - current_value)
        gaps.append((percentage.ticker, percentage.final_percentage, current_value, gap))

    total_gap = sum(gap for _, _, _, gap in gaps)

    items: list[RebalanceItem] = []
    for ticker, final_percentage, current_value, gap in gaps:
        price = current_price_by_asset.get(ticker)
        if price is None:
            raise MissingPriceError(ticker)

        suggested_value = (
            contribution_amount * (gap / total_gap) if total_gap > 0 else contribution_amount * final_percentage
        )
        suggested_quantity = int(suggested_value // price)

        items.append(
            RebalanceItem(
                ticker=ticker,
                current_percentage=(current_value / current_total_value) if current_total_value > 0 else 0.0,
                target_percentage=final_percentage,
                suggested_value=suggested_value,
                suggested_quantity=suggested_quantity,
            )
        )

    allocated_value = sum(item.suggested_quantity * current_price_by_asset[item.ticker] for item in items)

    return RebalanceSuggestion(
        contribution_amount=contribution_amount,
        items=items,
        unallocated_value=contribution_amount - allocated_value,
    )
