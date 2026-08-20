"""B3 statement import use case (docs/business-rules.md §7 and §10).

Pipeline: parse → deduplicate → persist → derive corporate-action factors →
batch sanity check → recalculate affected tickers. Rows that cannot be decided
automatically (ambiguous duplicates, unknown tickers, underivable factors,
positions that would go negative) are queued for manual review instead of
failing the import.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.domain.average_price_calculator import InsufficientPositionError
from backend.domain.dividend_withholding import net_value_per_share, withholding_rate_for
from backend.domain.entities import CorporateAction, Transaction
from backend.domain.position_history import position_before_date, replay_history
from backend.domain.statement_dedup import match_transaction
from backend.infrastructure.b3_import.statement_parser import (
    ParsedCorporateActionEvent,
    ParsedStatement,
)
from backend.infrastructure.persistence.models import (
    AssetModel,
    CorporateActionModel,
    DividendModel,
    ImportReviewRowModel,
    TransactionModel,
)
from backend.infrastructure.persistence.repositories import (
    to_domain_corporate_action,
    to_domain_transaction,
)


@dataclass
class ImportResult:
    transactions_created: int = 0
    dividends_created: int = 0
    corporate_actions_created: int = 0
    duplicates_skipped: int = 0
    rows_for_manual_review: list[dict] = field(default_factory=list)
    affected_tickers: set[str] = field(default_factory=set)
    # Tickers whose post-import history is inconsistent (sell exceeds position):
    # flagged for review, and excluded from recalculation until the user fixes them.
    inconsistent_tickers: set[str] = field(default_factory=set)


def _derive_factor(
    event: ParsedCorporateActionEvent,
    transactions: list[Transaction],
    corporate_actions: list[CorporateAction],
) -> float | None:
    """Derives the multiplicative factor from the credited/debited quantity and the
    position held just before the event (see parser docstring for B3 semantics)."""
    before = position_before_date(event.ticker, event.date, transactions, corporate_actions)
    if before.quantity <= 0:
        return None

    if event.type == "split":
        return (before.quantity + event.quantity) / before.quantity
    if event.type == "bonus_shares":
        return event.quantity / before.quantity
    if event.type == "reverse_split":
        if event.direction == "debit":  # shares removed
            remaining = before.quantity - event.quantity
            return remaining / before.quantity if remaining > 0 else None
        # credit: the new total replaces the old position
        return event.quantity / before.quantity if event.quantity < before.quantity else None
    return None


def import_b3_statement(
    session: Session, statement: ParsedStatement, filename: str
) -> ImportResult:
    result = ImportResult()
    review: list[tuple[int, str, str]] = [
        (r.row, r.reason, r.raw) for r in statement.review_rows
    ]

    known_tickers = set(session.scalars(select(AssetModel.ticker)).all())

    def ticker_known(row: int, ticker: str, raw: str = "") -> bool:
        if ticker in known_tickers:
            return True
        review.append((row, f"Unknown ticker {ticker} — confirm the asset first.", raw))
        return False

    # --- transactions (chronological order matters for the later factor derivation)
    for trade in sorted(statement.trades, key=lambda t: t.date):
        if not ticker_known(trade.row, trade.ticker):
            continue
        existing = [
            to_domain_transaction(m)
            for m in session.scalars(
                select(TransactionModel).where(TransactionModel.ticker == trade.ticker)
            ).all()
        ]
        candidate = Transaction(
            id=str(uuid.uuid4()),
            ticker=trade.ticker,
            type=trade.type,
            quantity=trade.quantity,
            price_per_share=trade.price_per_share,
            date=trade.date,
        )
        outcome = match_transaction(candidate, existing)
        if outcome == "duplicate":
            result.duplicates_skipped += 1
            continue
        if outcome == "ambiguous":
            review.append(
                (
                    trade.row,
                    f"Ambiguous duplicate: more than one existing {trade.ticker} transaction "
                    f"matches date/quantity/price.",
                    "",
                )
            )
            continue
        session.add(
            TransactionModel(
                id=uuid.UUID(candidate.id),
                ticker=trade.ticker,
                type=trade.type,
                quantity=trade.quantity,
                price_per_share=trade.price_per_share,
                date=date_type.fromisoformat(trade.date),
                fees=0,
                source="b3_import",
            )
        )
        session.flush()
        result.transactions_created += 1
        result.affected_tickers.add(trade.ticker)

    # --- dividends
    for dividend in statement.dividends:
        if not ticker_known(dividend.row, dividend.ticker):
            continue
        duplicate = session.scalars(
            select(DividendModel).where(
                DividendModel.ticker == dividend.ticker,
                DividendModel.type == dividend.type,
                DividendModel.payment_date == date_type.fromisoformat(dividend.payment_date),
            )
        ).all()
        if any(
            abs(float(d.gross_value_per_share) - dividend.gross_value_per_share) <= 0.01
            for d in duplicate
        ):
            result.duplicates_skipped += 1
            continue
        rate = withholding_rate_for(dividend.type)
        session.add(
            DividendModel(
                id=uuid.uuid4(),
                ticker=dividend.ticker,
                type=dividend.type,
                quantity=dividend.quantity,
                gross_value_per_share=dividend.gross_value_per_share,
                withholding_tax_rate=rate,
                net_value_per_share=net_value_per_share(
                    dividend.type, dividend.gross_value_per_share
                ),
                ex_date=None,
                payment_date=date_type.fromisoformat(dividend.payment_date),
                status="paid",
                source="b3_import",
            )
        )
        result.dividends_created += 1

    # --- corporate actions (factor derived against the position on that date)
    for event in sorted(statement.corporate_actions, key=lambda e: e.date):
        if not ticker_known(event.row, event.ticker):
            continue
        already = session.scalars(
            select(CorporateActionModel).where(
                CorporateActionModel.ticker == event.ticker,
                CorporateActionModel.type == event.type,
                CorporateActionModel.date == date_type.fromisoformat(event.date),
            )
        ).first()
        if already is not None:
            result.duplicates_skipped += 1
            continue

        transactions = [
            to_domain_transaction(m)
            for m in session.scalars(
                select(TransactionModel).where(TransactionModel.ticker == event.ticker)
            ).all()
        ]
        actions = [
            to_domain_corporate_action(m)
            for m in session.scalars(
                select(CorporateActionModel).where(CorporateActionModel.ticker == event.ticker)
            ).all()
        ]
        factor = _derive_factor(event, transactions, actions)
        if factor is None or factor <= 0:
            review.append(
                (
                    event.row,
                    f"Could not derive the {event.type} factor for {event.ticker}: no position "
                    f"held on {event.date} (or inconsistent quantities).",
                    "",
                )
            )
            continue
        session.add(
            CorporateActionModel(
                id=uuid.uuid4(),
                ticker=event.ticker,
                type=event.type,
                date=date_type.fromisoformat(event.date),
                factor=factor,
                source="b3_import",
            )
        )
        session.flush()
        result.corporate_actions_created += 1
        result.affected_tickers.add(event.ticker)

    # --- batch sanity check (docs/business-rules.md §10): flags, never rejects
    for ticker in sorted(result.affected_tickers):
        transactions = [
            to_domain_transaction(m)
            for m in session.scalars(
                select(TransactionModel).where(TransactionModel.ticker == ticker)
            ).all()
        ]
        actions = [
            to_domain_corporate_action(m)
            for m in session.scalars(
                select(CorporateActionModel).where(CorporateActionModel.ticker == ticker)
            ).all()
        ]
        try:
            replay_history(ticker, transactions, actions)
        except InsufficientPositionError as error:
            result.inconsistent_tickers.add(ticker)
            review.append((0, f"Inconsistent history after import: {error}", ""))

    for row_number, reason, raw in review:
        session.add(
            ImportReviewRowModel(
                id=uuid.uuid4(),
                row_number=row_number,
                reason=reason,
                raw_content=raw[:1000],
                filename=filename[:255],
            )
        )
        result.rows_for_manual_review.append({"row": row_number, "reason": reason})

    session.commit()
    return result
