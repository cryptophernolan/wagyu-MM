#!/usr/bin/env python3
"""CLI Daily PnL Report generator — reads from SQLite, outputs monospace text report."""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.persistence.database import close_db, create_tables, init_db
from bot.persistence import repository


def compute_sharpe(net_pnls: list[float]) -> float:
    """Compute annualised Sharpe ratio from a daily net-PnL series."""
    if len(net_pnls) < 2:
        return 0.0
    mean_pnl = sum(net_pnls) / len(net_pnls)
    variance = sum((p - mean_pnl) ** 2 for p in net_pnls) / (len(net_pnls) - 1)
    std_pnl = math.sqrt(variance) if variance > 0 else 0.0
    return (mean_pnl / std_pnl * math.sqrt(365)) if std_pnl > 0 else 0.0


def format_report(rows: list[dict[str, Any]], days: int) -> str:
    lines: list[str] = []
    lines.append("Wagyu.xyz MM Bot v2.4.1 — DAILY P&L REPORT")
    lines.append("XMR1/USDC | Algo: Avellaneda-Stoikov")

    if rows:
        running_since = str(rows[0].get("date", "—"))
        lines.append(f"Running since: {running_since}")

    lines.append("")

    header = (
        f"{'Day':>4}  {'Date':<12}  {'Fills':>6}  "
        f"{'Realized PnL':>13}  {'Fee Rebates':>12}  {'Net P&L':>10}"
    )
    sep = "─" * len(header)
    lines.append(header)
    lines.append(sep)

    total_fills = 0
    total_realized = 0.0
    total_fees = 0.0
    total_net = 0.0
    net_pnls: list[float] = []

    for r in rows:
        day = int(str(r.get("day", 0)))
        date = str(r.get("date", ""))
        fills = int(str(r.get("fills", 0)))
        realized = float(str(r.get("realized_pnl", 0)))
        fee_rebates = float(str(r.get("fee_rebates", 0)))
        net_pnl = float(str(r.get("net_pnl", 0)))

        lines.append(
            f"{day:>4}  {date:<12}  {fills:>6}  "
            f"${realized:>12.2f}  ${fee_rebates:>11.2f}  ${net_pnl:>9.2f}"
        )
        total_fills += fills
        total_realized += realized
        total_fees += fee_rebates
        total_net += net_pnl
        net_pnls.append(net_pnl)

    lines.append(sep)
    total_days = len(rows)
    lines.append(
        f"{'TOTAL':>4}  {f'{total_days} days':<12}  {total_fills:>6}  "
        f"${total_realized:>12.2f}  ${total_fees:>11.2f}  ${total_net:>9.2f}"
    )
    lines.append("")

    avg_per_day = total_net / total_days if total_days > 0 else 0.0
    lines.append(f"CUMULATIVE: ${total_net:,.2f}   AVG/DAY: ${avg_per_day:,.2f}")

    if net_pnls:
        peak_idx = net_pnls.index(max(net_pnls))
        worst_idx = net_pnls.index(min(net_pnls))
        peak_row = rows[peak_idx]
        worst_row = rows[worst_idx]
        lines.append(
            f"PEAK DAY:   ${net_pnls[peak_idx]:,.2f} ({peak_row.get('date', '')})   "
            f"WORST: ${net_pnls[worst_idx]:,.2f} ({worst_row.get('date', '')})"
        )
        winning = sum(1 for p in net_pnls if p > 0)
        win_rate = winning / len(net_pnls) * 100
        lines.append(f"WIN RATE:   {win_rate:.1f}% ({winning}/{len(net_pnls)} days)")
        sharpe = compute_sharpe(net_pnls)
        lines.append(f"SHARPE (ann): {sharpe:.2f}")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Daily PnL Report from SQLite")
    parser.add_argument("--days", type=int, default=30, help="Number of days (default: 30)")
    parser.add_argument(
        "--output", type=str, default="", help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--db", type=str, default="data/marketmaker.db", help="SQLite DB path"
    )
    args = parser.parse_args()

    db_url = f"sqlite+aiosqlite:///{args.db}"
    init_db(db_url)
    await create_tables()

    rows = await repository.get_daily_pnl_summary(args.days)

    report = format_report(rows, args.days)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(report)

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
