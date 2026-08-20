from fastapi import APIRouter, Depends
from sqlalchemy import or_, select

from backend.api.dependencies import SessionDep, require_auth
from backend.api.errors import ApiError
from backend.api.schemas import AssetResponse
from backend.infrastructure.persistence.models import AssetModel

router = APIRouter(prefix="/assets", tags=["assets"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[AssetResponse], response_model_by_alias=True)
def search_assets(session: SessionDep, q: str | None = None) -> list[AssetModel]:
    query = select(AssetModel).order_by(AssetModel.ticker)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(AssetModel.ticker.ilike(pattern), AssetModel.name.ilike(pattern))
        )
    return list(session.scalars(query.limit(20)).all())


@router.get("/{ticker}", response_model=AssetResponse, response_model_by_alias=True)
def get_asset(ticker: str, session: SessionDep) -> AssetModel:
    asset = session.get(AssetModel, ticker.upper())
    if asset is None:
        raise ApiError(404, "ASSET_NOT_FOUND", f"Asset {ticker.upper()} not found.")
    return asset
