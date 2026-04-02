"""Quote Activity Agent — detects quoting enabled but no orders placed."""
from __future__ import annotations

import time

from bot.agents.base_agent import AgentReport, BaseAgent, ReportCallback
from bot.config import AppConfig
from bot.engine.market_maker import MarketMaker


class QuoteActivityAgent(BaseAgent):
    """Monitors that orders exist when quoting is active.

    Detects:
    - quoting=ON, wagyu=ON, state=RUNNING — but open_orders_count stays at 0
      for an extended time. Indicates order placement is silently failing
      (ALO rejections all at once, SDK error, insufficient balance, etc.).

    Uses a consecutive-check streak to avoid false positives from the brief
    window between cancel_all() and place_quotes() each cycle.

    Thresholds:
    - WARN     : 0 orders for 1 consecutive check  (15 s)
    - CRITICAL : 0 orders for 3 consecutive checks (45 s)
    """

    name = "quote_activity"
    check_interval = 15.0

    _CRITICAL_STREAK = 3

    def __init__(
        self,
        bot: MarketMaker,
        config: AppConfig,
        on_report: ReportCallback,
    ) -> None:
        super().__init__(on_report)
        self._bot = bot
        self._zero_streak = 0

    async def check(self) -> AgentReport:
        state = self._bot.get_state()

        if state.state != "RUNNING":
            self._zero_streak = 0
            return AgentReport(
                agent=self.name,
                status="OK",
                message=f"Bot is {state.state} — not monitoring quote activity",
            )

        if not state.quoting_enabled or not state.wagyu_enabled:
            self._zero_streak = 0
            return AgentReport(
                agent=self.name,
                status="OK",
                message="Quoting/wagyu disabled — zero orders is expected",
                details={"quoting": state.quoting_enabled, "wagyu": state.wagyu_enabled},
            )

        # Bot hasn't priced up yet — feed just connected
        if state.fair_price == 0.0:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message="Fair price is 0 — feeds may not have initialized yet",
            )

        # Intentional pause: Hyperliquid cumulative rate limit back-off
        if state.rate_limit_backoff_until > time.monotonic():
            remaining = round(state.rate_limit_backoff_until - time.monotonic())
            self._zero_streak = 0  # reset streak — this is not a silent failure
            return AgentReport(
                agent=self.name,
                status="WARN",
                message=f"Order placement paused: Hyperliquid cumulative rate limit — resuming in {remaining}s",
                details={"backoff_remaining_s": remaining},
            )

        if state.open_orders_count == 0:
            self._zero_streak += 1
            elapsed_s = self._zero_streak * self.check_interval

            if self._zero_streak >= self._CRITICAL_STREAK:
                return AgentReport(
                    agent=self.name,
                    status="CRITICAL",
                    message=(
                        f"No open orders for {elapsed_s:.0f}s while quoting is active. "
                        "Order placement is failing silently — check ALO rejections or balance."
                    ),
                    details={
                        "zero_order_streak": self._zero_streak,
                        "elapsed_seconds": elapsed_s,
                        "fair_price": state.fair_price,
                        "cycle_count": state.cycle_count,
                    },
                )

            return AgentReport(
                agent=self.name,
                status="WARN",
                message=f"No open orders (streak {self._zero_streak}/{self._CRITICAL_STREAK} checks)",
                details={
                    "zero_order_streak": self._zero_streak,
                    "elapsed_seconds": elapsed_s,
                },
            )

        # Orders exist — reset streak
        self._zero_streak = 0
        return AgentReport(
            agent=self.name,
            status="OK",
            message=f"{state.open_orders_count} orders active",
            details={"open_orders_count": state.open_orders_count},
        )
