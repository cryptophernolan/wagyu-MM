"""GLFT (Guéant-Lehalle-Fernandez-Tapia) market making algorithm."""
from __future__ import annotations

import math
from decimal import Decimal

from bot.config import AppConfig
from bot.engine.algorithms.base import QuoteContext, QuoteLevel, QuoteSet
from bot.utils.math_utils import bps_to_multiplier, round_to_tick
from bot.utils.logger import get_logger

logger = get_logger(__name__)

MIN_NOTIONAL = Decimal("10")


class GLFTAlgorithm:
    """
    GLFT closed-form solution with hard inventory bounds.
    Uses same mathematical structure as AS but with hard stop when max_position reached.
    More conservative than AS — stops quoting in one direction when bounds are hit.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "glft"

    def compute_quotes(self, ctx: QuoteContext) -> QuoteSet:
        gamma = 0.06  # Fixed risk aversion for GLFT
        T = self._config.volatility.window_minutes / (365 * 24 * 60)
        sigma = ctx.sigma if ctx.sigma > 0 else 0.001

        inventory = float(ctx.inventory)
        max_pos = self._config.inventory.max_position_xmr
        mid = float(ctx.fair_price)

        # Hard inventory bounds
        at_max_long = inventory >= max_pos
        at_max_short = inventory <= -max_pos

        reservation = mid - inventory * gamma * (sigma ** 2) * T
        try:
            half_spread = (gamma * (sigma ** 2) * T) / 2.0 + (1.0 / gamma) * math.log(1 + gamma)
        except (ValueError, ZeroDivisionError):
            half_spread = 0.0
        half_spread_frac = max(half_spread / mid if mid > 0 else half_spread, float(bps_to_multiplier(2.0)))

        spacing_frac = float(bps_to_multiplier(self._config.spread.level_spacing_bps))
        levels = self._config.trading.order_levels
        level_sizes = self._config.trading.level_sizes
        reservation_dec = Decimal(str(round(reservation, 6)))

        bids: list[QuoteLevel] = []
        asks: list[QuoteLevel] = []

        for i in range(levels):
            extra_frac = spacing_frac * i
            size_usdc = Decimal(str(level_sizes[i] if i < len(level_sizes) else level_sizes[-1]))

            tick = Decimal(str(self._config.exchange.price_tick_size))
            step = Decimal(str(self._config.exchange.size_step))

            if not at_max_long:
                bid_frac = half_spread_frac + extra_frac
                bid_price = round_to_tick(reservation_dec * (Decimal("1") - Decimal(str(bid_frac))), tick)
                if bid_price > Decimal("0"):
                    bid_size = round_to_tick(size_usdc / bid_price, step)
                    if bid_price * bid_size >= MIN_NOTIONAL:
                        bids.append(QuoteLevel(price=bid_price, size=bid_size, side="bid"))

            if not at_max_short:
                ask_frac = half_spread_frac + extra_frac
                ask_price = round_to_tick(reservation_dec * (Decimal("1") + Decimal(str(ask_frac))), tick)
                if ask_price > Decimal("0"):
                    ask_size = round_to_tick(size_usdc / ask_price, step)
                    if ask_price * ask_size >= MIN_NOTIONAL:
                        asks.append(QuoteLevel(price=ask_price, size=ask_size, side="ask"))

        return QuoteSet(bids=bids, asks=asks)
