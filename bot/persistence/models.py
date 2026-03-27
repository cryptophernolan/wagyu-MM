"""SQLAlchemy 2.0 ORM models for the market maker database."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    oid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "buy" | "sell"
    price: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, nullable=False)
    is_maker: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mid_price_at_fill: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    oid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fair_price: Mapped[float] = mapped_column(Float, nullable=False)
    bid_prices: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    ask_prices: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    mid_hl: Mapped[float | None] = mapped_column(Float, nullable=True)
    mid_kraken: Mapped[float | None] = mapped_column(Float, nullable=True)


class PnLSnapshot(Base):
    __tablename__ = "pnl_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_value_usdc: Mapped[float] = mapped_column(Float, nullable=False)


class HodlBenchmark(Base):
    __tablename__ = "hodl_benchmark"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    xmr_price: Mapped[float] = mapped_column(Float, nullable=False)
    usdc_balance: Mapped[float] = mapped_column(Float, nullable=False)
    xmr_balance: Mapped[float] = mapped_column(Float, nullable=False)
