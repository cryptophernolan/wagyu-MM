"""Fills history endpoint."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from bot.persistence import repository
from server.schemas.api_types import FillItem, FillsResponse

router = APIRouter(prefix="/api", tags=["fills"])


def _parse_ts(ts: str) -> datetime:
    """Parse ISO timestamp string to datetime."""
    return datetime.fromisoformat(ts)


@router.get("/fills", response_model=FillsResponse)
async def get_fills(page: int = 1, limit: int = 50) -> FillsResponse:
    items, total = await repository.get_fills(page=page, limit=limit)
    fill_items = [
        FillItem(
            id=f["id"],
            timestamp=_parse_ts(f["timestamp"]),
            oid=f["oid"],
            side=f["side"],
            price=f["price"],
            size=f["size"],
            fee=f["fee"],
            is_maker=f["is_maker"],
            mid_price_at_fill=f["mid_price_at_fill"],
        )
        for f in items
    ]
    return FillsResponse(items=fill_items, total=total, page=page, limit=limit)
