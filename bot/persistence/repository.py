"""Repository layer — async CRUD operations over SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text

from bot.persistence.database import get_session
from bot.persistence.models import Fill, HodlBenchmark, Order, PnLSnapshot, PriceSnapshot


# ---------------------------------------------------------------------------
# Fills
# ---------------------------------------------------------------------------


async def save_fill(fill_data: dict[str, Any]) -> None:
    """Persist a new fill record to the database."""
    async with get_session() as session:
        fill = Fill(
            timestamp=fill_data["timestamp"],
            oid=fill_data["oid"],
            side=fill_data["side"],
            price=float(fill_data["price"]),
            size=float(fill_data["size"]),
            fee=float(fill_data["fee"]),
            is_maker=bool(fill_data.get("is_maker", True)),
            mid_price_at_fill=float(fill_data.get("mid_price_at_fill", 0.0)),
        )
        session.add(fill)


async def get_fills(page: int = 1, limit: int = 50) -> tuple[list[dict[str, Any]], int]:
    """
    Return a paginated list of fills and the total count.

    Args:
        page:  1-based page number.
        limit: Number of records per page.

    Returns:
        Tuple of (list_of_fill_dicts, total_count).
    """
    offset = (page - 1) * limit
    async with get_session() as session:
        total_result = await session.execute(select(func.count()).select_from(Fill))
        total: int = total_result.scalar_one()

        rows_result = await session.execute(
            select(Fill).order_by(Fill.timestamp.desc()).offset(offset).limit(limit)
        )
        rows = rows_result.scalars().all()

        items: list[dict[str, Any]] = [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "oid": r.oid,
                "side": r.side,
                "price": r.price,
                "size": r.size,
                "fee": r.fee,
                "is_maker": r.is_maker,
                "mid_price_at_fill": r.mid_price_at_fill,
            }
            for r in rows
        ]
    return items, total


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


async def save_order(order_data: dict[str, Any]) -> None:
    """Insert a new order record, or ignore if the oid already exists."""
    async with get_session() as session:
        # Check for existing order by oid to prevent unique-constraint violations.
        existing = await session.execute(
            select(Order).where(Order.oid == order_data["oid"])
        )
        if existing.scalar_one_or_none() is not None:
            return

        now = datetime.now(tz=timezone.utc)
        order = Order(
            oid=order_data["oid"],
            side=order_data["side"],
            price=float(order_data["price"]),
            size=float(order_data["size"]),
            status=order_data.get("status", "open"),
            created_at=order_data.get("created_at", now),
            updated_at=order_data.get("updated_at", now),
        )
        session.add(order)


async def update_order_status(oid: str, status: str) -> None:
    """Update the status of an existing order identified by its oid."""
    async with get_session() as session:
        result = await session.execute(select(Order).where(Order.oid == oid))
        order = result.scalar_one_or_none()
        if order is not None:
            order.status = status
            order.updated_at = datetime.now(tz=timezone.utc)


async def update_order_price(oid: str, price: float, size: float) -> None:
    """Update price and size of an existing order after a modify-in-place operation."""
    async with get_session() as session:
        result = await session.execute(select(Order).where(Order.oid == oid))
        order = result.scalar_one_or_none()
        if order is not None:
            order.price = price
            order.size = size
            order.updated_at = datetime.now(tz=timezone.utc)


async def get_open_orders() -> list[dict[str, Any]]:
    """Return all orders with status='open', ordered by creation time descending."""
    async with get_session() as session:
        result = await session.execute(
            select(Order)
            .where(Order.status == "open")
            .order_by(Order.created_at.desc())
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "oid": r.oid,
                "side": r.side,
                "price": r.price,
                "size": r.size,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Price snapshots
# ---------------------------------------------------------------------------


async def save_price_snapshot(data: dict[str, Any]) -> None:
    """Persist a price snapshot record."""
    async with get_session() as session:
        snapshot = PriceSnapshot(
            timestamp=data["timestamp"],
            fair_price=float(data["fair_price"]),
            bid_prices=list(data.get("bid_prices", [])),
            ask_prices=list(data.get("ask_prices", [])),
            mid_hl=float(data["mid_hl"]) if data.get("mid_hl") is not None else None,
            mid_kraken=(
                float(data["mid_kraken"]) if data.get("mid_kraken") is not None else None
            ),
        )
        session.add(snapshot)


async def get_price_history(since: datetime) -> list[dict[str, Any]]:
    """Return all price snapshots at or after *since*, ordered by timestamp ascending."""
    async with get_session() as session:
        result = await session.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.timestamp >= since)
            .order_by(PriceSnapshot.timestamp.asc())
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "fair_price": r.fair_price,
                "bid_prices": r.bid_prices,
                "ask_prices": r.ask_prices,
                "mid_hl": r.mid_hl,
                "mid_kraken": r.mid_kraken,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# PnL snapshots
# ---------------------------------------------------------------------------


async def save_pnl_snapshot(data: dict[str, Any]) -> None:
    """Persist a PnL snapshot record."""
    async with get_session() as session:
        snapshot = PnLSnapshot(
            timestamp=data["timestamp"],
            realized_pnl=float(data["realized_pnl"]),
            unrealized_pnl=float(data["unrealized_pnl"]),
            total_pnl=float(data["total_pnl"]),
            portfolio_value_usdc=float(data["portfolio_value_usdc"]),
        )
        session.add(snapshot)


async def get_pnl_history(since: datetime) -> list[dict[str, Any]]:
    """Return all PnL snapshots at or after *since*, ordered by timestamp ascending."""
    async with get_session() as session:
        result = await session.execute(
            select(PnLSnapshot)
            .where(PnLSnapshot.timestamp >= since)
            .order_by(PnLSnapshot.timestamp.asc())
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat(),
                "realized_pnl": r.realized_pnl,
                "unrealized_pnl": r.unrealized_pnl,
                "total_pnl": r.total_pnl,
                "portfolio_value_usdc": r.portfolio_value_usdc,
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# HODL benchmark
# ---------------------------------------------------------------------------


async def get_hodl_benchmark() -> dict[str, Any] | None:
    """Return the most recently saved HODL benchmark row, or None if absent."""
    async with get_session() as session:
        result = await session.execute(
            select(HodlBenchmark).order_by(HodlBenchmark.timestamp.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "timestamp": row.timestamp.isoformat(),
            "xmr_price": row.xmr_price,
            "usdc_balance": row.usdc_balance,
            "xmr_balance": row.xmr_balance,
        }


async def save_hodl_benchmark(data: dict[str, Any]) -> None:
    """Persist a new HODL benchmark snapshot."""
    async with get_session() as session:
        benchmark = HodlBenchmark(
            timestamp=data["timestamp"],
            xmr_price=float(data["xmr_price"]),
            usdc_balance=float(data["usdc_balance"]),
            xmr_balance=float(data["xmr_balance"]),
        )
        session.add(benchmark)


# ---------------------------------------------------------------------------
# Daily PnL summary
# ---------------------------------------------------------------------------


async def get_daily_pnl_summary(days: int = 30) -> list[dict[str, Any]]:
    """
    Return a per-day summary of trading activity for the last *days* days.

    For each UTC calendar day the function produces:
      - date:          ISO date string (YYYY-MM-DD)
      - day:           1-based index (1 = oldest, N = today)
      - fills:         total number of fills on that day
      - fee_rebates:   estimated maker rebate = sum(size * price * 0.0001) per fill
      - realized_pnl:  delta of realized_pnl between the day's earliest and latest
                       PnL snapshot (0 if fewer than 2 snapshots exist for that day)
      - net_pnl:       realized_pnl + fee_rebates

    The query uses raw SQL for the date-grouping to stay compatible with both
    SQLite (strftime) and other backends the operator might switch to.
    """
    async with get_session() as session:
        # ------------------------------------------------------------------
        # 1. Per-day fill aggregates
        # ------------------------------------------------------------------
        fills_sql = text(
            """
            SELECT
                strftime('%Y-%m-%d', timestamp) AS day_str,
                COUNT(*)                         AS fills_count,
                SUM(size * price * 0.0001)       AS rebates
            FROM fills
            WHERE timestamp >= datetime('now', :offset)
            GROUP BY day_str
            ORDER BY day_str ASC
            """
        )
        fills_result = await session.execute(fills_sql, {"offset": f"-{days} days"})
        fills_rows = fills_result.fetchall()

        # Map day_str -> {fills_count, rebates}
        fills_map: dict[str, dict[str, Any]] = {}
        for row in fills_rows:
            fills_map[row[0]] = {
                "fills_count": int(row[1]),
                "rebates": float(row[2]) if row[2] is not None else 0.0,
            }

        # ------------------------------------------------------------------
        # 2. Per-day PnL delta (latest realized_pnl - earliest realized_pnl)
        # ------------------------------------------------------------------
        pnl_sql = text(
            """
            SELECT
                strftime('%Y-%m-%d', timestamp) AS day_str,
                MIN(realized_pnl)               AS pnl_open,
                MAX(realized_pnl)               AS pnl_close,
                -- Use first/last by picking rows at min/max timestamp
                MIN(timestamp)                  AS ts_open,
                MAX(timestamp)                  AS ts_close
            FROM pnl_snapshots
            WHERE timestamp >= datetime('now', :offset)
            GROUP BY day_str
            ORDER BY day_str ASC
            """
        )
        pnl_result = await session.execute(pnl_sql, {"offset": f"-{days} days"})
        pnl_rows = pnl_result.fetchall()

        # For a proper "first/last" delta we need the actual realized_pnl at the
        # boundary timestamps.  The MIN/MAX(realized_pnl) above is a shortcut that
        # works well for a monotonically increasing realized_pnl series (which is
        # the normal case).  We compute delta = pnl_close - pnl_open.
        pnl_map: dict[str, float] = {}
        for row in pnl_rows:
            day_str: str = row[0]
            pnl_open: float = float(row[1]) if row[1] is not None else 0.0
            pnl_close: float = float(row[2]) if row[2] is not None else 0.0
            pnl_map[day_str] = pnl_close - pnl_open

        # ------------------------------------------------------------------
        # 3. Merge and build result list
        # ------------------------------------------------------------------
        # Collect all unique dates from both queries
        all_dates: set[str] = set(fills_map.keys()) | set(pnl_map.keys())
        sorted_dates = sorted(all_dates)

        summary: list[dict[str, Any]] = []
        for idx, date_str in enumerate(sorted_dates, start=1):
            fill_info = fills_map.get(date_str, {"fills_count": 0, "rebates": 0.0})
            realized = pnl_map.get(date_str, 0.0)
            rebates = fill_info["rebates"]
            summary.append(
                {
                    "day": idx,
                    "date": date_str,
                    "fills": fill_info["fills_count"],
                    "realized_pnl": round(realized, 6),
                    "fee_rebates": round(rebates, 6),
                    "net_pnl": round(realized + rebates, 6),
                }
            )

        return summary
