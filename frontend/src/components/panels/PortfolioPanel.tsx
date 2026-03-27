"use client";
import { useBotStore } from "@/store/botStore";

export function PortfolioPanel(): React.JSX.Element {
  const status = useBotStore((s) => s.status);

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Portfolio Value</h3>
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">USDC</span>
          <span className="text-zinc-200 font-mono">{status ? `$${(status.portfolio_value * 0.8).toFixed(2)}` : "—"}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">XMR1</span>
          <span className="text-zinc-200 font-mono">{status ? `${(status.inventory_pct / 100).toFixed(4)} XMR` : "—"}</span>
        </div>
        <div className="border-t border-zinc-800 pt-2 flex justify-between">
          <span className="text-zinc-300 font-semibold">Total</span>
          <span className="text-zinc-100 font-bold font-mono text-base">${(status?.portfolio_value ?? 0).toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
