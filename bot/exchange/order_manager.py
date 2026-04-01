"""Order manager: track open orders, place quotes, cancel stale orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from bot.engine.algorithms.base import QuoteSet
from bot.exchange.hyperliquid_client import HyperliquidClient, ModifyRequest, OrderRequest, UserState
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

    async def place_quotes(
        self,
        quote_set: QuoteSet,
        fair_price: Decimal,
        user_state: UserState | None = None,
    ) -> int:
        """Place all quotes from a QuoteSet. Returns count of placed orders.

        Skips levels that would exceed available spot balance to prevent
        'Insufficient spot balance' rejections from the exchange.

        Pass ``user_state`` when the caller already has a fresh state to avoid
        an extra round-trip to the exchange.
        """
        if user_state is None:
            user_state = await self._client.async_get_user_state()
        avail_usdc = user_state.usdc_available
        avail_xmr = user_state.xmr_available

        requests: list[OrderRequest] = []
        for level in quote_set.bids:
            cost = level.price * level.size
            if cost > avail_usdc:
                logger.debug(
                    "Skipping bid level: insufficient USDC",
                    needed=float(cost),
                    available=float(avail_usdc),
                )
                continue
            avail_usdc -= cost
            requests.append(
                OrderRequest(
                    side="buy",
                    price=level.price,
                    size=level.size,
                    asset=self._asset,
                )
            )
        for level in quote_set.asks:
            if level.size > avail_xmr:
                logger.debug(
                    "Skipping ask level: insufficient XMR",
                    needed=float(level.size),
                    available=float(avail_xmr),
                )
                continue
            avail_xmr -= level.size
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

        responses = await self._client.async_bulk_place_orders(requests)
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

    async def modify_or_replace_quotes(
        self,
        quote_set: QuoteSet,
        fair_price: Decimal,
        use_modify: bool = True,
        user_state: UserState | None = None,
    ) -> int:
        """Place quotes using modify-in-place when possible, else cancel+replace.

        Modify-in-place uses 1 API op per order (vs 2 for cancel+place), saving
        ~50% of Hyperliquid order weight budget per refresh cycle.

        Pass ``user_state`` (already fetched in the calling cycle) so the fallback
        cancel+replace path can skip redundant exchange fetches and avoid stalling
        the event loop for 25-30 s when the API is slow.

        Falls back to cancel+replace when:
        - use_modify is False (config opt-out)
        - No existing open orders to modify
        - Level count changed (e.g. regime switch CALM→VOLATILE reduces levels)
        - The bulk modify call fails (SDK error, order already filled, etc.)
        """
        existing_bids = sorted(
            [o for o in self._open_orders.values() if o.side == "buy"],
            key=lambda o: o.price,
            reverse=True,  # best bid (highest) first — matches quote_set.bids order
        )
        existing_asks = sorted(
            [o for o in self._open_orders.values() if o.side == "sell"],
            key=lambda o: o.price,  # best ask (lowest) first — matches quote_set.asks order
        )

        can_modify = (
            use_modify
            and bool(self._open_orders)
            and len(existing_bids) == len(quote_set.bids)
            and len(existing_asks) == len(quote_set.asks)
        )

        if can_modify:
            modifies: list[ModifyRequest] = []
            for old, new_level in zip(existing_bids, quote_set.bids):
                modifies.append(ModifyRequest(oid=old.oid, side="buy", price=new_level.price, size=new_level.size))
            for old, new_level in zip(existing_asks, quote_set.asks):
                modifies.append(ModifyRequest(oid=old.oid, side="sell", price=new_level.price, size=new_level.size))

            success = await self._client.async_bulk_modify_orders(modifies)
            if success:
                # Update tracked prices/sizes in place (oids remain the same)
                for mod in modifies:
                    if mod.oid in self._open_orders:
                        self._open_orders[mod.oid].price = mod.price
                        self._open_orders[mod.oid].size = mod.size
                        await repository.update_order_price(mod.oid, float(mod.price), float(mod.size))
                logger.debug("Modified quotes in place", count=len(modifies))
                return len(modifies)
            # Modify failed — fall through to cancel+replace
            logger.debug("modify_or_replace: modify failed, falling back to cancel+replace")

        # Standard cancel+replace path.
        # Use cancel_all() (locally tracked oids) to avoid an extra exchange GET
        # in the hot path. Any untracked resting orders are cleaned up every 30 s
        # by OrderIntegrityAgent's cancel_all_exchange_orders call.
        await self.cancel_all()

        # Re-use the caller-provided user_state to skip one more round-trip.
        # After cancel, held amounts are freed, so available = total balance.
        # If user_state is unavailable, place_quotes fetches fresh.
        freed_state: UserState | None = None
        if user_state is not None:
            freed_state = UserState(
                usdc_balance=user_state.usdc_balance,
                xmr_balance=user_state.xmr_balance,
                usdc_available=user_state.usdc_balance,   # holds cleared by cancel
                xmr_available=user_state.xmr_balance,    # holds cleared by cancel
                open_orders=[],
            )
        return await self.place_quotes(quote_set, fair_price, user_state=freed_state)

    async def cancel_all(self) -> int:
        """Cancel all tracked open orders. Returns count cancelled."""
        if not self._open_orders:
            return 0
        oids = list(self._open_orders.keys())
        success = await self._client.async_bulk_cancel_orders(oids)
        if success:
            for oid in oids:
                await repository.update_order_status(oid, "cancelled")
            self._open_orders.clear()
            # Invalidate balance cache so subsequent place_quotes() sees freed hold
            self._client.invalidate_user_state_cache()
            logger.debug("Cancelled all orders", count=len(oids))
            return len(oids)
        return 0

    async def cancel_all_exchange_orders(self) -> int:
        """Cancel ALL open orders on the exchange (including from previous sessions).

        Uses async_get_open_orders (1 HTTP call) instead of async_get_user_state
        (2 HTTP calls) since we only need the oid list here.
        """
        try:
            raw_orders = await self._client.async_get_open_orders()
            stale_oids = [str(o["oid"]) for o in raw_orders]
            if not stale_oids:
                return 0
            await self._client.async_bulk_cancel_orders(stale_oids)
            self._client.invalidate_user_state_cache()
            self._open_orders.clear()
            logger.debug("Cancelled all exchange orders", count=len(stale_oids))
            return len(stale_oids)
        except Exception as e:
            logger.warning("cancel_all_exchange_orders failed", error=str(e))
            return 0

    def clear_local_orders(self) -> int:
        """Clear locally tracked orders without touching the exchange.

        Returns the number of orders cleared. Used by OrderIntegrityAgent to
        recover from ghost-order state. Returns 0 if already empty (harmless race).
        """
        count = len(self._open_orders)
        self._open_orders.clear()
        if count > 0:
            logger.warning("Local order state cleared (ghost order recovery)", count=count)
        return count

    def remove_order(self, oid: str) -> None:
        """Remove a single order from local tracking (e.g. on fill event)."""
        self._open_orders.pop(oid, None)

    def on_order_update(self, event: dict[str, Any]) -> None:
        """Process an order update event from WebSocket.

        Hyperliquid orderUpdates nests oid under event["order"]["oid"],
        not at the top level. We check both locations for robustness.
        """
        order_data: dict[str, Any] = event.get("order", {}) if isinstance(event.get("order"), dict) else {}
        oid = str(order_data.get("oid", "") or event.get("oid", ""))
        status: str = str(event.get("status", ""))
        if not oid:
            return
        if status in ("cancelled", "filled", "rejected"):
            self._open_orders.pop(oid, None)
        elif oid in self._open_orders:
            self._open_orders[oid].status = status
