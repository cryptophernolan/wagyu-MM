"use client";
import { useState } from "react";
import { ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TimeframeSelector } from "@/components/ui/TimeframeSelector";
import { usePnLHistory } from "@/hooks/useChartData";

const TIMEFRAMES = ["24h", "7d", "30d", "all"];

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function PnLChart(): React.JSX.Element {
  const [timeframe, setTimeframe] = useState("24h");
  const { data, loading } = usePnLHistory(timeframe);

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-300">PnL History</h3>
        <TimeframeSelector value={timeframe} onChange={setTimeframe} options={TIMEFRAMES} />
      </div>
      {loading ? (
        <div className="h-48 flex items-center justify-center text-zinc-600">Loading...</div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="ts" tickFormatter={formatTs} tick={{ fill: "#71717a", fontSize: 10 }} />
            <YAxis tick={{ fill: "#71717a", fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 6 }}
              formatter={(v: number) => [`$${v.toFixed(2)}`, ""]}
            />
            <Area type="monotone" dataKey="total" fill="#3b82f620" stroke="#3b82f6" strokeWidth={2} name="Total PnL" />
            <Line type="monotone" dataKey="realized" stroke="#f97316" strokeWidth={2} dot={false} name="Realized" />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
