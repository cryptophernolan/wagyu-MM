"""Hyperliquid exchange client wrapping the official SDK."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from bot.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrderRequest:
    """A single order request to place."""
    side: str  # "buy" | "sell"
    price: Decimal
    size: Decimal
    asset: str
    is_buy: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_buy = self.side == "buy"


@dataclass
class OrderResponse:
    """Response from placing an order."""
    oid: str
    status: str
    price: Decimal
    size: Decimal
    side: str


@dataclass
class ModifyRequest:
    """A single in-place order modification (price/size change, same oid)."""
    oid: str
    side: str  # "buy" | "sell"
    price: Decimal
    size: Decimal
    is_buy: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_buy = self.side == "buy"


@dataclass
class L2Level:
    price: Decimal
    size: Decimal


@dataclass
class L2Book:
    bids: list[L2Level]
    asks: list[L2Level]


@dataclass
class UserState:
    usdc_balance: Decimal
    xmr_balance: Decimal
    usdc_available: Decimal   # usdc_balance - amount held in open bid orders
    xmr_available: Decimal    # xmr_balance  - amount held in open ask orders
    open_orders: list[dict[str, Any]]


class HyperliquidClient:
    """Wraps hyperliquid-python-sdk Exchange + Info clients."""

    def __init__(
        self,
        api_url: str,
        private_key: str,
        wallet_address: str,
        asset: str = "XMR1",
        base_coin: str = "",
    ) -> None:
        self._api_url = api_url
        self._private_key = private_key
        self._wallet_address = wallet_address
        self._asset = asset
        # base_coin is the actual token name for balance lookup (e.g. "HYPE" for "@1035").
        # Falls back to asset.split("/")[0] if not set.
        self._base_coin: str = base_coin if base_coin else asset.split("/")[0]
        self._exchange: Any = None
        self._info: Any = None
        # User state cache — avoids a blocking REST call every cycle
        self._user_state_cache: UserState | None = None
        self._user_state_cache_ts: float = 0.0
        self._user_state_cache_ttl: float = 10.0  # seconds

    def initialize(self) -> None:
        """Initialize SDK clients. Call once before using."""
        try:
            import socket as _socket
            import eth_account
            from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]
            from hyperliquid.info import Info  # type: ignore[import-untyped]

            # Set global socket timeout so SDK HTTP calls (which have no built-in
            # timeout) cannot block a thread-pool thread for more than 10 seconds.
            # Without this, a slow exchange API hangs the thread, saturates the
            # executor pool, and causes the asyncio event loop to appear frozen.
            _socket.setdefaulttimeout(10.0)

            account = eth_account.Account.from_key(self._private_key)
            base_url = self._api_url

            # Pre-fetch and filter spot_meta to remove entries with out-of-range
            # token indices (occurs on testnet with newly deployed/incomplete markets).
            import requests as _requests
            raw_spot: dict[str, Any] = _requests.post(
                base_url.rstrip("/") + "/info",
                json={"type": "spotMeta"},
                timeout=10,
            ).json()
            num_tokens = len(raw_spot.get("tokens", []))
            raw_spot["universe"] = [
                u for u in raw_spot.get("universe", [])
                if all(t < num_tokens for t in u.get("tokens", []))
            ]
            self._info = Info(base_url, skip_ws=True, spot_meta=raw_spot)
            self._exchange = Exchange(
                account, base_url,
                account_address=self._wallet_address,
                spot_meta=raw_spot,
            )
            logger.info(
                "HyperliquidClient initialized",
                wallet=self._wallet_address[:10] + "...",
            )
        except ImportError:
            logger.error(
                "hyperliquid-python-sdk not installed. Run: pip install hyperliquid-python-sdk"
            )
            raise
        except Exception as e:
            logger.error("Failed to initialize HyperliquidClient", error=str(e))
            raise

    def get_l2_book(self, asset: str | None = None) -> L2Book:
        """Fetch current L2 order book."""
        target = asset or self._asset
        try:
            raw: dict[str, Any] = self._info.l2_snapshot(target)
            # levels is [[bid_list], [ask_list]] where each entry has "px"/"sz" keys
            raw_levels: list[list[dict[str, str]]] = raw.get("levels", [[], []])
            bid_list = raw_levels[0] if len(raw_levels) > 0 else []
            ask_list = raw_levels[1] if len(raw_levels) > 1 else []
            bids = [L2Level(Decimal(b["px"]), Decimal(b["sz"])) for b in bid_list[:10]]
            asks = [L2Level(Decimal(a["px"]), Decimal(a["sz"])) for a in ask_list[:10]]
            return L2Book(bids=bids, asks=asks)
        except Exception as e:
            logger.warning("get_l2_book failed", error=str(e))
            return L2Book(bids=[], asks=[])

    def get_open_orders(self) -> list[dict[str, Any]]:
        """Fetch all open orders directly from the exchange REST API."""
        try:
            import requests as _requests
            raw: list[dict[str, Any]] = _requests.post(
                self._api_url.rstrip("/") + "/info",
                json={"type": "openOrders", "user": self._wallet_address},
                timeout=10,
            ).json()
            return raw if isinstance(raw, list) else []
        except Exception as e:
            logger.warning("get_open_orders failed", error=str(e))
            return []

    def invalidate_user_state_cache(self) -> None:
        """Force next get_user_state() call to fetch fresh data (call on fill)."""
        self._user_state_cache = None

    def get_user_state(self) -> UserState:
        """Fetch user spot balances and open orders via spotClearinghouseState.
        Results are cached for up to _user_state_cache_ttl seconds.
        Call invalidate_user_state_cache() after a fill to get fresh balances.
        """
        now = time.monotonic()
        if (
            self._user_state_cache is not None
            and (now - self._user_state_cache_ts) < self._user_state_cache_ttl
        ):
            return self._user_state_cache
        try:
            import requests as _requests
            raw: dict[str, Any] = _requests.post(
                self._api_url.rstrip("/") + "/info",
                json={"type": "spotClearinghouseState", "user": self._wallet_address},
                timeout=10,
            ).json()
            balances_list: list[dict[str, Any]] = raw.get("balances", [])
            usdc = Decimal("0")
            usdc_hold = Decimal("0")
            xmr_bal = Decimal("0")
            xmr_hold = Decimal("0")
            for b in balances_list:
                coin = b.get("coin", "")
                total = Decimal(str(b.get("total", "0")))
                hold = Decimal(str(b.get("hold", "0")))
                if coin == "USDC":
                    usdc = total
                    usdc_hold = hold
                elif coin == self._base_coin:
                    xmr_bal = total
                    xmr_hold = hold
            open_orders: list[dict[str, Any]] = self.get_open_orders()
            result = UserState(
                usdc_balance=usdc,
                xmr_balance=xmr_bal,
                usdc_available=max(Decimal("0"), usdc - usdc_hold),
                xmr_available=max(Decimal("0"), xmr_bal - xmr_hold),
                open_orders=open_orders,
            )
            self._user_state_cache = result
            self._user_state_cache_ts = time.monotonic()
            return result
        except Exception as e:
            logger.warning("get_user_state failed", error=str(e))
            return UserState(
                usdc_balance=Decimal("0"),
                xmr_balance=Decimal("0"),
                usdc_available=Decimal("0"),
                xmr_available=Decimal("0"),
                open_orders=[],
            )

    # Cumulative rate-limit back-off: when Hyperliquid rejects orders because the
    # account has sent too many ops relative to volume traded, we back off for
    # _CUMULATIVE_RL_BACKOFF_S seconds to avoid hammering the counter further.
    # (0.0 means "not rate-limited"; set to monotonic() + backoff on detection.)
    _cumulative_rl_until: float = 0.0
    _CUMULATIVE_RL_BACKOFF_S: float = 60.0
    _CUMULATIVE_RL_MSG = "Too many cumulative requests sent"

    def is_cumulative_rate_limited(self) -> bool:
        """Return True while the cumulative order-op rate limit back-off is active."""
        return time.monotonic() < self._cumulative_rl_until

    def _handle_cumulative_rl(self, error_msg: str) -> bool:
        """If error is the cumulative rate-limit, activate back-off and return True."""
        if self._CUMULATIVE_RL_MSG in error_msg:
            self._cumulative_rl_until = time.monotonic() + self._CUMULATIVE_RL_BACKOFF_S
            logger.warning(
                "Cumulative order-op rate limit hit — pausing order placement",
                backoff_seconds=self._CUMULATIVE_RL_BACKOFF_S,
                error=error_msg[:200],
            )
            return True
        return False

    def bulk_place_orders(self, orders: list[OrderRequest]) -> list[OrderResponse]:
        """Place multiple orders in one signed request (ALO/post-only)."""
        if not orders:
            return []
        if self.is_cumulative_rate_limited():
            logger.debug("bulk_place_orders: cumulative rate limit active, skipping")
            return []
        try:
            order_specs: list[dict[str, Any]] = []
            for o in orders:
                order_specs.append({
                    "coin": self._asset,
                    "is_buy": o.is_buy,
                    "sz": float(o.size),
                    "limit_px": float(o.price),
                    "order_type": {"limit": {"tif": "Alo"}},
                    "reduce_only": False,
                })
            raw_result: Any = self._exchange.bulk_orders(order_specs)
            if not isinstance(raw_result, dict):
                logger.warning("bulk_orders returned non-dict", result=str(raw_result)[:200])
                return []
            result: dict[str, Any] = raw_result
            # Check for top-level error (e.g. rate-limit: response is a string, not dict)
            if result.get("status") == "err":
                error_msg = str(result.get("response", ""))
                self._handle_cumulative_rl(error_msg)
                logger.warning("bulk_orders exchange error", error=error_msg[:300])
                return []
            response_field: Any = result.get("response", {})
            if not isinstance(response_field, dict):
                logger.warning("bulk_orders unexpected response format", result=str(result)[:300])
                return []
            responses: list[OrderResponse] = []
            statuses: list[Any] = (
                response_field
                .get("data", {})
                .get("statuses", [])
            )
            for i, status in enumerate(statuses):
                if "resting" in status:
                    resting: dict[str, Any] = status["resting"]
                    oid = str(resting.get("oid", ""))
                    responses.append(
                        OrderResponse(
                            oid=oid,
                            status="open",
                            price=orders[i].price,
                            size=orders[i].size,
                            side=orders[i].side,
                        )
                    )
                elif "error" in status:
                    logger.warning(
                        "Order rejected", error=status["error"], order_index=i
                    )
            return responses
        except Exception as e:
            logger.error("bulk_place_orders failed", error=str(e))
            return []

    def modify_order_sync(self, modify: ModifyRequest) -> bool:
        """Modify a single open order in place (price/size). Uses 1 API op vs 2 for cancel+place."""
        if not hasattr(self._exchange, "modify_order"):
            logger.warning("SDK does not support modify_order; use_order_modify should be false")
            return False
        try:
            # SDK signature: modify_order(oid, name, is_buy, sz, limit_px, order_type, ...)
            raw_result: Any = self._exchange.modify_order(
                int(modify.oid),
                self._asset,
                modify.is_buy,
                float(modify.size),
                float(modify.price),
                {"limit": {"tif": "Alo"}},
            )
            if not isinstance(raw_result, dict):
                logger.warning("modify_order unexpected result", result=str(raw_result)[:200])
                return False
            if raw_result.get("status") == "ok":
                return True
            # Parse statuses array — response may be a string on error (e.g. rate-limit
            # or order-not-found), so guard with isinstance before calling .get()
            resp: Any = raw_result.get("response", {})
            if isinstance(resp, dict):
                statuses: list[Any] = resp.get("data", {}).get("statuses", [])
                if statuses and isinstance(statuses[0], dict) and "resting" in statuses[0]:
                    return True
            # Any non-err response is treated as success
            if raw_result.get("status") != "err":
                return True
            logger.warning("modify_order rejected", result=str(raw_result)[:300])
            return False
        except Exception as e:
            logger.warning("modify_order_sync failed", oid=modify.oid, error=str(e))
            return False

    def bulk_modify_orders(self, modifies: list[ModifyRequest]) -> bool:
        """Modify multiple open orders in a single signed batch request.

        Uses Exchange.bulk_modify_orders_new() — one nonce for the entire batch,
        eliminating the duplicate-nonce error that occurred when concurrent
        individual modify_order() calls all fired within the same millisecond.
        """
        if not modifies:
            return True
        if not hasattr(self._exchange, "bulk_modify_orders_new"):
            # Fallback: sequential individual modifies (no nonce collisions since sequential)
            logger.warning("SDK lacks bulk_modify_orders_new; falling back to sequential modify")
            results = [self.modify_order_sync(m) for m in modifies]
            return any(results)
        try:
            sdk_modifies: list[dict[str, Any]] = []
            for m in modifies:
                sdk_modifies.append({
                    "oid": int(m.oid),
                    "order": {
                        "coin": self._asset,
                        "is_buy": m.is_buy,
                        "sz": float(m.size),
                        "limit_px": float(m.price),
                        "order_type": {"limit": {"tif": "Alo"}},
                        "reduce_only": False,
                    },
                })
            raw_result: Any = self._exchange.bulk_modify_orders_new(sdk_modifies)
            if not isinstance(raw_result, dict):
                logger.warning("bulk_modify_orders_new returned non-dict", result=str(raw_result)[:200])
                return False
            if raw_result.get("status") == "err":
                logger.warning("bulk_modify_orders_new exchange error", error=str(raw_result.get("response", ""))[:300])
                return False
            statuses: list[Any] = (
                raw_result.get("response", {})
                .get("data", {})
                .get("statuses", [])
            )
            error_msgs = [s.get("error", "") for s in statuses if isinstance(s, dict) and "error" in s]
            failed = len(error_msgs)
            total = len(statuses) if statuses else len(modifies)
            if failed == total:
                logger.warning(
                    "bulk_modify: all modifies failed",
                    failed=failed,
                    total=total,
                    errors=error_msgs[:3],  # log first 3 errors to diagnose
                )
                return False
            if failed > 0:
                logger.warning(
                    "bulk_modify: partial failures (continuing)",
                    failed=failed,
                    total=total,
                    errors=error_msgs[:3],
                )
            else:
                logger.debug("bulk_modify OK", count=total)
            return True
        except Exception as e:
            logger.error("bulk_modify_orders failed", error=str(e))
            return False

    async def async_bulk_modify_orders(self, modifies: list[ModifyRequest]) -> bool:
        """Async wrapper for bulk_modify_orders — runs in thread pool with timeout."""
        if not modifies:
            return True
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.bulk_modify_orders, modifies),
                timeout=12.0,
            )
        except asyncio.TimeoutError:
            logger.warning("async_bulk_modify_orders timed out after 12s — treating as failed")
            return False

    # ── Async wrappers (run sync SDK calls in thread pool, non-blocking) ──────
    # All wrappers enforce a hard timeout so a slow exchange API call never
    # blocks the asyncio event loop for more than _EXCHANGE_TIMEOUT_S seconds.

    _EXCHANGE_TIMEOUT_S = 8.0  # max seconds to wait for any single exchange call

    async def async_get_open_orders(self) -> list[dict[str, Any]]:
        """Async wrapper for get_open_orders — fetches open order list only (1 HTTP call)."""
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.get_open_orders),
                timeout=self._EXCHANGE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("async_get_open_orders timed out — returning empty list")
            return []

    async def async_get_user_state(self) -> UserState:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.get_user_state),
                timeout=self._EXCHANGE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("async_get_user_state timed out — returning empty state")
            return UserState(
                usdc_balance=Decimal("0"), xmr_balance=Decimal("0"),
                usdc_available=Decimal("0"), xmr_available=Decimal("0"),
                open_orders=[],
            )

    async def async_get_l2_book(self, asset: str | None = None) -> L2Book:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.get_l2_book, asset),
                timeout=self._EXCHANGE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("async_get_l2_book timed out — returning empty book")
            return L2Book(bids=[], asks=[])

    async def async_bulk_place_orders(self, orders: list[OrderRequest]) -> list[OrderResponse]:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.bulk_place_orders, orders),
                timeout=self._EXCHANGE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("async_bulk_place_orders timed out after 12s — orders may or may not have been placed")
            return []

    async def async_bulk_cancel_orders(self, oids: list[str]) -> bool:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.bulk_cancel_orders, oids),
                timeout=self._EXCHANGE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("async_bulk_cancel_orders timed out after 12s")
            return False

    def bulk_cancel_orders(self, oids: list[str]) -> bool:
        """Cancel multiple orders by oid."""
        if not oids:
            return True
        try:
            cancels: list[dict[str, Any]] = [
                {"coin": self._asset, "oid": int(oid)} for oid in oids
            ]
            raw_cancel: Any = self._exchange.bulk_cancel(cancels)
            if not isinstance(raw_cancel, dict):
                logger.warning("bulk_cancel returned non-dict", result=str(raw_cancel)[:200])
                return True  # treat as success to clear tracked orders
            statuses: list[Any] = (
                raw_cancel.get("response", {}).get("data", {}).get("statuses", [])
            )
            failed = [s for s in statuses if s != "success" and not isinstance(s, str)]
            if failed:
                # "already canceled, or filled" is expected when a fill races the cancel — log at debug
                real_failures = [
                    s for s in failed
                    if not (isinstance(s, dict) and "already canceled, or filled" in s.get("error", ""))
                ]
                if real_failures:
                    logger.warning("Some cancels failed", failed=real_failures, total=len(oids))
                else:
                    logger.debug("Cancel: orders already filled/cancelled (fill race)", count=len(failed))
            else:
                logger.debug("Bulk cancel OK", count=len(oids))
            return True
        except Exception as e:
            logger.error("bulk_cancel_orders failed", error=str(e))
            return False
