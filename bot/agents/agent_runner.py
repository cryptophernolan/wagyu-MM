"""Agent runner — starts all health agents and aggregates their reports."""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime, timezone
from typing import Any, Callable

from bot.agents.base_agent import AgentReport, AgentStatus, BaseAgent
from bot.engine.market_maker import MarketMaker
from bot.utils.logger import get_logger

logger = get_logger(__name__)

# Async function that broadcasts a dict to all dashboard WS clients
BroadcastFn = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


def _task_exception_cb(task: asyncio.Task[None]) -> None:
    """Done-callback: log unhandled agent task exceptions."""
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            logger.error("Agent task crashed", task=task.get_name(), error=str(exc))


class AgentRunner:
    """Manages all monitoring agents and routes their reports.

    Responsibilities:
    - Start each agent as an independent asyncio background task.
    - Collect AgentReport results via callback.
    - Inject WARN/CRITICAL messages into the bot's alert list (visible on dashboard).
    - Broadcast each report to connected frontend clients via WebSocket.
    - Expose ``get_reports()`` for the ``GET /api/health/agents`` REST endpoint.
    """

    def __init__(
        self,
        agents: list[BaseAgent],
        bot: MarketMaker,
        broadcast: BroadcastFn,
    ) -> None:
        self._agents = agents
        self._bot = bot
        self._broadcast = broadcast
        self._reports: dict[str, AgentReport] = {}
        self._tasks: list[asyncio.Task[None]] = []

        # Wire each agent's callback to our central handler
        for agent in self._agents:
            agent._on_report = self._on_report

    # ── Public interface ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn all agents as asyncio tasks."""
        for agent in self._agents:
            task = asyncio.create_task(agent.run(), name=f"agent.{agent.name}")
            task.add_done_callback(_task_exception_cb)
            self._tasks.append(task)
        logger.info("AgentRunner started", agents=[a.name for a in self._agents])

    async def stop(self) -> None:
        """Cancel and await all agent tasks."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("AgentRunner stopped")

    def get_reports(self) -> list[dict[str, Any]]:
        """Return all latest agent reports as JSON-serialisable dicts."""
        return [
            {
                "agent": r.agent,
                "status": r.status,
                "message": r.message,
                "timestamp": r.timestamp.isoformat(),
                "details": r.details,
            }
            for r in sorted(self._reports.values(), key=lambda r: r.agent)
        ]

    def get_overall_status(self) -> AgentStatus:
        """Return the worst status across all agent reports."""
        if not self._reports:
            return "UNKNOWN"
        statuses = {r.status for r in self._reports.values()}
        for worst in ("CRITICAL", "WARN", "UNKNOWN"):
            if worst in statuses:
                return worst  # type: ignore[return-value]
        return "OK"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_report(self, report: AgentReport) -> None:
        """Receive a report from an agent, alert if degraded, broadcast via WS."""
        prev = self._reports.get(report.agent)
        self._reports[report.agent] = report

        # Log on status transitions
        prev_status = prev.status if prev else "UNKNOWN"
        if prev_status != report.status:
            if report.status == "CRITICAL":
                logger.error("Agent CRITICAL", agent=report.agent, message=report.message)
            elif report.status == "WARN":
                logger.warning("Agent WARN", agent=report.agent, message=report.message)
            elif prev_status in ("CRITICAL", "WARN"):
                logger.info(
                    "Agent recovered",
                    agent=report.agent,
                    prev=prev_status,
                    now=report.status,
                )

        # Push degraded messages into the bot's alert list (dashboard Health tab)
        if report.status in ("CRITICAL", "WARN"):
            alert = f"[{report.agent.upper()}] {report.message}"
            bot_alerts = self._bot.get_state().alerts
            # Deduplicate: don't repeat the same alert more than once in the last 5
            if not bot_alerts or bot_alerts[-1] != alert:
                bot_alerts.append(alert)

        # Broadcast to WebSocket clients (non-blocking fire-and-forget)
        asyncio.create_task(
            self._broadcast(
                {
                    "type": "agent_report",
                    "data": {
                        "agent": report.agent,
                        "status": report.status,
                        "message": report.message,
                        "timestamp": report.timestamp.isoformat(),
                        "details": report.details,
                    },
                }
            )
        )
