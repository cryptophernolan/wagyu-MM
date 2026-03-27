"""Volatility estimator with rolling window and regime detection."""
from __future__ import annotations

import math
import time
from collections import deque
from decimal import Decimal
from typing import Literal

from bot.utils.logger import get_logger

logger = get_logger(__name__)

Regime = Literal["CALM", "VOLATILE"]


class VolatilityEstimator:
    """
    Rolling realized volatility estimator with CALM/VOLATILE regime detection.
    Uses hysteresis to prevent regime flickering.
    """

    def __init__(
        self,
        window_minutes: int = 30,
        calm_threshold_bps: float = 20.0,
        volatile_threshold_bps: float = 35.0,
    ) -> None:
        self._window_seconds = window_minutes * 60
        self._calm_threshold = calm_threshold_bps / 10000.0  # convert to fraction
        self._volatile_threshold = volatile_threshold_bps / 10000.0
        self._prices: deque[tuple[float, Decimal]] = deque()  # (timestamp, price)
        self._regime: Regime = "CALM"

    def add_price(self, price: Decimal, ts: float | None = None) -> None:
        now = ts if ts is not None else time.time()
        self._prices.append((now, price))
        # Evict old prices outside the rolling window
        cutoff = now - self._window_seconds
        while self._prices and self._prices[0][0] < cutoff:
            self._prices.popleft()

    def compute_realized_vol(self) -> float:
        """Compute realized volatility as annualized fraction from log returns."""
        if len(self._prices) < 2:
            return 0.0
        prices = [float(p) for _, p in self._prices]
        log_returns = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0.0 and prices[i] > 0.0
        ]
        if not log_returns:
            return 0.0
        mean_ret = sum(log_returns) / len(log_returns)
        variance = sum((r - mean_ret) ** 2 for r in log_returns) / max(
            len(log_returns) - 1, 1
        )
        std_per_obs = math.sqrt(variance)
        # Annualize: observations arrive roughly every 2s
        # 365 * 24 * 3600 / 2 = 15_768_000 observations per year
        obs_per_year = 365 * 24 * 1800
        annualized = std_per_obs * math.sqrt(obs_per_year)
        return annualized

    def compute_realized_vol_bps(self) -> float:
        """Return realized vol in basis points (annualized)."""
        return self.compute_realized_vol() * 10000.0

    def get_vol_bps(self) -> float:
        return self.compute_realized_vol_bps()

    def get_regime(self) -> Regime:
        """
        Get current regime with hysteresis:
        CALM -> VOLATILE when vol > volatile_threshold
        VOLATILE -> CALM when vol < calm_threshold
        """
        vol = self.compute_realized_vol()
        if self._regime == "CALM" and vol > self._volatile_threshold:
            self._regime = "VOLATILE"
            logger.info(
                "Regime switch: CALM -> VOLATILE",
                vol_bps=round(vol * 10000, 2),
            )
        elif self._regime == "VOLATILE" and vol < self._calm_threshold:
            self._regime = "CALM"
            logger.info(
                "Regime switch: VOLATILE -> CALM",
                vol_bps=round(vol * 10000, 2),
            )
        return self._regime

    @property
    def price_count(self) -> int:
        return len(self._prices)
