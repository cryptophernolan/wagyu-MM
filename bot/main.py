"""Bot entry point — initialize all components and start event loop."""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

from bot.config import load_config
from bot.engine.inventory import InventoryManager
from bot.engine.market_maker import MarketMaker
from bot.engine.quoting import QuoteCalculator
from bot.engine.volatility import VolatilityEstimator
from bot.exchange.hyperliquid_client import HyperliquidClient
from bot.exchange.order_manager import OrderManager
from bot.exchange.ws_client import HyperliquidWsClient
from bot.feeds.hyperliquid_feed import HyperliquidFeed
from bot.feeds.kraken_feed import KrakenFeed
from bot.feeds.price_aggregator import PriceAggregator
from bot.persistence.database import close_db, create_tables, init_db
from bot.risk.risk_manager import RiskManager
from bot.utils.logger import get_logger, setup_logger


async def main() -> None:
    config = load_config()
    setup_logger(config.env.log_level, config.env.env)
    logger = get_logger("main")
    logger.info("Starting Wagyu Market Maker", version="2.4.1")

    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    # Init database
    init_db()
    await create_tables()

    # Init feeds
    hl_feed = HyperliquidFeed(config.exchange.ws_url, config.exchange.asset)
    feeds: list[Any] = [hl_feed]
    if config.exchange.kraken_symbol:
        kraken_feed = KrakenFeed()
        feeds.append(kraken_feed)
        logger.info("Kraken feed enabled", symbol=config.exchange.kraken_symbol)
    else:
        logger.info("Kraken feed disabled (kraken_symbol is empty)")
    aggregator = PriceAggregator(
        feeds=feeds,
        stale_seconds=config.risk.stale_feed_seconds,
    )

    # Init exchange client
    client = HyperliquidClient(
        api_url=config.exchange.api_url,
        private_key=config.env.hl_private_key,
        wallet_address=config.env.hl_wallet_address,
        asset=config.exchange.asset,
    )
    client.initialize()

    ws_client = HyperliquidWsClient(config.exchange.ws_url, config.env.hl_wallet_address)

    inventory = InventoryManager()
    volatility = VolatilityEstimator(
        window_minutes=config.volatility.window_minutes,
        calm_threshold_bps=config.volatility.calm_threshold_bps,
        volatile_threshold_bps=config.volatility.volatile_threshold_bps,
    )
    order_manager = OrderManager(client, config.exchange.asset)
    risk_manager = RiskManager(config)
    quote_calculator = QuoteCalculator(config)

    bot = MarketMaker(
        config=config,
        client=client,
        ws_client=ws_client,
        aggregator=aggregator,
        inventory=inventory,
        volatility=volatility,
        order_manager=order_manager,
        risk_manager=risk_manager,
        quote_calculator=quote_calculator,
    )

    loop = asyncio.get_event_loop()

    def shutdown(sig: signal.Signals) -> None:
        logger.info("Shutdown signal received", signal=sig.name)
        bot.stop()

    # Register signal handlers (Unix only; Windows does not support SIGTERM via add_signal_handler)
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: shutdown(s))

    try:
        await bot.run()
    finally:
        await close_db()
        logger.info("MarketMaker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
