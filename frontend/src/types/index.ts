// All TypeScript interfaces for the Wagyu MM Dashboard

export interface FeedInfo {
  source: string;
  healthy: boolean;
  price: number | null;
  latency_ms: number;
  last_updated: number;
}

export interface ToggleState {
  feeds: boolean;
  wagyu: boolean;
  quoting: boolean;
  inv_limit: boolean;
}

export interface BotStatus {
  state: string;
  toggles: ToggleState;
  fair_price: number;
  regime: string;
  inventory_pct: number;
  realized_pnl: number;
  unrealized_pnl: number;
  portfolio_value: number;
  open_orders_count: number;
  fills_count: number;
  last_cycle_ms: number;
  cycle_count: number;
  feed_health: FeedInfo[];
  halt_reason: string | null;
  alerts: string[];
}

export interface Fill {
  id: number;
  timestamp: string;
  oid: string;
  side: string;
  price: number;
  size: number;
  fee: number;
  is_maker: boolean;
  mid_price_at_fill: number;
}

export interface Order {
  oid: string;
  side: string;
  price: number;
  size: number;
  status: string;
  age_seconds: number;
}

export interface PricePoint {
  ts: number;
  fair: number;
  avg_entry: number | null;
  bid1: number | null;
  ask1: number | null;
}

export interface PnLPoint {
  ts: number;
  total: number;
  realized: number;
}

export interface BotVsHodlPoint {
  ts: number;
  bot_pct: number;
  hodl_pct: number;
}

export interface DailyPnLRow {
  day: number;
  date: string;
  fills: number;
  realized_pnl: number;
  fee_rebates: number;
  net_pnl: number;
}

export interface ReportSummary {
  cumulative: number;
  avg_per_day: number;
  peak_day: DailyPnLRow | null;
  worst_day: DailyPnLRow | null;
  win_rate: number;
  sharpe_annualized: number;
  total_days: number;
  running_since: string;
}

export interface Portfolio {
  usdc_balance: number;
  xmr_balance: number;
  total_value_usdc: number;
  xmr_price: number;
}

// WebSocket event discriminated union
export type WsEvent =
  | { type: "state_update"; data: BotStatus }
  | { type: "fill_event"; data: { side: string; price: number; size: number; fee: number } }
  | { type: "order_event"; data: Order }
  | { type: "alert_event"; data: { message: string } };
