"use client";
import { useQuery } from "@tanstack/react-query";
import { fetchOrders } from "@/lib/api";

export function OrdersTab(): React.JSX.Element {
  const { data } = useQuery({
    queryKey: ["orders"],
    queryFn: fetchOrders,
    refetchInterval: 3000,
  });

  const orders = data?.items ?? [];

  return (
    <div className="p-4">
      <div className="bg-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 flex justify-between">
          <h3 className="text-sm font-semibold text-zinc-300">Open Orders</h3>
          <span className="text-xs text-zinc-500">{orders.length} orders</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500 text-xs uppercase">
              <th className="px-4 py-2 text-left">OID</th>
              <th className="px-4 py-2 text-left">Side</th>
              <th className="px-4 py-2 text-right">Price</th>
              <th className="px-4 py-2 text-right">Size</th>
              <th className="px-4 py-2 text-left">Status</th>
              <th className="px-4 py-2 text-right">Age</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-zinc-600 text-xs">No open orders</td></tr>
            ) : (
              orders.map((order) => (
                <tr key={order.oid} className="border-b border-zinc-800 last:border-b-0 hover:bg-zinc-800/50">
                  <td className="px-4 py-2 text-zinc-400 font-mono text-xs">{order.oid.slice(0, 12)}...</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${order.side === "buy" ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                      {order.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-zinc-200 font-mono">${order.price.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right text-zinc-300 font-mono">{order.size.toFixed(4)}</td>
                  <td className="px-4 py-2 text-zinc-400 text-xs">{order.status}</td>
                  <td className="px-4 py-2 text-right text-zinc-500 text-xs">{Math.round(order.age_seconds)}s</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
