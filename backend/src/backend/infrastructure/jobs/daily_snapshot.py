"""daily_snapshot job (docs/architecture.md §4.5): records the day's
PortfolioSnapshot after market close. Failures are logged loudly — there is no
on-call team, so the "last job run" panel (SystemState) is the visibility."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from backend.application.snapshot_service import compute_and_store_snapshot
from backend.infrastructure.market_data.brapi_provider import today_isoformat
from backend.ports.market_data_provider import MarketDataProvider

logger = logging.getLogger(__name__)


def run_daily_snapshot(
    session_factory: sessionmaker[Session], provider: MarketDataProvider
) -> None:
    try:
        compute_and_store_snapshot(session_factory, provider, today_isoformat())
    except Exception:
        logger.exception("daily_snapshot failed — today's portfolio value was NOT recorded.")
        raise
