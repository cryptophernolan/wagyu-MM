"use client";
import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { TimeframeSelector } from "@/components/ui/TimeframeSelector";
import { useBotVsHodlData } from "@/hooks/useChartData";

const TIMEFRAMES = ["7d", "30d", "all"];

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function BotVsHodlChart(): React.JSX.Element {
  const [timeframe, setTimeframe] = useState("30d");
  const { data, loading } = useBotVsHodlData(timeframe);

  return (
    <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-300">Bot vs HODL</h3>
        <TimeframeSelector value={timeframe} onChange={setTimeframe} options={TIMEFRAMES} />
      </div>
      {loading ? (
        <div className="h-48 flex items-center justify-center text-zinc-600">Loading...</div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="ts" tickFormatter={formatTs} tick={{ fill: "#71717a", fontSize: 10 }} />
            <YAxis tick={{ fill: "#71717a", fontSize: 10 }} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
            <ReferenceLine y={0} stroke="#52525b" strokeDasharray="4 4" />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 6 }}
              formatter={(v: number) => [`${v.toFixed(2)}%`, ""]}
            />
            <Line type="monotone" dataKey="bot_pct" stroke="#f97316" strokeWidth={2} dot={false} name="Bot" />
            <Line type="monotone" dataKey="hodl_pct" stroke="#a1a1aa" strokeWidth={2} dot={false} strokeDasharray="5 5" name="HODL" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
