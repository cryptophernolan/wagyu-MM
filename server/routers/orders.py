"""Open orders endpoint."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from bot.engine.market_maker import MarketMaker
from server.dependencies import get_bot
from server.schemas.api_types import OrderItem, OrdersResponse

router = APIRouter(prefix="/api", tags=["orders"])


def _get_mm(bot: Annotated[MarketMaker, Depends(get_bot)]) -> MarketMaker:
    return bot


@router.get("/orders", response_model=OrdersResponse)
async def get_orders(mm: Annotated[MarketMaker, Depends(_get_mm)]) -> OrdersResponse:
    now = datetime.now(timezone.utc)
    orders = mm._order_manager.get_open_orders()
    items = [
        OrderItem(
            oid=o.oid,
            side=o.side,
            price=float(o.price),
            size=float(o.size),
            status=o.status,
            age_seconds=(now - o.created_at).total_seconds(),
        )
        for o in orders
    ]
    return OrdersResponse(items=items)
