from dataclasses import dataclass, field
from typing import Literal, Optional

AssetCategory = Literal["stock", "reit", "fixed_income", "crypto"]


@dataclass(frozen=True)
class Asset:
    ticker: str
    name: str
    category: AssetCategory
    logo_url: Optional[str] = None


TransactionType = Literal["buy", "sell"]


@dataclass(frozen=True)
class Transaction:
    id: str
    ticker: str
    type: TransactionType
    quantity: float
    price_per_share: float
    date: str  # ISO date (YYYY-MM-DD)
    fees: float = 0.0


@dataclass(frozen=True)
class Position:
    ticker: str
    quantity: float
    average_price: float


DividendType = Literal["dividend", "jcp", "reit_income", "fixed_income_redemption"]


@dataclass(frozen=True)
class Dividend:
    id: str
    ticker: str
    type: DividendType
    gross_value_per_share: float
    ex_date: Optional[str]
    payment_date: str
    withholding_tax_rate: float
    net_value_per_share: float
    quantity: float = 0.0  # shares that earned the payout
    reinvested: bool = False


CorporateActionType = Literal["split", "reverse_split", "bonus_shares", "subscription_rights"]


@dataclass(frozen=True)
class CorporateAction:
    id: str
    ticker: str
    type: CorporateActionType
    date: str
    # split/reverse_split: quantity multiplier (e.g. 2 for a 1:2 split, 0.1 for a 1:10 reverse split)
    # bonus_shares: fraction (e.g. 0.1 for a 10% bonus share event)
    # subscription_rights: not applicable, see corporate_action_applier.py
    factor: float


@dataclass(frozen=True)
class TargetAsset:
    ticker: str
    weight_in_category: Optional[float] = None  # None = split equally within the category


@dataclass(frozen=True)
class AllocationTarget:
    category: AssetCategory
    percentage: float
    assets: list[TargetAsset] = field(default_factory=list)


@dataclass(frozen=True)
class PortfolioSnapshot:
    date: str
    total_value: float
    value_by_category: dict[str, float]
    cumulative_contributions: float
    cumulative_reinvested_dividends: float


@dataclass(frozen=True)
class GrowthBreakdown:
    total_change: float
    contributions: float
    appreciation: float
    reinvested_dividends: float


IndicatorMarker = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class Indicator:
    name: str
    value: float
    marker: IndicatorMarker
    description: str
