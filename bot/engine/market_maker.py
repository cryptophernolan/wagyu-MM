"""Market maker orchestrator — main async trading loop."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Literal

from bot.config import AppConfig
from bot.engine.inventory import InventoryManager
from bot.engine.quoting import QuoteCalculator
from bot.engine.volatility import VolatilityEstimator
from bot.exchange.hyperliquid_client import HyperliquidClient
from bot.exchange.order_manager import OrderManager
from bot.exchange.ws_client import HyperliquidWsClient
from bot.feeds.price_aggregator import PriceAggregator
from bot.persistence import repository
from bot.risk.risk_manager import RiskManager
from bot.utils.logger import get_logger

logger = get_logger(__name__)

State = Literal["STARTING", "RUNNING", "PAUSED", "STOPPED", "HALTED"]


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Done-callback: log any exception from a fire-and-forget repository task."""
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            logger.warning("repository_save_failed", error=str(exc))

EventCallback = Callable[[dict[str, Any]], None]


@dataclass
class BotState:
    state: State = "STARTING"
    feeds_enabled: bool = True
    wagyu_enabled: bool = True
    quoting_enabled: bool = True
    inv_limit_enabled: bool = True
    cycle_count: int = 0
    last_cycle_ms: float = 0.0
    last_cycle_time: datetime | None = None
    fills_count: int = 0
    fair_price: float = 0.0
    regime: str = "CALM"
    inventory_pct: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    portfolio_value: float = 0.0
    feed_health: list[dict[str, Any]] = field(default_factory=list)
    open_orders_count: int = 0
    halt_reason: str | None = None
    alerts: list[str] = field(default_factory=list)
    # Cumulative rate limit backoff: non-zero while placement is intentionally paused
    rate_limit_backoff_until: float = 0.0


class MarketMaker:
    """Async market maker orchestrator."""

    def __init__(
        self,
        config: AppConfig,
        client: HyperliquidClient,
        ws_client: HyperliquidWsClient,
        aggregator: PriceAggregator,
        inventory: InventoryManager,
        volatility: VolatilityEstimator,
        order_manager: OrderManager,
        risk_manager: RiskManager,
        quote_calculator: QuoteCalculator,
    ) -> None:
        self._config = config
        self._client = client
        self._ws_client = ws_client
        self._aggregator = aggregator
        self._inventory = inventory
        self._volatility = volatility
        self._order_manager = order_manager
        self._risk_manager = risk_manager
        self._quote_calculator = quote_calculator

        self._state = BotState()
        self._event_listeners: list[EventCallback] = []
        self._running = False
        self._fair_price: Decimal = Decimal("0")

        # Dead-band rate-limit tracking
        self._last_quoted_price: Decimal = Decimal("0")
        self._last_refresh_time: float = 0.0
        self._force_refresh: bool = False  # set True on fill to bypass dead-band

    def add_event_listener(self, cb: EventCallback) -> None:
        self._event_listeners.append(cb)

    def _emit(self, event: dict[str, Any]) -> None:
        for cb in self._event_listeners:
            try:
                cb(event)
            except Exception as e:
                logger.warning("Event listener error", error=str(e))

    def get_state(self) -> BotState:
        return self._state

    def toggle_feeds(self) -> bool:
        self._state.feeds_enabled = not self._state.feeds_enabled
        logger.info("Feeds toggled", enabled=self._state.feeds_enabled)
        return self._state.feeds_enabled

    def toggle_wagyu(self) -> bool:
        self._state.wagyu_enabled = not self._state.wagyu_enabled
        logger.info("Wagyu toggled", enabled=self._state.wagyu_enabled)
        return self._state.wagyu_enabled

    def toggle_quoting(self) -> bool:
        self._state.quoting_enabled = not self._state.quoting_enabled
        if not self._state.quoting_enabled:
            asyncio.create_task(self._order_manager.cancel_all())
        logger.info("Quoting toggled", enabled=self._state.quoting_enabled)
        return self._state.quoting_enabled

    def toggle_inv_limit(self) -> bool:
        self._state.inv_limit_enabled = not self._state.inv_limit_enabled
        logger.info("Inv limit toggled", enabled=self._state.inv_limit_enabled)
        return self._state.inv_limit_enabled

    def _should_refresh(self, fair_price: Decimal) -> bool:
        """Return True if quotes should be refreshed this cycle.

        Refresh is triggered when ANY of these is true:
        1. _force_refresh flag (set after a fill — inventory changed)
        2. No open orders exist (bot just started or halted)
        3. Timer fallback: max_refresh_interval_seconds elapsed (keeps quotes from going stale)
        4. Dead-band crossed: price moved > deadband_bps from last quoted price
        """
        if self._force_refresh:
            return True
        if not self._order_manager.get_open_orders():
            return True
        elapsed = time.monotonic() - self._last_refresh_time
        if elapsed >= self._config.rate_limit.max_refresh_interval_seconds:
            return True
        if self._last_quoted_price > Decimal("0"):
            move_bps = (
                abs(fair_price - self._last_quoted_price)
                / self._last_quoted_price
                * Decimal("10000")
            )
            if float(move_bps) >= self._config.rate_limit.deadband_bps:
                return True
        return False

    def _on_fill(self, fill_data: dict[str, Any]) -> None:
        """Handle fill event from WebSocket."""
        try:
            side: Literal["buy", "sell"] = (
                "buy" if fill_data.get("side") == "B" else "sell"
            )
            price = Decimal(str(fill_data.get("px", "0")))
            size = Decimal(str(fill_data.get("sz", "0")))
            fee = Decimal(str(fill_data.get("fee", "0")))
            oid = str(fill_data.get("oid", ""))
            is_maker = fill_data.get("liquidated", False) is False

            self._inventory.on_fill(side, price, size, fee)
            self._client.invalidate_user_state_cache()  # Force fresh balance on next cycle
            self._force_refresh = True  # Inventory changed → bypass dead-band next cycle
            self._state.fills_count += 1
            # Eagerly remove from local order tracking — orderUpdates may arrive late,
            # causing modify attempts on an already-filled oid (duplicate-nonce / ghost order)
            if oid:
                self._order_manager.remove_order(oid)

            fair = float(self._fair_price)
            _save_task = asyncio.create_task(
                repository.save_fill({
                    "timestamp": datetime.now(timezone.utc),
                    "oid": oid,
                    "side": side,
                    "price": float(price),
                    "size": float(size),
                    "fee": float(fee),
                    "is_maker": is_maker,
                    "mid_price_at_fill": fair,
                })
            )
            _save_task.add_done_callback(_log_task_exception)

            self._emit({
                "type": "fill_event",
                "data": {
                    "side": side,
                    "price": float(price),
                    "size": float(size),
                    "fee": float(fee),
                },
            })
        except Exception as e:
            logger.error("Fill processing error", error=str(e))

    async def run(self) -> None:
        """Main async loop."""
        logger.info("MarketMaker starting")
        self._state.state = "STARTING"
        self._running = True

        # Set up WebSocket callbacks
        self._ws_client.on_fill(self._on_fill)
        self._ws_client.on_order_update(self._order_manager.on_order_update)

        # Connect feeds and WS
        await self._aggregator.connect_all()
        await self._ws_client.connect()
        await asyncio.sleep(2.0)  # Allow feeds to initialize

        # Cancel any stale orders from previous sessions before starting
        cancelled = await self._order_manager.cancel_all_exchange_orders()
        if cancelled > 0:
            logger.info("Cancelled stale exchange orders on startup", count=cancelled)
            await asyncio.sleep(1.0)  # Allow exchange to release held balance

        # Wait for a valid price before setting initial portfolio (up to 10s)
        for _ in range(20):
            raw_init = self._aggregator.get_price()
            if raw_init is not None:
                self._fair_price = Decimal(str(round(raw_init, 6)))
                break
            await asyncio.sleep(0.5)

        # Get initial portfolio value for drawdown tracking (use actual wallet balances)
        user_state = await self._client.async_get_user_state()
        initial_portfolio = user_state.usdc_balance + user_state.xmr_balance * self._fair_price
        self._risk_manager.set_session_start_portfolio(initial_portfolio)
        logger.info("Session start portfolio", value=float(initial_portfolio), fair_price=float(self._fair_price))

        # Auto-seed HODL benchmark on first run so BotVsHODL chart works without
        # requiring the user to manually run scripts/set_benchmark.py
        existing_benchmark = await repository.get_hodl_benchmark()
        if existing_benchmark is None and self._fair_price > Decimal("0"):
            await repository.save_hodl_benchmark({
                "timestamp": datetime.now(timezone.utc),
                "xmr_price": float(self._fair_price),
                "usdc_balance": float(user_state.usdc_balance),
                "xmr_balance": float(user_state.xmr_balance),
            })
            logger.info(
                "Auto-seeded HODL benchmark",
                xmr_price=float(self._fair_price),
                usdc=float(user_state.usdc_balance),
                xmr=float(user_state.xmr_balance),
            )

        self._state.state = "RUNNING"
        logger.info("MarketMaker running")

        try:
            while self._running:
                cycle_start = time.monotonic()
                try:
                    await self.run_cycle()
                except Exception as e:
                    logger.error("Cycle error", error=str(e))
                    self._state.alerts.append(f"Cycle error: {e}")
                    # Always update last_cycle_time so the watchdog doesn't
                    # report a false stall when run_cycle raises before reaching
                    # its own last_cycle_time update.
                    self._state.last_cycle_time = datetime.now(timezone.utc)

                elapsed = time.monotonic() - cycle_start
                sleep_time = max(0.0, self._config.trading.cycle_interval_seconds - elapsed)
                await asyncio.sleep(sleep_time)
        finally:
            logger.info("MarketMaker stopping")
            self._state.state = "STOPPED"
            await self._order_manager.cancel_all()
            await self._aggregator.disconnect_all()
            await self._ws_client.disconnect()

    async def run_cycle(self) -> None:
        """Execute one market making cycle."""
        cycle_start = time.monotonic()

        # 1. Get fair price
        raw_price = self._aggregator.get_price()
        if raw_price is None:
            logger.warning("No price available, skipping cycle")
            # Update cycle timestamp so watchdog doesn't fire false CRITICAL alerts
            # during brief feed outages. Risk manager handles cancel-on-stale-feed
            # separately via its HALT mechanism.
            self._state.last_cycle_time = datetime.now(timezone.utc)
            return

        self._fair_price = Decimal(str(round(raw_price, 6)))
        self._volatility.add_price(self._fair_price)

        # 2. Compute regime, sigma, inventory metrics
        regime = self._volatility.get_regime()
        sigma = self._volatility.compute_realized_vol()
        max_pos = self._config.inventory.max_position_xmr
        inv_ratio = self._inventory.inventory_ratio(max_pos)
        inv_skew = self._inventory.compute_skew(max_pos, self._config.inventory.skew_factor)

        # 3. Compute PnL and portfolio value — fetch user_state + l2_book in parallel
        # to avoid two sequential round-trips when exchange is slow.
        realized_pnl = self._inventory.realized_pnl
        unrealized_pnl = self._inventory.compute_unrealized_pnl(self._fair_price)
        should_refresh = self._should_refresh(self._fair_price)

        if should_refresh and self._state.quoting_enabled and self._state.wagyu_enabled:
            user_state, l2_book = await asyncio.gather(
                self._client.async_get_user_state(),
                self._client.async_get_l2_book(),
            )
        else:
            user_state = await self._client.async_get_user_state()
            l2_book = None

        # Use actual wallet balances for portfolio value (not session-tracked inventory)
        # so drawdown check works correctly across restarts.
        portfolio_value = user_state.usdc_balance + user_state.xmr_balance * self._fair_price

        # 4. Risk check
        risk_result = self._risk_manager.check_pre_cycle(
            self._aggregator,
            realized_pnl,
            portfolio_value,
            self._inventory.xmr_position,
        )

        if risk_result.status == "HALT" or self._risk_manager.is_halted:
            self._state.state = "HALTED"
            # Use risk_result.reason for transient halts (stale feed); manager.halt_reason for permanent
            self._state.halt_reason = self._risk_manager.halt_reason or risk_result.reason
            self._state.fair_price = float(self._fair_price)  # Show price even when halted
            self._state.last_cycle_time = datetime.now(timezone.utc)  # Keep watchdog from false-alerting
            await self._order_manager.cancel_all()
            self._last_quoted_price = Decimal("0")  # Force fresh quotes on un-halt
            self._emit(self._build_state_event())
            return

        # 5. Manage quotes: cancel if disabled, or refresh if dead-band crossed / fill received
        # If the exchange cumulative rate limit is active, skip order placement this cycle
        # to avoid incrementing the counter further while we're already over quota.
        if self._client.is_cumulative_rate_limited():
            remaining = self._client._cumulative_rl_until - time.monotonic()
            logger.debug("Skipping quotes: cumulative rate limit active", remaining_s=round(remaining, 1))
            self._state.last_cycle_time = datetime.now(timezone.utc)
            self._state.rate_limit_backoff_until = self._client._cumulative_rl_until
            self._emit(self._build_state_event())
            return

        # Clear backoff flag once we're past the rate limit window
        self._state.rate_limit_backoff_until = 0.0

        if not self._state.quoting_enabled or not self._state.wagyu_enabled:
            # Quoting just toggled off — cancel any resting orders
            cancelled = await self._order_manager.cancel_all()
            if cancelled > 0:
                self._last_quoted_price = Decimal("0")  # Force fresh quotes on re-enable
        else:
            # 5a. Dead-band gate: skip order refresh if price hasn't moved enough
            if should_refresh:
                if l2_book is None:
                    l2_book = await self._client.async_get_l2_book()
                l2_bids = [(b.price, b.size) for b in l2_book.bids]
                l2_asks = [(a.price, a.size) for a in l2_book.asks]

                quote_set = self._quote_calculator.compute_quotes(
                    fair_price=self._fair_price,
                    regime=regime,
                    sigma=sigma,
                    inventory=self._inventory.xmr_position,
                    inv_skew=inv_skew,
                    l2_bids=l2_bids,
                    l2_asks=l2_asks,
                )
                # 5b. Use modify-in-place when possible (saves ~50% API ops vs cancel+place).
                # Pass user_state so the fallback cancel+replace path can skip redundant
                # exchange fetches (eliminates the 25-30s event loop stall on slow API).
                await self._order_manager.modify_or_replace_quotes(
                    quote_set,
                    self._fair_price,
                    use_modify=self._config.rate_limit.use_order_modify,
                    user_state=user_state,
                )
                self._last_quoted_price = self._fair_price
                self._last_refresh_time = time.monotonic()
                self._force_refresh = False
            else:
                logger.debug(
                    "Skipping quote refresh (dead-band)",
                    deadband_bps=self._config.rate_limit.deadband_bps,
                )

        # 6. Save price and PnL snapshots
        open_orders = self._order_manager.get_open_orders()
        await repository.save_price_snapshot({
            "timestamp": datetime.now(timezone.utc),
            "fair_price": float(self._fair_price),
            "bid_prices": [float(o.price) for o in open_orders if o.side == "buy"],
            "ask_prices": [float(o.price) for o in open_orders if o.side == "sell"],
            "mid_hl": None,
            "mid_kraken": None,
        })
        await repository.save_pnl_snapshot({
            "timestamp": datetime.now(timezone.utc),
            "realized_pnl": float(realized_pnl),
            "unrealized_pnl": float(unrealized_pnl),
            "total_pnl": float(realized_pnl + unrealized_pnl),
            "portfolio_value_usdc": float(portfolio_value),
        })

        # 8. Update bot state and emit event
        cycle_ms = (time.monotonic() - cycle_start) * 1000
        self._state.cycle_count += 1
        self._state.last_cycle_ms = cycle_ms
        self._state.last_cycle_time = datetime.now(timezone.utc)
        self._state.fair_price = float(self._fair_price)
        self._state.halt_reason = None  # Clear any transient halt reason on successful cycle
        self._state.regime = regime
        self._state.inventory_pct = inv_ratio * 100
        self._state.realized_pnl = float(realized_pnl)
        self._state.unrealized_pnl = float(unrealized_pnl)
        self._state.portfolio_value = float(portfolio_value)
        self._state.open_orders_count = len(open_orders)
        self._state.feed_health = [
            {
                "source": h.source,
                "healthy": h.healthy,
                "price": h.price,
                "latency_ms": h.latency_ms,
                "last_updated": h.last_updated,
            }
            for h in self._aggregator.get_feed_health()
        ]
        self._state.state = "RUNNING"

        self._emit(self._build_state_event())
        logger.debug(
            "Cycle complete",
            cycle_ms=round(cycle_ms, 1),
            fair=float(self._fair_price),
        )

    def _build_state_event(self) -> dict[str, Any]:
        s = self._state
        return {
            "type": "state_update",
            "data": {
                "state": s.state,
                "toggles": {
                    "feeds": s.feeds_enabled,
                    "wagyu": s.wagyu_enabled,
                    "quoting": s.quoting_enabled,
                    "inv_limit": s.inv_limit_enabled,
                },
                "cycle_count": s.cycle_count,
                "last_cycle_ms": s.last_cycle_ms,
                "fills_count": s.fills_count,
                "fair_price": s.fair_price,
                "regime": s.regime,
                "inventory_pct": s.inventory_pct,
                "realized_pnl": s.realized_pnl,
                "unrealized_pnl": s.unrealized_pnl,
                "portfolio_value": s.portfolio_value,
                "open_orders_count": s.open_orders_count,
                "feed_health": s.feed_health,
                "halt_reason": s.halt_reason,
                "alerts": s.alerts[-10:],
            },
        }

    def force_refresh(self) -> None:
        """Signal that quotes must be refreshed on the next cycle.

        Called by agents (e.g. OrderIntegrityAgent) to trigger immediate
        re-quoting after auto-reconciliation without waiting for the dead-band.
        """
        self._force_refresh = True
        self._last_quoted_price = Decimal("0")

    def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        """Gracefully stop the bot: cancel all open orders, then stop the loop."""
        self._running = False
        try:
            await self._order_manager.cancel_all()
        except Exception as e:
            logger.warning("shutdown_cancel_all_failed", error=str(e))
        logger.info("shutdown_complete")
