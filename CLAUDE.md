# Wagyu Market Maker Bot — Product Requirements Document

## 1. Product Overview

**Goal:** An automated market making bot for the XMR1/USDC trading pair on the Hyperliquid spot DEX, accessed via the Wagyu interface. The bot continuously quotes both sides of the order book to earn maker fees while managing inventory risk.

**Dashboard:** A local Next.js dark-theme monitoring dashboard (not public-facing) displaying real-time bot status, portfolio, PnL, charts, fills, and open orders.

**Target user:** Solo trader/developer running the bot on their own machine. No authentication, no multi-user, no cloud deployment required.

**Scope:** Single asset pair (XMR1/USDC), single exchange (Hyperliquid), local SQLite persistence.

---

## 2. Research Findings — Platform & API

### Wagyu / Hyperliquid

Wagyu is a frontend interface layered on top of the Hyperliquid spot DEX. All trading is executed directly against Hyperliquid's API — Wagyu provides no separate API; it is purely a UI.

**API Endpoints:**
| Environment | REST Base | WebSocket |
|-------------|-----------|-----------|
| Mainnet | `https://api.hyperliquid.xyz` | `wss://api.hyperliquid.xyz/ws` |
| Testnet | `https://api.hyperliquid-testnet.xyz` | `wss://api.hyperliquid-testnet.xyz/ws` |

**Authentication:**
- EIP-712 signing with a private key (Ethereum-compatible wallet)
- Recommended pattern: API wallet — a separate keypair authorized by your main wallet, never storing the main wallet private key
- All order actions are signed messages submitted to the REST endpoint as JSON

**Key REST Endpoints:**
- `POST /exchange` — all order actions (place, cancel, bulk operations)
- `POST /info` — query market data, user state, order book

**Key WebSocket Subscriptions:**
- `allMids` — real-time mid prices for all assets (use for XMR1/USDC feed)
- `l2Book` — full order book depth
- `orderUpdates` — order lifecycle events for authenticated user
- `userFills` — fill notifications for authenticated user

**XMR1/USDC Market Parameters:**
| Parameter | Value |
|-----------|-------|
| price_decimals | 2 |
| size_decimals | 2 |
| min_order_notional | $10 USD |
| maker_fee | 1 bps (0.01%) |
| taker_fee | 3.5 bps (0.035%) |

**Order Type for Market Making:**
- **ALO (Add Liquidity Only)** = post-only. Order is rejected (not filled as taker) if it would immediately cross the spread.
- This guarantees the maker rebate and prevents accidentally paying taker fees.
- Set via `orderType: { limit: { tif: "Alo" } }` in the SDK.

**Batch API:**
- `bulkOrders` — place up to ~20 orders in a single signed request
- `bulkCancel` — cancel multiple orders by oid in one request
- Reduces API calls and rate limit consumption significantly

**Rate Limits:**
- 1200 weight/minute
- Each order placement/cancellation = 1 weight
- Batch operations count as N weights (one per order in batch)
- Info queries = lower weight; aggressive info polling still consumes budget

---

## 3. Research Findings — Market Making Best Practices

### Core Principle: Earn Maker Fees, Manage Inventory

A market maker profits by:
1. Earning the bid-ask spread (buying at bid, selling at ask)
2. Earning maker fee rebates on every filled order
3. Net: ~2-4 bps per round trip on XMR1/USDC

Risk comes from **inventory accumulation** — if the price moves directionally, the position built up from fills loses value faster than fees earned.

### Post-Only Orders (ALO)

Always use ALO. Never place orders that could cross the spread as taker:
- Taker fee (3.5 bps) wipes out the spread profit on that fill
- The ALO rejection mechanism is free insurance against this

### Spread Configuration

**Minimum viable spread:** Must exceed round-trip fee cost = 2 × maker_fee = 2 bps. Safe minimum: 4 bps.

**Regime-based spread:**
- **CALM regime** (low volatility): tighter spread (e.g., 6-10 bps) to capture more fills
- **VOLATILE regime** (high volatility): wider spread (e.g., 20-40 bps) to protect against adverse selection

**Volatility detection:** Compute realized volatility from rolling 30-minute price window. Compare against thresholds with hysteresis (transition CALM→VOLATILE at higher threshold than VOLATILE→CALM) to avoid flickering.

### Inventory Skew

When the bot accumulates a position:
- **Long XMR:** Want to sell → tighten ask spread (cheaper to buy from us), widen bid spread (more expensive to sell to us)
- **Short XMR:** Want to buy → tighten bid spread, widen ask spread

Skew formula:
```
bid_spread = base_spread × (1 + skew_factor × inventory_ratio)
ask_spread = base_spread × (1 - skew_factor × inventory_ratio)
```
Where `inventory_ratio = current_position / max_position ∈ [-1, 1]`

### Multi-Level Quoting

Place 2-3 price levels per side:
- Level 1: tightest spread, smallest size (most likely to fill)
- Level 2: wider spread, medium size
- Level 3: widest spread, largest size (rarely fills, provides depth)

Benefits: higher probability of partial fills, more natural order book presence, better maker fee capture.

### Price Feed Aggregation

Use multiple independent price feeds to compute fair value:
- **Primary:** Hyperliquid WebSocket `allMids` for XMR1/USDC
- **Secondary:** Kraken public WebSocket for XMR/USDT as independent reference
- **Aggregation:** Weighted average (50/50 when both healthy)
- **Fallback:** Use single feed if one is stale (>5s without update)
- **Halt:** Stop quoting if both feeds stale

### Kill Switches & Risk Controls

| Control | Trigger | Action |
|---------|---------|--------|
| Stale feed | No price update >5s | Pause quoting, cancel all orders |
| Daily loss limit | Realized PnL < -N USDC today | Full halt, require manual restart |
| Max drawdown | Portfolio value down >X% from session start | Full halt |
| Max inventory | Position > max_position_xmr | Stop adding in that direction |
| Manual kill switch | UI toggle | Cancel all, stop quoting |

### Cycle Design

```
Every ~2 seconds:
1. Check risk controls → abort if triggered
2. Get latest fair price from aggregator
3. Compute volatility regime
4. Compute inventory skew
5. Calculate new quotes (multi-level bid/ask arrays)
6. Cancel all existing orders (bulk cancel)
7. Place new quotes (bulk place, ALO)
8. Record price snapshot to DB
9. Compute unrealized PnL
10. Emit state event to dashboard
```

---

## 3.5 Market Making Algorithms — Research & Selection

### Algorithm Overview

Nghiên cứu các thuật toán market making phổ biến trong crypto:

| Thuật toán | Độ phức tạp | Quản lý Inventory | Phù hợp cho |
|------------|-------------|-------------------|-------------|
| Simple Symmetric Spread | Thấp | Không có | Testing/học tập, không dùng production |
| **Avellaneda-Stoikov (AS)** | **Trung bình** | **Soft penalty qua γ** | **⭐ Khuyến nghị: pair kém thanh khoản** |
| GLFT (Guéant-Lehalle-Fernandez-Tapia) | Trung bình | Hard inventory bounds | Trader bảo thủ, muốn giới hạn cứng |
| Reinforcement Learning (RL) | Rất cao | Học ngầm qua training | Nghiên cứu, multi-asset (không phù hợp production) |

### Thuật toán được chọn: Avellaneda-Stoikov

**Khuyến nghị: Chạy MỘT thuật toán (Avellaneda-Stoikov) + regime switching để điều chỉnh tham số.**

**Tại sao chọn Avellaneda-Stoikov:**
- Tối ưu về mặt toán học (stochastic control theory) cho pair kém thanh khoản như XMR1/USDC
- Quản lý inventory qua **soft penalty** (tham số γ): khác GLFT dùng hard bounds có thể ngăn đặt lệnh khi sách lệnh mỏng
- Cộng đồng triển khai phong phú: Hummingbot, [fedecaccia/avellaneda-stoikov](https://github.com/fedecaccia/avellaneda-stoikov), [AymenCode/Avellaneda-Stoikov-Market-Making](https://github.com/AymenCode/Avellaneda-Stoikov-Market-Making)
- Tham số dễ hiểu và dễ điều chỉnh dựa trên kết quả thực tế

**Công thức AS cốt lõi:**
```
reservation_price = mid_price - inventory × γ × σ² × (T - t)
spread = γ × σ² × (T - t) + (2/γ) × ln(1 + γ/λ)

bid = reservation_price - spread/2
ask = reservation_price + spread/2
```

Trong đó:
- `γ` (gamma): hệ số risk aversion — cao hơn = spread rộng hơn, ít rủi ro inventory
- `σ` (sigma): realized volatility của giá (tính từ rolling window)
- `T - t`: time horizon (thích nghi thành rolling window cho crypto 24/7)
- `λ` (lambda): tốc độ đến của lệnh (ước tính từ độ sâu sổ lệnh)
- `inventory`: vị thế XMR hiện tại

**Tham số AS theo regime:**
```
CALM regime:    γ = 0.04, order_levels = 3
VOLATILE regime: γ = 0.08, order_levels = 2
```

### ❌ Tại sao KHÔNG chạy nhiều thuật toán đồng thời

Chạy nhiều thuật toán cùng lúc (ví dụ AS + GLFT song song) **bị khuyến cáo mạnh**:

1. **Xung đột order book:** Hai thuật toán tính bid/ask khác nhau → đặt lệnh trùng lặp, tạo vị thế không mong muốn
2. **Inventory tracking vỡ:** Mỗi thuật toán ước tính spread tối ưu **độc lập**, không biết về fill của nhau
3. **Lãng phí rate limit:** Đặt và hủy lệnh chồng chéo tốn API weight vô ích
4. **Không có lợi ích cộng thêm:** Nếu AS là tối ưu, thêm GLFT chỉ tạo nhiễu, không tạo alpha
5. **Chi phí phối hợp cao:** Giải quyết xung đột giữa các thuật toán cần numerical optimization phức tạp

**Thay vào đó:** Một thuật toán + regime switching = hành vi rõ ràng, dễ debug. Regime switching chỉ thay đổi **tham số** của cùng một thuật toán — không chạy thuật toán riêng biệt.

### Algorithm Abstraction Layer

Codebase triển khai một lớp trừu tượng để dễ thay thế thuật toán sau này (không cần refactor):

```python
# bot/engine/algorithms/base.py
class QuotingAlgorithm(Protocol):
    def compute_quotes(self, ctx: QuoteContext) -> QuoteSet: ...
    @property
    def name(self) -> str: ...

# Implementations:
# bot/engine/algorithms/simple_spread.py   — SimpleSpreadAlgorithm
# bot/engine/algorithms/avellaneda_stoikov.py — AvellanedaStoikovAlgorithm (default)
# bot/engine/algorithms/glft.py            — GLFTAlgorithm (for future use)
```

**Config để chọn thuật toán:**
```yaml
algorithm:
  name: "avellaneda_stoikov"  # Tùy chọn: "simple_spread", "avellaneda_stoikov", "glft"
  # ⚠️  Chỉ chọn MỘT thuật toán. Chạy nhiều thuật toán đồng thời KHÔNG được hỗ trợ.
```

### Tóm tắt lựa chọn

> **Kết luận:** Dùng `avellaneda_stoikov` (mặc định) với regime-based parameter switching. Đây là cách tiếp cận đã được kiểm chứng cho crypto market making bởi Hummingbot, Elixir Protocol, và nhiều công ty MM chuyên nghiệp. Tùy chọn `simple_spread` và `glft` được cung cấp trong codebase nhưng chỉ dùng cho mục đích so sánh/thử nghiệm.

---

## 4. Feature Requirements

### Bot Engine

| ID | Feature | Description |
|----|---------|-------------|
| F1 | Price Aggregation | Real-time price from HL WebSocket (`allMids`) + Kraken WebSocket; weighted average; staleness detection |
| F2 | Volatility Regime | Rolling 30-min price window; compute realized vol in bps; CALM/VOLATILE states with hysteresis thresholds |
| F3 | Multi-level Quoting | 3 bid + 3 ask levels per cycle; spread_bps configurable per regime; size configurable per level |
| F4 | Inventory Skew | Skew bid/ask spreads asymmetrically based on position vs max_position; skew_factor configurable |
| F5 | Order Lifecycle | Cancel all stale orders (bulk) → place fresh quotes (bulk) each cycle; track open order dict |
| F6 | Post-Only Enforcement | All orders placed with ALO tif; never market orders; never limit orders that cross |
| F7 | Position Tracking | Track XMR position; compute VWAP avg entry from fills; update on every fill event |
| F8 | PnL Tracking | Realized PnL from closed fills; unrealized PnL = (fair - entry) × position; snapshot every cycle |
| F9 | Risk Controls | Stale feed halt; daily loss limit; drawdown limit; max inventory guard; manual kill switch |
| F10 | Persistence | SQLite via SQLAlchemy async: fills, orders, price_snapshots, pnl_snapshots, hodl_benchmark tables |

### Dashboard Frontend

| ID | Feature | Description |
|----|---------|-------------|
| F11 | Header | Bot title "Wagyu MM Dashboard", 5-tab navigation (Overview, Health, Fills, Orders, **Report**), notification bell |
| F12 | Status Bar | Toggle pills: Feeds / Wagyu / Quoting / Inv Limit (on=green, off=gray); Connection badges: HL price+latency, Kraken price+latency (green/yellow/red health) |
| F13 | Stats Strip | Inv% of max \| Vol Regime \| Orders count \| Fills count \| Last Fill time \| Cycle time (ms) |
| F14 | Overview Panels | Portfolio Value card (USDC + XMR); Total PnL card (Realized + Unrealized); Position card (size, entry, fair, bps diff) |
| F15 | Price Chart | Multi-line Recharts: Fair Price (orange), Avg Entry (dashed white), Bids (green), Asks (red); timeframe selector (12h/24h/7d/30d/6m/1y/All) |
| F16 | PnL History Chart | Area chart: Total PnL (blue fill) + Realized line (orange); timeframe selector |
| F17 | Bot vs HODL Chart | Line chart: Bot % return (orange) vs HODL % return (dashed white); timeframe selector |
| F18 | Health Tab | Feed health table (source, status, price, latency, last update); recent error log / alert list |
| F19 | Fills Tab | Paginated table: time \| side (color-coded BUY/SELL) \| price \| size \| fee \| maker badge |
| F20 | Orders Tab | Live open orders table: oid (truncated) \| side \| price \| size \| status \| age |
| F21 | Real-time Updates | WebSocket connection from frontend to FastAPI; no polling for live data; exponential backoff reconnect |
| F22 | Dark Theme | zinc-900/zinc-950 background palette; consistent with provided screenshot reference |
| F23 | Daily PnL Report Tab | Monospace-style text table showing per-day breakdown: Day \| Date \| Fills \| Realized PnL \| Fee Rebates \| Net P&L; summary footer (Cumulative, Avg/Day, Peak Day, Worst Day, Win Rate, Sharpe ann); timeframe selector (7d/30d/90d/All); "Export .txt" button |

### F23 — Daily PnL Report: Detail Specification

**Report Format (matching `reportexample.jpg`):**
```
Wagyu.xyz MM Bot v2.x.x — DAILY P&L REPORT
XMR1/USDC | Algo: Avellaneda-Stoikov
Running since: 2026-02-14 00:00 UTC

 Day  Date      Fills   Realized PnL   Fee Rebates   Net P&L
   1  Feb 14      487          $207           $11       $218
   2  Feb 15      612          $287           $14       $301
   3  Feb 16       93           -$3            $8         $5
 ...
─────────────────────────────────────────────────────────────
TOTAL  30 days   18,591        $22,731          $782    $23,513

CUMULATIVE: $23,513   AVG/DAY: $783.77
PEAK DAY:   $1,268 (Mar 10)   WORST: -$3 (Feb 16)
WIN RATE:   29/30 days (96.7%)
SHARPE (ann): 3.87
```

**Column Definitions:**
| Column | Calculation |
|--------|-------------|
| **Fills** | Count of fills for the day from `fills` table |
| **Realized PnL** | VWAP-based realized PnL delta: end-of-day `realized_pnl` − start-of-day `realized_pnl` (from `pnl_snapshots`) |
| **Fee Rebates** | Sum of maker rebates earned = `sum(fill_notional × 0.0001)` per day (1 bps maker rate) |
| **Net P&L** | Realized PnL + Fee Rebates (total cash-positive outcome for the day) |

> **Note:** Unlike the example screenshot (which has an "Unwind" column for perp hedge P&L and a "Fund" column for funding payments), this bot does not hedge with perp contracts. The two components are simply: spread/inventory PnL (Realized PnL) and maker fee rebates (Fee Rebates).

**Summary Stats:**
| Stat | Calculation |
|------|-------------|
| **Cumulative** | Sum of all Net P&L across selected timeframe |
| **Avg/Day** | Cumulative ÷ number of trading days |
| **Peak Day** | Day with highest Net P&L + date |
| **Worst Day** | Day with lowest Net P&L + date |
| **Win Rate** | Days where Net P&L > 0 ÷ total days |
| **Sharpe (ann)** | `(mean_daily_pnl / std_daily_pnl) × sqrt(365)` — annualized daily Sharpe ratio |

**Persistence requirement:** The `pnl_snapshots` table must record at least one snapshot per day at consistent intervals so that start/end-of-day realized_pnl can be computed. The `fills` table already provides fee data. No extra table required.

**API endpoint:** `GET /api/report/daily?days=30` → returns `{ rows: DailyPnLRow[], summary: ReportSummary }`.
**Export endpoint:** `GET /api/report/daily/export?days=30` → returns `text/plain` monospace-formatted report for download.
**CLI script:** `python scripts/daily_report.py --days 30` → prints same text to terminal; `--output report.txt` saves to file.

---

## 5. Non-Requirements (Explicitly Excluded)

- **Multi-asset support:** Only XMR1/USDC is in scope. No abstraction for other pairs needed now.
- **Multi-user / authentication:** This is a local personal tool. No login, no API keys per user.
- **Mobile responsiveness:** Dashboard is for desktop monitoring only.
- **Cloud deployment:** Bot and dashboard run on the same local machine.
- **Backtesting engine:** A basic backtest script (`scripts/backtest.py`) is included but is not a core feature.
- **Order routing / smart order routing:** Single venue only.
- **Telegram / alert notifications:** Out of scope (alerts are in the Health tab only).

---

## 6. Technology Stack

> **Nguyên tắc bắt buộc — Typed Programming Language:**
> Toàn bộ dự án phải sử dụng ngôn ngữ có kiểu tĩnh (Typed Programming Language). Mục đích: phát hiện lỗi type và syntax sớm trước khi chạy, giúp testing dễ dàng hơn, và dễ refactor an toàn hơn.
> - **Python backend:** Bắt buộc full type hints (PEP 484/526) trên tất cả functions, arguments, return values, và variables. Enforce với `mypy --strict`.
> - **TypeScript frontend:** Bắt buộc, không dùng `any`, không dùng `@ts-ignore`. Enforce với `tsc --noEmit`.

### Bot Engine
| Component | Technology | Lý do |
|-----------|-----------|--------|
| Language | **Python 3.11+ với Full Type Hints** | Async support; type hints bắt buộc (PEP 484/526); phát hiện lỗi sớm |
| Type checker | **mypy (strict mode)** | Static type checking; `--strict` bật tất cả kiểm tra type |
| Exchange SDK | hyperliquid-python-sdk | Official SDK; handles EIP-712 signing |
| Async runtime | asyncio | Single-thread event loop, compatible với SDK |
| Config | Pydantic v2 + pydantic-settings | Runtime type validation + config typed từ YAML + .env |
| Logging | structlog | Structured JSON logs; easy to grep/filter |
| Kraken feed | websockets library | Direct WebSocket tới Kraken public API |

**Yêu cầu type hints Python — Ví dụ:**
```python
# ✅ Đúng — full type hints
from decimal import Decimal
from typing import Literal

def compute_spread(
    fair_price: Decimal,
    gamma: float,
    sigma: float,
    inventory: Decimal,
) -> tuple[Decimal, Decimal]:
    ...

# ❌ Sai — thiếu type hints
def compute_spread(fair_price, gamma, sigma, inventory):
    ...
```

### Server
| Component | Technology | Lý do |
|-----------|-----------|--------|
| Framework | FastAPI + uvicorn | Async-native, WebSocket support, fast |
| ORM | SQLAlchemy 2.0 async | Async queries; compatible với aiosqlite |
| Database | SQLite + aiosqlite | Simple, local, zero-config, đủ cho 1 user |
| Serialization | **Pydantic v2 models** | Typed response schemas; runtime validation |

### Frontend
| Component | Technology | Lý do |
|-----------|-----------|--------|
| Framework | Next.js 14 (App Router) | React 18 streaming; fast local dev |
| Language | **TypeScript (strict mode)** | Type safety; `strict: true` trong tsconfig; không dùng `any` |
| Styling | Tailwind CSS | Utility-first; dễ dark theme |
| Charts | Recharts | Composable React charting; không deps ngoài |
| State | Zustand | Lightweight; no boilerplate; fine-grained subscriptions |
| Server state | TanStack Query | Caching + deduplication cho REST endpoints |

### Config Files
- `config/config.yaml` — exchange, trading, spread, inventory, risk parameters (copy from `config.example.yaml`)
- `.env` — private key, API wallet address (never commit)

---

## 7. Directory Structure

```
MarketMaker/
├── bot/
│   ├── config.py
│   ├── main.py
│   ├── engine/
│   │   ├── market_maker.py      # Main orchestrator
│   │   ├── quoting.py           # Quote calculator (wraps algorithm)
│   │   ├── volatility.py        # Regime detection
│   │   ├── inventory.py         # Position + PnL tracking
│   │   └── algorithms/
│   │       ├── base.py          # QuotingAlgorithm Protocol + QuoteContext/QuoteSet types
│   │       ├── simple_spread.py # SimpleSpreadAlgorithm (testing only)
│   │       ├── avellaneda_stoikov.py  # AvellanedaStoikovAlgorithm (DEFAULT)
│   │       └── glft.py          # GLFTAlgorithm (future use)
│   ├── exchange/
│   │   ├── hyperliquid_client.py
│   │   ├── order_manager.py
│   │   └── ws_client.py
│   ├── feeds/
│   │   ├── base.py
│   │   ├── hyperliquid_feed.py
│   │   ├── kraken_feed.py
│   │   └── price_aggregator.py
│   ├── persistence/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── repository.py
│   ├── risk/
│   │   └── risk_manager.py
│   └── utils/
│       ├── logger.py
│       └── math_utils.py
├── server/
│   ├── main.py
│   ├── dependencies.py
│   ├── schemas/
│   │   └── api_types.py
│   ├── routers/
│   │   ├── status.py
│   │   ├── portfolio.py
│   │   ├── fills.py
│   │   ├── orders.py
│   │   ├── pnl.py
│   │   ├── health.py
│   │   ├── chart.py
│   │   └── report.py
│   └── ws/
│       └── hub.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   │   ├── TogglePill.tsx
│   │   │   │   ├── ConnectionBadge.tsx
│   │   │   │   ├── TimeframeSelector.tsx
│   │   │   │   └── NotificationBell.tsx
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── StatusBar.tsx
│   │   │   │   └── StatsStrip.tsx
│   │   │   ├── panels/
│   │   │   │   ├── PortfolioPanel.tsx
│   │   │   │   ├── PnLPanel.tsx
│   │   │   │   └── PositionPanel.tsx
│   │   │   ├── charts/
│   │   │   │   ├── PriceChart.tsx
│   │   │   │   ├── PnLChart.tsx
│   │   │   │   └── BotVsHodlChart.tsx
│   │   │   └── tabs/
│   │   │       ├── OverviewTab.tsx
│   │   │       ├── HealthTab.tsx
│   │   │       ├── FillsTab.tsx
│   │   │       ├── OrdersTab.tsx
│   │   │       └── ReportTab.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useChartData.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   └── formatters.ts
│   │   ├── store/
│   │   │   └── botStore.ts
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── config/
│   └── config.example.yaml
├── data/                        # SQLite DB stored here
├── logs/
├── scripts/
│   ├── set_benchmark.py
│   ├── daily_report.py
│   └── backtest.py
├── tests/
│   ├── test_quoting.py
│   ├── test_inventory.py
│   ├── test_volatility.py
│   └── test_risk.py
├── .env.example
├── pyproject.toml
├── Makefile
├── CLAUDE.md                    # This file
└── IMPLEMENTATION_PLAN.md
```

---

## 8. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Python Bot Engine                       │
│                                                             │
│  [KrakenFeed] [HyperliquidFeed] → PriceAggregator           │
│       ↓                                                     │
│  VolatilityEstimator → InventoryManager → QuoteCalculator   │
│       ↓                                                     │
│  RiskManager → OrderManager → Hyperliquid Exchange API      │
│       ↓                                                     │
│  Repository → SQLite (fills, snapshots, PnL)                │
│       ↓                                                     │
│  EventBus ──────────────────────────────────────────────┐   │
└─────────────────────────────────────────────────────────│───┘
                                                          │
┌─────────────────────────────────────────────────────────▼───┐
│                      FastAPI Server                          │
│                                                             │
│  REST: /api/status, /api/fills, /api/orders, /api/chart/*,  │
│        /api/report/daily, /api/report/daily/export          │
│  WebSocket: /ws → WebSocketHub → fanout to frontend clients  │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket events + REST
┌──────────────────────────────▼──────────────────────────────┐
│                    Next.js Dashboard                         │
│                                                             │
│  Zustand Store ← useWebSocket hook ← WS connection          │
│       ↓                                                     │
│  Header + StatusBar + StatsStrip                            │
│  OverviewTab: [Portfolio][PnL][Position] + 3 Charts         │
│  HealthTab | FillsTab | OrdersTab                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. Key Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| **Quoting algorithm** | **Avellaneda-Stoikov (single)** | **Mathematically optimal for illiquid pairs; soft inventory penalty; không xung đột** |
| **Multi-algorithm** | **Không** | **Conflicting orders, broken inventory tracking, no alpha benefit** |
| **Typed language** | **Python + mypy strict / TypeScript strict** | **Phát hiện lỗi type sớm; dễ refactor; bắt buộc toàn dự án** |
| Order type | ALO (post-only) | Guarantees 1bps maker fee; prevents crossing spread accidentally |
| Order placement | Batch API (`bulkOrders`) | Minimize rate limit consumption; atomic placement |
| Database | SQLite + SQLAlchemy async | Simple, local, no external service dependency |
| Quote cycle interval | ~2 seconds | Balance between latency and rate limit budget |
| Price feed | HL `allMids` + Kraken WebSocket | Redundancy; Kraken as independent reference price |
| Frontend state | Zustand | Lightweight; no boilerplate; fine-grained subscriptions |
| Charts | Recharts | Composable React charting; works without additional deps |
| Frontend real-time | WebSocket (not polling) | Low latency; efficient for 2-second cycle updates |
| Config | YAML + .env | Human-readable trading params; secrets in .env never committed |
| Spread minimum | 4 bps | Must exceed 2×maker_fee round-trip cost with buffer |

---

## 10. Configuration Reference

```yaml
# config/config.example.yaml

exchange:
  api_url: "https://api.hyperliquid.xyz"  # or testnet URL
  ws_url: "wss://api.hyperliquid.xyz/ws"
  asset: "XMR1"
  quote_asset: "USDC"

trading:
  cycle_interval_seconds: 2.0
  order_levels: 3              # bid + ask levels per side
  level_sizes: [50, 100, 200]  # USDC notional per level

algorithm:
  name: "avellaneda_stoikov"   # Options: "simple_spread", "avellaneda_stoikov", "glft"
  # ⚠️  Chỉ chọn MỘT thuật toán — chạy nhiều thuật toán song song KHÔNG được hỗ trợ.
  # Khuyến nghị: "avellaneda_stoikov" cho XMR1/USDC (illiquid pair)

avellaneda_stoikov:
  gamma_calm: 0.04             # risk aversion trong CALM regime (lower = tighter spreads)
  gamma_volatile: 0.08         # risk aversion trong VOLATILE regime (higher = wider spreads)
  # lambda (order arrival rate) được ước tính tự động từ order book depth
  # T (time horizon) được set tự động theo rolling window = volatility.window_minutes

spread:
  calm_spread_bps: 8           # fallback spread cho simple_spread algorithm (CALM)
  volatile_spread_bps: 25      # fallback spread cho simple_spread algorithm (VOLATILE)
  level_spacing_bps: 4         # additional bps per level away from mid

inventory:
  max_position_xmr: 10.0       # halt new longs/shorts beyond this
  skew_factor: 0.5             # multiplier on inventory ratio for skew
  target_position_xmr: 0.0    # neutral target (usually 0)

risk:
  daily_loss_limit_usdc: 50.0  # halt if daily PnL < -50 USDC
  max_drawdown_pct: 5.0        # halt if portfolio down 5% from session start
  stale_feed_seconds: 5.0      # halt if no price update for 5 seconds

volatility:
  window_minutes: 30           # rolling window for realized vol
  calm_threshold_bps: 20       # below this → CALM regime
  volatile_threshold_bps: 35   # above this → VOLATILE regime (hysteresis)
```

```bash
# .env.example
HL_PRIVATE_KEY=0x...           # API wallet private key
HL_WALLET_ADDRESS=0x...        # API wallet address (authorized on main wallet)
```

---

## 11. Verification Checklist

1. **Bot standalone (testnet):** `make bot` → orders appear in Hyperliquid testnet UI; fills saved to SQLite; log cycle times < 500ms
2. **Server standalone:** `make server` → `GET /api/status` returns valid JSON; `GET /api/chart/price?timeframe=24h` returns time series array
3. **Frontend standalone:** `make dev` → dashboard loads; WS connects; all panels render (zeros OK if bot not running)
4. **Full stack:** All three running → dashboard updates in real-time; toggle pills pause/resume quoting; fills appear in Fills tab within 1 cycle
5. **Risk controls:** Disconnect network → quoting halts within 5s; alert appears in Health tab; no new orders placed
6. **ALO enforcement:** Verify no taker fills in fill history (all fills should have `liquidated: false`, side matches posted side)
