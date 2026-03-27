"use client";
import { TogglePill } from "@/components/ui/TogglePill";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { useBotStore } from "@/store/botStore";
import { toggleFeature } from "@/lib/api";

export function StatusBar(): React.JSX.Element {
  const status = useBotStore((s) => s.status);

  const toggle = async (target: string): Promise<void> => {
    try {
      await toggleFeature(target);
      // Status will update via WebSocket
    } catch {
      console.error("Toggle failed");
    }
  };

  const toggles = status?.toggles;
  const feeds = status?.feed_health ?? [];

  return (
    <div className="bg-zinc-900 border-b border-zinc-800 px-6 py-2 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 mr-2">Controls:</span>
        <TogglePill label="Feeds" active={toggles?.feeds ?? false} onToggle={() => void toggle("feeds")} />
        <TogglePill label="Wagyu" active={toggles?.wagyu ?? false} onToggle={() => void toggle("wagyu")} />
        <TogglePill label="Quoting" active={toggles?.quoting ?? false} onToggle={() => void toggle("quoting")} />
        <TogglePill label="Inv Limit" active={toggles?.inv_limit ?? false} onToggle={() => void toggle("inv_limit")} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 mr-2">Feeds:</span>
        {feeds.map((f) => (
          <ConnectionBadge
            key={f.source}
            source={f.source}
            price={f.price}
            latency_ms={f.latency_ms}
            healthy={f.healthy ? "ok" : "error"}
          />
        ))}
      </div>
    </div>
  );
}
