from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.schemas import (
    GrowthBreakdownResponse,
    PortfolioSnapshotResponse,
    PortfolioSummaryResponse,
)
from backend.infrastructure.market_data.brapi_provider import today_isoformat
from backend.infrastructure.market_data.factory import get_market_data_provider
from backend.infrastructure.persistence.models import (
    DividendModel,
    PortfolioSnapshotModel,
    PositionModel,
)
from backend.ports.market_data_provider import MarketDataUnavailableError, Quote

router = APIRouter(prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(require_auth)])


def fetch_quotes_or_empty(tickers: list[str]) -> dict[str, Quote]:
    """Live quotes are an enrichment: a provider outage degrades the numbers to
    cost basis instead of failing the request."""
    if not tickers:
        return {}
    try:
        return get_market_data_provider().get_quotes(tickers)
    except MarketDataUnavailableError:
        return {}


@router.get("/summary", response_model=PortfolioSummaryResponse, response_model_by_alias=True)
def portfolio_summary(session: SessionDep) -> PortfolioSummaryResponse:
    positions = session.scalars(
        select(PositionModel).where(PositionModel.quantity > 0)
    ).all()
    quotes = fetch_quotes_or_empty([p.ticker for p in positions])

    total_value = 0.0
    change_weighted = 0.0
    change_weight = 0.0
    for position in positions:
        quote = quotes.get(position.ticker)
        price = quote.price if quote else float(position.average_price)
        value = float(position.quantity) * price
        total_value += value
        if quote and quote.change_percent is not None:
            change_weighted += value * quote.change_percent
            change_weight += value

    today = date_type.fromisoformat(today_isoformat())
    month_start = today.replace(day=1)
    dividends = session.scalars(
        select(DividendModel).where(DividendModel.payment_date >= today - timedelta(days=365))
    ).all()
    month_dividends = sum(
        float(d.net_value_per_share) * float(d.quantity)
        for d in dividends
        if d.payment_date >= month_start and d.payment_date <= today
    )
    year_dividends = sum(
        float(d.net_value_per_share) * float(d.quantity) for d in dividends if d.payment_date <= today
    )

    month_baseline = session.scalars(
        select(PortfolioSnapshotModel)
        .where(PortfolioSnapshotModel.date < month_start)
        .order_by(PortfolioSnapshotModel.date.desc())
        .limit(1)
    ).first()
    month_profit = None
    if month_baseline is not None and float(month_baseline.total_value) > 0:
        month_profit = (
            (total_value - float(month_baseline.total_value))
            / float(month_baseline.total_value)
            * 100
        )

    return PortfolioSummaryResponse(
        total_value=total_value,
        today_change_percentage=(change_weighted / change_weight) if change_weight else None,
        month_profit_percentage=month_profit,
        month_dividends=month_dividends,
        average_dy=(year_dividends / total_value * 100) if total_value else None,
        asset_count=len(positions),
    )


@router.get(
    "/snapshots", response_model=list[PortfolioSnapshotResponse], response_model_by_alias=True
)
def portfolio_snapshots(
    session: SessionDep,
    from_: date_type | None = Query(default=None, alias="from"),
    to: date_type | None = None,
) -> list[PortfolioSnapshotResponse]:
    query = select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.date)
    if from_ is not None:
        query = query.where(PortfolioSnapshotModel.date >= from_)
    if to is not None:
        query = query.where(PortfolioSnapshotModel.date <= to)
    return [
        PortfolioSnapshotResponse(
            date=row.date,
            total_value=float(row.total_value),
            value_by_category={k: float(v) for k, v in (row.value_by_category or {}).items()},
            cumulative_contributions=float(row.cumulative_contributions),
            cumulative_reinvested_dividends=float(row.cumulative_reinvested_dividends),
        )
        for row in session.scalars(query).all()
    ]


@router.get(
    "/growth-breakdown", response_model=GrowthBreakdownResponse, response_model_by_alias=True
)
def growth_breakdown(
    session: SessionDep,
    from_: date_type | None = Query(default=None, alias="from"),
    to: date_type | None = None,
) -> GrowthBreakdownResponse:
    """Breakdown by residual (docs/business-rules.md §8): the three parts always
    add up to the observed total change between the period's first and last snapshots."""
    query = select(PortfolioSnapshotModel).order_by(PortfolioSnapshotModel.date)
    if from_ is not None:
        query = query.where(PortfolioSnapshotModel.date >= from_)
    if to is not None:
        query = query.where(PortfolioSnapshotModel.date <= to)
    snapshots = session.scalars(query).all()
    if len(snapshots) < 2:
        return GrowthBreakdownResponse(
            total_change=0, contributions=0, appreciation=0, reinvested_dividends=0
        )

    first, last = snapshots[0], snapshots[-1]
    total_change = float(last.total_value) - float(first.total_value)
    contributions = float(last.cumulative_contributions) - float(first.cumulative_contributions)
    reinvested = float(last.cumulative_reinvested_dividends) - float(
        first.cumulative_reinvested_dividends
    )
    return GrowthBreakdownResponse(
        total_change=total_change,
        contributions=contributions,
        appreciation=total_change - contributions - reinvested,
        reinvested_dividends=reinvested,
    )
