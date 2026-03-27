"use client";
import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TimeframeSelector } from "@/components/ui/TimeframeSelector";
import { usePriceChart } from "@/hooks/useChartData";

const TIMEFRAMES = ["12h", "24h", "7d", "30d", "6m", "1y", "All"];

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

export function PriceChart(): React.JSX.Element {
  const [timeframe, setTimeframe] = useState("24h");
  const { data, loading } = usePriceChart(timeframe);

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-300">Price Chart</h3>
        <TimeframeSelector value={timeframe} onChange={setTimeframe} options={TIMEFRAMES} />
      </div>
      {loading ? (
        <div className="h-48 flex items-center justify-center text-zinc-600">Loading...</div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="ts" tickFormatter={formatTs} tick={{ fill: "#71717a", fontSize: 10 }} />
            <YAxis tick={{ fill: "#71717a", fontSize: 10 }} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 6 }}
              labelStyle={{ color: "#a1a1aa" }}
              formatter={(v: number) => [`$${v.toFixed(2)}`, ""]}
            />
            <Line type="monotone" dataKey="fair" stroke="#f97316" strokeWidth={2} dot={false} name="Fair" />
            <Line type="monotone" dataKey="bid1" stroke="#22c55e" strokeWidth={1} dot={false} name="Bid L1" />
            <Line type="monotone" dataKey="ask1" stroke="#ef4444" strokeWidth={1} dot={false} name="Ask L1" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
