"""Exchange Probe Agent — verifies exchange REST API reachability."""
from __future__ import annotations

import asyncio
import time

from bot.agents.base_agent import AgentReport, BaseAgent, ReportCallback
from bot.engine.market_maker import MarketMaker
from bot.exchange.hyperliquid_client import HyperliquidClient


class ExchangeProbeAgent(BaseAgent):
    """Periodically probes the exchange REST API for connectivity and latency.

    Detects:
    - Exchange API completely unreachable (network partition, DNS failure).
    - API responding but with high latency (> 3 s WARN, > 8 s CRITICAL),
      which will cause slow cycles and possible order placement timeouts.

    This complements WebSocket health — the WS feed might appear healthy
    (prices flowing) even when REST order-placement endpoint is degraded.

    Check interval is 60 s to avoid adding unnecessary API load.
    """

    name = "exchange_probe"
    check_interval = 60.0

    _WARN_MS = 3_000.0
    _CRITICAL_MS = 8_000.0

    def __init__(
        self,
        bot: MarketMaker,
        client: HyperliquidClient,
        on_report: ReportCallback,
    ) -> None:
        super().__init__(on_report)
        self._bot = bot
        self._client = client

    async def check(self) -> AgentReport:
        state = self._bot.get_state()

        if state.state == "STOPPED":
            return AgentReport(
                agent=self.name,
                status="OK",
                message="Bot stopped — skipping exchange probe",
            )

        start = time.monotonic()
        try:
            loop = asyncio.get_event_loop()
            # get_open_orders is a lightweight /info POST — no auth required.
            # Hard cap at 15 s so a drip-feeding server never occupies a thread
            # pool slot indefinitely (requests timeout=10 is per-socket-op, not
            # total, so a slow server can stall for minutes without this guard).
            await asyncio.wait_for(
                loop.run_in_executor(None, self._client.get_open_orders),
                timeout=15.0,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if latency_ms >= self._CRITICAL_MS:
                return AgentReport(
                    agent=self.name,
                    status="CRITICAL",
                    message=f"Exchange API critically slow: {latency_ms:.0f}ms — order placement at risk",
                    details={"latency_ms": round(latency_ms, 1)},
                )

            if latency_ms >= self._WARN_MS:
                return AgentReport(
                    agent=self.name,
                    status="WARN",
                    message=f"Exchange API slow: {latency_ms:.0f}ms — cycles may be delayed",
                    details={"latency_ms": round(latency_ms, 1)},
                )

            return AgentReport(
                agent=self.name,
                status="OK",
                message=f"Exchange reachable ({latency_ms:.0f}ms)",
                details={"latency_ms": round(latency_ms, 1)},
            )

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - start) * 1000
            return AgentReport(
                agent=self.name,
                status="CRITICAL",
                message=f"Exchange API critically slow: {latency_ms:.0f}ms (probe timed out after 15s)",
                details={"latency_ms": round(latency_ms, 1)},
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start) * 1000
            return AgentReport(
                agent=self.name,
                status="CRITICAL",
                message=f"Exchange API unreachable: {e}",
                details={"latency_ms": round(latency_ms, 1), "error": str(e)},
            )
