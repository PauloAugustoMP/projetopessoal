"""price_poll job (docs/architecture.md §4.1): during B3 market hours, fetches
quotes for held tickers and pushes them to connected clients over WebSocket."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.infrastructure.market_data.brapi_provider import is_b3_market_hours
from backend.infrastructure.persistence.models import PositionModel
from backend.ports.market_data_provider import MarketDataProvider, MarketDataUnavailableError

logger = logging.getLogger(__name__)


def poll_prices(
    session_factory: sessionmaker[Session],
    provider: MarketDataProvider,
    broadcast: "callable",
    force: bool = False,
) -> None:
    if not force and not is_b3_market_hours():
        return

    session = session_factory()
    try:
        tickers = list(
            session.scalars(
                select(PositionModel.ticker).where(PositionModel.quantity > 0)
            ).all()
        )
    finally:
        session.close()
    if not tickers:
        return

    try:
        quotes = provider.get_quotes(tickers)
    except MarketDataUnavailableError as error:
        logger.warning("price_poll: provider unavailable (%s).", error)
        return

    if quotes:
        broadcast(
            {
                "type": "quotes",
                "at": datetime.now(timezone.utc).isoformat(),
                "quotes": {
                    ticker: {"price": quote.price, "changePercent": quote.change_percent}
                    for ticker, quote in quotes.items()
                },
            }
        )
