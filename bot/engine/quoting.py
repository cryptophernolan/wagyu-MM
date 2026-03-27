"""Quote calculator — delegates to selected algorithm and applies inventory skew."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from bot.config import AppConfig
from bot.engine.algorithms.base import (
    QuoteContext,
    QuoteLevel,
    QuoteSet,
    QuotingAlgorithm,
    get_algorithm,
)
from bot.utils.logger import get_logger
from bot.utils.math_utils import round_to_tick

logger = get_logger(__name__)

MIN_NOTIONAL = Decimal("10")
TICK_SIZE = Decimal("0.01")
SIZE_STEP = Decimal("0.01")


class QuoteCalculator:
    """Wraps chosen algorithm and applies post-algorithm inventory skew."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._algorithm: QuotingAlgorithm = get_algorithm(config.algorithm.name, config)
        logger.info("QuoteCalculator initialized", algorithm=self._algorithm.name)

    def compute_quotes(
        self,
        fair_price: Decimal,
        regime: Literal["CALM", "VOLATILE"],
        sigma: float,
        inventory: Decimal,
        inv_skew: tuple[float, float],
        l2_bids: list[tuple[Decimal, Decimal]],
        l2_asks: list[tuple[Decimal, Decimal]],
    ) -> QuoteSet:
        ctx = QuoteContext(
            fair_price=fair_price,
            inventory=inventory,
            sigma=sigma,
            regime=regime,
            config=self._config,
            l2_bids=l2_bids,
            l2_asks=l2_asks,
        )

        raw_quotes = self._algorithm.compute_quotes(ctx)
        bid_mult, ask_mult = inv_skew

        # Apply inventory skew to spreads (adjust distance from mid)
        adjusted_bids: list[QuoteLevel] = []
        for level in raw_quotes.bids:
            dist_from_fair = fair_price - level.price
            new_dist = dist_from_fair * Decimal(str(bid_mult))
            new_price = round_to_tick(fair_price - new_dist, TICK_SIZE)
            if new_price <= Decimal("0"):
                continue
            new_size = round_to_tick(level.size, SIZE_STEP)
            if new_price * new_size >= MIN_NOTIONAL:
                adjusted_bids.append(
                    QuoteLevel(price=new_price, size=new_size, side="bid")
                )

        adjusted_asks: list[QuoteLevel] = []
        for level in raw_quotes.asks:
            dist_from_fair = level.price - fair_price
            new_dist = dist_from_fair * Decimal(str(ask_mult))
            new_price = round_to_tick(fair_price + new_dist, TICK_SIZE)
            if new_price <= Decimal("0"):
                continue
            new_size = round_to_tick(level.size, SIZE_STEP)
            if new_price * new_size >= MIN_NOTIONAL:
                adjusted_asks.append(
                    QuoteLevel(price=new_price, size=new_size, side="ask")
                )

        return QuoteSet(bids=adjusted_bids, asks=adjusted_asks)
