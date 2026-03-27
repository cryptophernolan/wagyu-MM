"""Avellaneda-Stoikov market making algorithm (DEFAULT)."""
from __future__ import annotations

import math
from decimal import Decimal

from bot.config import AppConfig
from bot.engine.algorithms.base import QuoteContext, QuoteLevel, QuoteSet
from bot.utils.math_utils import bps_to_multiplier, round_to_tick
from bot.utils.logger import get_logger

logger = get_logger(__name__)

MIN_NOTIONAL = Decimal("10")


class AvellanedaStoikovAlgorithm:
    """
    Avellaneda-Stoikov optimal market making model.

    reservation_price = mid - inventory * gamma * sigma^2 * T
    optimal_spread = gamma * sigma^2 * T + (2/gamma) * ln(1 + gamma/lambda)

    bid = reservation_price - spread/2
    ask = reservation_price + spread/2
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "avellaneda_stoikov"

    def _estimate_lambda(self, ctx: QuoteContext) -> float:
        """Estimate order arrival rate from L2 book depth (volume-weighted)."""
        total_bid_depth = sum(float(s) for _, s in ctx.l2_bids[:5])
        total_ask_depth = sum(float(s) for _, s in ctx.l2_asks[:5])
        avg_depth = (total_bid_depth + total_ask_depth) / 2.0
        # Lambda roughly proportional to depth: deeper book = more order flow
        lam = max(0.5, min(5.0, avg_depth / 10.0))
        return lam

    def compute_quotes(self, ctx: QuoteContext) -> QuoteSet:
        gamma = (
            self._config.avellaneda_stoikov.gamma_calm
            if ctx.regime == "CALM"
            else self._config.avellaneda_stoikov.gamma_volatile
        )

        # T: rolling time horizon in "years" — use window_minutes normalized
        T = self._config.volatility.window_minutes / (365 * 24 * 60)
        # sigma: realized vol as fraction per year
        sigma = ctx.sigma if ctx.sigma > 0 else 0.001
        lam = self._estimate_lambda(ctx)

        inventory = float(ctx.inventory)
        mid = float(ctx.fair_price)

        # Reservation price (skewed by inventory)
        reservation = mid - inventory * gamma * (sigma ** 2) * T

        # Optimal half-spread
        try:
            log_term = math.log(1 + gamma / lam)
        except (ValueError, ZeroDivisionError):
            log_term = 0.0

        half_spread = (gamma * (sigma ** 2) * T) / 2.0 + (1.0 / gamma) * log_term
        # Express as fraction of mid (not absolute $)
        half_spread_frac = half_spread / mid if mid > 0 else half_spread

        # Minimum half-spread: 2 bps (1 maker fee per side)
        min_half_spread_frac = float(bps_to_multiplier(2.0))
        half_spread_frac = max(half_spread_frac, min_half_spread_frac)

        spacing_frac = float(bps_to_multiplier(self._config.spread.level_spacing_bps))
        levels = self._config.trading.order_levels
        level_sizes = self._config.trading.level_sizes

        bids: list[QuoteLevel] = []
        asks: list[QuoteLevel] = []

        reservation_dec = Decimal(str(round(reservation, 6)))

        for i in range(levels):
            extra_frac = spacing_frac * i
            bid_frac = half_spread_frac + extra_frac
            ask_frac = half_spread_frac + extra_frac

            tick = Decimal(str(self._config.exchange.price_tick_size))
            step = Decimal(str(self._config.exchange.size_step))

            bid_price = round_to_tick(
                reservation_dec * (Decimal("1") - Decimal(str(bid_frac))), tick
            )
            ask_price = round_to_tick(
                reservation_dec * (Decimal("1") + Decimal(str(ask_frac))), tick
            )

            if bid_price <= Decimal("0") or ask_price <= Decimal("0"):
                continue

            size_usdc = Decimal(str(level_sizes[i] if i < len(level_sizes) else level_sizes[-1]))
            bid_size = round_to_tick(size_usdc / bid_price, step)
            ask_size = round_to_tick(size_usdc / ask_price, step)

            if bid_price * bid_size >= MIN_NOTIONAL:
                bids.append(QuoteLevel(price=bid_price, size=bid_size, side="bid"))
            if ask_price * ask_size >= MIN_NOTIONAL:
                asks.append(QuoteLevel(price=ask_price, size=ask_size, side="ask"))

        logger.debug(
            "AS quotes computed",
            gamma=gamma, sigma=sigma, T=T, lam=lam,
            reservation=float(reservation_dec),
            half_spread_bps=round(half_spread_frac * 10000, 2),
            bid_levels=len(bids), ask_levels=len(asks)
        )
        return QuoteSet(bids=bids, asks=asks)
