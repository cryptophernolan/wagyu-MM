"""Risk manager: pre-cycle checks and circuit breakers."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from bot.config import AppConfig
from bot.feeds.price_aggregator import PriceAggregator
from bot.utils.logger import get_logger

logger = get_logger(__name__)

RiskStatus = Literal["OK", "HALT"]


@dataclass
class RiskCheckResult:
    status: RiskStatus
    reason: str | None = None


class RiskManager:
    """Checks risk conditions before each trading cycle."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._halted = False
        self._halt_reason: str | None = None
        self._daily_realized_pnl_start: Decimal = Decimal("0")
        self._session_start_portfolio: Decimal | None = None

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def set_session_start_portfolio(self, value: Decimal) -> None:
        self._session_start_portfolio = value

    def set_daily_pnl_start(self, realized_pnl: Decimal) -> None:
        self._daily_realized_pnl_start = realized_pnl

    def reset_daily_pnl(self, current_realized_pnl: Decimal) -> None:
        """Call at midnight to reset daily PnL tracking."""
        self._daily_realized_pnl_start = current_realized_pnl
        logger.info("Daily PnL reset", start_pnl=float(current_realized_pnl))

    def trigger_halt(self, reason: str) -> None:
        self._halted = True
        self._halt_reason = reason
        logger.error("RISK HALT triggered", reason=reason)

    def clear_halt(self) -> None:
        self._halted = False
        self._halt_reason = None
        logger.info("Risk halt cleared")

    def check_pre_cycle(
        self,
        aggregator: PriceAggregator,
        realized_pnl: Decimal,
        portfolio_value: Decimal,
        inventory_xmr: Decimal,
    ) -> RiskCheckResult:
        """Run all pre-cycle risk checks. Returns OK or HALT with reason."""
        if self._halted:
            return RiskCheckResult(status="HALT", reason=self._halt_reason)

        # Check 1: Feed staleness — transient halt (auto-recovers when feed is healthy)
        # Do NOT use trigger_halt() here; that would permanently halt the bot.
        # Daily-loss and drawdown halts are permanent; stale-feed is not.
        if aggregator.is_halted():
            logger.warning("Price feeds stale — pausing cycle")
            return RiskCheckResult(status="HALT", reason="All price feeds are stale")

        # Check 2: Daily loss limit
        daily_pnl = float(realized_pnl - self._daily_realized_pnl_start)
        if daily_pnl <= -self._config.risk.daily_loss_limit_usdc:
            self.trigger_halt(f"Daily loss limit breached: {daily_pnl:.2f} USDC")
            return RiskCheckResult(status="HALT", reason=self._halt_reason)

        # Check 3: Max drawdown from session start
        if (
            self._session_start_portfolio is not None
            and self._session_start_portfolio > Decimal("0")
        ):
            drawdown_pct = float(
                (self._session_start_portfolio - portfolio_value)
                / self._session_start_portfolio
                * 100
            )
            if drawdown_pct >= self._config.risk.max_drawdown_pct:
                self.trigger_halt(f"Max drawdown breached: {drawdown_pct:.2f}%")
                return RiskCheckResult(status="HALT", reason=self._halt_reason)

        return RiskCheckResult(status="OK")
