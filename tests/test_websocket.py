"""WebSocket hub unit tests — in-memory mocks, no real server required."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.ws.hub import WebSocketHub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(fail_send: bool = False) -> MagicMock:
    """Return a mock WebSocket with an async send_text method."""
    ws = MagicMock()
    if fail_send:
        ws.send_text = AsyncMock(side_effect=RuntimeError("disconnected"))
    else:
        ws.send_text = AsyncMock()
    ws.accept = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# WebSocketHub unit tests
# ---------------------------------------------------------------------------


class TestWebSocketHubClientCount:
    @pytest.mark.asyncio
    async def test_initial_client_count_is_zero(self) -> None:
        hub = WebSocketHub()
        assert hub.client_count == 0

    @pytest.mark.asyncio
    async def test_connect_increments_count(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)
        assert hub.client_count == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_clients(self) -> None:
        hub = WebSocketHub()
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        await hub.connect(ws1)
        await hub.connect(ws2)
        await hub.connect(ws3)
        assert hub.client_count == 3

    @pytest.mark.asyncio
    async def test_disconnect_decrements_count(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)
        hub.disconnect(ws)
        assert hub.client_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_client_is_safe(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        # disconnect without connecting — should not raise
        hub.disconnect(ws)
        assert hub.client_count == 0

    @pytest.mark.asyncio
    async def test_connect_calls_ws_accept(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)
        ws.accept.assert_awaited_once()


class TestWebSocketHubBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_hub_does_not_raise(self) -> None:
        hub = WebSocketHub()
        event: dict[str, Any] = {"type": "state_update", "data": {"state": "RUNNING"}}
        # Should complete without error
        await hub.broadcast(event)

    @pytest.mark.asyncio
    async def test_broadcast_sends_json_to_all_clients(self) -> None:
        hub = WebSocketHub()
        ws1, ws2 = _make_ws(), _make_ws()
        await hub.connect(ws1)
        await hub.connect(ws2)

        event: dict[str, Any] = {"type": "fill_event", "data": {"side": "buy"}}
        await hub.broadcast(event)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_message_is_valid_json(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)

        event: dict[str, Any] = {"type": "ping", "ts": 1700000000.0}
        await hub.broadcast(event)

        call_args = ws.send_text.call_args
        assert call_args is not None
        raw_msg: str = call_args[0][0]
        parsed: dict[str, Any] = json.loads(raw_msg)
        assert parsed["type"] == "ping"

    @pytest.mark.asyncio
    async def test_broadcast_serializes_nested_data(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)

        event: dict[str, Any] = {
            "type": "state_update",
            "data": {
                "state": "RUNNING",
                "fair_price": 155.50,
                "feed_health": [{"source": "hyperliquid", "healthy": True}],
            },
        }
        await hub.broadcast(event)

        raw: str = ws.send_text.call_args[0][0]
        parsed = json.loads(raw)
        assert parsed["data"]["fair_price"] == pytest.approx(155.50)
        assert len(parsed["data"]["feed_health"]) == 1

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_clients(self) -> None:
        hub = WebSocketHub()
        good_ws = _make_ws(fail_send=False)
        bad_ws = _make_ws(fail_send=True)

        await hub.connect(good_ws)
        await hub.connect(bad_ws)
        assert hub.client_count == 2

        event: dict[str, Any] = {"type": "test"}
        await hub.broadcast(event)

        # The bad client should have been removed automatically
        assert hub.client_count == 1
        good_ws.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_multiple_events_accumulate_on_client(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)

        for i in range(3):
            await hub.broadcast({"type": "tick", "i": i})

        assert ws.send_text.await_count == 3

    @pytest.mark.asyncio
    async def test_disconnect_then_broadcast_skips_removed_client(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)
        hub.disconnect(ws)

        await hub.broadcast({"type": "test"})
        ws.send_text.assert_not_awaited()


class TestWebSocketHubMessageFormat:
    @pytest.mark.asyncio
    async def test_state_update_event_type_field(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)

        event: dict[str, Any] = {
            "type": "state_update",
            "data": {
                "state": "RUNNING",
                "cycle_count": 5,
            },
        }
        await hub.broadcast(event)

        raw: str = ws.send_text.call_args[0][0]
        parsed = json.loads(raw)
        assert "type" in parsed
        assert parsed["type"] == "state_update"

    @pytest.mark.asyncio
    async def test_fill_event_type_field(self) -> None:
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws)

        event: dict[str, Any] = {
            "type": "fill_event",
            "data": {"side": "sell", "price": 155.80, "size": 0.25, "fee": 0.002},
        }
        await hub.broadcast(event)

        raw: str = ws.send_text.call_args[0][0]
        parsed = json.loads(raw)
        assert parsed["type"] == "fill_event"
        assert parsed["data"]["side"] == "sell"
