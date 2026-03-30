"""FastAPI dependency injection providers."""
from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bot.engine.market_maker import MarketMaker
from bot.persistence.database import get_session
from bot.utils.logger import get_logger
from server.ws.hub import WebSocketHub

if TYPE_CHECKING:
    from bot.agents.agent_runner import AgentRunner

logger = get_logger(__name__)

# These will be set by server/main.py lifespan
_bot: MarketMaker | None = None
_ws_hub: WebSocketHub | None = None
_agent_runner: "AgentRunner | None" = None


def set_bot(bot: MarketMaker) -> None:
    global _bot
    _bot = bot


def set_ws_hub(hub: WebSocketHub) -> None:
    global _ws_hub
    _ws_hub = hub


def set_agent_runner(runner: "AgentRunner") -> None:
    global _agent_runner
    _agent_runner = runner


def get_bot() -> MarketMaker:
    if _bot is None:
        raise RuntimeError("Bot not initialized")
    return _bot


def get_ws_hub() -> WebSocketHub:
    if _ws_hub is None:
        raise RuntimeError("WebSocket hub not initialized")
    return _ws_hub


def get_agent_runner() -> "AgentRunner":
    if _agent_runner is None:
        raise RuntimeError("AgentRunner not initialized")
    return _agent_runner


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session() as session:
        yield session
