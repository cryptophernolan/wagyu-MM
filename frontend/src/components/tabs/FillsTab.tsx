"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFills } from "@/lib/api";
import { formatRelativeTime } from "@/lib/formatters";

export function FillsTab(): React.JSX.Element {
  const [page, setPage] = useState(1);
  const { data } = useQuery({
    queryKey: ["fills", page],
    queryFn: () => fetchFills(page, 50),
    refetchInterval: 5000,
  });

  const fills = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / 50);

  return (
    <div className="p-4">
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-zinc-300">Fill History</h3>
          <span className="text-xs text-zinc-500">{total} total fills</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-zinc-500 text-xs uppercase">
                <th className="px-4 py-2 text-left">Time</th>
                <th className="px-4 py-2 text-left">Side</th>
                <th className="px-4 py-2 text-right">Price</th>
                <th className="px-4 py-2 text-right">Size</th>
                <th className="px-4 py-2 text-right">Fee</th>
                <th className="px-4 py-2 text-center">Maker</th>
              </tr>
            </thead>
            <tbody>
              {fills.map((fill) => (
                <tr key={fill.id} className="border-b border-zinc-800 last:border-b-0 hover:bg-zinc-800/50">
                  <td className="px-4 py-2 text-zinc-400 text-xs">{formatRelativeTime(fill.timestamp)}</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${fill.side === "buy" ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                      {fill.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-200 font-mono">${fill.price.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right text-zinc-300 font-mono">{fill.size.toFixed(4)}</td>
                  <td className="px-4 py-2 text-right text-zinc-400 font-mono">${fill.fee.toFixed(4)}</td>
                  <td className="px-4 py-2 text-center">
                    {fill.is_maker && <span className="px-2 py-0.5 bg-blue-900 text-blue-300 rounded text-xs">M</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-zinc-800 flex justify-between items-center">
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} className="text-xs text-zinc-400 disabled:opacity-30">
              ← Prev
            </button>
            <span className="text-xs text-zinc-500">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page === totalPages} className="text-xs text-zinc-400 disabled:opacity-30">
              Next →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
