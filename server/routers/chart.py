"""Chart data endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from bot.persistence import repository
from server.schemas.api_types import BotVsHodlPoint, BotVsHodlResponse, PriceChartResponse, PricePoint

router = APIRouter(prefix="/api", tags=["chart"])

TIMEFRAME_MAP: dict[str, int] = {
    "12h": 12, "24h": 24, "7d": 168, "30d": 720, "6m": 4380, "1y": 8760, "all": 87600
}


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


@router.get("/chart/price", response_model=PriceChartResponse)
async def get_price_chart(timeframe: str = "24h") -> PriceChartResponse:
    hours = TIMEFRAME_MAP.get(timeframe, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await repository.get_price_history(since)
    points = [
        PricePoint(
            ts=_ts(r["timestamp"]),
            fair=r["fair_price"],
            avg_entry=None,
            bid1=r["bid_prices"][0] if r["bid_prices"] else None,
            ask1=r["ask_prices"][0] if r["ask_prices"] else None,
        )
        for r in rows
    ]
    return PriceChartResponse(points=points)


@router.get("/chart/pnl", response_model=PriceChartResponse)
async def get_pnl_chart(timeframe: str = "24h") -> PriceChartResponse:
    hours = TIMEFRAME_MAP.get(timeframe, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = await repository.get_pnl_history(since)
    points = [
        PricePoint(
            ts=_ts(r["timestamp"]),
            fair=r["total_pnl"],
            avg_entry=r["realized_pnl"],
            bid1=None,
            ask1=None,
        )
        for r in rows
    ]
    return PriceChartResponse(points=points)


@router.get("/chart/bot_vs_hodl", response_model=BotVsHodlResponse)
async def get_bot_vs_hodl(timeframe: str = "24h") -> BotVsHodlResponse:
    hours = TIMEFRAME_MAP.get(timeframe, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    pnl_rows = await repository.get_pnl_history(since)
    benchmark = await repository.get_hodl_benchmark()
    if not pnl_rows or not benchmark:
        return BotVsHodlResponse(points=[])
    start_portfolio = (
        benchmark.get("usdc_balance", 0.0)
        + benchmark.get("xmr_balance", 0.0) * benchmark.get("xmr_price", 0.0)
    )
    if start_portfolio == 0:
        return BotVsHodlResponse(points=[])
    hodl_xmr = float(benchmark.get("xmr_balance", 0.0))
    hodl_usdc = float(benchmark.get("usdc_balance", 0.0))
    benchmark_price = float(benchmark.get("xmr_price", 0.0))
    price_rows = await repository.get_price_history(since)
    price_map: dict[int, float] = {int(_ts(r["timestamp"])): r["fair_price"] for r in price_rows}

    points: list[BotVsHodlPoint] = []
    for row in pnl_rows:
        ts = _ts(row["timestamp"])
        bot_pnl = float(row["total_pnl"])
        bot_pct = (bot_pnl / start_portfolio) * 100 if start_portfolio else 0.0
        nearest_price = next(
            (price_map[k] for k in sorted(price_map.keys()) if abs(k - ts) < 120),
            benchmark_price,
        )
        hodl_value = hodl_usdc + hodl_xmr * nearest_price
        hodl_pct = ((hodl_value - start_portfolio) / start_portfolio) * 100 if start_portfolio else 0.0
        points.append(BotVsHodlPoint(ts=ts, bot_pct=bot_pct, hodl_pct=hodl_pct))
    return BotVsHodlResponse(points=points)
