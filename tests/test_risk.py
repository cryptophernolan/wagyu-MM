"""Unit tests for RiskManager."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bot.config import (
    AlgorithmConfig,
    AppConfig,
    AvellanedaStoikovConfig,
    EnvConfig,
    ExchangeConfig,
    InventoryConfig,
    RiskConfig,
    SpreadConfig,
    TradingConfig,
    VolatilityConfig,
)
from bot.risk.risk_manager import RiskManager


def make_config() -> AppConfig:
    return AppConfig(
        exchange=ExchangeConfig(
            api_url="https://api.hyperliquid-testnet.xyz",
            ws_url="wss://api.hyperliquid-testnet.xyz/ws",
        ),
        trading=TradingConfig(),
        algorithm=AlgorithmConfig(),
        avellaneda_stoikov=AvellanedaStoikovConfig(),
        spread=SpreadConfig(),
        inventory=InventoryConfig(max_position_xmr=10.0),
        risk=RiskConfig(
            daily_loss_limit_usdc=50.0, max_drawdown_pct=5.0, stale_feed_seconds=5.0
        ),
        volatility=VolatilityConfig(),
        env=EnvConfig(hl_private_key="", hl_wallet_address=""),
    )


def make_healthy_aggregator() -> MagicMock:
    agg = MagicMock()
    agg.is_halted.return_value = False
    return agg


def make_stale_aggregator() -> MagicMock:
    agg = MagicMock()
    agg.is_halted.return_value = True
    return agg


class TestRiskManager:
    def test_all_ok_passes(self) -> None:
        rm = RiskManager(make_config())
        rm.set_session_start_portfolio(Decimal("1000"))
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("0"),
            portfolio_value=Decimal("1000"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "OK"

    def test_stale_feed_halts(self) -> None:
        rm = RiskManager(make_config())
        result = rm.check_pre_cycle(
            make_stale_aggregator(),
            realized_pnl=Decimal("0"),
            portfolio_value=Decimal("1000"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"
        assert "stale" in (result.reason or "").lower()

    def test_daily_loss_limit_halts(self) -> None:
        rm = RiskManager(make_config())
        rm.set_daily_pnl_start(Decimal("0"))
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("-60"),  # > daily limit of 50
            portfolio_value=Decimal("940"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"

    def test_max_drawdown_halts(self) -> None:
        rm = RiskManager(make_config())
        rm.set_session_start_portfolio(Decimal("1000"))
        # 6% drawdown > 5% limit
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("0"),
            portfolio_value=Decimal("940"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"

    def test_trigger_halt_sets_flag(self) -> None:
        rm = RiskManager(make_config())
        assert not rm.is_halted
        rm.trigger_halt("test reason")
        assert rm.is_halted
        assert rm.halt_reason == "test reason"

    def test_clear_halt(self) -> None:
        rm = RiskManager(make_config())
        rm.trigger_halt("test")
        rm.clear_halt()
        assert not rm.is_halted
        assert rm.halt_reason is None

    def test_halted_state_blocks_cycle(self) -> None:
        rm = RiskManager(make_config())
        rm.trigger_halt("manual halt")
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("0"),
            portfolio_value=Decimal("1000"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"


class TestRiskManagerBoundary:
    """RM-08/09/10 boundary tests from TEST_PLAN.md."""

    def test_rm_08_daily_loss_exactly_at_limit_halts(self) -> None:
        """RM-08: realized_pnl == -daily_loss_limit → HALT (boundary)."""
        rm = RiskManager(make_config())
        rm.set_session_start_portfolio(Decimal("1000"))
        rm.set_daily_pnl_start(Decimal("0"))
        # Exactly at the boundary: -50 = -limit → should HALT
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("-50.00"),
            portfolio_value=Decimal("950"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"

    def test_rm_09_just_under_limit_is_ok(self) -> None:
        """RM-09: realized_pnl == -49.99 (< limit of 50) → OK."""
        rm = RiskManager(make_config())
        rm.set_session_start_portfolio(Decimal("1000"))
        rm.set_daily_pnl_start(Decimal("0"))
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("-49.99"),
            portfolio_value=Decimal("950.01"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "OK"

    def test_rm_10_drawdown_exactly_at_5pct_halts(self) -> None:
        """RM-10: portfolio down exactly 5% → HALT (boundary)."""
        rm = RiskManager(make_config())
        rm.set_session_start_portfolio(Decimal("1000"))
        rm.set_daily_pnl_start(Decimal("0"))
        # 5% down from $1000 = $950
        result = rm.check_pre_cycle(
            make_healthy_aggregator(),
            realized_pnl=Decimal("0"),
            portfolio_value=Decimal("950.00"),
            inventory_xmr=Decimal("0"),
        )
        assert result.status == "HALT"
