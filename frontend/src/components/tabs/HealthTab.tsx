"use client";
import { useBotStore } from "@/store/botStore";
import { formatLatency } from "@/lib/formatters";

export function HealthTab(): React.JSX.Element {
  const status = useBotStore((s) => s.status);
  const alerts = useBotStore((s) => s.alerts);
  const feeds = status?.feed_health ?? [];

  return (
    <div className="p-4 space-y-4">
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-300">Feed Health</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500 text-xs uppercase">
              <th className="px-4 py-2 text-left">Source</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-right">Price</th>
              <th className="px-4 py-2 text-right">Latency</th>
            </tr>
          </thead>
          <tbody>
            {feeds.map((f) => (
              <tr key={f.source} className="border-b border-zinc-800 last:border-b-0">
                <td className="px-4 py-2 text-zinc-300 font-medium capitalize">{f.source}</td>
                <td className="px-4 py-2">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${f.healthy ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                    {f.healthy ? "OK" : "STALE"}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-zinc-200 font-mono">
                  {f.price !== null ? `$${f.price.toFixed(2)}` : "—"}
                </td>
                <td className="px-4 py-2 text-right text-zinc-400">{formatLatency(f.latency_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-300">Alerts & Errors</h3>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {alerts.length === 0 ? (
            <p className="px-4 py-4 text-xs text-zinc-600">No alerts</p>
          ) : (
            alerts.slice(0, 20).map((alert, i) => (
              <div key={i} className="px-4 py-2 border-b border-zinc-800 last:border-b-0 text-xs text-zinc-400">
                {alert}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
