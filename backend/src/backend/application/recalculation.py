"""Retroactive recalculation engine (docs/business-rules.md §2).

Recalculates an asset's position by replaying its ENTIRE transaction history in
chronological order — never incrementally — which is what makes backdated
entries and edits safe, and makes the run idempotent. Triggered as a background
task on every transaction create/edit/delete; while it runs, the ticker is
flagged so the API can answer `recalculating: true`.

Snapshot and dividend-eligibility recalculation (steps 2-3 of the business
rule) land in Sprint 3 together with the market data provider.
"""

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from backend.domain.position_history import replay_history
from backend.infrastructure.persistence.repositories import (
    SqlAlchemyCorporateActionRepository,
    SqlAlchemyPositionRepository,
    SqlAlchemyTransactionRepository,
)

logger = logging.getLogger(__name__)

_recalculating: set[str] = set()
_lock = threading.Lock()


def is_recalculating(ticker: str) -> bool:
    with _lock:
        return ticker in _recalculating


def recalculate_position(session_factory: sessionmaker[Session], ticker: str) -> None:
    with _lock:
        _recalculating.add(ticker)
    try:
        session = session_factory()
        try:
            transactions = SqlAlchemyTransactionRepository(session).list_by_ticker(ticker)
            corporate_actions = SqlAlchemyCorporateActionRepository(session).list_by_ticker(ticker)
            positions = SqlAlchemyPositionRepository(session)
            if not transactions:
                positions.delete(ticker)
            else:
                result = replay_history(ticker, transactions, corporate_actions)
                positions.upsert(
                    ticker,
                    quantity=result.position.quantity,
                    average_price=result.position.average_price,
                )
            session.commit()
        finally:
            session.close()
    except Exception:
        logger.exception("Recalculation failed for %s", ticker)
        raise
    finally:
        with _lock:
            _recalculating.discard(ticker)
