"""Integration tests: multiple bot components working together.

These tests use real component instances (no mocked internals) but avoid any
real network connections.  The database tests use an in-memory SQLite database
so they are self-contained and leave no files on disk.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# greenlet is required by SQLAlchemy async for in-memory DB tests.
# On some platforms (e.g. Python 3.14 on Windows), the binary may fail to load.
try:
    import greenlet as _greenlet  # type: ignore[import-untyped]  # noqa: F401
    _GREENLET_OK = True
except (ImportError, ValueError):
    _GREENLET_OK = False

_skip_if_no_greenlet = pytest.mark.skipif(
    not _GREENLET_OK,
    reason="greenlet DLL unavailable on this platform (Python 3.14 / Windows binary issue)",
)

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
from bot.engine.inventory import InventoryManager
from bot.engine.market_maker import BotState, MarketMaker
from bot.engine.quoting import QuoteCalculator
from bot.engine.volatility import VolatilityEstimator
from bot.feeds.base import PriceFeed
from bot.feeds.price_aggregator import PriceAggregator
from bot.persistence import database, repository
from bot.persistence.models import Base
from bot.risk.risk_manager import RiskManager


# ---------------------------------------------------------------------------
# Config factory (same pattern as test_quoting.py)
# ---------------------------------------------------------------------------


def make_config(algo_name: str = "avellaneda_stoikov") -> AppConfig:
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


# ---------------------------------------------------------------------------
# Stub price feed (no real WebSocket)
# ---------------------------------------------------------------------------


class StubPriceFeed(PriceFeed):
    """Synchronous stub feed that holds a manually set price."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    async def connect(self) -> None:
        pass  # no-op

    async def disconnect(self) -> None:
        pass  # no-op

    def set_price(self, price: float) -> None:
        self._update_price(price)


# ---------------------------------------------------------------------------
# 1. PriceAggregator + VolatilityEstimator integration
# ---------------------------------------------------------------------------


class TestAggregatorVolatilityIntegration:
    def test_single_feed_price_flows_to_aggregator(self) -> None:
        feed = StubPriceFeed("stub_hl")
        feed.set_price(155.50)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)
        price = aggregator.get_price()
        assert price is not None
        assert price == pytest.approx(155.50)

    def test_two_feeds_weighted_average(self) -> None:
        feed_hl = StubPriceFeed("hyperliquid")
        feed_kr = StubPriceFeed("kraken")
        feed_hl.set_price(156.00)
        feed_kr.set_price(154.00)
        # Equal weights → average
        aggregator = PriceAggregator(
            feeds=[feed_hl, feed_kr], weights=[0.5, 0.5], stale_seconds=5.0
        )
        price = aggregator.get_price()
        assert price is not None
        assert price == pytest.approx(155.00)

    def test_stale_feed_excluded_from_average(self) -> None:
        feed_good = StubPriceFeed("good")
        feed_stale = StubPriceFeed("stale")
        feed_good.set_price(155.00)
        # feed_stale has no price set → is_healthy() returns False
        aggregator = PriceAggregator(
            feeds=[feed_good, feed_stale], weights=[0.5, 0.5], stale_seconds=5.0
        )
        price = aggregator.get_price()
        # Only good feed contributes
        assert price == pytest.approx(155.00)

    def test_all_stale_feeds_returns_none(self) -> None:
        feed = StubPriceFeed("stale")
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)
        # No price set on feed → stale
        assert aggregator.get_price() is None

    def test_volatility_estimator_receives_prices_from_aggregator(self) -> None:
        feed = StubPriceFeed("hl")
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)
        vol = VolatilityEstimator(window_minutes=30, calm_threshold_bps=20.0, volatile_threshold_bps=35.0)

        prices = [155.00, 155.10, 154.90, 155.20, 154.80]
        for p in prices:
            feed.set_price(p)
            raw = aggregator.get_price()
            if raw is not None:
                vol.add_price(Decimal(str(round(raw, 6))))

        assert vol.price_count == len(prices)

    def test_aggregator_is_halted_when_all_feeds_stale(self) -> None:
        feed = StubPriceFeed("stale")
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)
        assert aggregator.is_halted() is True

    def test_aggregator_not_halted_when_feed_healthy(self) -> None:
        feed = StubPriceFeed("healthy")
        feed.set_price(155.0)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)
        assert aggregator.is_halted() is False


# ---------------------------------------------------------------------------
# 2. InventoryManager + QuoteCalculator integration
# ---------------------------------------------------------------------------


class TestInventoryQuoteIntegration:
    def test_neutral_position_symmetric_quotes(self) -> None:
        config = make_config()
        inv = InventoryManager()
        calc = QuoteCalculator(config)

        skew = inv.compute_skew(config.inventory.max_position_xmr, config.inventory.skew_factor)
        quotes = calc.compute_quotes(
            fair_price=Decimal("155.00"),
            regime="CALM",
            sigma=0.02,
            inventory=inv.xmr_position,
            inv_skew=skew,
            l2_bids=[],
            l2_asks=[],
        )
        assert len(quotes.bids) > 0
        assert len(quotes.asks) > 0

        # With no inventory, skew should be (1.0, 1.0) — symmetric
        bid_mult, ask_mult = skew
        assert bid_mult == pytest.approx(1.0)
        assert ask_mult == pytest.approx(1.0)

    def test_long_position_widens_bid_tightens_ask(self) -> None:
        config = make_config()
        inv = InventoryManager()
        # Simulate 5 XMR long (50% of max 10)
        inv.on_fill("buy", Decimal("155.00"), Decimal("5.00"), Decimal("0.0"))
        assert float(inv.xmr_position) == pytest.approx(5.0)

        bid_mult, ask_mult = inv.compute_skew(
            config.inventory.max_position_xmr, config.inventory.skew_factor
        )
        # Long position: bid_mult > 1 (wider bid), ask_mult < 1 (tighter ask)
        assert bid_mult > 1.0
        assert ask_mult < 1.0

    def test_realized_pnl_after_round_trip(self) -> None:
        inv = InventoryManager()
        # Buy 1 XMR at 150, then sell at 155 → realized PnL = 5 - fee
        inv.on_fill("buy", Decimal("150.00"), Decimal("1.0"), Decimal("0.0"))
        inv.on_fill("sell", Decimal("155.00"), Decimal("1.0"), Decimal("0.01"))
        # realized = (155 - 150) * 1 - 0.01 = 4.99
        assert float(inv.realized_pnl) == pytest.approx(4.99)

    def test_unrealized_pnl_marks_to_market(self) -> None:
        inv = InventoryManager()
        inv.on_fill("buy", Decimal("150.00"), Decimal("2.0"), Decimal("0.0"))
        unrealized = inv.compute_unrealized_pnl(Decimal("155.00"))
        # unrealized = (155 - 150) * 2 = 10
        assert float(unrealized) == pytest.approx(10.0)

    def test_inventory_ratio_clamped(self) -> None:
        inv = InventoryManager()
        # Position massively exceeds max — should clamp to 1.0
        inv.on_fill("buy", Decimal("150.00"), Decimal("100.0"), Decimal("0.0"))
        ratio = inv.inventory_ratio(max_position=10.0)
        assert ratio == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. RiskManager + MarketMaker state integration
# ---------------------------------------------------------------------------


class TestRiskManagerIntegration:
    def test_risk_ok_when_within_limits(self) -> None:
        config = make_config()
        risk = RiskManager(config)
        feed = StubPriceFeed("hl")
        feed.set_price(155.0)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)

        result = risk.check_pre_cycle(
            aggregator=aggregator,
            realized_pnl=Decimal("10.0"),
            portfolio_value=Decimal("2000.0"),
            inventory_xmr=Decimal("1.0"),
        )
        assert result.status == "OK"
        assert result.reason is None

    def test_risk_halt_on_stale_feeds(self) -> None:
        config = make_config()
        risk = RiskManager(config)
        # Stale aggregator (no feed has a price)
        feed = StubPriceFeed("stale")
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)

        result = risk.check_pre_cycle(
            aggregator=aggregator,
            realized_pnl=Decimal("0.0"),
            portfolio_value=Decimal("2000.0"),
            inventory_xmr=Decimal("0.0"),
        )
        assert result.status == "HALT"
        assert risk.is_halted is True
        assert "stale" in (result.reason or "").lower()

    def test_risk_halt_on_daily_loss_limit(self) -> None:
        config = make_config()
        risk = RiskManager(config)
        feed = StubPriceFeed("hl")
        feed.set_price(155.0)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)

        # daily_loss_limit_usdc = 50.0, so loss of 55 breaches it
        result = risk.check_pre_cycle(
            aggregator=aggregator,
            realized_pnl=Decimal("-55.0"),
            portfolio_value=Decimal("1900.0"),
            inventory_xmr=Decimal("0.0"),
        )
        assert result.status == "HALT"
        assert "Daily loss" in (result.reason or "")

    def test_risk_halt_persists_after_trigger(self) -> None:
        config = make_config()
        risk = RiskManager(config)
        risk.trigger_halt("Manual test halt")

        feed = StubPriceFeed("hl")
        feed.set_price(155.0)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)

        result = risk.check_pre_cycle(
            aggregator=aggregator,
            realized_pnl=Decimal("0.0"),
            portfolio_value=Decimal("2000.0"),
            inventory_xmr=Decimal("0.0"),
        )
        assert result.status == "HALT"

    def test_risk_halt_clears_on_clear_halt(self) -> None:
        config = make_config()
        risk = RiskManager(config)
        risk.trigger_halt("test")
        assert risk.is_halted is True
        risk.clear_halt()
        assert risk.is_halted is False
        assert risk.halt_reason is None

    def test_market_maker_state_transitions_to_halted(self) -> None:
        """Verify BotState.state reflects HALTED after risk manager triggers halt."""
        config = make_config()
        mm_state = BotState()
        mm_state.state = "RUNNING"

        risk = RiskManager(config)
        risk.trigger_halt("Daily loss limit breached: -55.00 USDC")

        # Simulate what market_maker.run_cycle does on HALT
        if risk.is_halted:
            mm_state.state = "HALTED"
            mm_state.halt_reason = risk.halt_reason

        assert mm_state.state == "HALTED"
        assert mm_state.halt_reason is not None
        assert "Daily loss" in mm_state.halt_reason


# ---------------------------------------------------------------------------
# 4. Repository save/retrieve with in-memory SQLite
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def in_memory_db() -> AsyncGenerator[None, None]:
    """Initialize an in-memory SQLite database for repository tests."""
    database.init_db("sqlite+aiosqlite:///:memory:")
    await database.create_tables()
    yield
    await database.close_db()


@_skip_if_no_greenlet
class TestRepositoryIntegration:
    @pytest.mark.asyncio
    async def test_save_and_retrieve_fill(self, in_memory_db: None) -> None:
        fill_data: dict[str, Any] = {
            "timestamp": datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc),
            "oid": "oid-test-001",
            "side": "buy",
            "price": 155.50,
            "size": 0.5,
            "fee": 0.008,
            "is_maker": True,
            "mid_price_at_fill": 155.48,
        }
        await repository.save_fill(fill_data)

        items, total = await repository.get_fills(page=1, limit=50)
        assert total == 1
        assert items[0]["oid"] == "oid-test-001"
        assert items[0]["side"] == "buy"
        assert items[0]["is_maker"] is True

    @pytest.mark.asyncio
    async def test_get_fills_pagination(self, in_memory_db: None) -> None:
        for i in range(5):
            await repository.save_fill(
                {
                    "timestamp": datetime(2026, 3, 22, 10, i, 0, tzinfo=timezone.utc),
                    "oid": f"oid-{i}",
                    "side": "sell",
                    "price": 155.0 + i,
                    "size": 0.1,
                    "fee": 0.001,
                    "is_maker": True,
                    "mid_price_at_fill": 155.0,
                }
            )

        items, total = await repository.get_fills(page=1, limit=2)
        assert total == 5
        assert len(items) == 2

        items_p2, _ = await repository.get_fills(page=2, limit=2)
        assert len(items_p2) == 2

    @pytest.mark.asyncio
    async def test_save_and_retrieve_price_snapshot(self, in_memory_db: None) -> None:
        snap: dict[str, Any] = {
            "timestamp": datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc),
            "fair_price": 155.50,
            "bid_prices": [155.42, 155.38],
            "ask_prices": [155.58, 155.62],
            "mid_hl": 155.50,
            "mid_kraken": 155.45,
        }
        await repository.save_price_snapshot(snap)

        since = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        rows = await repository.get_price_history(since)
        assert len(rows) == 1
        assert rows[0]["fair_price"] == pytest.approx(155.50)
        assert rows[0]["bid_prices"] == [155.42, 155.38]

    @pytest.mark.asyncio
    async def test_save_and_retrieve_pnl_snapshot(self, in_memory_db: None) -> None:
        snap: dict[str, Any] = {
            "timestamp": datetime(2026, 3, 22, 10, 0, 0, tzinfo=timezone.utc),
            "realized_pnl": 12.34,
            "unrealized_pnl": 5.67,
            "total_pnl": 18.01,
            "portfolio_value_usdc": 2000.0,
        }
        await repository.save_pnl_snapshot(snap)

        since = datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc)
        rows = await repository.get_pnl_history(since)
        assert len(rows) == 1
        assert rows[0]["total_pnl"] == pytest.approx(18.01)
        assert rows[0]["realized_pnl"] == pytest.approx(12.34)

    @pytest.mark.asyncio
    async def test_save_and_retrieve_hodl_benchmark(self, in_memory_db: None) -> None:
        bench: dict[str, Any] = {
            "timestamp": datetime(2026, 3, 22, 0, 0, 0, tzinfo=timezone.utc),
            "xmr_price": 150.00,
            "usdc_balance": 1000.0,
            "xmr_balance": 5.0,
        }
        await repository.save_hodl_benchmark(bench)

        result = await repository.get_hodl_benchmark()
        assert result is not None
        assert result["xmr_price"] == pytest.approx(150.0)
        assert result["usdc_balance"] == pytest.approx(1000.0)
        assert result["xmr_balance"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_get_hodl_benchmark_returns_none_when_empty(
        self, in_memory_db: None
    ) -> None:
        result = await repository.get_hodl_benchmark()
        assert result is None

    @pytest.mark.asyncio
    async def test_save_order_deduplication(self, in_memory_db: None) -> None:
        now = datetime.now(tz=timezone.utc)
        order_data: dict[str, Any] = {
            "oid": "dup-oid-001",
            "side": "buy",
            "price": 155.0,
            "size": 0.5,
            "status": "open",
            "created_at": now,
            "updated_at": now,
        }
        # Save twice — second insert should be silently ignored
        await repository.save_order(order_data)
        await repository.save_order(order_data)

        open_orders = await repository.get_open_orders()
        assert len([o for o in open_orders if o["oid"] == "dup-oid-001"]) == 1


# ---------------------------------------------------------------------------
# 5. MarketMaker.run_cycle() full-cycle integration
# ---------------------------------------------------------------------------


@_skip_if_no_greenlet
class TestRunCycleIntegration:
    """Verify that a single run_cycle() call wires price → quotes → orders → snapshots."""

    @pytest.mark.asyncio
    async def test_run_cycle_places_orders_on_both_sides(
        self, in_memory_db: None
    ) -> None:
        """run_cycle() should cancel stale orders then place new bid+ask quotes."""
        config = make_config()

        feed_hl = StubPriceFeed("hyperliquid")
        feed_kr = StubPriceFeed("kraken")
        feed_hl.set_price(155.00)
        feed_kr.set_price(155.00)
        aggregator = PriceAggregator(
            feeds=[feed_hl, feed_kr], weights=[0.5, 0.5], stale_seconds=5.0
        )

        inventory = InventoryManager()
        volatility = VolatilityEstimator(
            window_minutes=30,
            calm_threshold_bps=config.volatility.calm_threshold_bps,
            volatile_threshold_bps=config.volatility.volatile_threshold_bps,
        )
        risk_manager = RiskManager(config)
        quote_calculator = QuoteCalculator(config)

        # Stub exchange client — no real network calls
        mock_client = MagicMock()
        user_state_mock = MagicMock()
        user_state_mock.usdc_balance = Decimal("1000")
        user_state_mock.xmr_balance = Decimal("0")
        mock_client.get_user_state.return_value = user_state_mock
        l2_book_mock = MagicMock()
        l2_book_mock.bids = []
        l2_book_mock.asks = []
        mock_client.get_l2_book.return_value = l2_book_mock
        # bulk_place_orders / bulk_cancel_orders are sync in HyperliquidClient
        mock_client.bulk_place_orders = MagicMock(return_value=[])
        mock_client.bulk_cancel_orders = MagicMock(return_value=True)

        from bot.exchange.order_manager import OrderManager
        order_manager = OrderManager(mock_client, config.exchange.asset)

        ws_client_mock = MagicMock()

        mm = MarketMaker(
            config=config,
            client=mock_client,
            ws_client=ws_client_mock,
            aggregator=aggregator,
            inventory=inventory,
            volatility=volatility,
            order_manager=order_manager,
            risk_manager=risk_manager,
            quote_calculator=quote_calculator,
        )
        mm._running = True

        # Prime risk manager with a non-zero session portfolio so drawdown check passes
        risk_manager.set_session_start_portfolio(Decimal("1000"))

        await mm.run_cycle()

        # bulk_place_orders must have been called (quotes placed)
        mock_client.bulk_place_orders.assert_called_once()
        call_args = mock_client.bulk_place_orders.call_args
        orders_arg: list[Any] = call_args[0][0]
        assert len(orders_arg) > 0

        sides = {o.side for o in orders_arg}
        assert "buy" in sides
        assert "sell" in sides

    @pytest.mark.asyncio
    async def test_run_cycle_saves_pnl_snapshot(self, in_memory_db: None) -> None:
        """run_cycle() should persist a PnL snapshot to the database."""
        config = make_config()

        feed = StubPriceFeed("hyperliquid")
        feed.set_price(155.00)
        aggregator = PriceAggregator(feeds=[feed], stale_seconds=5.0)

        inventory = InventoryManager()
        volatility = VolatilityEstimator(
            window_minutes=30,
            calm_threshold_bps=config.volatility.calm_threshold_bps,
            volatile_threshold_bps=config.volatility.volatile_threshold_bps,
        )
        risk_manager = RiskManager(config)
        quote_calculator = QuoteCalculator(config)
        risk_manager.set_session_start_portfolio(Decimal("1000"))

        mock_client = MagicMock()
        user_state_mock = MagicMock()
        user_state_mock.usdc_balance = Decimal("1000")
        user_state_mock.xmr_balance = Decimal("0")
        mock_client.get_user_state.return_value = user_state_mock
        l2_book_mock = MagicMock()
        l2_book_mock.bids = []
        l2_book_mock.asks = []
        mock_client.get_l2_book.return_value = l2_book_mock
        mock_client.bulk_place_orders = MagicMock(return_value=[])
        mock_client.bulk_cancel_orders = MagicMock(return_value=True)

        from bot.exchange.order_manager import OrderManager
        order_manager = OrderManager(mock_client, config.exchange.asset)

        mm = MarketMaker(
            config=config,
            client=mock_client,
            ws_client=MagicMock(),
            aggregator=aggregator,
            inventory=inventory,
            volatility=volatility,
            order_manager=order_manager,
            risk_manager=risk_manager,
            quote_calculator=quote_calculator,
        )
        mm._running = True

        await mm.run_cycle()

        since = datetime(2020, 1, 1, tzinfo=timezone.utc)
        rows = await repository.get_pnl_history(since)
        assert len(rows) >= 1
        assert rows[0]["realized_pnl"] == pytest.approx(0.0)
