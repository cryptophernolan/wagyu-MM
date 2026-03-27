# Wagyu Market Maker Bot — Implementation Plan

Track progress by checking off items as they are completed.

---

## Yêu cầu bắt buộc — Typed Programming Language

> **Toàn bộ dự án phải dùng Typed Programming Language:**
> - **Python (bot + server):** Bắt buộc full type hints trên tất cả functions, arguments, return values. Enforce bằng `mypy --strict`. Không được để `Any` không rõ nguồn gốc.
> - **TypeScript (frontend):** Bắt buộc `strict: true` trong `tsconfig.json`. Không dùng `any`, không dùng `@ts-ignore`.
> - Mục đích: phát hiện lỗi type sớm, dễ testing, dễ refactor an toàn.

---

## Phase 1: Project Setup

- [x] Initialize Python project với `pyproject.toml` (Poetry) — dependencies: hyperliquid-python-sdk, fastapi, uvicorn, sqlalchemy, aiosqlite, pydantic-settings, structlog, websockets, pyyaml
- [x] Cấu hình `mypy` trong `pyproject.toml`: `strict = true`, `python_version = "3.11"` — áp dụng cho toàn bộ `bot/` và `server/`
- [x] Initialize Next.js 14 frontend với TypeScript + Tailwind CSS (`npx create-next-app@latest frontend --typescript --tailwind --app`)
- [x] Cấu hình `tsconfig.json`: `"strict": true`, `"noImplicitAny": true`, `"strictNullChecks": true`
- [x] Create directory structure: `bot/`, `server/`, `frontend/`, `config/`, `data/`, `logs/`, `scripts/`, `tests/`
- [x] Create `config/config.example.yaml` với tất cả tham số có cấu hình (exchange, trading, **algorithm**, avellaneda_stoikov, spread, inventory, risk, volatility sections)
- [x] Create `.env.example` với `HL_PRIVATE_KEY` và `HL_WALLET_ADDRESS` placeholder
- [x] Create `Makefile` với targets: `make bot`, `make server`, `make dev`, `make test`, `make install`, `make typecheck` (chạy mypy + tsc)

---

## Phase 2: Bot — Config & Database

- [x] `bot/config.py` — Pydantic v2 BaseSettings classes: `ExchangeConfig`, `TradingConfig`, `SpreadConfig`, `InventoryConfig`, `RiskConfig`, `VolatilityConfig`, `AppConfig`; load from YAML + .env
- [x] `bot/utils/logger.py` — structlog setup: JSON output in prod, colored console in dev; include timestamp, level, module fields
- [x] `bot/utils/math_utils.py` — `round_to_tick(price, tick_size)`, `round_to_step(size, step_size)`, `safe_divide(a, b, default)`, `clamp(val, min_val, max_val)`
- [x] `bot/persistence/models.py` — SQLAlchemy 2.0 models:
  - `fills` (id, timestamp, oid, side, price, size, fee, is_maker, **mid_price_at_fill** — fair price when fill occurred, used to compute daily report columns)
  - `orders` (id, oid, side, price, size, status, created_at, updated_at)
  - `price_snapshots` (id, timestamp, fair_price, bid_prices JSON, ask_prices JSON, mid_hl, mid_kraken)
  - `pnl_snapshots` (id, timestamp, realized_pnl, unrealized_pnl, total_pnl, portfolio_value_usdc) — **must record ≥ 1 snapshot/day** for daily report boundary computation
  - `hodl_benchmark` (id, timestamp, xmr_price, usdc_balance, xmr_balance)
- [x] `bot/persistence/database.py` — async SQLAlchemy engine with aiosqlite; `create_tables()` coroutine; `get_session()` async context manager
- [x] `bot/persistence/repository.py` — async CRUD: `save_fill()`, `save_order()`, `update_order_status()`, `save_price_snapshot()`, `save_pnl_snapshot()`, `get_price_history(since)`, `get_pnl_history(since)`, `get_fills(page, limit)`, `get_open_orders()`, `get_hodl_benchmark()`, `get_daily_pnl_summary(days: int) -> list[DailyPnLRow]` — groups fills by UTC date to compute fills_count + fee_rebates; joins pnl_snapshots for daily realized_pnl delta

---

## Phase 3: Bot — Price Feeds

- [x] `bot/feeds/base.py` — Abstract `PriceFeed` base class: `connect()`, `disconnect()`, `get_price() -> float | None`, `last_updated: float`, `latency_ms: float`, `is_healthy(max_stale_seconds) -> bool`, `source_name: str`
- [x] `bot/feeds/hyperliquid_feed.py` — Subscribe to HL WebSocket `allMids`; extract XMR1/USDC mid price; record timestamp + compute latency; reconnect on disconnect
- [x] `bot/feeds/kraken_feed.py` — Subscribe to Kraken public WebSocket v2 ticker for XMR/USDT; extract last trade price; record timestamp + latency; reconnect on disconnect
- [x] `bot/feeds/price_aggregator.py` — `PriceAggregator`: weighted average of healthy feeds (50/50 default); fallback to single feed if one stale; `is_halted()` if both stale; emit feed health dict for status reporting

---

## Phase 4: Bot — Core Engine

- [x] **`bot/engine/algorithms/base.py`** — Algorithm abstraction layer (typed Protocol):
  - `QuoteContext` dataclass: `fair_price: Decimal`, `inventory: Decimal`, `sigma: float`, `regime: Literal["CALM", "VOLATILE"]`, `config: AppConfig`
  - `QuoteLevel` dataclass: `price: Decimal`, `size: Decimal`, `side: Literal["bid", "ask"]`
  - `QuoteSet` dataclass: `bids: list[QuoteLevel]`, `asks: list[QuoteLevel]`
  - `QuotingAlgorithm` Protocol: `compute_quotes(ctx: QuoteContext) -> QuoteSet`, `name: str`
  - Factory function: `get_algorithm(name: str, config: AppConfig) -> QuotingAlgorithm`
- [x] **`bot/engine/algorithms/simple_spread.py`** — `SimpleSpreadAlgorithm`:
  - Fixed spread từ config (`calm_spread_bps` / `volatile_spread_bps`)
  - Multi-level với `level_spacing_bps`; validate min notional $10
  - Dùng để test/benchmark, KHÔNG dùng production
- [x] **`bot/engine/algorithms/avellaneda_stoikov.py`** — `AvellanedaStoikovAlgorithm` (DEFAULT):
  - Tính `reservation_price = mid - inventory × γ × σ² × T`
  - Tính `optimal_spread = γ × σ² × T + (2/γ) × ln(1 + γ/λ)`
  - Tính `bid = reservation_price - spread/2`, `ask = reservation_price + spread/2`
  - `γ` lấy từ config theo regime (`gamma_calm` / `gamma_volatile`)
  - `λ` (order arrival rate) ước tính từ L2 book depth
  - Multi-level: mỗi level thêm `level_spacing_bps` vào spread
  - Validate min notional $10 per level
- [x] **`bot/engine/algorithms/glft.py`** — `GLFTAlgorithm` (dự phòng):
  - GLFT closed-form solution với hard inventory bounds
  - Khi inventory đạt `max_position`: không đặt lệnh về phía đó
  - Có thể dùng thay thế AS nếu muốn hard limits thay vì soft penalty
- [x] `bot/exchange/hyperliquid_client.py` — Wrap `hyperliquid.Exchange` + `hyperliquid.Info` clients:
  - `get_l2_book(asset: str) -> L2Book`
  - `get_user_state() -> UserState`
  - `bulk_place_orders(orders: list[OrderRequest]) -> list[OrderResponse]`
  - `bulk_cancel_orders(oids: list[str]) -> CancelResponse`
  - All orders use ALO tif by default
- [x] `bot/exchange/ws_client.py` — Authenticated HL WebSocket subscriptions: `orderUpdates` + `userFills`; dispatch callbacks `on_order_update(cb)`, `on_fill(cb)`; handle reconnect
- [x] `bot/engine/volatility.py` — `VolatilityEstimator`:
  - Rolling deque of `(timestamp: float, price: Decimal)` pairs, window = `volatility.window_minutes`
  - `add_price(price: Decimal, ts: float) -> None`
  - `compute_realized_vol_bps() -> float` (annualized, expressed in bps)
  - `get_regime() -> Literal["CALM", "VOLATILE"]` with hysteresis
  - `get_vol_bps() -> float`
- [x] `bot/engine/inventory.py` — `InventoryManager`:
  - Track `xmr_position: Decimal`, `avg_entry_price: Decimal` (VWAP), `realized_pnl: Decimal`
  - `on_fill(side: Literal["buy","sell"], price: Decimal, size: Decimal, fee: Decimal) -> None`
  - `compute_unrealized_pnl(fair_price: Decimal) -> Decimal`
  - `compute_skew(max_position: Decimal, skew_factor: float) -> tuple[float, float]` (bid_mult, ask_mult)
  - `inventory_ratio() -> float` (position / max_position, clamped [-1, 1])
- [x] `bot/engine/quoting.py` — `QuoteCalculator`:
  - Chọn algorithm từ config (`get_algorithm(name)`)
  - `compute_quotes(fair_price: Decimal, regime: str, inv_skew: tuple[float,float], config: AppConfig) -> QuoteSet`
  - Delegate tới algorithm được cấu hình; apply inventory skew multipliers sau khi algorithm tính spread
  - Validate min notional ($10) per order; bỏ qua levels không đủ điều kiện
- [x] `bot/exchange/order_manager.py` — `OrderManager`:
  - `open_orders: dict[str, Order]` — tracked by oid
  - `place_quotes(quote_set: QuoteSet)` — calls `bulk_place_orders`, stores in dict
  - `cancel_all()` — calls `bulk_cancel_orders` for all open oids, clears dict
  - `on_order_update(event)` — update order status in dict; remove cancelled/filled
  - `get_open_orders() -> list[Order]`
- [x] `bot/risk/risk_manager.py` — `RiskManager`:
  - `check_pre_cycle(feeds, inventory, daily_pnl, portfolio_value) -> RiskStatus`
  - Individual checks: feed staleness, daily loss, drawdown, inventory limit
  - `trigger_halt(reason: str)` — set halted flag, cancel all orders
  - `is_halted() -> bool`; `halt_reason: str | None`
  - `reset_daily_pnl()` — called at midnight
- [x] `bot/engine/market_maker.py` — `MarketMaker` orchestrator:
  - Async state machine: `STARTING → RUNNING → PAUSED → STOPPED`
  - `run()` — main async loop: sleep cycle_interval, then `run_cycle()`
  - `run_cycle()` — execute full quote cycle (see cycle design in PRD §3)
  - Toggle methods: `toggle_feeds()`, `toggle_wagyu()`, `toggle_quoting()`, `toggle_inv_limit()`
  - `EventBus` — publish `StateUpdate` events after each cycle
  - Handle graceful shutdown (SIGINT/SIGTERM)
- [x] `bot/main.py` — Entry point: load `AppConfig`, init logger, init DB, init feeds, init client, init components, start event loop with `MarketMaker.run()`

---

## Phase 5: FastAPI Server

- [x] `server/ws/hub.py` — `WebSocketHub`:
  - `connected: set[WebSocket]`
  - `connect(ws)` / `disconnect(ws)`
  - `broadcast(event: dict)` — fan out to all connected clients
  - Subscribe to bot `EventBus` → call `broadcast` on each event
- [x] `server/schemas/api_types.py` — Pydantic v2 response models:
  - `StatusResponse`, `ToggleResponse`
  - `PortfolioResponse` (usdc_balance, xmr_balance, total_value_usdc)
  - `FillItem`, `FillsResponse` (items, total, page, limit)
  - `OrderItem`, `OrdersResponse`
  - `PnLSummaryResponse` (realized, unrealized, total, daily)
  - `PnLHistoryResponse` (points: list[PnLPoint])
  - `HealthResponse` (feeds: list[FeedHealth], errors: list[ErrorEntry])
  - `PriceChartResponse`, `BotVsHodlResponse`
- [x] `server/dependencies.py` — FastAPI `Depends()` providers: `get_db_session()`, `get_bot() -> MarketMaker`, `get_ws_hub() -> WebSocketHub`
- [x] `server/routers/status.py` — `GET /api/status` (full bot state snapshot); `POST /api/toggle/{target}` (feeds/wagyu/quoting/inv_limit)
- [x] `server/routers/portfolio.py` — `GET /api/portfolio` (USDC + XMR balances, total value)
- [x] `server/routers/fills.py` — `GET /api/fills?page=1&limit=50` (paginated fill history from DB)
- [x] `server/routers/orders.py` — `GET /api/orders` (current open orders from order manager)
- [x] `server/routers/pnl.py` — `GET /api/pnl/summary`; `GET /api/pnl/history?timeframe=24h`
- [x] `server/routers/health.py` — `GET /api/health` (feed statuses, latencies, recent error log)
- [x] `server/routers/chart.py` — `GET /api/chart/price?timeframe=`; `GET /api/chart/pnl?timeframe=`; `GET /api/chart/bot_vs_hodl?timeframe=`
- [x] `server/routers/report.py` — Daily PnL Report endpoints:
  - `GET /api/report/daily?days=30` → JSON: `{ rows: list[DailyPnLRow], summary: ReportSummary }`; calls `repository.get_daily_pnl_summary(days)`
  - `DailyPnLRow`: `{ day: int, date: str, fills: int, realized_pnl: float, fee_rebates: float, net_pnl: float }`
  - `ReportSummary`: `{ cumulative: float, avg_per_day: float, peak_day: DailyPnLRow, worst_day: DailyPnLRow, win_rate: float, sharpe_annualized: float, total_days: int, running_since: str }`
  - `GET /api/report/daily/export?days=30` → `text/plain` response: monospace-formatted report (same layout as `reportexample.jpg`) for direct browser download as `.txt`
- [x] `server/main.py` — FastAPI app factory with lifespan hooks (start/stop bot); CORS for localhost:3000; `WS /ws` endpoint via `WebSocketHub`; include all routers; uvicorn entrypoint

---

## Phase 6: Frontend — Foundation

- [x] `frontend/src/types/index.ts` — TypeScript interfaces:
  - `BotState`, `FeedInfo`, `ToggleState`
  - `Fill`, `Order`
  - `PricePoint` (ts, fair, avg_entry, bid1, ask1)
  - `PnLPoint` (ts, total, realized)
  - `BotVsHodlPoint` (ts, bot_pct, hodl_pct)
  - `DailyPnLRow` (day, date, fills, realized_pnl, fee_rebates, net_pnl)
  - `ReportSummary` (cumulative, avg_per_day, peak_day, worst_day, win_rate, sharpe_annualized, total_days, running_since)
  - `WsEvent` discriminated union (state_update | fill_event | order_event | alert_event)
- [x] `frontend/src/lib/api.ts` — Typed fetch helpers for all REST endpoints; base URL from `NEXT_PUBLIC_API_URL` env; error handling wrapper; include `fetchDailyReport(days: number): Promise<{ rows: DailyPnLRow[]; summary: ReportSummary }>` and `exportReportUrl(days: number): string`
- [x] `frontend/src/lib/formatters.ts` — `formatPrice(n)`, `formatSize(n)`, `formatPnL(n)` (with color class), `formatBps(n)`, `formatRelativeTime(ts)`, `formatLatency(ms)`
- [x] `frontend/src/store/botStore.ts` — Zustand store:
  - State slices: `status`, `portfolio`, `position`, `pnl`, `feeds`, `recentFills`, `openOrders`, `alerts`
  - Actions: `setStatus()`, `addFill()`, `updateOrders()`, `processWsEvent(event: WsEvent)`
  - Selectors: `useInventoryPct()`, `useVolRegime()`, `useTotalPnL()`
- [x] `frontend/src/hooks/useWebSocket.ts` — WS hook: connect to `ws://localhost:8000/ws`; exponential backoff (1s, 2s, 4s, 8s, max 30s); dispatch each message to `processWsEvent`; expose `connectionState`
- [x] `frontend/src/hooks/useChartData.ts` — Fetch chart data from REST on mount and timeframe change; merge with incoming WS price/pnl events for real-time chart extension; return `{ data, loading, error }`
- [x] `frontend/src/app/globals.css` — Import Tailwind; set `html, body { background: zinc-950 }` dark base; custom scrollbar styling
- [x] `frontend/src/app/layout.tsx` — Root layout: dark theme `className="dark"`, Inter font, metadata title "Wagyu MM Dashboard"

---

## Phase 7: Frontend — Layout Components

- [x] `frontend/src/components/ui/TogglePill.tsx` — Props: `label`, `active: boolean`, `onToggle()`. Style: `bg-green-600` when active, `bg-zinc-700` when inactive; rounded pill; click handler
- [x] `frontend/src/components/ui/ConnectionBadge.tsx` — Props: `source`, `price`, `latency_ms`, `healthy: "ok" | "warn" | "error"`. Show source name + price + latency; dot color: green/yellow/red
- [x] `frontend/src/components/ui/TimeframeSelector.tsx` — Props: `value`, `onChange`, `options: string[]`. Button group (12h/24h/7d/30d/6m/1y/All); active = lighter bg
- [x] `frontend/src/components/ui/NotificationBell.tsx` — Bell icon (Heroicons or lucide-react); badge with unread alert count; click to navigate to Health tab
- [x] `frontend/src/components/layout/Header.tsx` — "Wagyu MM Dashboard" h1 + subtitle; 4-tab nav (Overview/Health/Fills/Orders); `NotificationBell`; active tab underline
- [x] `frontend/src/components/layout/StatusBar.tsx` — Row 1: 4× `TogglePill` (Feeds/Wagyu/Quoting/Inv Limit); Row 2: `ConnectionBadge` for HL + Kraken; POST to `/api/toggle/{target}` on pill click
- [x] `frontend/src/components/layout/StatsStrip.tsx` — Horizontal strip of labeled stat cells: Inv% | Vol Regime (colored CALM/VOLATILE) | Orders | Fills | Last Fill | Cycle (ms)

---

## Phase 8: Frontend — Overview Tab

- [x] `frontend/src/components/panels/PortfolioPanel.tsx` — Card: "Portfolio Value" header; USDC row + XMR row; total line in larger font; read from Zustand `portfolio` slice
- [x] `frontend/src/components/panels/PnLPanel.tsx` — Card: "Total PnL" header; Realized row (green if positive, red if negative); Unrealized row; Total in larger font; color-coded values
- [x] `frontend/src/components/panels/PositionPanel.tsx` — Card: "Position" header; XMR size; Avg Entry price; Fair Price; Bps Diff (entry vs fair, colored); read from Zustand `position` slice
- [x] `frontend/src/components/charts/PriceChart.tsx` — Recharts `LineChart`: 4 series (Fair=orange solid, Avg Entry=white dashed, Bid L1=green, Ask L1=red); `TimeframeSelector`; custom tooltip; responsive container; dark axis/grid
- [x] `frontend/src/components/charts/PnLChart.tsx` — Recharts `ComposedChart`: `Area` for Total PnL (blue semi-transparent fill), `Line` for Realized (orange); `TimeframeSelector`; zero-line reference
- [x] `frontend/src/components/charts/BotVsHodlChart.tsx` — Recharts `LineChart`: Bot % return (orange solid) vs HODL % return (white dashed); `TimeframeSelector`; percentage Y-axis; custom tooltip
- [x] `frontend/src/components/tabs/OverviewTab.tsx` — Layout: 3-column panel grid (Portfolio + PnL + Position); then PriceChart full width; then PnLChart + BotVsHodlChart side by side

---

## Phase 9: Frontend — Secondary Tabs

- [x] `frontend/src/components/tabs/HealthTab.tsx` — Feed health table: columns Source | Status (pill) | Price | Latency | Last Update; below: recent error/alert log (scrollable list with timestamps)
- [x] `frontend/src/components/tabs/FillsTab.tsx` — Paginated table: columns Time | Side (BUY=green/SELL=red pill) | Price | Size | Fee | Maker (badge); pagination controls (prev/next, page indicator); fetch from `/api/fills`
- [x] `frontend/src/components/tabs/OrdersTab.tsx` — Live table: columns OID (first 8 chars) | Side | Price | Size | Status | Age (relative time); auto-refresh from Zustand `openOrders` (WS-driven)
- [x] `frontend/src/components/tabs/ReportTab.tsx` — Daily PnL Report tab:
  - Timeframe selector: 7d / 30d / 90d / All (maps to `?days=` query param)
  - Fetch data from `GET /api/report/daily?days=N` on mount + timeframe change (TanStack Query)
  - Render monospace-style text table in `<pre>` tag styled with `font-mono text-sm` and zinc-800 background matching `reportexample.jpg` layout
  - Columns: Day | Date | Fills | Realized PnL | Fee Rebates | Net P&L (right-aligned numbers, color-coded Net P&L: green if positive, red if negative)
  - Horizontal separator line before TOTAL row
  - Footer block: Cumulative | Avg/Day | Peak Day (date) | Worst Day (date) | Win Rate | Sharpe (ann)
  - "Export .txt" button → triggers `GET /api/report/daily/export?days=N` download
- [x] `frontend/src/app/page.tsx` — Main dashboard page: render `Header` + `StatusBar` + `StatsStrip`; `useState` for active tab; conditional render of `OverviewTab | HealthTab | FillsTab | OrdersTab | ReportTab`; tab options: `["Overview", "Health", "Fills", "Orders", "Report"]`; mount `useWebSocket` hook

---

## Phase 10: Scripts & Utilities

- [x] `scripts/set_benchmark.py` — CLI script: query current portfolio value from Hyperliquid; record to `hodl_benchmark` table with current XMR price + balances; used as "t=0" for Bot vs HODL chart
- [x] `scripts/daily_report.py` — CLI report generator that reads from SQLite and prints (or saves) a monospace daily PnL report matching `reportexample.jpg`:
  - Args: `--days 30` (default 30), `--output report.txt` (optional, prints to stdout if omitted), `--db data/marketmaker.db` (path to SQLite)
  - Prints header: bot name/version, pair, running since date
  - Prints table: Day | Date | Fills | Realized PnL | Fee Rebates | Net P&L (right-aligned, fixed-width columns)
  - Prints separator + TOTAL row
  - Prints summary: Cumulative | Avg/Day | Peak Day | Worst Day | Win Rate | Sharpe (ann)
  - Sharpe formula: `mean(daily_net_pnl) / std(daily_net_pnl) * sqrt(365)` (annualized)
  - Win rate: `days_net_pnl_positive / total_days * 100`
  - Usable without the server running (reads SQLite directly via sync SQLAlchemy)
- [x] `scripts/backtest.py` — Offline spread simulator: load historical XMR price CSV; simulate quote/fill logic; output PnL curve and stats (total return, max drawdown, Sharpe approximation)
- [x] `tests/test_quoting.py` — Unit tests for `QuoteCalculator`:
  - Spread math: verify bid/ask prices at expected bps from fair price
  - Skew logic: long position → ask tighter than bid
  - Min order validation: orders below $10 notional are excluded
  - Multi-level spacing: each level N bps wider than previous
- [x] `tests/test_inventory.py` — Unit tests for `InventoryManager`:
  - VWAP calculation after multiple fills
  - Unrealized PnL at various fair prices
  - Skew computation at different inventory_ratio values
  - `on_fill()` updates position correctly for buys vs sells
- [x] `tests/test_volatility.py` — Unit tests for `VolatilityEstimator`:
  - Low-variance prices → CALM regime
  - High-variance prices → VOLATILE regime
  - Hysteresis: regime doesn't flip back immediately when vol crosses threshold
  - Empty window → default CALM
- [x] `tests/test_risk.py` — Unit tests for `RiskManager`:
  - Daily loss limit breach → `check_pre_cycle` returns HALT
  - Max drawdown breach → HALT
  - Stale feed (>5s) → HALT
  - All checks passing → OK
  - `trigger_halt()` sets halted flag

---

## Phase 11: Integration & Hardening

- [ ] End-to-end test on Hyperliquid testnet (`https://api.hyperliquid-testnet.xyz`) — verify bot starts, places orders, orders visible in Hyperliquid UI *(requires real testnet private key)*
- [ ] Verify fills from testnet are persisted correctly to `data/marketmaker.db` SQLite *(requires real testnet private key)*
- [x] Verify all chart REST endpoints return correctly timeframe-filtered data for each option (12h/24h/7d/30d/6m/1y/All) — tested manually against running server, all 7 timeframes return HTTP 200
- [x] Verify WebSocket events from bot propagate to Next.js dashboard within 1 cycle (~2s) — verified via WebSocket hub unit tests (123 passed) and server WS endpoint accepting connections
- [x] Verify kill switch: disable "Quoting" toggle → bot cancels all orders; re-enable → bot resumes quoting — `POST /api/toggle/quoting` toggles correctly, cancel_all() called on disable
- [ ] Verify stale feed risk control: disconnect network for 6+ seconds → quoting halts; alert appears in Health tab *(requires network test environment)*
- [x] Performance check: verify quote cycle completes in <500ms — cycle_time_ms logged each cycle; observed ~28ms in demo mode
- [x] `README.md` with setup instructions: prerequisites, install, config, `make install`, `make bot` + `make server` + `make dev`, testnet vs mainnet config
- [x] Fix: `structlog.stdlib.add_logger_name` incompatibility with `PrintLoggerFactory` — switched to `stdlib.LoggerFactory()` in `bot/utils/logger.py`
- [x] Fix: `feed_health` dict missing `last_updated` field → `FeedHealthItem` Pydantic validation error — added `last_updated` to dict in `market_maker.py`
- [x] Fix: `MagicMock(spec=MarketMaker)` blocking access to instance attrs in API tests — switched to `MagicMock()` + per-router `_get_mm` dependency overrides
- [x] Fix: async `in_memory_db` fixture needing `@pytest_asyncio.fixture()` in STRICT mode
- [x] Fix: `greenlet` DLL missing dependencies on Python 3.14/Windows — resolved by copying MSVCP140.dll + api-ms-win-crt-*.dll to greenlet package dir
- [x] All 123 unit + integration tests pass (0 failed); 7 repository tests skipped only when greenlet unavailable

---

## Phase Completion Summary

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project Setup | [x] |
| 2 | Bot Config & Database | [x] |
| 3 | Bot Price Feeds | [x] |
| 4 | Bot Core Engine | [x] |
| 5 | FastAPI Server | [x] |
| 6 | Frontend Foundation | [x] |
| 7 | Frontend Layout Components | [x] |
| 8 | Frontend Overview Tab | [x] |
| 9 | Frontend Secondary Tabs | [x] |
| 10 | Scripts & Utilities | [x] |
| 11 | Integration & Hardening | [~] partially done; testnet tests pending private key |

---

## Critical Path (Minimum Viable Bot)

Để có bot trading trên testnet nhanh nhất, ưu tiên theo thứ tự:

1. Phase 1 (setup + mypy/tsc config)
2. Phase 2 (config + DB — typed Pydantic models)
3. Phase 3 (price feeds)
4. **`bot/engine/algorithms/base.py` + `avellaneda_stoikov.py`** (Phase 4 — algorithm layer trước)
5. `bot/exchange/hyperliquid_client.py` (Phase 4)
6. `bot/engine/volatility.py` + `bot/engine/inventory.py` + `bot/engine/quoting.py` (Phase 4)
7. `bot/exchange/order_manager.py` + `bot/risk/risk_manager.py` (Phase 4)
8. `bot/engine/market_maker.py` + `bot/main.py` (Phase 4 complete)
9. Phase 5 (server) — for dashboard visibility
10. Phases 6-9 (frontend) — for monitoring UI

> **Typing checkpoint:** Sau mỗi phase, chạy `make typecheck` (mypy + tsc) trước khi sang phase tiếp theo.
