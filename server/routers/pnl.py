"""PnL summary and history endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from bot.engine.market_maker import MarketMaker
from bot.persistence import repository
from server.dependencies import get_bot
from server.schemas.api_types import PnLHistoryResponse, PnLPoint, PnLSummaryResponse

router = APIRouter(prefix="/api", tags=["pnl"])


def _get_mm(bot: Annotated[MarketMaker, Depends(get_bot)]) -> MarketMaker:
    return bot


TIMEFRAME_MAP: dict[str, int] = {
    "12h": 12, "24h": 24, "7d": 168, "30d": 720, "6m": 4380, "1y": 8760, "all": 87600
}


@router.get("/pnl/summary", response_model=PnLSummaryResponse)
async def get_pnl_summary(mm: Annotated[MarketMaker, Depends(_get_mm)]) -> PnLSummaryResponse:
    s = mm.get_state()
    return PnLSummaryResponse(
        realized=s.realized_pnl,
        unrealized=s.unrealized_pnl,
        total=s.realized_pnl + s.unrealized_pnl,
        daily=s.realized_pnl,
    )


@router.get("/pnl/history", response_model=PnLHistoryResponse)
async def get_pnl_history(timeframe: str = "24h") -> PnLHistoryResponse:
    hours = TIMEFRAME_MAP.get(timeframe, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await repository.get_pnl_history(since)
    points = [
        PnLPoint(
            ts=datetime.fromisoformat(r["timestamp"]).timestamp(),
            total=r["total_pnl"],
            realized=r["realized_pnl"],
        )
        for r in rows
    ]
    return PnLHistoryResponse(points=points)
