"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDailyReport, exportReportUrl } from "@/lib/api";
import type { DailyPnLRow } from "@/types";

const DAYS_OPTIONS = [
  { label: "7d", value: 7 },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "All", value: 365 },
];

function pnlColor(n: number): string {
  return n >= 0 ? "text-green-400" : "text-red-400";
}

function fmt(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(2);
}

export function ReportTab(): React.JSX.Element {
  const [days, setDays] = useState(30);
  const { data, isLoading } = useQuery({
    queryKey: ["dailyReport", days],
    queryFn: () => fetchDailyReport(days),
    refetchInterval: 30000,
  });

  const rows = data?.rows ?? [];
  const summary = data?.summary;

  return (
    <div className="p-4">
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="px-4 py-3 border-b border-zinc-800 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-zinc-300">Daily P&L Report</h3>
          <div className="flex items-center gap-3">
            <div className="flex gap-1">
              {DAYS_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setDays(opt.value)}
                  className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                    days === opt.value ? "bg-zinc-600 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <a
              href={exportReportUrl(days)}
              download
              className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-xs rounded transition-colors"
            >
              Export .txt
            </a>
          </div>
        </div>

        {isLoading ? (
          <div className="p-8 text-center text-zinc-600 text-sm">Loading...</div>
        ) : (
          <div className="overflow-x-auto">
            <pre className="font-mono text-xs text-zinc-300 bg-zinc-900 p-4 leading-relaxed">
              <span className="text-zinc-100 font-bold">Wagyu.xyz MM Bot v2.4.1 — DAILY P&L REPORT</span>{"\n"}
              <span className="text-zinc-400">XMR1/USDC | Algo: Avellaneda-Stoikov</span>{"\n"}
              {summary && <span className="text-zinc-400">Running since: {summary.running_since}</span>}{"\n"}
              {"\n"}
              {/* Header */}
              <span className="text-zinc-500">{" Day  Date         Fills   Realized PnL   Fee Rebates    Net P&L"}</span>{"\n"}
              <span className="text-zinc-700">{"─".repeat(64)}</span>{"\n"}
              {/* Rows */}
              {rows.map((row: DailyPnLRow) => (
                <span key={row.day}>
                  {String(row.day).padStart(4)}{"  "}{row.date.padEnd(12)}{String(row.fills).padStart(6)}{"   "}
                  <span className={pnlColor(row.realized_pnl)}>${fmt(row.realized_pnl).padStart(11)}</span>{"   "}
                  <span className="text-zinc-300">${row.fee_rebates.toFixed(2).padStart(10)}</span>{"   "}
                  <span className={pnlColor(row.net_pnl)}>${fmt(row.net_pnl).padStart(8)}</span>{"\n"}
                </span>
              ))}
              {rows.length > 0 && (
                <>
                  <span className="text-zinc-700">{"─".repeat(64)}</span>{"\n"}
                  {summary && (
                    <span>
                      <span className="text-zinc-400">{"TOTAL "}{summary.total_days} days{"  "}</span>
                      <span className={pnlColor(summary.cumulative)}>${summary.cumulative.toFixed(2)}</span>{"   "}
                      <span className="text-zinc-400">AVG/DAY: </span>
                      <span className={pnlColor(summary.avg_per_day)}>${summary.avg_per_day.toFixed(2)}</span>{"\n"}
                      {"\n"}
                      {summary.peak_day && (
                        <span>
                          <span className="text-zinc-400">PEAK DAY:  </span>
                          <span className="text-green-400">${summary.peak_day.net_pnl.toFixed(2)}</span>
                          <span className="text-zinc-500"> ({summary.peak_day.date})</span>
                          {"   "}
                          {summary.worst_day && (
                            <>
                              <span className="text-zinc-400">WORST: </span>
                              <span className="text-red-400">${summary.worst_day.net_pnl.toFixed(2)}</span>
                              <span className="text-zinc-500"> ({summary.worst_day.date})</span>
                            </>
                          )}{"\n"}
                        </span>
                      )}
                      <span className="text-zinc-400">WIN RATE:  </span>
                      <span className="text-zinc-200">{(summary.win_rate * 100).toFixed(1)}%</span>
                      <span className="text-zinc-500"> ({Math.round(summary.win_rate * summary.total_days)}/{summary.total_days} days)</span>{"\n"}
                      <span className="text-zinc-400">SHARPE (ann): </span>
                      <span className="text-zinc-200">{summary.sharpe_annualized.toFixed(2)}</span>{"\n"}
                    </span>
                  )}
                </>
              )}
              {rows.length === 0 && (
                <span className="text-zinc-600">No data for this period. Run the bot to generate fill history.</span>
              )}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
