import uuid
from datetime import date as date_type

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.errors import ApiError
from backend.api.schemas import TransactionInput, TransactionResponse
from backend.application.recalculation import is_recalculating, recalculate_position
from backend.domain.average_price_calculator import InsufficientPositionError
from backend.domain.entities import Transaction
from backend.domain.position_history import replay_history
from backend.infrastructure.persistence.database import get_session_factory
from backend.infrastructure.persistence.models import AssetModel, TransactionModel
from backend.infrastructure.persistence.repositories import (
    SqlAlchemyCorporateActionRepository,
    to_domain_transaction,
)

router = APIRouter(
    prefix="/transactions", tags=["transactions"], dependencies=[Depends(require_auth)]
)


def _to_response(model: TransactionModel, recalculating: bool) -> TransactionResponse:
    return TransactionResponse(
        id=str(model.id),
        ticker=model.ticker,
        type=model.type,  # type: ignore[arg-type]
        quantity=float(model.quantity),
        price_per_share=float(model.price_per_share),
        date=model.date,
        fees=float(model.fees),
        source=model.source,  # type: ignore[arg-type]
        recalculating=recalculating,
    )


def _require_known_ticker(session: SessionDep, ticker: str) -> None:
    if session.get(AssetModel, ticker) is None:
        raise ApiError(
            400,
            "UNKNOWN_TICKER",
            f"Ticker {ticker} is not a known asset. Confirm the asset before recording "
            "the transaction (docs/business-rules.md §10).",
        )


def _validate_history(session: SessionDep, ticker: str, transactions: list[Transaction]) -> None:
    """Sanity check: replaying the prospective history (corporate actions included)
    must never sell more than the position available on that date
    (docs/business-rules.md §10)."""
    corporate_actions = SqlAlchemyCorporateActionRepository(session).list_by_ticker(ticker)
    try:
        replay_history(ticker, transactions, corporate_actions)
    except InsufficientPositionError as error:
        raise ApiError(422, "SELL_EXCEEDS_POSITION", str(error)) from error


def _existing_domain_transactions(
    session: SessionDep, ticker: str, exclude_id: uuid.UUID | None = None
) -> list[Transaction]:
    query = select(TransactionModel).where(TransactionModel.ticker == ticker)
    if exclude_id is not None:
        query = query.where(TransactionModel.id != exclude_id)
    return [to_domain_transaction(row) for row in session.scalars(query).all()]


def _get_or_404(session: SessionDep, transaction_id: uuid.UUID) -> TransactionModel:
    model = session.get(TransactionModel, transaction_id)
    if model is None:
        raise ApiError(404, "TRANSACTION_NOT_FOUND", f"Transaction {transaction_id} not found.")
    return model


def _schedule_recalculation(background_tasks: BackgroundTasks, *tickers: str) -> None:
    for ticker in dict.fromkeys(tickers):
        background_tasks.add_task(recalculate_position, get_session_factory(), ticker)


@router.get("", response_model=list[TransactionResponse], response_model_by_alias=True)
def list_transactions(
    session: SessionDep,
    ticker: str | None = None,
    from_: date_type | None = Query(default=None, alias="from"),
    to: date_type | None = None,
) -> list[TransactionResponse]:
    query = select(TransactionModel).order_by(
        TransactionModel.date.desc(), TransactionModel.created_at.desc()
    )
    if ticker:
        query = query.where(TransactionModel.ticker == ticker.upper())
    if from_ is not None:
        query = query.where(TransactionModel.date >= from_)
    if to is not None:
        query = query.where(TransactionModel.date <= to)
    return [
        _to_response(row, is_recalculating(row.ticker))
        for row in session.scalars(query).all()
    ]


@router.post(
    "",
    status_code=201,
    response_model=TransactionResponse,
    response_model_by_alias=True,
)
def create_transaction(
    body: TransactionInput, session: SessionDep, background_tasks: BackgroundTasks
) -> TransactionResponse:
    ticker = body.ticker.upper()
    _require_known_ticker(session, ticker)

    model = TransactionModel(
        id=uuid.uuid4(),
        ticker=ticker,
        type=body.type,
        quantity=body.quantity,
        price_per_share=body.price_per_share,
        date=body.date,
        fees=body.fees or 0.0,
        source="manual",
    )
    candidate = _existing_domain_transactions(session, ticker)
    candidate.append(
        Transaction(
            id=str(model.id),
            ticker=ticker,
            type=body.type,
            quantity=body.quantity,
            price_per_share=body.price_per_share,
            date=body.date.isoformat(),
            fees=body.fees or 0.0,
        )
    )
    _validate_history(session, ticker, candidate)

    session.add(model)
    session.commit()
    _schedule_recalculation(background_tasks, ticker)
    return _to_response(model, recalculating=True)


@router.get("/{transaction_id}", response_model=TransactionResponse, response_model_by_alias=True)
def get_transaction(transaction_id: uuid.UUID, session: SessionDep) -> TransactionResponse:
    model = _get_or_404(session, transaction_id)
    return _to_response(model, is_recalculating(model.ticker))


@router.patch("/{transaction_id}", response_model=TransactionResponse, response_model_by_alias=True)
def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionInput,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TransactionResponse:
    model = _get_or_404(session, transaction_id)
    old_ticker = model.ticker
    new_ticker = body.ticker.upper()
    _require_known_ticker(session, new_ticker)

    updated = Transaction(
        id=str(model.id),
        ticker=new_ticker,
        type=body.type,
        quantity=body.quantity,
        price_per_share=body.price_per_share,
        date=body.date.isoformat(),
        fees=body.fees or 0.0,
    )
    new_history = _existing_domain_transactions(session, new_ticker, exclude_id=model.id)
    new_history.append(updated)
    _validate_history(session, new_ticker, new_history)
    if old_ticker != new_ticker:
        _validate_history(
            session, old_ticker, _existing_domain_transactions(session, old_ticker, exclude_id=model.id)
        )

    model.ticker = new_ticker
    model.type = body.type
    model.quantity = body.quantity
    model.price_per_share = body.price_per_share
    model.date = body.date
    model.fees = body.fees or 0.0
    session.commit()
    _schedule_recalculation(background_tasks, old_ticker, new_ticker)
    return _to_response(model, recalculating=True)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: uuid.UUID, session: SessionDep, background_tasks: BackgroundTasks
) -> None:
    model = _get_or_404(session, transaction_id)
    ticker = model.ticker
    _validate_history(
        session, ticker, _existing_domain_transactions(session, ticker, exclude_id=model.id)
    )
    session.delete(model)
    session.commit()
    _schedule_recalculation(background_tasks, ticker)
