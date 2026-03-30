"""Cycle Watchdog Agent — detects stale or hung trading cycles."""
from __future__ import annotations

from datetime import datetime, timezone

from bot.agents.base_agent import AgentReport, BaseAgent, ReportCallback
from bot.config import AppConfig
from bot.engine.market_maker import MarketMaker


class CycleWatchdogAgent(BaseAgent):
    """Monitors that trading cycles run on schedule.

    Detects:
    - Bot state is RUNNING but no cycle has executed in an abnormally long time
      (event loop blocked, asyncio task hung, or run_cycle raised unhandled exception).
    - Individual cycles taking too long (> 5 s), indicating slow exchange API calls.

    Thresholds:
    - WARN  : last cycle > 3× cycle_interval ago
    - CRITICAL: last cycle > 10× cycle_interval ago
    - WARN  : last cycle took > 5,000 ms
    """

    name = "cycle_watchdog"
    check_interval = 10.0

    _SLOW_CYCLE_WARN_MS = 5_000.0

    def __init__(
        self,
        bot: MarketMaker,
        config: AppConfig,
        on_report: ReportCallback,
    ) -> None:
        super().__init__(on_report)
        self._bot = bot
        self._cycle_interval = config.trading.cycle_interval_seconds

    async def check(self) -> AgentReport:
        state = self._bot.get_state()

        if state.state != "RUNNING":
            return AgentReport(
                agent=self.name,
                status="OK",
                message=f"Bot is {state.state} — cycle monitoring inactive",
                details={"bot_state": state.state},
            )

        last_cycle_time = state.last_cycle_time
        cycle_ms = state.last_cycle_ms

        if last_cycle_time is None:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message="No cycles completed yet since startup",
                details={"cycle_count": state.cycle_count},
            )

        age_s = (datetime.now(timezone.utc) - last_cycle_time).total_seconds()
        expected = self._cycle_interval

        if age_s > expected * 10:
            return AgentReport(
                agent=self.name,
                status="CRITICAL",
                message=(
                    f"Cycle engine stalled: no cycle for {age_s:.1f}s "
                    f"(expected every {expected:.0f}s). Event loop may be blocked."
                ),
                details={
                    "age_seconds": round(age_s, 1),
                    "expected_interval_s": expected,
                    "last_cycle_time": last_cycle_time.isoformat(),
                    "cycle_count": state.cycle_count,
                    "last_cycle_ms": round(cycle_ms, 1),
                },
            )

        if age_s > expected * 3:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message=f"Cycle delayed: {age_s:.1f}s since last cycle (expected every {expected:.0f}s)",
                details={
                    "age_seconds": round(age_s, 1),
                    "expected_interval_s": expected,
                    "cycle_count": state.cycle_count,
                },
            )

        if cycle_ms > self._SLOW_CYCLE_WARN_MS:
            return AgentReport(
                agent=self.name,
                status="WARN",
                message=f"Slow cycle: {cycle_ms:.0f}ms (possible exchange API latency spike)",
                details={
                    "cycle_ms": round(cycle_ms, 1),
                    "age_seconds": round(age_s, 1),
                    "cycle_count": state.cycle_count,
                },
            )

        return AgentReport(
            agent=self.name,
            status="OK",
            message=f"Cycles healthy — #{state.cycle_count} ran {age_s:.1f}s ago in {cycle_ms:.0f}ms",
            details={
                "cycle_ms": round(cycle_ms, 1),
                "age_seconds": round(age_s, 1),
                "cycle_count": state.cycle_count,
            },
        )
