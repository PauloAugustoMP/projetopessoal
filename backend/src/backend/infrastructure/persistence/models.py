import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ASSET_CATEGORIES = ("stock", "reit", "fixed_income", "crypto")
TRANSACTION_TYPES = ("buy", "sell")
TRANSACTION_SOURCES = ("manual", "b3_import")
DIVIDEND_TYPES = ("dividend", "jcp", "reit_income", "fixed_income_redemption")
DIVIDEND_STATUSES = ("announced", "paid", "pending_review")
CORPORATE_ACTION_TYPES = ("split", "reverse_split", "bonus_shares", "subscription_rights")


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


class DividendModel(Base):
    __tablename__ = "dividends"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(ForeignKey("assets.ticker"), index=True)
    type: Mapped[str] = mapped_column(
        Enum(*DIVIDEND_TYPES, name="dividend_type", native_enum=False, length=30)
    )
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    gross_value_per_share: Mapped[float] = mapped_column(Numeric(18, 6))
    withholding_tax_rate: Mapped[float] = mapped_column(Numeric(6, 4))
    net_value_per_share: Mapped[float] = mapped_column(Numeric(18, 6))
    # The B3 movement statement only carries the payment date; the ex-date is
    # filled in later (manual entry or the quote provider, Sprint 6).
    ex_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        Enum(*DIVIDEND_STATUSES, name="dividend_status", native_enum=False, length=20),
        default="paid",
    )
    reinvested: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(
        Enum(*TRANSACTION_SOURCES, name="transaction_source", native_enum=False, length=20),
        default="manual",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CorporateActionModel(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(ForeignKey("assets.ticker"), index=True)
    type: Mapped[str] = mapped_column(
        Enum(*CORPORATE_ACTION_TYPES, name="corporate_action_type", native_enum=False, length=30)
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    factor: Mapped[float] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(
        Enum(*TRANSACTION_SOURCES, name="transaction_source", native_enum=False, length=20),
        default="b3_import",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ImportReviewRowModel(Base):
    __tablename__ = "import_review_rows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    row_number: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(500))
    raw_content: Mapped[str] = mapped_column(String(1000))
    filename: Mapped[str] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PositionModel(Base):
    __tablename__ = "positions"

    ticker: Mapped[str] = mapped_column(ForeignKey("assets.ticker"), primary_key=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 6))
    average_price: Mapped[float] = mapped_column(Numeric(18, 6))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
