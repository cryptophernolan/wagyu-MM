// Formatting utilities for display values

export function formatPrice(n: number): string {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatSize(n: number): string {
  return n.toFixed(4);
}

export function formatPnL(n: number): string {
  const abs = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n >= 0 ? `+$${abs}` : `-$${abs}`;
}

export function formatPnLColor(n: number): string {
  return n >= 0 ? "text-green-400" : "text-red-400";
}

export function formatBps(n: number): string {
  return `${n.toFixed(1)} bps`;
}

export function formatRelativeTime(ts: string | number): string {
  const date = typeof ts === "string" ? new Date(ts) : new Date(ts * 1000);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function formatPct(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function formatCycleMs(ms: number): string {
  return `${Math.round(ms)}ms`;
}
