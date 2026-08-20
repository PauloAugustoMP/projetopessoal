from fastapi import APIRouter, Depends
from sqlalchemy import select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.schemas import CorporateActionResponse
from backend.infrastructure.persistence.models import CorporateActionModel

router = APIRouter(
    prefix="/corporate-actions",
    tags=["corporate-actions"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[CorporateActionResponse], response_model_by_alias=True)
def list_corporate_actions(
    session: SessionDep, ticker: str | None = None
) -> list[CorporateActionResponse]:
    query = select(CorporateActionModel).order_by(CorporateActionModel.date)
    if ticker:
        query = query.where(CorporateActionModel.ticker == ticker.upper())
    return [
        CorporateActionResponse(
            id=str(row.id),
            ticker=row.ticker,
            type=row.type,  # type: ignore[arg-type]
            date=row.date,
            factor=float(row.factor),
            source=row.source,  # type: ignore[arg-type]
        )
        for row in session.scalars(query).all()
    ]
