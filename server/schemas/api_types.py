"""Pydantic v2 response schemas for all FastAPI endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedHealthItem(BaseModel):
    source: str
    healthy: bool
    price: float | None
    latency_ms: float
    last_updated: float


class ToggleState(BaseModel):
    feeds: bool
    wagyu: bool
    quoting: bool
    inv_limit: bool


class StatusResponse(BaseModel):
    state: str
    toggles: ToggleState
    fair_price: float
    regime: str
    inventory_pct: float
    realized_pnl: float
    unrealized_pnl: float
    portfolio_value: float
    open_orders_count: int
    fills_count: int
    last_cycle_ms: float
    cycle_count: int
    feed_health: list[FeedHealthItem]
    halt_reason: str | None
    alerts: list[str]


class ToggleResponse(BaseModel):
    target: str
    enabled: bool


class PortfolioResponse(BaseModel):
    usdc_balance: float
    xmr_balance: float
    total_value_usdc: float
    xmr_price: float


class FillItem(BaseModel):
    id: int
    timestamp: datetime
    oid: str
    side: str
    price: float
    size: float
    fee: float
    is_maker: bool
    mid_price_at_fill: float


class FillsResponse(BaseModel):
    items: list[FillItem]
    total: int
    page: int
    limit: int


class OrderItem(BaseModel):
    oid: str
    side: str
    price: float
    size: float
    status: str
    age_seconds: float


class OrdersResponse(BaseModel):
    items: list[OrderItem]


class PnLSummaryResponse(BaseModel):
    realized: float
    unrealized: float
    total: float
    daily: float


class PnLPoint(BaseModel):
    ts: float
    total: float
    realized: float


class PnLHistoryResponse(BaseModel):
    points: list[PnLPoint]


class PricePoint(BaseModel):
    ts: float
    fair: float
    avg_entry: float | None
    bid1: float | None
    ask1: float | None


class PriceChartResponse(BaseModel):
    points: list[PricePoint]


class BotVsHodlPoint(BaseModel):
    ts: float
    bot_pct: float
    hodl_pct: float


class BotVsHodlResponse(BaseModel):
    points: list[BotVsHodlPoint]


class HealthErrorEntry(BaseModel):
    ts: float
    message: str


class HealthResponse(BaseModel):
    feeds: list[FeedHealthItem]
    errors: list[HealthErrorEntry]


class DailyPnLRow(BaseModel):
    day: int
    date: str
    fills: int
    realized_pnl: float
    fee_rebates: float
    net_pnl: float


class ReportSummary(BaseModel):
    cumulative: float
    avg_per_day: float
    peak_day: DailyPnLRow | None
    worst_day: DailyPnLRow | None
    win_rate: float
    sharpe_annualized: float
    total_days: int
    running_since: str


class DailyReportResponse(BaseModel):
    rows: list[DailyPnLRow]
    summary: ReportSummary
