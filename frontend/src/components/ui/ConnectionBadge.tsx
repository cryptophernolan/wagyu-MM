interface Props {
  source: string;
  price: number | null;
  latency_ms: number;
  healthy: "ok" | "warn" | "error";
}

const dotColors = { ok: "bg-green-400", warn: "bg-yellow-400", error: "bg-red-500" };

export function ConnectionBadge({ source, price, latency_ms, healthy }: Props): React.JSX.Element {
  return (
    <div className="flex items-center gap-2 bg-zinc-800 px-3 py-1 rounded text-xs">
      <div className={`w-2 h-2 rounded-full ${dotColors[healthy]}`} />
      <span className="text-zinc-400 font-medium uppercase">{source}</span>
      <span className="text-zinc-200">{price !== null ? `$${price.toFixed(2)}` : "—"}</span>
      <span className="text-zinc-500">{Math.round(latency_ms)}ms</span>
    </div>
  );
}
