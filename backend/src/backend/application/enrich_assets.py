"""Fills in catalog details the B3 statement cannot provide — logo and the
provider's display name.

Runs after an import, in the background: the statement alone is enough to record
the asset (ticker, name, category), so this never blocks and never fails the
import. A provider outage simply leaves the catalog as the statement wrote it.

What it will and won't overwrite: the logo is filled whenever it is missing,
since a statement never carries one. The name is only replaced when all we have
is the ticker itself — B3's wording ("TRX REAL ESTATE FDO INV IMOB") is not
obviously worse than the provider's, and silently rewriting a name the user
already recognizes would be a regression, not an enrichment.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.infrastructure.persistence.models import AssetModel
from backend.ports.market_data_provider import MarketDataProvider, MarketDataUnavailableError

logger = logging.getLogger(__name__)


def enrich_assets(
    session_factory: sessionmaker[Session],
    provider: MarketDataProvider,
    tickers: list[str],
) -> int:
    """Returns how many catalog entries were improved."""
    if not tickers:
        return 0

    session = session_factory()
    try:
        assets = {
            asset.ticker: asset
            for asset in session.scalars(
                select(AssetModel).where(AssetModel.ticker.in_(tickers))
            ).all()
        }
        pending = [
            ticker
            for ticker, asset in assets.items()
            if asset.logo_url is None or asset.name == ticker
        ]
        if not pending:
            return 0

        try:
            quotes = provider.get_quotes(pending)
        except MarketDataUnavailableError as error:
            logger.info("Asset enrichment skipped — provider unavailable (%s).", error)
            return 0

        improved = 0
        for ticker, quote in quotes.items():
            asset = assets.get(ticker)
            if asset is None:
                continue
            changed = False
            if asset.logo_url is None and quote.logo_url:
                asset.logo_url = quote.logo_url[:500]
                changed = True
            if asset.name == ticker and quote.name:
                asset.name = quote.name[:120]
                changed = True
            if changed:
                improved += 1

        session.commit()
        if improved:
            logger.info("Enriched %d asset(s) from the market data provider.", improved)
        return improved
    finally:
        session.close()
