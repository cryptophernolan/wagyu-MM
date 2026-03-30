"""Order Integrity Agent — cross-checks exchange orders against local state."""
from __future__ import annotations

import asyncio

from bot.agents.base_agent import AgentReport, BaseAgent, ReportCallback
from bot.config import AppConfig
from bot.engine.market_maker import MarketMaker
from bot.exchange.hyperliquid_client import HyperliquidClient
from bot.exchange.order_manager import OrderManager


class OrderIntegrityAgent(BaseAgent):
    """Verifies that locally tracked orders actually exist on the exchange.

    Detects:
    - "Ghost orders": local dict says N orders open, but exchange returns 0.
      Caused by: silent WebSocket disconnect (fills/cancels not received),
      SDK errors during placement that were swallowed, or exchange-side rejection.
    - Significant count mismatch (> 1) indicating partial sync loss.

    Check interval is deliberately long (30 s) because this makes a REST call
    to the exchange outside the normal trading cycle.
    """

    name = "order_integrity"
    check_interval = 30.0

    def __init__(
        self,
        bot: MarketMaker,
        client: HyperliquidClient,
        order_manager: OrderManager,
        config: AppConfig,
        on_report: ReportCallback,
    ) -> None:
        super().__init__(on_report)
        self._bot = bot
        self._client = client
        self._order_manager = order_manager
        self._asset = config.exchange.asset

    async def check(self) -> AgentReport:
        state = self._bot.get_state()

        # Only relevant when actively quoting
        if state.state != "RUNNING":
            return AgentReport(
                agent=self.name,
                status="OK",
                message=f"Bot is {state.state} — skipping order integrity check",
            )

        if not state.wagyu_enabled or not state.quoting_enabled:
            return AgentReport(
                agent=self.name,
                status="OK",
                message="Quoting/wagyu disabled — no orders expected",
                details={"wagyu": state.wagyu_enabled, "quoting": state.quoting_enabled},
            )

        local_orders = self._order_manager.get_open_orders()
        local_count = len(local_orders)

        # Fetch actual open orders from exchange REST API (blocking → run in executor)
        try:
            loop = asyncio.get_event_loop()
            exchange_orders: list[dict] = await loop.run_in_executor(
                None, self._client.get_open_orders
            )
            # Filter to our asset only to avoid counting other pairs
            exchange_asset_orders = [
                o for o in exchange_orders if o.get("coin", "") == self._asset
            ]
            exchange_count = len(exchange_asset_orders)
        except Exception as e:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message=f"Cannot verify orders — exchange query failed: {e}",
                details={"local_count": local_count, "error": str(e)},
            )

        # Ghost orders: bot thinks orders exist but exchange has none
        if local_count > 0 and exchange_count == 0:
            return AgentReport(
                agent=self.name,
                status="CRITICAL",
                message=(
                    f"Ghost orders detected: bot tracks {local_count} orders but exchange "
                    f"has 0. WebSocket may have missed fill/cancel events."
                ),
                details={
                    "local_count": local_count,
                    "exchange_count": exchange_count,
                    "local_oids": [o.oid for o in local_orders],
                },
            )

        # Significant mismatch — allow difference of 1 for fill race conditions
        mismatch = abs(local_count - exchange_count)
        if mismatch > 1:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message=(
                    f"Order count mismatch: local={local_count}, exchange={exchange_count} "
                    f"(diff={mismatch}). Possible fill race or WS lag."
                ),
                details={
                    "local_count": local_count,
                    "exchange_count": exchange_count,
                    "mismatch": mismatch,
                },
            )

        return AgentReport(
            agent=self.name,
            status="OK",
            message=f"Orders consistent — {exchange_count} on exchange, {local_count} tracked locally",
            details={"local_count": local_count, "exchange_count": exchange_count},
        )
