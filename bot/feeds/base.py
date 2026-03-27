"""Abstract base class for price feeds."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod


class PriceFeed(ABC):
    """Abstract price feed providing real-time prices."""

    def __init__(self) -> None:
        self._last_price: float | None = None
        self._last_updated: float = 0.0
        self._latency_ms: float = 0.0

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique name of this price source."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the price source and start receiving updates."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect cleanly."""
        ...

    def get_price(self) -> float | None:
        """Return the latest price, or None if unavailable."""
        return self._last_price

    @property
    def last_updated(self) -> float:
        return self._last_updated

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    def is_healthy(self, max_stale_seconds: float = 5.0) -> bool:
        if self._last_price is None:
            return False
        return (time.time() - self._last_updated) < max_stale_seconds

    def _update_price(self, price: float, send_ts: float | None = None) -> None:
        now = time.time()
        self._last_price = price
        self._last_updated = now
        if send_ts is not None:
            self._latency_ms = (now - send_ts) * 1000.0
