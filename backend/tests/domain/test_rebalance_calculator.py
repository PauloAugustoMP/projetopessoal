import pytest

from backend.domain import (
    AllocationTarget,
    InvalidAllocationTargetsError,
    MissingPriceError,
    TargetAsset,
    resolve_target_percentages,
    simulate_contribution,
    validate_allocation_targets,
)


def test_accepts_categories_that_add_up_to_100_percent() -> None:
    targets = [
        AllocationTarget(category="stock", percentage=0.6, assets=[]),
        AllocationTarget(category="reit", percentage=0.4, assets=[]),
    ]
    validate_allocation_targets(targets)  # should not raise


def test_rejects_categories_that_dont_add_up_to_100_percent() -> None:
    targets = [
        AllocationTarget(category="stock", percentage=0.5, assets=[]),
        AllocationTarget(category="reit", percentage=0.4, assets=[]),
    ]
    with pytest.raises(InvalidAllocationTargetsError):
        validate_allocation_targets(targets)


def test_splits_category_percentage_equally_among_assets_without_explicit_weight() -> None:
    targets = [
        AllocationTarget(
            category="reit",
            percentage=0.1,
            assets=[
                TargetAsset(ticker="MXRF11"),
                TargetAsset(ticker="HGLG11"),
                TargetAsset(ticker="KNRI11"),
                TargetAsset(ticker="VISC11"),
                TargetAsset(ticker="XPLG11"),
            ],
        )
    ]
    result = resolve_target_percentages(targets)
    assert len(result) == 5
    for item in result:
        assert item.final_percentage == pytest.approx(0.02)  # 10% / 5 assets = 2% each
    assert sum(item.final_percentage for item in result) == pytest.approx(0.1)


def test_honors_explicit_weight_and_splits_remainder_equally() -> None:
    targets = [
        AllocationTarget(
            category="stock",
            percentage=0.5,
            assets=[
                TargetAsset(ticker="ITSA4", weight_in_category=0.5),  # 50% of category = 25% of portfolio
                TargetAsset(ticker="PETR4"),  # half of the remainder
                TargetAsset(ticker="VALE3"),  # half of the remainder
            ],
        )
    ]
    result = resolve_target_percentages(targets)
    itsa4 = next(r for r in result if r.ticker == "ITSA4")
    petr4 = next(r for r in result if r.ticker == "PETR4")
    assert itsa4.final_percentage == pytest.approx(0.25)
    assert petr4.final_percentage == pytest.approx(0.125)


REIT_TARGETS = [
    AllocationTarget(
        category="reit",
        percentage=1,
        assets=[TargetAsset(ticker="MXRF11"), TargetAsset(ticker="HGLG11")],
    )
]


def test_directs_the_contribution_toward_the_asset_furthest_below_target() -> None:
    result = simulate_contribution(
        targets=REIT_TARGETS,
        current_total_value=1000,
        current_value_by_asset={"MXRF11": 800, "HGLG11": 200},  # target would be 500/500
        current_price_by_asset={"MXRF11": 10, "HGLG11": 100},
        contribution_amount=300,
    )
    hglg = next(i for i in result.items if i.ticker == "HGLG11")
    mxrf = next(i for i in result.items if i.ticker == "MXRF11")
    assert hglg.suggested_value > mxrf.suggested_value


def test_never_suggests_a_negative_value() -> None:
    result = simulate_contribution(
        targets=REIT_TARGETS,
        current_total_value=1000,
        current_value_by_asset={"MXRF11": 950, "HGLG11": 50},
        current_price_by_asset={"MXRF11": 10, "HGLG11": 100},
        contribution_amount=100,
    )
    for item in result.items:
        assert item.suggested_value >= 0


def test_splits_by_target_weight_once_every_asset_is_above_target() -> None:
    result = simulate_contribution(
        targets=REIT_TARGETS,
        current_total_value=10000,
        current_value_by_asset={"MXRF11": 5000, "HGLG11": 5000},
        current_price_by_asset={"MXRF11": 10, "HGLG11": 100},
        contribution_amount=200,
    )
    for item in result.items:
        assert item.suggested_value == pytest.approx(100)  # 50% of contribution each, equal weight


def test_suggested_quantity_is_always_an_integer() -> None:
    result = simulate_contribution(
        targets=REIT_TARGETS,
        current_total_value=0,
        current_value_by_asset={},
        current_price_by_asset={"MXRF11": 30, "HGLG11": 100},
        contribution_amount=100,
    )
    for item in result.items:
        assert isinstance(item.suggested_quantity, int)
    assert result.unallocated_value >= 0
    assert result.unallocated_value < 200  # less than the highest unit price involved


def test_throws_when_current_price_of_a_target_asset_is_missing() -> None:
    with pytest.raises(MissingPriceError):
        simulate_contribution(
            targets=REIT_TARGETS,
            current_total_value=0,
            current_value_by_asset={},
            current_price_by_asset={"MXRF11": 10},
            contribution_amount=100,
        )
