"""Health tab endpoints."""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends

from bot.engine.market_maker import MarketMaker
from server.dependencies import get_bot
from server.schemas.api_types import FeedHealthItem, HealthErrorEntry, HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


def _get_mm(bot: Annotated[MarketMaker, Depends(get_bot)]) -> MarketMaker:
    return bot


@router.get("/health", response_model=HealthResponse)
async def get_health(mm: Annotated[MarketMaker, Depends(_get_mm)]) -> HealthResponse:
    s = mm.get_state()
    feeds = [
        FeedHealthItem(
            source=fh["source"],
            healthy=fh["healthy"],
            price=fh.get("price"),
            latency_ms=fh.get("latency_ms", 0.0),
            last_updated=fh.get("last_updated", 0.0),
        )
        for fh in s.feed_health
    ]
    errors = [
        HealthErrorEntry(ts=time.time(), message=alert)
        for alert in s.alerts[-20:]
    ]
    return HealthResponse(feeds=feeds, errors=errors)
