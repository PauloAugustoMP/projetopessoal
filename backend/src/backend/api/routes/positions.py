from fastapi import APIRouter, Depends
from sqlalchemy import select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.routes.portfolio import fetch_quotes_or_empty
from backend.api.schemas import PositionResponse
from backend.infrastructure.persistence.models import AssetModel, PositionModel

router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[PositionResponse], response_model_by_alias=True)
def list_positions(session: SessionDep) -> list[PositionResponse]:
    rows = session.execute(
        select(PositionModel, AssetModel.category)
        .join(AssetModel, AssetModel.ticker == PositionModel.ticker)
        .where(PositionModel.quantity > 0)
        .order_by(PositionModel.ticker)
    ).all()
    quotes = fetch_quotes_or_empty([position.ticker for position, _ in rows])

    values: dict[str, float] = {}
    for position, _ in rows:
        quote = quotes.get(position.ticker)
        price = quote.price if quote else None
        values[position.ticker] = float(position.quantity) * (
            price if price is not None else float(position.average_price)
        )
    total_value = sum(values.values())

    responses: list[PositionResponse] = []
    for position, category in rows:
        quote = quotes.get(position.ticker)
        average_price = float(position.average_price)
        current_price = quote.price if quote else None
        profit = None
        if current_price is not None and average_price > 0:
            profit = (current_price - average_price) / average_price * 100
        responses.append(
            PositionResponse(
                ticker=position.ticker,
                category=category,
                quantity=float(position.quantity),
                average_price=average_price,
                current_price=current_price,
                profit_percentage=profit,
                portfolio_percentage=(
                    values[position.ticker] / total_value * 100 if total_value else None
                ),
            )
        )
    return responses
