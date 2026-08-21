"""Computes and persists one day's portfolio snapshot (docs/business-rules.md §8).

Price resolution order per held ticker: local price_history cache → provider
historical fetch (stored for next time) → latest live quote → cost basis (the
domain calculator's fallback). Provider outages never fail the snapshot.
"""

import logging
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.domain.snapshot_calculator import compute_snapshot
from backend.infrastructure.persistence.models import (
    AssetModel,
    CorporateActionModel,
    DividendModel,
    PortfolioSnapshotModel,
    TransactionModel,
)
from backend.infrastructure.persistence.repositories import (
    SqlAlchemyPriceHistoryRepository,
    SystemStateRepository,
    to_domain_corporate_action,
    to_domain_dividend,
    to_domain_transaction,
)
from backend.ports.market_data_provider import MarketDataProvider, MarketDataUnavailableError

logger = logging.getLogger(__name__)

LAST_SNAPSHOT_DATE_KEY = "last_snapshot_date"
LAST_RUN_AT_KEY = "last_run_at"

HISTORY_FETCH_WINDOW_DAYS = 90


def _ensure_price_coverage(
    session: Session,
    provider: MarketDataProvider,
    ticker: str,
    snapshot_date: str,
    coverage_until: str,
) -> None:
    """Makes sure the local price cache reaches `snapshot_date`, fetching from the
    provider in one go up to `coverage_until` (a catch-up passes today, so a
    multi-day backfill costs a single request per ticker)."""
    history_repo = SqlAlchemyPriceHistoryRepository(session)
    latest = history_repo.latest_date(ticker)
    if latest is not None and latest >= snapshot_date:
        return
    if latest is not None:
        window_start = (date_type.fromisoformat(latest) + timedelta(days=1)).isoformat()
    else:
        window_start = (
            date_type.fromisoformat(snapshot_date) - timedelta(days=HISTORY_FETCH_WINDOW_DAYS)
        ).isoformat()
    try:
        fetched = provider.get_price_history(ticker, window_start, coverage_until)
        if fetched:
            history_repo.save_prices(ticker, fetched)
    except MarketDataUnavailableError:
        logger.warning("Price history unavailable for %s — using what is cached.", ticker)


def _resolve_price(
    session: Session,
    provider: MarketDataProvider,
    ticker: str,
    snapshot_date: str,
    coverage_until: str,
) -> float | None:
    _ensure_price_coverage(session, provider, ticker, snapshot_date, coverage_until)
    price = SqlAlchemyPriceHistoryRepository(session).latest_price_on_or_before(
        ticker, snapshot_date
    )
    if price is not None:
        return price
    try:
        quotes = provider.get_quotes([ticker])
        if ticker in quotes:
            return quotes[ticker].price
    except MarketDataUnavailableError:
        pass
    logger.warning("No price available for %s on %s — falling back to cost.", ticker, snapshot_date)
    return None


def compute_and_store_snapshot(
    session_factory: sessionmaker[Session],
    provider: MarketDataProvider,
    snapshot_date: str,
    coverage_until: str | None = None,
) -> None:
    session = session_factory()
    try:
        transactions = [
            to_domain_transaction(m) for m in session.scalars(select(TransactionModel)).all()
        ]
        corporate_actions = [
            to_domain_corporate_action(m)
            for m in session.scalars(select(CorporateActionModel)).all()
        ]
        dividends = [to_domain_dividend(m) for m in session.scalars(select(DividendModel)).all()]
        categories = {
            asset.ticker: asset.category for asset in session.scalars(select(AssetModel)).all()
        }

        held_tickers = sorted(
            {t.ticker for t in transactions if t.date <= snapshot_date}
        )
        prices: dict[str, float] = {}
        for ticker in held_tickers:
            price = _resolve_price(
                session, provider, ticker, snapshot_date, coverage_until or snapshot_date
            )
            if price is not None:
                prices[ticker] = price

        snapshot = compute_snapshot(
            snapshot_date, transactions, corporate_actions, dividends, prices, categories
        )

        day = date_type.fromisoformat(snapshot_date)
        row = session.get(PortfolioSnapshotModel, day)
        if row is None:
            row = PortfolioSnapshotModel(
                date=day,
                total_value=snapshot.total_value,
                value_by_category=snapshot.value_by_category,
                cumulative_contributions=snapshot.cumulative_contributions,
                cumulative_reinvested_dividends=snapshot.cumulative_reinvested_dividends,
            )
            session.add(row)
        else:
            row.total_value = snapshot.total_value
            row.value_by_category = snapshot.value_by_category
            row.cumulative_contributions = snapshot.cumulative_contributions
            row.cumulative_reinvested_dividends = snapshot.cumulative_reinvested_dividends

        state = SystemStateRepository(session)
        previous = state.get(LAST_SNAPSHOT_DATE_KEY)
        if previous is None or previous < snapshot_date:
            state.set(LAST_SNAPSHOT_DATE_KEY, snapshot_date)
        state.set(LAST_RUN_AT_KEY, datetime.now(timezone.utc).isoformat())
        session.commit()
    finally:
        session.close()
