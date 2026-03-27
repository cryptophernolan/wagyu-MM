"""Unit tests for PriceFeed base class and PriceAggregator — PA-01 through PA-05."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.feeds.base import PriceFeed
from bot.feeds.price_aggregator import FeedHealth, PriceAggregator


class MockFeed(PriceFeed):
    """Concrete PriceFeed for testing — exposes internal setters."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    def set_price(self, price: float, age_seconds: float = 0.0) -> None:
        """Inject a price with a specific age (0 = just updated)."""
        self._last_price = price
        self._last_updated = time.time() - age_seconds
        self._latency_ms = 10.0


class TestPriceFeedBase:
    def test_initial_price_is_none(self) -> None:
        feed = MockFeed("test")
        assert feed.get_price() is None

    def test_initial_is_not_healthy(self) -> None:
        feed = MockFeed("test")
        assert not feed.is_healthy(5.0)

    def test_fresh_price_is_healthy(self) -> None:
        feed = MockFeed("test")
        feed.set_price(150.0, age_seconds=0.0)
        assert feed.is_healthy(5.0)

    def test_stale_price_is_not_healthy(self) -> None:
        feed = MockFeed("test")
        feed.set_price(150.0, age_seconds=10.0)  # 10s old, threshold is 5s
        assert not feed.is_healthy(5.0)

    def test_latency_updated_via_update_price(self) -> None:
        feed = MockFeed("test")
        send_ts = time.time() - 0.050  # simulated 50ms ago
        feed._update_price(150.0, send_ts=send_ts)
        assert feed.latency_ms >= 40.0  # at least 40ms

    def test_source_name_property(self) -> None:
        feed = MockFeed("hyperliquid")
        assert feed.source_name == "hyperliquid"


class TestPriceAggregator:
    def _make_feeds(
        self,
        prices: list[float | None],
        ages: list[float] | None = None,
    ) -> list[MockFeed]:
        if ages is None:
            ages = [0.0] * len(prices)
        feeds = []
        for i, (price, age) in enumerate(zip(prices, ages)):
            f = MockFeed(f"feed_{i}")
            if price is not None:
                f.set_price(price, age_seconds=age)
            feeds.append(f)
        return feeds

    def test_pa_01_both_feeds_healthy_weighted_average(self) -> None:
        """PA-01: Both feeds healthy → weighted average (50/50)."""
        feeds = self._make_feeds([100.0, 200.0])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        price = agg.get_price()
        assert price is not None
        assert abs(price - 150.0) < 0.001

    def test_pa_02_one_stale_uses_healthy_feed(self) -> None:
        """PA-02: Feed A healthy, Feed B stale → use Feed A price."""
        feeds = self._make_feeds([100.0, 200.0], ages=[0.0, 10.0])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        price = agg.get_price()
        assert price is not None
        assert abs(price - 100.0) < 0.001

    def test_pa_03_both_stale_is_halted(self) -> None:
        """PA-03: Both feeds stale → is_halted() = True."""
        feeds = self._make_feeds([100.0, 200.0], ages=[10.0, 10.0])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        assert agg.is_halted()

    def test_pa_03_both_stale_get_price_returns_none(self) -> None:
        feeds = self._make_feeds([100.0, 200.0], ages=[10.0, 10.0])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        assert agg.get_price() is None

    def test_pa_04_get_feed_health_has_two_entries(self) -> None:
        """PA-04: get_feed_health() returns list with len==2 for 2 feeds."""
        feeds = self._make_feeds([100.0, 200.0])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        health = agg.get_feed_health()
        assert len(health) == 2
        for item in health:
            assert isinstance(item, FeedHealth)
            assert item.source in ("feed_0", "feed_1")
            assert item.healthy is True

    def test_pa_05_feed_recovers_clears_halt(self) -> None:
        """PA-05: Feed returns healthy after stale → is_halted() = False."""
        feed = MockFeed("feed_0")
        feed.set_price(100.0, age_seconds=10.0)  # start stale
        agg = PriceAggregator([feed], stale_seconds=5.0)
        assert agg.is_halted()

        feed.set_price(100.0, age_seconds=0.0)  # now fresh
        assert not agg.is_halted()

    def test_no_feeds_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="At least one feed"):
            PriceAggregator([])

    def test_single_feed_returns_its_price(self) -> None:
        feeds = self._make_feeds([175.5])
        agg = PriceAggregator(feeds, stale_seconds=5.0)
        price = agg.get_price()
        assert price is not None
        assert abs(price - 175.5) < 0.001

    def test_no_price_feed_returns_none_even_if_fresh(self) -> None:
        """Feed is 'fresh' but has no price (last_updated>0 but price=None is impossible
        via is_healthy since is_healthy returns False when price is None)."""
        feed = MockFeed("feed_0")
        # Never set a price → is_healthy returns False → aggregator treats as stale
        agg = PriceAggregator([feed], stale_seconds=5.0)
        assert agg.get_price() is None

    def test_custom_weights_applied(self) -> None:
        feeds = self._make_feeds([100.0, 200.0])
        # Weight feed_0 heavily: 0.8 vs 0.2
        agg = PriceAggregator(feeds, weights=[0.8, 0.2], stale_seconds=5.0)
        price = agg.get_price()
        assert price is not None
        expected = (100.0 * 0.8 + 200.0 * 0.2) / (0.8 + 0.2)
        assert abs(price - expected) < 0.001
