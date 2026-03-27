"""FastAPI application factory with lifespan, CORS, WebSocket, and all routers."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from bot.persistence.database import close_db, create_tables, init_db
from bot.utils.logger import get_logger, setup_logger
from server import dependencies
from server.routers import chart, fills, health, orders, pnl, portfolio, report, status
from server.ws.hub import WebSocketHub

logger = get_logger(__name__)

_hub: WebSocketHub = WebSocketHub()
_bot_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    setup_logger()
    init_db()
    await create_tables()

    # Import here to avoid circular imports
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
    from bot.risk.risk_manager import RiskManager

    config = load_config()
    hl_feed = HyperliquidFeed(config.exchange.ws_url, config.exchange.asset)
    # Only include Kraken feed when a symbol is configured; skip for PURR/testnet
    feeds = [hl_feed]
    if config.exchange.kraken_symbol:
        kraken_feed = KrakenFeed(symbol=config.exchange.kraken_symbol)
        feeds.append(kraken_feed)
        logger.info("Kraken feed enabled", symbol=config.exchange.kraken_symbol)
    else:
        logger.info("Kraken feed disabled (no kraken_symbol configured)")
    aggregator = PriceAggregator(feeds=feeds, stale_seconds=config.risk.stale_feed_seconds)
    client = HyperliquidClient(
        api_url=config.exchange.api_url,
        private_key=config.env.hl_private_key,
        wallet_address=config.env.hl_wallet_address,
        asset=config.exchange.asset,
        base_coin=config.exchange.base_coin,
    )
    try:
        client.initialize()
    except Exception as e:
        logger.warning("Exchange client init failed (demo mode)", error=str(e))

    ws_hl = HyperliquidWsClient(config.exchange.ws_url, config.env.hl_wallet_address)
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
        config=config, client=client, ws_client=ws_hl,
        aggregator=aggregator, inventory=inventory, volatility=volatility,
        order_manager=order_manager, risk_manager=risk_manager,
        quote_calculator=quote_calculator,
    )

    # Wire bot events to WS hub
    def _on_bot_event(event: dict[str, Any]) -> None:
        asyncio.create_task(_hub.broadcast(event))

    bot.add_event_listener(_on_bot_event)

    dependencies.set_bot(bot)
    dependencies.set_ws_hub(_hub)

    global _bot_task
    _bot_task = asyncio.create_task(bot.run())

    logger.info("FastAPI server started")
    yield

    logger.info("FastAPI server shutting down")
    await bot.shutdown()
    if _bot_task is not None:
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title="Wagyu MM Dashboard API", version="2.4.1", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(status.router)
    app.include_router(portfolio.router)
    app.include_router(fills.router)
    app.include_router(orders.router)
    app.include_router(pnl.router)
    app.include_router(health.router)
    app.include_router(chart.router)
    app.include_router(report.router)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await _hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except WebSocketDisconnect:
            _hub.disconnect(websocket)

    return app


app = create_app()
