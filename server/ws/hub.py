"""WebSocket hub — fanout bot events to all connected dashboard clients."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from bot.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketHub:
    """Manages connected WebSocket clients and broadcasts events."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("WS client connected", total=len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("WS client disconnected", total=len(self._clients))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send event JSON to all connected clients. Remove disconnected ones."""
        if not self._clients:
            return
        message = json.dumps(event)
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)
