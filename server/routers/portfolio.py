"""Portfolio endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from bot.engine.market_maker import MarketMaker
from server.dependencies import get_bot
from server.schemas.api_types import PortfolioResponse

router = APIRouter(prefix="/api", tags=["portfolio"])


def _get_mm(bot: Annotated[MarketMaker, Depends(get_bot)]) -> MarketMaker:
    return bot


@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(mm: Annotated[MarketMaker, Depends(_get_mm)]) -> PortfolioResponse:
    s = mm.get_state()
    fair_price = s.fair_price
    # Get balances from exchange client
    from decimal import Decimal
    client = mm._client
    user_state = client.get_user_state()
    usdc = float(user_state.usdc_balance)
    xmr = float(user_state.xmr_balance)
    total = usdc + xmr * fair_price
    return PortfolioResponse(
        usdc_balance=usdc,
        xmr_balance=xmr,
        total_value_usdc=total,
        xmr_price=fair_price,
    )
