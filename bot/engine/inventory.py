"""Inventory manager: position tracking, VWAP, PnL, and skew computation."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from bot.utils.logger import get_logger
from bot.utils.math_utils import clamp, safe_divide

logger = get_logger(__name__)


class InventoryManager:
    """
    Tracks XMR position, VWAP avg entry, realized PnL, and computes inventory skew.
    """

    def __init__(self) -> None:
        self._xmr_position: Decimal = Decimal("0")
        self._avg_entry_price: Decimal = Decimal("0")
        self._realized_pnl: Decimal = Decimal("0")

    @property
    def xmr_position(self) -> Decimal:
        return self._xmr_position

    @property
    def avg_entry_price(self) -> Decimal:
        return self._avg_entry_price

    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl

    def on_fill(
        self,
        side: Literal["buy", "sell"],
        price: Decimal,
        size: Decimal,
        fee: Decimal,
    ) -> None:
        """Update position and PnL on a fill event."""
        if side == "buy":
            if self._xmr_position < Decimal("0"):
                # Closing (or reducing) a short position → realize PnL
                closed = min(size, abs(self._xmr_position))
                pnl_delta = (self._avg_entry_price - price) * closed - fee
                self._realized_pnl += pnl_delta
                logger.debug(
                    "Realized PnL on short cover (buy)",
                    closed=float(closed),
                    pnl_delta=float(pnl_delta),
                    total_realized=float(self._realized_pnl),
                )

            # Update position and VWAP for remaining/new long portion
            new_position = self._xmr_position + size
            if new_position > Decimal("0"):
                # Entering or adding to a long — update VWAP
                long_add = size if self._xmr_position >= Decimal("0") else new_position
                self._avg_entry_price = safe_divide(
                    self._avg_entry_price * max(self._xmr_position, Decimal("0")) + price * long_add,
                    new_position,
                    Decimal("0"),
                )
            self._xmr_position = new_position
        else:  # sell
            if self._xmr_position > Decimal("0"):
                # Realize PnL on closed long portion
                closed = min(size, self._xmr_position)
                pnl_delta = (price - self._avg_entry_price) * closed - fee
                self._realized_pnl += pnl_delta
                logger.debug(
                    "Realized PnL on sell",
                    closed=float(closed),
                    pnl_delta=float(pnl_delta),
                    total_realized=float(self._realized_pnl),
                )
                self._xmr_position -= size
                # If we flipped from long to short
                if self._xmr_position < Decimal("0"):
                    short_size = abs(self._xmr_position)
                    self._avg_entry_price = price
                    logger.debug(
                        "Position flipped to short",
                        short_size=float(short_size),
                    )
            else:
                # Already short or flat — increasing short position
                new_position = self._xmr_position - size
                if abs(new_position) > abs(self._xmr_position):
                    # Deepening short: update VWAP of short entry
                    self._avg_entry_price = safe_divide(
                        self._avg_entry_price * abs(self._xmr_position) + price * size,
                        abs(new_position),
                        Decimal("0"),
                    )
                else:
                    # Closing short: realize PnL
                    closed = min(size, abs(self._xmr_position))
                    pnl_delta = (self._avg_entry_price - price) * closed - fee
                    self._realized_pnl += pnl_delta
                    logger.debug(
                        "Realized PnL on short cover",
                        closed=float(closed),
                        pnl_delta=float(pnl_delta),
                        total_realized=float(self._realized_pnl),
                    )
                self._xmr_position = new_position

        logger.debug(
            "Inventory updated",
            position=float(self._xmr_position),
            avg_entry=float(self._avg_entry_price),
            realized_pnl=float(self._realized_pnl),
        )

    def compute_unrealized_pnl(self, fair_price: Decimal) -> Decimal:
        """Compute mark-to-market unrealized PnL."""
        if self._xmr_position == Decimal("0") or self._avg_entry_price == Decimal("0"):
            return Decimal("0")
        return (fair_price - self._avg_entry_price) * self._xmr_position

    def inventory_ratio(self, max_position: float) -> float:
        """Return inventory as fraction of max_position, clamped to [-1, 1]."""
        if max_position == 0:
            return 0.0
        return clamp(float(self._xmr_position) / max_position, -1.0, 1.0)

    def compute_skew(
        self,
        max_position: float,
        skew_factor: float,
    ) -> tuple[float, float]:
        """
        Compute (bid_multiplier, ask_multiplier) for spread adjustment.
        Long position -> widen bid spread, tighten ask spread (want to sell).
        Short position -> tighten bid spread, widen ask spread (want to buy).
        Returns multipliers: > 1.0 means wider spread, < 1.0 means tighter.
        """
        ratio = self.inventory_ratio(max_position)
        bid_mult = 1.0 + skew_factor * ratio
        ask_mult = 1.0 - skew_factor * ratio
        # Clamp to reasonable range to prevent degenerate quotes
        bid_mult = clamp(bid_mult, 0.5, 2.0)
        ask_mult = clamp(ask_mult, 0.5, 2.0)
        return bid_mult, ask_mult
