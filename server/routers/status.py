"""Bot status and toggle endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from bot.engine.market_maker import MarketMaker
from server.dependencies import get_bot
from server.schemas.api_types import FeedHealthItem, StatusResponse, ToggleResponse, ToggleState

router = APIRouter(prefix="/api", tags=["status"])


def _get_mm(bot: Annotated[MarketMaker, Depends(get_bot)]) -> MarketMaker:
    return bot


@router.get("/status", response_model=StatusResponse)
async def get_status(mm: Annotated[MarketMaker, Depends(_get_mm)]) -> StatusResponse:
    s = mm.get_state()
    return StatusResponse(
        state=s.state,
        toggles=ToggleState(
            feeds=s.feeds_enabled,
            wagyu=s.wagyu_enabled,
            quoting=s.quoting_enabled,
            inv_limit=s.inv_limit_enabled,
        ),
        fair_price=s.fair_price,
        regime=s.regime,
        inventory_pct=s.inventory_pct,
        realized_pnl=s.realized_pnl,
        unrealized_pnl=s.unrealized_pnl,
        portfolio_value=s.portfolio_value,
        open_orders_count=s.open_orders_count,
        fills_count=s.fills_count,
        last_cycle_ms=s.last_cycle_ms,
        cycle_count=s.cycle_count,
        feed_health=[FeedHealthItem(**fh) for fh in s.feed_health],
        halt_reason=s.halt_reason,
        alerts=s.alerts[-10:],
    )


@router.post("/toggle/{target}", response_model=ToggleResponse)
async def toggle(target: str, mm: Annotated[MarketMaker, Depends(_get_mm)]) -> ToggleResponse:
    valid_targets = {"feeds", "wagyu", "quoting", "inv_limit"}
    if target not in valid_targets:
        raise HTTPException(status_code=400, detail=f"Invalid toggle target: {target}")
    toggles = {
        "feeds": mm.toggle_feeds,
        "wagyu": mm.toggle_wagyu,
        "quoting": mm.toggle_quoting,
        "inv_limit": mm.toggle_inv_limit,
    }
    enabled: bool = toggles[target]()
    return ToggleResponse(target=target, enabled=enabled)
