import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ASSET_CATEGORIES = ("stock", "reit", "fixed_income", "crypto")
TRANSACTION_TYPES = ("buy", "sell")
TRANSACTION_SOURCES = ("manual", "b3_import")


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetModel(Base):
    __tablename__ = "assets"

    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(
        Enum(*ASSET_CATEGORIES, name="asset_category", native_enum=False, length=20)
    )
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(ForeignKey("assets.ticker"), index=True)
    type: Mapped[str] = mapped_column(
        Enum(*TRANSACTION_TYPES, name="transaction_type", native_enum=False, length=10)
    )
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    price_per_share: Mapped[float] = mapped_column(Numeric(18, 6))
    date: Mapped[date] = mapped_column(Date, index=True)
    fees: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    source: Mapped[str] = mapped_column(
        Enum(*TRANSACTION_SOURCES, name="transaction_source", native_enum=False, length=20),
        default="manual",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PositionModel(Base):
    __tablename__ = "positions"

    ticker: Mapped[str] = mapped_column(ForeignKey("assets.ticker"), primary_key=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    average_price: Mapped[float] = mapped_column(Numeric(18, 6))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
