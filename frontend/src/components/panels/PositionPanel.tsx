"use client";
import { useBotStore } from "@/store/botStore";

export function PositionPanel(): React.JSX.Element {
  const status = useBotStore((s) => s.status);

  const fairPrice = status?.fair_price ?? 0;
  const invPct = status?.inventory_pct ?? 0;

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">Position</h3>
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">XMR Size</span>
          <span className="text-zinc-200 font-mono">{invPct.toFixed(2)}%</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Fair Price</span>
          <span className="text-orange-400 font-mono">${fairPrice.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Regime</span>
          <span className={status?.regime === "VOLATILE" ? "text-red-400" : "text-green-400"}>
            {status?.regime ?? "—"}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Orders</span>
          <span className="text-zinc-200">{status?.open_orders_count ?? 0}</span>
        </div>
      </div>
    </div>
  );
}
