"""Startup catch-up (docs/business-rules.md §8.1, architecture §4.4): backfills
the daily snapshots missed while the app was off. State advances after every
successful day, so an interrupted run resumes exactly where it stopped."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from backend.application.snapshot_service import (
    LAST_SNAPSHOT_DATE_KEY,
    compute_and_store_snapshot,
)
from backend.domain.snapshot_catchup import compute_missing_snapshot_dates
from backend.infrastructure.persistence.repositories import SystemStateRepository
from backend.ports.market_data_provider import MarketDataProvider

logger = logging.getLogger(__name__)


def run_startup_catchup(
    session_factory: sessionmaker[Session],
    provider: MarketDataProvider,
    today: str,
) -> list[str]:
    """Returns the dates that were backfilled (empty on the very first run)."""
    session = session_factory()
    try:
        last_snapshot_date = SystemStateRepository(session).get(LAST_SNAPSHOT_DATE_KEY)
    finally:
        session.close()

    missing = compute_missing_snapshot_dates(last_snapshot_date, today)
    if missing:
        logger.info(
            "Catch-up: backfilling %d snapshot(s) from %s to %s.",
            len(missing),
            missing[0],
            missing[-1],
        )
    for day in missing:
        # coverage_until=today: the first day's history fetch already covers the
        # whole backfill range, so the provider is hit once per ticker, not per day.
        compute_and_store_snapshot(session_factory, provider, day, coverage_until=today)
    return missing
