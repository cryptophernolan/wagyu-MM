"use client";
import { useBotStore } from "@/store/botStore";
import { formatCycleMs } from "@/lib/formatters";

interface StatCellProps {
  label: string;
  value: React.ReactNode;
}

function StatCell({ label, value }: StatCellProps): React.JSX.Element {
  return (
    <div className="flex flex-col items-center px-4 border-r border-zinc-800 last:border-r-0">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
      <span className="text-sm font-semibold text-zinc-200">{value}</span>
    </div>
  );
}

export function StatsStrip(): React.JSX.Element {
  const status = useBotStore((s) => s.status);

  const regimeColor = status?.regime === "VOLATILE" ? "text-red-400" : "text-green-400";

  return (
    <div className="bg-zinc-900 border-b border-zinc-800 px-4 py-2 flex items-center">
      <StatCell label="Inv%" value={`${(status?.inventory_pct ?? 0).toFixed(1)}%`} />
      <StatCell
        label="Vol Regime"
        value={<span className={regimeColor}>{status?.regime ?? "—"}</span>}
      />
      <StatCell label="Orders" value={status?.open_orders_count ?? 0} />
      <StatCell label="Fills" value={status?.fills_count ?? 0} />
      <StatCell label="State" value={status?.state ?? "—"} />
      <StatCell label="Cycle" value={status ? formatCycleMs(status.last_cycle_ms) : "—"} />
    </div>
  );
}
