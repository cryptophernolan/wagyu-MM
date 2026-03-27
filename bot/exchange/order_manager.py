"""Order manager: track open orders, place quotes, cancel stale orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bot.engine.algorithms.base import QuoteSet
from bot.exchange.hyperliquid_client import HyperliquidClient, OrderRequest
from bot.persistence import repository
from bot.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrackedOrder:
    oid: str
    side: str
    price: Decimal
    size: Decimal
    status: str
    created_at: datetime


class OrderManager:
    """Manages the lifecycle of market maker orders."""

    def __init__(
        self,
        client: HyperliquidClient,
        asset: str = "XMR1",
    ) -> None:
        self._client = client
        self._asset = asset
        self._open_orders: dict[str, TrackedOrder] = {}

    def get_open_orders(self) -> list[TrackedOrder]:
        return list(self._open_orders.values())

    async def place_quotes(self, quote_set: QuoteSet, fair_price: Decimal) -> int:
        """Place all quotes from a QuoteSet. Returns count of placed orders."""
        requests: list[OrderRequest] = []
        for level in quote_set.bids:
            requests.append(
                OrderRequest(
                    side="buy",
                    price=level.price,
                    size=level.size,
                    asset=self._asset,
                )
            )
        for level in quote_set.asks:
            requests.append(
                OrderRequest(
                    side="sell",
                    price=level.price,
                    size=level.size,
                    asset=self._asset,
                )
            )

        if not requests:
            return 0

        responses = self._client.bulk_place_orders(requests)
        now = datetime.now(timezone.utc)
        placed = 0
        for resp in responses:
            order = TrackedOrder(
                oid=resp.oid,
                side=resp.side,
                price=resp.price,
                size=resp.size,
                status="open",
                created_at=now,
            )
            self._open_orders[resp.oid] = order
            await repository.save_order({
                "oid": resp.oid,
                "side": resp.side,
                "price": float(resp.price),
                "size": float(resp.size),
                "status": "open",
                "created_at": now,
                "updated_at": now,
            })
            placed += 1

        logger.debug(
            "Placed quotes",
            count=placed,
            bids=len(quote_set.bids),
            asks=len(quote_set.asks),
        )
        return placed

    async def cancel_all(self) -> int:
        """Cancel all tracked open orders. Returns count cancelled."""
        if not self._open_orders:
            return 0
        oids = list(self._open_orders.keys())
        success = self._client.bulk_cancel_orders(oids)
        if success:
            for oid in oids:
                await repository.update_order_status(oid, "cancelled")
            self._open_orders.clear()
            logger.debug("Cancelled all orders", count=len(oids))
            return len(oids)
        return 0

    async def cancel_all_exchange_orders(self) -> int:
        """Cancel ALL open orders on the exchange (including from previous sessions)."""
        try:
            user_state = self._client.get_user_state()
            stale_oids = [str(o["oid"]) for o in user_state.open_orders]
            if not stale_oids:
                return 0
            self._client.bulk_cancel_orders(stale_oids)
            self._open_orders.clear()
            logger.info("Cancelled stale exchange orders on startup", count=len(stale_oids))
            return len(stale_oids)
        except Exception as e:
            logger.warning("cancel_all_exchange_orders failed", error=str(e))
            return 0

    def on_order_update(self, event: dict[str, Any]) -> None:
        """Process an order update event from WebSocket."""
        oid = str(event.get("oid", ""))
        status: str = str(event.get("status", ""))
        if not oid:
            return
        if status in ("cancelled", "filled", "rejected"):
            self._open_orders.pop(oid, None)
        elif oid in self._open_orders:
            self._open_orders[oid].status = status
