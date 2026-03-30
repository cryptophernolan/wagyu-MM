// Typed REST fetch helpers for all API endpoints

import type { AgentHealthResponse, BotStatus, DailyPnLRow, Fill, Order, Portfolio, PricePoint, PnLPoint, ReportSummary } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchStatus(): Promise<BotStatus> {
  return apiFetch<BotStatus>("/api/status");
}

export async function fetchPortfolio(): Promise<Portfolio> {
  return apiFetch<Portfolio>("/api/portfolio");
}

export async function fetchFills(page = 1, limit = 50): Promise<{ items: Fill[]; total: number; page: number; limit: number }> {
  return apiFetch(`/api/fills?page=${page}&limit=${limit}`);
}

export async function fetchOrders(): Promise<{ items: Order[] }> {
  return apiFetch("/api/orders");
}

export async function fetchPriceChart(timeframe = "24h"): Promise<{ points: PricePoint[] }> {
  return apiFetch(`/api/chart/price?timeframe=${timeframe}`);
}

export async function fetchPnLHistory(timeframe = "24h"): Promise<{ points: PnLPoint[] }> {
  return apiFetch(`/api/pnl/history?timeframe=${timeframe}`);
}

export async function fetchBotVsHodl(timeframe = "24h"): Promise<{ points: { ts: number; bot_pct: number; hodl_pct: number }[] }> {
  return apiFetch(`/api/chart/bot_vs_hodl?timeframe=${timeframe}`);
}

export async function fetchDailyReport(days = 30): Promise<{ rows: DailyPnLRow[]; summary: ReportSummary }> {
  return apiFetch(`/api/report/daily?days=${days}`);
}

export function exportReportUrl(days = 30): string {
  return `${API_BASE}/api/report/daily/export?days=${days}`;
}

export async function toggleFeature(target: string): Promise<{ target: string; enabled: boolean }> {
  const res = await fetch(`${API_BASE}/api/toggle/${target}`, { method: "POST" });
  if (!res.ok) throw new Error(`Toggle error ${res.status}`);
  return res.json() as Promise<{ target: string; enabled: boolean }>;
}

export async function fetchAgentHealth(): Promise<AgentHealthResponse> {
  return apiFetch<AgentHealthResponse>("/api/health/agents");
}
