"""Request/response models mirroring docs/openapi/openapi.yaml (camelCase on the wire)."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )


class LoginRequest(ApiModel):
    password: str


class LoginResponse(ApiModel):
    access_token: str
    refresh_token: str


class RefreshRequest(ApiModel):
    refresh_token: str


class RefreshResponse(ApiModel):
    access_token: str


class AssetResponse(ApiModel):
    ticker: str
    name: str
    category: Literal["stock", "reit", "fixed_income", "crypto"]
    logo_url: Optional[str] = None


class TransactionInput(ApiModel):
    ticker: str = Field(min_length=1, max_length=20)
    type: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price_per_share: float = Field(ge=0)
    date: date
    fees: Optional[float] = Field(default=None, ge=0)


class TransactionResponse(ApiModel):
    id: str
    ticker: str
    type: Literal["buy", "sell"]
    quantity: float
    price_per_share: float
    date: date
    fees: float
    source: Literal["manual", "b3_import"]
    recalculating: bool


class PositionResponse(ApiModel):
    ticker: str
    category: Literal["stock", "reit", "fixed_income", "crypto"]
    quantity: float
    average_price: float
    current_price: Optional[float] = None
    profit_percentage: Optional[float] = None
    portfolio_percentage: Optional[float] = None
