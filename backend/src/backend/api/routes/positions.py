from fastapi import APIRouter, Depends
from sqlalchemy import select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.schemas import PositionResponse
from backend.infrastructure.persistence.models import AssetModel, PositionModel

router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[PositionResponse], response_model_by_alias=True)
def list_positions(session: SessionDep) -> list[PositionResponse]:
    # currentPrice / profitPercentage / portfolioPercentage depend on the quote
    # provider (Sprint 3) and stay null until then.
    rows = session.execute(
        select(PositionModel, AssetModel.category)
        .join(AssetModel, AssetModel.ticker == PositionModel.ticker)
        .where(PositionModel.quantity > 0)
        .order_by(PositionModel.ticker)
    ).all()
    return [
        PositionResponse(
            ticker=position.ticker,
            category=category,
            quantity=float(position.quantity),
            average_price=float(position.average_price),
        )
        for position, category in rows
    ]
