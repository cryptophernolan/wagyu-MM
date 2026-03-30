"""Kraken WebSocket price feed (XMR/USDT ticker)."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from bot.feeds.base import PriceFeed
from bot.utils.logger import get_logger

logger = get_logger(__name__)

KRAKEN_WS_URL = "wss://ws.kraken.com/v2"


class KrakenFeed(PriceFeed):
    def __init__(self, symbol: str = "XMR/USDT") -> None:
        super().__init__()
        self._symbol = symbol
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def source_name(self) -> str:
        return "kraken"

    async def connect(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def disconnect(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(KRAKEN_WS_URL) as ws:
                    backoff = 1.0
                    subscribe_msg = json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "ticker", "symbol": [self._symbol]}
                    })
                    await ws.send(subscribe_msg)
                    logger.info("KrakenFeed connected", symbol=self._symbol)
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg: dict[str, Any] = json.loads(raw)
                            self._handle_message(msg)
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning("KrakenFeed parse error", error=str(e))
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                if not self._running:
                    break
                logger.warning("KrakenFeed disconnected, reconnecting", error=str(e), backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _handle_message(self, msg: dict[str, Any]) -> None:
        channel = msg.get("channel", "")
        if channel == "ticker":
            data_list = msg.get("data", [])
            if isinstance(data_list, list) and data_list:
                tick = data_list[0]
                last = tick.get("last")
                if last is not None:
                    try:
                        self._update_price(float(last))
                    except (ValueError, TypeError):
                        pass
        elif channel == "heartbeat":
            # Heartbeat confirms connection is alive. If we have a valid price,
            # refresh last_updated so the feed doesn't go stale between trades.
            # XMR/USDT is a low-volume pair on Kraken — trades may not arrive
            # every 5 seconds, but the last known price is still valid.
            if self._last_price is not None:
                self._last_updated = time.time()
