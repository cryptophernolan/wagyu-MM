"""Simple symmetric spread algorithm — for testing/benchmarking only."""
from __future__ import annotations

from decimal import Decimal

from bot.config import AppConfig
from bot.engine.algorithms.base import QuoteContext, QuoteLevel, QuoteSet
from bot.utils.math_utils import bps_to_multiplier, round_to_tick


class SimpleSpreadAlgorithm:
    """Fixed spread around mid price. No inventory management. Testing only."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "simple_spread"

    def compute_quotes(self, ctx: QuoteContext) -> QuoteSet:
        spread_bps = (
            self._config.spread.calm_spread_bps
            if ctx.regime == "CALM"
            else self._config.spread.volatile_spread_bps
        )
        half_spread = bps_to_multiplier(spread_bps / 2)
        spacing = bps_to_multiplier(self._config.spread.level_spacing_bps)
        tick = Decimal(str(self._config.exchange.price_tick_size))
        step = Decimal(str(self._config.exchange.size_step))
        min_notional = Decimal("10")
        levels = self._config.trading.order_levels
        level_sizes = self._config.trading.level_sizes

        bids: list[QuoteLevel] = []
        asks: list[QuoteLevel] = []

        for i in range(levels):
            extra = spacing * Decimal(i)
            bid_price = round_to_tick(ctx.fair_price * (Decimal("1") - half_spread - extra), tick)
            ask_price = round_to_tick(ctx.fair_price * (Decimal("1") + half_spread + extra), tick)
            size_usdc = Decimal(str(level_sizes[i] if i < len(level_sizes) else level_sizes[-1]))
            size_base = round_to_tick(size_usdc / bid_price, step)
            if bid_price * size_base >= min_notional:
                bids.append(QuoteLevel(price=bid_price, size=size_base, side="bid"))
            size_base_ask = round_to_tick(size_usdc / ask_price, step)
            if ask_price * size_base_ask >= min_notional:
                asks.append(QuoteLevel(price=ask_price, size=size_base_ask, side="ask"))

        return QuoteSet(bids=bids, asks=asks)
