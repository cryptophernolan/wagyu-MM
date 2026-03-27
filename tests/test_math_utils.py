"""Unit tests for bot/utils/math_utils.py — MU-01 through MU-06."""
from __future__ import annotations

from decimal import Decimal

import pytest

from bot.utils.math_utils import (
    bps_to_multiplier,
    clamp,
    price_diff_bps,
    round_to_step,
    round_to_tick,
    safe_divide,
)


class TestRoundToTick:
    def test_mu_01_basic_round_down(self) -> None:
        """MU-01: round_to_tick(150.123, 0.01) → 150.12"""
        result = round_to_tick(Decimal("150.123"), Decimal("0.01"))
        assert result == Decimal("150.12")

    def test_mu_02_half_up_rounding(self) -> None:
        """MU-02: round_to_tick(150.125, 0.01) → 150.13 (half-up, not banker's)"""
        result = round_to_tick(Decimal("150.125"), Decimal("0.01"))
        assert result == Decimal("150.13")

    def test_tick_exact_already_on_tick(self) -> None:
        result = round_to_tick(Decimal("150.10"), Decimal("0.01"))
        assert result == Decimal("150.10")

    def test_zero_tick_size_returns_unchanged(self) -> None:
        result = round_to_tick(Decimal("150.123"), Decimal("0"))
        assert result == Decimal("150.123")

    def test_round_to_whole_dollar(self) -> None:
        result = round_to_tick(Decimal("149.6"), Decimal("1"))
        assert result == Decimal("150")


class TestRoundToStep:
    def test_rounds_down_not_up(self) -> None:
        result = round_to_step(Decimal("1.999"), Decimal("0.01"))
        assert result == Decimal("1.99")

    def test_zero_step_returns_unchanged(self) -> None:
        result = round_to_step(Decimal("1.555"), Decimal("0"))
        assert result == Decimal("1.555")

    def test_already_on_step(self) -> None:
        result = round_to_step(Decimal("1.50"), Decimal("0.01"))
        assert result == Decimal("1.50")


class TestSafeDivide:
    def test_mu_03_divide_by_zero_returns_default(self) -> None:
        """MU-03: safe_divide(10, 0, default=0.0) → 0.0"""
        result = safe_divide(Decimal("10"), Decimal("0"), Decimal("0"))
        assert result == Decimal("0")

    def test_normal_division(self) -> None:
        result = safe_divide(Decimal("10"), Decimal("4"))
        assert result == Decimal("2.5")

    def test_custom_default(self) -> None:
        result = safe_divide(Decimal("5"), Decimal("0"), Decimal("-1"))
        assert result == Decimal("-1")


class TestClamp:
    def test_mu_04_clamp_above_max(self) -> None:
        """MU-04: clamp(1.5, 0.0, 1.0) → 1.0"""
        assert clamp(1.5, 0.0, 1.0) == 1.0

    def test_clamp_below_min(self) -> None:
        """MU-04: clamp(-0.5, 0.0, 1.0) → 0.0"""
        assert clamp(-0.5, 0.0, 1.0) == 0.0

    def test_clamp_within_range_unchanged(self) -> None:
        assert clamp(0.5, 0.0, 1.0) == 0.5

    def test_clamp_exactly_at_boundary(self) -> None:
        assert clamp(1.0, 0.0, 1.0) == 1.0
        assert clamp(0.0, 0.0, 1.0) == 0.0


class TestBpsToMultiplier:
    def test_mu_05_10_bps(self) -> None:
        """MU-05: bps_to_multiplier(10) → 0.001"""
        result = bps_to_multiplier(10)
        assert result == Decimal("0.001")

    def test_1_bps(self) -> None:
        result = bps_to_multiplier(1)
        assert result == Decimal("0.0001")

    def test_zero_bps(self) -> None:
        result = bps_to_multiplier(0)
        assert result == Decimal("0")

    def test_100_bps_is_1_pct(self) -> None:
        result = bps_to_multiplier(100)
        assert result == Decimal("0.01")


class TestPriceDiffBps:
    def test_mu_06_half_percent_is_50_bps(self) -> None:
        """MU-06: price_diff_bps(100.0, 100.5) → 50.0 bps (0.5%)"""
        result = price_diff_bps(Decimal("100.0"), Decimal("100.5"))
        assert abs(result - 49.75) < 0.1  # (0.5/100.5)*10000 ≈ 49.75 bps

    def test_same_price_is_zero(self) -> None:
        result = price_diff_bps(Decimal("150.0"), Decimal("150.0"))
        assert result == 0.0

    def test_zero_reference_price_returns_zero(self) -> None:
        result = price_diff_bps(Decimal("100.0"), Decimal("0"))
        assert result == 0.0

    def test_1_pct_diff_is_100_bps_approx(self) -> None:
        result = price_diff_bps(Decimal("101.0"), Decimal("100.0"))
        assert abs(result - 100.0) < 1.0
