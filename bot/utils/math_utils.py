"""Math utilities for price/size rounding and safe arithmetic."""
from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round price to nearest tick (half-up rounding)."""
    if tick_size <= Decimal("0"):
        return price
    return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size


def round_to_step(size: Decimal, step_size: Decimal) -> Decimal:
    """Round size down to nearest step (truncate)."""
    if step_size <= Decimal("0"):
        return size
    return (size / step_size).quantize(Decimal("1"), rounding=ROUND_DOWN) * step_size


def safe_divide(a: Decimal, b: Decimal, default: Decimal = Decimal("0")) -> Decimal:
    """Divide a by b; return default if b is zero."""
    if b == Decimal("0"):
        return default
    return a / b


def clamp(val: float, min_val: float, max_val: float) -> float:
    """Clamp val to [min_val, max_val]."""
    return max(min_val, min(max_val, val))


def bps_to_multiplier(bps: float) -> Decimal:
    """Convert basis points to a multiplier (e.g., 10 bps -> 0.001)."""
    return Decimal(str(bps)) / Decimal("10000")


def price_diff_bps(price_a: Decimal, price_b: Decimal) -> float:
    """Return absolute difference between two prices in basis points."""
    if price_b == Decimal("0"):
        return 0.0
    return float(abs(price_a - price_b) / price_b * Decimal("10000"))
