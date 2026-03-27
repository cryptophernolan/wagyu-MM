"""Price aggregator — weighted average of multiple feeds with fallback."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from bot.feeds.base import PriceFeed
from bot.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FeedHealth:
    source: str
    healthy: bool
    price: float | None
    latency_ms: float
    last_updated: float


class PriceAggregator:
    """Aggregates prices from multiple feeds with weighted average and fallback."""

    def __init__(self, feeds: list[PriceFeed], weights: list[float] | None = None, stale_seconds: float = 5.0) -> None:
        if len(feeds) == 0:
            raise ValueError("At least one feed required")
        self._feeds = feeds
        self._weights = weights if weights is not None else [1.0 / len(feeds)] * len(feeds)
        self._stale_seconds = stale_seconds
        self._halted = False

    async def connect_all(self) -> None:
        import asyncio
        await asyncio.gather(*[f.connect() for f in self._feeds])

    async def disconnect_all(self) -> None:
        import asyncio
        await asyncio.gather(*[f.disconnect() for f in self._feeds])

    def get_price(self) -> float | None:
        """Return weighted average of healthy feeds, or single healthy feed, or None."""
        healthy_pairs: list[tuple[float, float]] = []
        for feed, weight in zip(self._feeds, self._weights):
            if feed.is_healthy(self._stale_seconds):
                price = feed.get_price()
                if price is not None:
                    healthy_pairs.append((price, weight))

        if not healthy_pairs:
            return None

        total_weight = sum(w for _, w in healthy_pairs)
        if total_weight == 0:
            return None
        return sum(p * w for p, w in healthy_pairs) / total_weight

    def is_halted(self) -> bool:
        """Return True if NO feeds are healthy."""
        return not any(f.is_healthy(self._stale_seconds) for f in self._feeds)

    def get_feed_health(self) -> list[FeedHealth]:
        return [
            FeedHealth(
                source=f.source_name,
                healthy=f.is_healthy(self._stale_seconds),
                price=f.get_price(),
                latency_ms=f.latency_ms,
                last_updated=f.last_updated,
            )
            for f in self._feeds
        ]
