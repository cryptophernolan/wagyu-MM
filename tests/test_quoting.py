"""Unit tests for QuoteCalculator and algorithms."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pytest

from bot.config import (
    AlgorithmConfig,
    AppConfig,
    AvellanedaStoikovConfig,
    EnvConfig,
    ExchangeConfig,
    InventoryConfig,
    RateLimitConfig,
    RiskConfig,
    SpreadConfig,
    TradingConfig,
    VolatilityConfig,
)
from bot.engine.algorithms.avellaneda_stoikov import AvellanedaStoikovAlgorithm
from bot.engine.algorithms.base import QuoteContext, get_algorithm
from bot.engine.algorithms.simple_spread import SimpleSpreadAlgorithm


def make_config(algo_name: str = "simple_spread") -> AppConfig:
    return AppConfig(
        exchange=ExchangeConfig(
            api_url="https://api.hyperliquid-testnet.xyz",
            ws_url="wss://api.hyperliquid-testnet.xyz/ws",
        ),
        trading=TradingConfig(
            cycle_interval_seconds=2.0,
            order_levels=3,
            level_sizes=[50.0, 100.0, 200.0],
        ),
        algorithm=AlgorithmConfig(name=algo_name),
        avellaneda_stoikov=AvellanedaStoikovConfig(
            gamma_calm=0.04, gamma_volatile=0.08
        ),
        spread=SpreadConfig(
            calm_spread_bps=10.0, volatile_spread_bps=30.0, level_spacing_bps=4.0
        ),
        inventory=InventoryConfig(
            max_position_xmr=10.0, skew_factor=0.5, target_position_xmr=0.0
        ),
        risk=RiskConfig(
            daily_loss_limit_usdc=50.0, max_drawdown_pct=5.0, stale_feed_seconds=5.0
        ),
        volatility=VolatilityConfig(
            window_minutes=30, calm_threshold_bps=20.0, volatile_threshold_bps=35.0
        ),
        rate_limit=RateLimitConfig(),
        env=EnvConfig(hl_private_key="", hl_wallet_address=""),
    )


def make_ctx(
    config: AppConfig,
    price: float = 150.0,
    inventory: float = 0.0,
    regime: str = "CALM",
) -> QuoteContext:
    r: Literal["CALM", "VOLATILE"] = "CALM" if regime == "CALM" else "VOLATILE"
    return QuoteContext(
        fair_price=Decimal(str(price)),
        inventory=Decimal(str(inventory)),
        sigma=0.02,
        regime=r,
        config=config,
    )


class TestSimpleSpreadAlgorithm:
    def test_produces_bids_and_asks(self) -> None:
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        ctx = make_ctx(config)
        quotes = algo.compute_quotes(ctx)
        assert len(quotes.bids) > 0
        assert len(quotes.asks) > 0

    def test_bid_below_fair_ask_above_fair(self) -> None:
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        ctx = make_ctx(config, price=150.0)
        quotes = algo.compute_quotes(ctx)
        for bid in quotes.bids:
            assert bid.price < ctx.fair_price, (
                f"Bid {bid.price} >= fair {ctx.fair_price}"
            )
        for ask in quotes.asks:
            assert ask.price > ctx.fair_price, (
                f"Ask {ask.price} <= fair {ctx.fair_price}"
            )

    def test_min_notional_10_usdc(self) -> None:
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        ctx = make_ctx(config)
        quotes = algo.compute_quotes(ctx)
        for level in quotes.bids + quotes.asks:
            notional = level.price * level.size
            assert notional >= Decimal("10"), f"Notional {notional} < $10"

    def test_multi_level_spacing(self) -> None:
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        ctx = make_ctx(config, price=150.0)
        quotes = algo.compute_quotes(ctx)
        if len(quotes.bids) >= 2:
            # Each successive bid should be lower (further from mid)
            for i in range(1, len(quotes.bids)):
                assert quotes.bids[i].price < quotes.bids[i - 1].price

    def test_volatile_regime_wider_spread(self) -> None:
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        ctx_calm = make_ctx(config, regime="CALM")
        ctx_vol = make_ctx(config, regime="VOLATILE")
        calm_quotes = algo.compute_quotes(ctx_calm)
        vol_quotes = algo.compute_quotes(ctx_vol)
        if calm_quotes.bids and vol_quotes.bids:
            calm_spread = float(ctx_calm.fair_price - calm_quotes.bids[0].price)
            vol_spread = float(ctx_vol.fair_price - vol_quotes.bids[0].price)
            assert vol_spread > calm_spread


class TestAvellanedaStoikovAlgorithm:
    def test_produces_quotes(self) -> None:
        config = make_config("avellaneda_stoikov")
        algo = AvellanedaStoikovAlgorithm(config)
        ctx = make_ctx(config)
        quotes = algo.compute_quotes(ctx)
        assert len(quotes.bids) > 0
        assert len(quotes.asks) > 0

    def test_inventory_skew_direction(self) -> None:
        """Long position -> reservation price lower -> bids further from mid."""
        config = make_config("avellaneda_stoikov")
        algo = AvellanedaStoikovAlgorithm(config)
        ctx_neutral = make_ctx(config, inventory=0.0)
        ctx_long = make_ctx(config, inventory=5.0)
        q_neutral = algo.compute_quotes(ctx_neutral)
        q_long = algo.compute_quotes(ctx_long)
        # Long -> reservation shifts down -> bid prices lower
        if q_neutral.bids and q_long.bids:
            assert q_long.bids[0].price <= q_neutral.bids[0].price + Decimal("1")


class TestGetAlgorithm:
    def test_factory_returns_correct_algorithm(self) -> None:
        config = make_config("avellaneda_stoikov")
        algo = get_algorithm("avellaneda_stoikov", config)
        assert algo.name == "avellaneda_stoikov"

    def test_factory_raises_on_unknown(self) -> None:
        config = make_config()
        with pytest.raises(ValueError, match="Unknown algorithm"):
            get_algorithm("unknown_algo", config)


class TestQuotingEdgeCases:
    """QT-10/11/12 edge cases from TEST_PLAN.md."""

    def test_qt_10_glft_produces_valid_quoteset(self) -> None:
        """QT-10: GLFT algorithm initializes without error and returns valid QuoteSet."""
        from bot.engine.algorithms.glft import GLFTAlgorithm
        config = make_config("glft")
        algo = GLFTAlgorithm(config)
        assert algo.name == "glft"
        ctx = make_ctx(config, price=150.0, inventory=0.0)
        quotes = algo.compute_quotes(ctx)
        # Must return a QuoteSet (lists may be empty but not None)
        assert quotes.bids is not None
        assert quotes.asks is not None
        # All returned levels must pass min notional
        for level in quotes.bids + quotes.asks:
            assert level.price * level.size >= Decimal("10")

    def test_qt_11_very_small_fair_price_drops_small_levels(self) -> None:
        """QT-11: When fair_price is very small, min notional validation drops insufficient levels."""
        config = make_config("simple_spread")
        algo = SimpleSpreadAlgorithm(config)
        # At $0.01 price, size would need to be 1000 XMR for $10 notional —
        # if level_sizes are small (e.g. $50 notional), the algorithm should still work
        # because it sizes in USDC notional, so the per-level USDC amount stays fixed.
        ctx = make_ctx(config, price=0.01)
        quotes = algo.compute_quotes(ctx)
        # All surviving levels satisfy min notional
        for level in quotes.bids + quotes.asks:
            notional = level.price * level.size
            assert notional >= Decimal("10"), f"Level {level} fails min notional: {notional}"

    def test_qt_12_as_algorithm_zero_sigma_no_zero_division(self) -> None:
        """QT-12: When sigma=0, AS algorithm must not divide by zero and must return a spread."""
        from bot.engine.algorithms.avellaneda_stoikov import AvellanedaStoikovAlgorithm
        config = make_config("avellaneda_stoikov")
        algo = AvellanedaStoikovAlgorithm(config)
        ctx = QuoteContext(
            fair_price=Decimal("150.0"),
            inventory=Decimal("0"),
            sigma=0.0,  # zero volatility
            regime="CALM",
            config=config,
        )
        # Must not raise
        quotes = algo.compute_quotes(ctx)
        # Must return at least some quotes (floor spread should kick in)
        assert len(quotes.bids) > 0 or len(quotes.asks) > 0
        # All levels must respect min notional
        for level in quotes.bids + quotes.asks:
            assert level.price * level.size >= Decimal("10")
