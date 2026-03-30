"use client";
import { useState, useCallback } from "react";
import { TogglePill } from "@/components/ui/TogglePill";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { useBotStore } from "@/store/botStore";
import { toggleFeature } from "@/lib/api";
import type { ToggleState } from "@/types";

type ToggleKey = keyof ToggleState;

interface ToggleConfig {
  key: ToggleKey;
  label: string;
  description: string;
}

const TOGGLES: ToggleConfig[] = [
  {
    key: "feeds",
    label: "Price Feeds",
    description: "Kết nối giá real-time (Hyperliquid + Kraken). Tắt = dừng nhận giá, bot sẽ tự halt.",
  },
  {
    key: "wagyu",
    label: "Trading",
    description: "Cho phép gửi lệnh lên Hyperliquid. Tắt = không đặt lệnh mới nào.",
  },
  {
    key: "quoting",
    label: "Quoting",
    description: "Tính toán và đặt quotes tự động mỗi cycle. Tắt = bot dừng market-making.",
  },
  {
    key: "inv_limit",
    label: "Inv Guard",
    description: "Giới hạn inventory tối đa. Tắt = bỏ giới hạn position (rủi ro cao).",
  },
];

export function StatusBar(): React.JSX.Element {
  const status = useBotStore((s) => s.status);
  const [pending, setPending] = useState<Set<ToggleKey>>(new Set());
  const [errors, setErrors] = useState<Set<ToggleKey>>(new Set());
  // Optimistic overrides: key → desired state while request is in-flight
  const [optimistic, setOptimistic] = useState<Partial<Record<ToggleKey, boolean>>>({});

  const toggle = useCallback(
    async (key: ToggleKey): Promise<void> => {
      if (pending.has(key)) return;

      const currentState = status?.toggles?.[key] ?? false;
      const nextState = !currentState;

      // Optimistic update — show result immediately
      setOptimistic((prev) => ({ ...prev, [key]: nextState }));
      setPending((prev) => new Set(prev).add(key));
      setErrors((prev) => {
        const s = new Set(prev);
        s.delete(key);
        return s;
      });

      try {
        await toggleFeature(key);
        // WebSocket state_update will confirm the real state shortly
      } catch {
        // Revert optimistic update on failure
        setOptimistic((prev) => {
          const s = { ...prev };
          delete s[key];
          return s;
        });
        setErrors((prev) => new Set(prev).add(key));
        // Auto-clear error badge after 3s
        setTimeout(() => {
          setErrors((prev) => {
            const s = new Set(prev);
            s.delete(key);
            return s;
          });
        }, 3000);
      } finally {
        setPending((prev) => {
          const s = new Set(prev);
          s.delete(key);
          return s;
        });
        // Clear optimistic override once backend confirms via WS
        setTimeout(() => {
          setOptimistic((prev) => {
            const s = { ...prev };
            delete s[key];
            return s;
          });
        }, 2000);
      }
    },
    [pending, status]
  );

  const toggles = status?.toggles;
  const feeds = status?.feed_health ?? [];
  const isHalted = !!status?.halt_reason;

  return (
    <div className="bg-zinc-900 border-b border-zinc-800 px-6 py-3 space-y-2.5">
      {/* Toggle controls row */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs text-zinc-500 font-medium tracking-wide uppercase">Controls</span>
        <div className="w-px h-4 bg-zinc-700" />

        {TOGGLES.map(({ key, label, description }) => {
          const backendState = toggles?.[key] ?? false;
          const displayState = key in optimistic ? (optimistic[key] as boolean) : backendState;

          return (
            <TogglePill
              key={key}
              label={label}
              description={description}
              active={displayState}
              onToggle={() => void toggle(key)}
              loading={pending.has(key)}
              error={errors.has(key)}
              disabled={isHalted && key !== "feeds"}
            />
          );
        })}

        {/* Halt banner */}
        {isHalted && (
          <span className="ml-2 px-2.5 py-1 rounded-full bg-red-900/40 border border-red-700/50 text-red-400 text-xs font-semibold">
            ⚠ HALTED: {status.halt_reason}
          </span>
        )}
      </div>

      {/* Feed health row */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs text-zinc-500 font-medium tracking-wide uppercase">Feeds</span>
        <div className="w-px h-4 bg-zinc-700" />

        {feeds.length === 0 ? (
          <span className="text-xs text-zinc-600 italic">Đang kết nối...</span>
        ) : (
          feeds.map((f) => {
            // Compute staleness-aware health
            const ageSeconds = Date.now() / 1000 - f.last_updated;
            const health: "ok" | "warn" | "error" = !f.healthy
              ? "error"
              : ageSeconds > 10
              ? "warn"
              : "ok";
            return (
              <ConnectionBadge
                key={f.source}
                source={f.source}
                price={f.price}
                latency_ms={f.latency_ms}
                healthy={health}
              />
            );
          })
        )}
      </div>
    </div>
  );
}
