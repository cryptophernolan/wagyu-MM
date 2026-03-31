"""Hyperliquid WebSocket price feed (allMids subscription)."""
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


class HyperliquidFeed(PriceFeed):
    def __init__(self, ws_url: str, asset: str = "XMR1") -> None:
        super().__init__()
        self._ws_url = ws_url
        self._asset = asset
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def source_name(self) -> str:
        return "hyperliquid"

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
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                ) as ws:
                    backoff = 1.0
                    subscribe_msg = json.dumps({
                        "method": "subscribe",
                        "subscription": {"type": "allMids"}
                    })
                    await ws.send(subscribe_msg)
                    logger.info("HyperliquidFeed connected", ws_url=self._ws_url)
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            try:
                                msg: dict[str, Any] = json.loads(raw)
                                self._handle_message(msg)
                            except (json.JSONDecodeError, KeyError) as e:
                                logger.warning("HyperliquidFeed parse error", error=str(e))
                        except asyncio.TimeoutError:
                            # allMids normally streams every few seconds; 30 s timeout
                            # indicates the connection is silently dead — ping to check.
                            await ws.send(json.dumps({"method": "ping"}))
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                if not self._running:
                    break
                logger.warning("HyperliquidFeed disconnected, reconnecting", error=str(e), backoff=backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _handle_message(self, msg: dict[str, Any]) -> None:
        channel = msg.get("channel", "")
        if channel == "allMids":
            data = msg.get("data", {})
            mids: dict[str, str] = data.get("mids", {})
            price_str = mids.get(self._asset)
            if price_str is not None:
                try:
                    self._update_price(float(price_str))
                except ValueError:
                    pass
            else:
                # allMids received but asset not in this batch — server skips unchanged mids.
                # Connection is alive, so keep last_updated fresh (same as KrakenFeed heartbeat).
                if self._last_price is not None:
                    import time as _time
                    self._last_updated = _time.time()
