"""Daily PnL report endpoints."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from bot.persistence import repository
from server.schemas.api_types import DailyPnLRow, DailyReportResponse, ReportSummary

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/report/daily", response_model=DailyReportResponse)
async def get_daily_report(days: int = 30) -> DailyReportResponse:
    raw_rows = await repository.get_daily_pnl_summary(days)
    rows = [
        DailyPnLRow(
            day=r["day"],
            date=r["date"],
            fills=r["fills"],
            realized_pnl=r["realized_pnl"],
            fee_rebates=r["fee_rebates"],
            net_pnl=r["net_pnl"],
        )
        for r in raw_rows
    ]
    summary = _compute_summary(rows)
    return DailyReportResponse(rows=rows, summary=summary)


@router.get("/report/daily/export")
async def export_daily_report(days: int = 30) -> PlainTextResponse:
    raw_rows = await repository.get_daily_pnl_summary(days)
    rows = [DailyPnLRow(**r) for r in raw_rows]
    summary = _compute_summary(rows)
    text = _format_report(rows, summary)
    return PlainTextResponse(
        content=text,
        headers={"Content-Disposition": f"attachment; filename=wagyu_report_{days}d.txt"},
    )


def _compute_summary(rows: list[DailyPnLRow]) -> ReportSummary:
    if not rows:
        return ReportSummary(
            cumulative=0.0, avg_per_day=0.0, peak_day=None, worst_day=None,
            win_rate=0.0, sharpe_annualized=0.0, total_days=0,
            running_since=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
    net_pnls = [r.net_pnl for r in rows]
    cumulative = sum(net_pnls)
    avg = cumulative / len(rows)
    peak = max(rows, key=lambda r: r.net_pnl)
    worst = min(rows, key=lambda r: r.net_pnl)
    winning = sum(1 for p in net_pnls if p > 0)
    win_rate = winning / len(rows)
    if len(net_pnls) > 1:
        mean_pnl = avg
        variance = sum((p - mean_pnl) ** 2 for p in net_pnls) / (len(net_pnls) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 0.0
        sharpe = (mean_pnl / std_pnl * math.sqrt(365)) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0
    return ReportSummary(
        cumulative=round(cumulative, 2),
        avg_per_day=round(avg, 2),
        peak_day=peak,
        worst_day=worst,
        win_rate=round(win_rate, 4),
        sharpe_annualized=round(sharpe, 2),
        total_days=len(rows),
        running_since=rows[0].date if rows else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


def _format_report(rows: list[DailyPnLRow], summary: ReportSummary) -> str:
    lines: list[str] = []
    lines.append("Wagyu.xyz MM Bot v2.4.1 — DAILY P&L REPORT")
    lines.append("XMR1/USDC | Algo: Avellaneda-Stoikov")
    lines.append(f"Running since: {summary.running_since}")
    lines.append("")
    header = f"{'Day':>4}  {'Date':<10}  {'Fills':>6}  {'Realized PnL':>13}  {'Fee Rebates':>12}  {'Net P&L':>9}"
    sep = "─" * len(header)
    lines.append(header)
    lines.append(sep)
    for r in rows:
        lines.append(
            f"{r.day:>4}  {r.date:<10}  {r.fills:>6}  "
            f"${r.realized_pnl:>12.2f}  ${r.fee_rebates:>11.2f}  ${r.net_pnl:>8.2f}"
        )
    lines.append(sep)
    total_fills = sum(r.fills for r in rows)
    lines.append(
        f"{'TOTAL':>4}  {summary.total_days} days  {total_fills:>6}  "
        f"${sum(r.realized_pnl for r in rows):>12.2f}  "
        f"${sum(r.fee_rebates for r in rows):>11.2f}  ${summary.cumulative:>8.2f}"
    )
    lines.append("")
    lines.append(f"CUMULATIVE: ${summary.cumulative:,.2f}   AVG/DAY: ${summary.avg_per_day:,.2f}")
    if summary.peak_day and summary.worst_day:
        lines.append(
            f"PEAK DAY:   ${summary.peak_day.net_pnl:,.2f} ({summary.peak_day.date})   "
            f"WORST: ${summary.worst_day.net_pnl:,.2f} ({summary.worst_day.date})"
        )
    lines.append(
        f"WIN RATE:   {summary.win_rate * 100:.1f}% "
        f"({int(summary.win_rate * summary.total_days)}/{summary.total_days} days)"
    )
    lines.append(f"SHARPE (ann): {summary.sharpe_annualized:.2f}")
    return "\n".join(lines)
