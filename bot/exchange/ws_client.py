"""Authenticated Hyperliquid WebSocket for orderUpdates and userFills."""
from __future__ import annotations

import asyncio
import json
import time as _time
from typing import Any, Callable

import websockets
from websockets.exceptions import ConnectionClosed

from bot.utils.logger import get_logger

logger = get_logger(__name__)

FillCallback = Callable[[dict[str, Any]], None]
OrderCallback = Callable[[dict[str, Any]], None]


class HyperliquidWsClient:
    """Subscribe to authenticated WebSocket channels."""

    def __init__(self, ws_url: str, wallet_address: str) -> None:
        self._ws_url = ws_url
        self._wallet_address = wallet_address
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._fill_callbacks: list[FillCallback] = []
        self._order_callbacks: list[OrderCallback] = []
        # Record session start in ms so we can skip historical fills replayed on subscribe
        self._session_start_ms: int = int(_time.time() * 1000)

    def on_fill(self, cb: FillCallback) -> None:
        self._fill_callbacks.append(cb)

    def on_order_update(self, cb: OrderCallback) -> None:
        self._order_callbacks.append(cb)

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
                # Disable library-level ping — Hyperliquid uses application-level
                # keepalive. We send {"method": "ping"} every 30 s of inactivity.
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=None,
                ) as ws:
                    backoff = 1.0
                    # Subscribe to authenticated channels
                    for channel in ["orderUpdates", "userFills"]:
                        sub_msg = json.dumps({
                            "method": "subscribe",
                            "subscription": {
                                "type": channel,
                                "user": self._wallet_address,
                            },
                        })
                        await ws.send(sub_msg)
                    logger.info(
                        "HyperliquidWsClient connected",
                        wallet=self._wallet_address[:10],
                    )
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            try:
                                msg: dict[str, Any] = json.loads(raw)
                                # Respond to server-initiated pings immediately.
                                # Hyperliquid sends {"method": "ping"} and expects
                                # {"method": "pong"} back; without this it closes
                                # the connection with 1000 "Inactive" after ~100 s.
                                if msg.get("method") == "ping":
                                    await ws.send(json.dumps({"method": "pong"}))
                                    continue
                                await self._dispatch(msg)
                            except json.JSONDecodeError:
                                pass
                        except asyncio.TimeoutError:
                            # No message for 30 s — send app-level ping to keep alive
                            await ws.send(json.dumps({"method": "ping"}))
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                if not self._running:
                    break
                logger.warning(
                    "HyperliquidWsClient disconnected, retrying",
                    backoff=backoff,
                    error=str(e),
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        channel: str = msg.get("channel", "")
        data: Any = msg.get("data", {})
        if channel == "userFills":
            # Skip the initial snapshot of historical fills sent on subscription.
            # Hyperliquid replays recent fills on each WS connect; if we processed
            # them the InventoryManager would accumulate stale positions each restart.
            if isinstance(data, dict) and data.get("isSnapshot"):
                logger.debug("Skipping userFills snapshot (historical fills ignored)")
                return
            fills: list[Any] = (
                data
                if isinstance(data, list)
                else data.get("fills", [])
                if isinstance(data, dict)
                else []
            )
            for fill in fills:
                # Secondary guard: skip fills whose timestamp predates this session
                fill_time_ms = int(fill.get("time", 0))
                if fill_time_ms > 0 and fill_time_ms < self._session_start_ms:
                    logger.debug(
                        "Skipping historical fill",
                        oid=fill.get("oid"),
                        fill_time_ms=fill_time_ms,
                        session_start_ms=self._session_start_ms,
                    )
                    continue
                for cb in self._fill_callbacks:
                    cb(fill)
        elif channel == "orderUpdates":
            updates: list[Any] = data if isinstance(data, list) else [data]
            for update in updates:
                for cb in self._order_callbacks:
                    cb(update)
