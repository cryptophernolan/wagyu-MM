"""Base class for all autonomous health monitoring agents."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal

AgentStatus = Literal["OK", "WARN", "CRITICAL", "UNKNOWN"]


@dataclass
class AgentReport:
    """Result of a single agent health check."""

    agent: str
    status: AgentStatus
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)


ReportCallback = Callable[[AgentReport], None]


class BaseAgent(ABC):
    """Abstract base for all monitoring agents.

    Each agent runs in its own asyncio task, calling ``check()`` at a fixed
    interval and reporting results via a callback to the AgentRunner.
    """

    name: str
    check_interval: float  # seconds between checks

    def __init__(self, on_report: ReportCallback) -> None:
        self._on_report = on_report
        self._running = False

    async def run(self) -> None:
        """Continuous monitoring loop — runs until task is cancelled."""
        self._running = True
        while self._running:
            try:
                report = await self.check()
                self._on_report(report)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._on_report(
                    AgentReport(
                        agent=self.name,
                        status="UNKNOWN",
                        message=f"Agent check raised unexpected error: {e}",
                        details={"error": str(e)},
                    )
                )
            await asyncio.sleep(self.check_interval)

    def stop(self) -> None:
        self._running = False

    @abstractmethod
    async def check(self) -> AgentReport:
        """Perform one health check and return an AgentReport."""
        ...
