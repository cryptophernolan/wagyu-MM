"use client";
import { useBotStore } from "@/store/botStore";
import { formatLatency } from "@/lib/formatters";
import type { AgentHealthItem } from "@/types";

const AGENT_LABELS: Record<string, string> = {
  cycle_watchdog: "Cycle Watchdog",
  order_integrity: "Order Integrity",
  quote_activity: "Quote Activity",
  exchange_probe: "Exchange Probe",
};

const AGENT_DESCRIPTIONS: Record<string, string> = {
  cycle_watchdog: "Monitors trading cycle regularity — detects stalled or slow cycles",
  order_integrity: "Cross-checks local order state against the exchange — detects ghost orders",
  quote_activity: "Verifies orders are placed when quoting is active — detects silent placement failures",
  exchange_probe: "Probes exchange REST API connectivity and latency",
};

function AgentStatusBadge({ status }: { status: AgentHealthItem["status"] }): React.JSX.Element {
  const styles = {
    OK: "bg-green-900/40 text-green-300 border-green-700/50",
    WARN: "bg-amber-900/40 text-amber-300 border-amber-700/50",
    CRITICAL: "bg-red-900/40 text-red-300 border-red-700/50 animate-pulse",
    UNKNOWN: "bg-zinc-800 text-zinc-400 border-zinc-700",
  };
  const dots = {
    OK: "bg-green-400",
    WARN: "bg-amber-400",
    CRITICAL: "bg-red-400",
    UNKNOWN: "bg-zinc-500",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold border ${styles[status]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[status]}`} />
      {status}
    </span>
  );
}

export function HealthTab(): React.JSX.Element {
  const status = useBotStore((s) => s.status);
  const alerts = useBotStore((s) => s.alerts);
  const agentReports = useBotStore((s) => s.agentReports);
  const feeds = status?.feed_health ?? [];

  const agentList = Object.values(agentReports).sort((a, b) =>
    a.agent.localeCompare(b.agent)
  );

  const overallAgentStatus: AgentHealthItem["status"] = agentList.some((r) => r.status === "CRITICAL")
    ? "CRITICAL"
    : agentList.some((r) => r.status === "WARN")
    ? "WARN"
    : agentList.some((r) => r.status === "UNKNOWN")
    ? "UNKNOWN"
    : agentList.length > 0
    ? "OK"
    : "UNKNOWN";

  return (
    <div className="p-4 space-y-4">
      {/* Autonomous Agent Health */}
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-zinc-300">Autonomous Health Agents</h3>
            <p className="text-xs text-zinc-500 mt-0.5">Real-time monitors that detect silent failures not visible in status</p>
          </div>
          <AgentStatusBadge status={overallAgentStatus} />
        </div>

        {agentList.length === 0 ? (
          <div className="px-4 py-6 text-center text-xs text-zinc-600">
            Đang khởi động agents... (các agent bắt đầu sau 10–60s)
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {agentList.map((r) => (
              <div key={r.agent} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-semibold text-zinc-200">
                        {AGENT_LABELS[r.agent] ?? r.agent}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-400 truncate" title={r.message}>
                      {r.message}
                    </p>
                    {AGENT_DESCRIPTIONS[r.agent] && (
                      <p className="text-[10px] text-zinc-600 mt-0.5">{AGENT_DESCRIPTIONS[r.agent]}</p>
                    )}
                    {r.status !== "OK" && Object.keys(r.details).length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
                        {Object.entries(r.details).map(([k, v]) => (
                          <span key={k} className="text-[10px] font-mono text-zinc-500">
                            {k}: <span className="text-zinc-300">{String(v)}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex-shrink-0">
                    <AgentStatusBadge status={r.status} />
                  </div>
                </div>
                <p className="text-[10px] text-zinc-700 mt-1">
                  Last check: {new Date(r.timestamp).toLocaleTimeString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Price Feed Health */}
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-300">Price Feeds</h3>
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
            {feeds.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-center text-xs text-zinc-600">Đang kết nối...</td>
              </tr>
            ) : (
              feeds.map((f) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Alerts & Errors */}
      <div className="bg-zinc-900 rounded-lg border border-zinc-800">
        <div className="px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-semibold text-zinc-300">Alerts & Errors</h3>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {alerts.length === 0 ? (
            <p className="px-4 py-4 text-xs text-zinc-600">No alerts</p>
          ) : (
            alerts.slice(0, 20).map((alert, i) => {
              const isCritical = alert.includes("CRITICAL") || alert.includes("[CYCLE_WATCHDOG]") || alert.includes("[ORDER_INTEGRITY]");
              const isWarn = alert.includes("WARN") || alert.includes("[QUOTE_ACTIVITY]") || alert.includes("[EXCHANGE_PROBE]");
              return (
                <div
                  key={i}
                  className={`px-4 py-2 border-b border-zinc-800 last:border-b-0 text-xs ${
                    isCritical ? "text-red-400" : isWarn ? "text-amber-400" : "text-zinc-400"
                  }`}
                >
                  {alert}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
