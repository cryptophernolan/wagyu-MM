"use client";
import { useBotStore } from "@/store/botStore";
import { formatPnL, formatPnLColor } from "@/lib/formatters";

export function PnLPanel(): React.JSX.Element {
  const status = useBotStore((s) => s.status);

  const realized = status?.realized_pnl ?? 0;
  const unrealized = status?.unrealized_pnl ?? 0;
  const total = realized + unrealized;

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Total PnL</h3>
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Realized</span>
          <span className={`font-mono ${formatPnLColor(realized)}`}>{formatPnL(realized)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Unrealized</span>
          <span className={`font-mono ${formatPnLColor(unrealized)}`}>{formatPnL(unrealized)}</span>
        </div>
        <div className="border-t border-zinc-800 pt-2 flex justify-between">
          <span className="text-zinc-300 font-semibold">Total</span>
          <span className={`font-bold font-mono text-base ${formatPnLColor(total)}`}>{formatPnL(total)}</span>
        </div>
      </div>
    </div>
  );
}
