"""Unit tests for InventoryManager."""
from __future__ import annotations

from decimal import Decimal

import pytest

from bot.engine.inventory import InventoryManager


class TestInventoryManager:
    def test_initial_state(self) -> None:
        inv = InventoryManager()
        assert inv.xmr_position == Decimal("0")
        assert inv.realized_pnl == Decimal("0")

    def test_buy_fill_increases_position(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("150.0"), Decimal("1.0"), Decimal("0.015"))
        assert inv.xmr_position == Decimal("1.0")
        assert inv.avg_entry_price == Decimal("150.0")

    def test_vwap_after_multiple_buys(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("100.0"), Decimal("1.0"), Decimal("0"))
        inv.on_fill("buy", Decimal("200.0"), Decimal("1.0"), Decimal("0"))
        # VWAP should be 150
        assert inv.avg_entry_price == Decimal("150.0")
        assert inv.xmr_position == Decimal("2.0")

    def test_sell_fill_realizes_profit(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("100.0"), Decimal("1.0"), Decimal("0"))
        inv.on_fill("sell", Decimal("110.0"), Decimal("1.0"), Decimal("0"))
        # PnL = (110 - 100) * 1 = 10
        assert inv.realized_pnl == Decimal("10.0")
        assert inv.xmr_position == Decimal("0")

    def test_unrealized_pnl(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("100.0"), Decimal("2.0"), Decimal("0"))
        unrealized = inv.compute_unrealized_pnl(Decimal("120.0"))
        assert unrealized == Decimal("40.0")  # (120 - 100) * 2

    def test_inventory_ratio_clamped(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("150.0"), Decimal("15.0"), Decimal("0"))
        ratio = inv.inventory_ratio(max_position=10.0)
        assert ratio == 1.0  # Clamped at max

    def test_skew_long_widens_bid(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("150.0"), Decimal("5.0"), Decimal("0"))
        bid_mult, ask_mult = inv.compute_skew(max_position=10.0, skew_factor=0.5)
        assert bid_mult > 1.0  # Long -> wider bid spread
        assert ask_mult < 1.0  # Long -> tighter ask spread

    def test_skew_neutral_no_change(self) -> None:
        inv = InventoryManager()
        bid_mult, ask_mult = inv.compute_skew(max_position=10.0, skew_factor=0.5)
        assert bid_mult == 1.0
        assert ask_mult == 1.0


class TestInventoryEdgeCases:
    """IV-09/10/11 edge cases from TEST_PLAN.md."""

    def test_iv_09_sell_from_flat_creates_short_position(self) -> None:
        """IV-09: Sell when position=0 → short position; buy to close earns PnL."""
        inv = InventoryManager()
        # Sell 1 XMR @ $150 → short 1 XMR, avg_entry = 150
        inv.on_fill("sell", Decimal("150.0"), Decimal("1.0"), Decimal("0"))
        assert inv.xmr_position == Decimal("-1.0")
        # Buy to close @ $140 → profit = (150 - 140) * 1 = $10
        inv.on_fill("buy", Decimal("140.0"), Decimal("1.0"), Decimal("0"))
        assert inv.xmr_position == Decimal("0")
        assert inv.realized_pnl == Decimal("10.0")

    def test_iv_10_fee_deducted_from_realized_pnl(self) -> None:
        """IV-10: Fee is subtracted from realized PnL when closing a position."""
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("100.0"), Decimal("1.0"), Decimal("0"))
        # Sell with fee=0.05 → realized = (110-100)*1 - 0.05 = 9.95
        inv.on_fill("sell", Decimal("110.0"), Decimal("1.0"), Decimal("0.05"))
        assert inv.realized_pnl == Decimal("9.95")

    def test_iv_11_vwap_five_fills_weighted_correctly(self) -> None:
        """IV-11: VWAP with 5 fills at different prices matches manual calculation."""
        inv = InventoryManager()
        fills = [
            (Decimal("100.0"), Decimal("2.0")),
            (Decimal("120.0"), Decimal("1.0")),
            (Decimal("80.0"), Decimal("3.0")),
            (Decimal("110.0"), Decimal("2.0")),
            (Decimal("90.0"), Decimal("2.0")),
        ]
        total_cost = sum(p * s for p, s in fills)
        total_size = sum(s for _, s in fills)
        expected_vwap = total_cost / total_size

        for price, size in fills:
            inv.on_fill("buy", price, size, Decimal("0"))

        assert inv.xmr_position == total_size
        # Allow small floating-point rounding in Decimal arithmetic
        diff = abs(inv.avg_entry_price - expected_vwap)
        assert diff < Decimal("0.0001"), f"VWAP mismatch: {inv.avg_entry_price} != {expected_vwap}"
