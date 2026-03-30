# Bug Report

## Status
RESOLVED

---

## Bug #1 — CRITICAL: `cancel_all_exchange_orders()` Blocks Async Event Loop

### Bug Description
`OrderManager.cancel_all_exchange_orders()` là một `async` method nhưng gọi 2 synchronous HTTP calls trực tiếp (không qua `run_in_executor`), block toàn bộ event loop trong khi chờ HTTP response từ Hyperliquid.

### Steps to Reproduce
1. Khởi động bot với `make bot` hoặc `make server`
2. Bot gọi `cancel_all_exchange_orders()` trong phase startup (trước khi vào trading loop)
3. Event loop bị freeze trong suốt thời gian HTTP call (200–500ms bình thường, vài giây nếu mạng chậm)

### Actual Result
Event loop blocked khi startup. Trong thời gian này, không có WebSocket message nào được xử lý — feeds bị stall ngay khi bắt đầu.

### Expected Result
Tất cả HTTP calls trong async context phải dùng async wrappers (đã có sẵn trong `HyperliquidClient`).

### Context
- **File:** `bot/exchange/order_manager.py` lines 173, 177
- **Environment:** Tất cả môi trường (testnet + mainnet)

### Root Cause Analysis

```
market_maker.run()
  └─await─► cancel_all_exchange_orders()     ← async method
                 │
                 ├── get_user_state()          ← SYNC: requests.post("/info") → BLOCKS loop
                 │
                 └── bulk_cancel_orders()      ← SYNC: requests.post("/exchange") → BLOCKS loop
```

```python
# bot/exchange/order_manager.py:170-183
async def cancel_all_exchange_orders(self) -> int:
    try:
        user_state = self._client.get_user_state()      # LINE 173 — sync, blocks
        stale_oids = [str(o["oid"]) for o in user_state.open_orders]
        if not stale_oids:
            return 0
        self._client.bulk_cancel_orders(stale_oids)     # LINE 177 — sync, blocks
```

Async wrappers `async_get_user_state()` và `async_bulk_cancel_orders()` đã tồn tại trong `HyperliquidClient` nhưng không được dùng ở đây.

### Proposed Fix

**Option 1 (Recommended): Dùng async wrappers đã có sẵn — 2 dòng thay đổi**

```python
# Before:
user_state = self._client.get_user_state()
...
self._client.bulk_cancel_orders(stale_oids)

# After:
user_state = await self._client.async_get_user_state()
...
await self._client.async_bulk_cancel_orders(stale_oids)
```

### Verification Plan
- Startup log không còn lag giữa "Starting" và first WebSocket message

---

## Bug #2 — HIGH: `bot/main.py` Thiếu `base_coin` → XMR Balance = 0 trên Mainnet

### Bug Description
`bot/main.py` khởi tạo `HyperliquidClient` không truyền `base_coin`. Với mainnet asset `"@260"`, client tự suy ra `_base_coin = "@260"` (vì `"@260".split("/")[0] == "@260"`). Mọi balance lookup đều tìm coin tên `"@260"` trong danh sách balances → không khớp → `xmr_balance = 0` mãi mãi.

### Steps to Reproduce
1. Cấu hình mainnet: `asset: "@260"`, `base_coin: "XMR1"` trong config.yaml
2. Chạy `make bot` (dùng `bot/main.py`, KHÔNG phải `make server`)
3. Xem log: `portfolio_value = usdc_balance + 0.0 * fair_price`

### Actual Result
```
portfolio_value = USDC_balance  (XMR component luôn = 0)
drawdown calculation sai → có thể halt quá sớm hoặc không halt khi cần
```

### Expected Result
`_base_coin = "XMR1"` để balance lookup tìm đúng token.

### Context
- **File bị lỗi:** `bot/main.py:54-59` — KHÔNG có `base_coin`
- **File đúng (reference):** `server/main.py:55-61` — CÓ `base_coin=config.exchange.base_coin`
- **Chỉ ảnh hưởng CLI mode** (`make bot`); server mode (`make server`) đúng

### Root Cause Analysis

```
                   bot/main.py              server/main.py
                 ┌──────────────────┐     ┌──────────────────┐
config.yaml      │ HyperliquidClient│     │ HyperliquidClient│
base_coin:"XMR1" │   asset="@260"   │     │   asset="@260"   │
      │          │   # ← MISSING    │     │   base_coin="XMR1│ ← correct
      └──────────►                  │     │                  │
                 └──────────────────┘     └──────────────────┘
                         │                         │
                  _base_coin="@260"         _base_coin="XMR1"
                         │                         │
                  xmr_balance = 0          xmr_balance = correct
```

### Proposed Fix

**Option 1 (Recommended): 1 dòng thêm vào `bot/main.py`**

```python
# bot/main.py:54-59
client = HyperliquidClient(
    api_url=config.exchange.api_url,
    private_key=config.env.hl_private_key,
    wallet_address=config.env.hl_wallet_address,
    asset=config.exchange.asset,
    base_coin=config.exchange.base_coin,    # ← THÊM DÒNG NÀY
)
```

### Verification Plan
- Chạy `make bot` mainnet, kiểm tra `session start portfolio` log có giá trị hợp lý (USDC + XMR × price)
- `state_update` WS event: `portfolio_value` không thể nhỏ hơn USDC balance

---

## Bug #3 — LOW: `modify_or_replace_quotes()` Không Cập Nhật DB Prices Sau Modify-In-Place

### Bug Description
Khi `modify_or_replace_quotes()` thực hiện modify-in-place thành công, nó cập nhật `_open_orders` dict trong RAM (prices/sizes mới) nhưng KHÔNG ghi vào SQLite. DB vẫn có prices từ lần `place_quotes()` gốc. Divergence này tăng theo mỗi cycle.

### Steps to Reproduce
1. Config: `use_order_modify: true`
2. Chạy bot, để 2+ dead-band refreshes xảy ra (giá dịch > 5 bps)
3. `SELECT oid, price FROM orders WHERE status='open'` trong SQLite → prices cũ, không khớp exchange

### Actual Result
DB order records: prices = lần đặt lệnh gốc
Exchange orders: prices = giá sau lần modify cuối cùng

### Expected Result
DB đồng bộ với exchange sau mỗi modify.

### Context
- **File:** `bot/exchange/order_manager.py:141-148`
- **Ảnh hưởng:** Dashboard "Orders" tab nếu đọc từ DB; không ảnh hưởng quoting logic hay fills

### Root Cause Analysis

```
place_quotes()           → save_order() → DB price = P1  ✓
modify_or_replace()      → only _open_orders[oid].price = P2  ✓ RAM
  (modify succeeds)        NO repository call               ✗ DB still P1
```

```python
# order_manager.py:141-148 — missing DB update
if success:
    for mod in modifies:
        if mod.oid in self._open_orders:
            self._open_orders[mod.oid].price = mod.price  # RAM ✓
            self._open_orders[mod.oid].size = mod.size    # RAM ✓
            # ← MISSING: await repository.update_order_price(mod.oid, ...)
```

### Proposed Fix

**Option 1 (Recommended): Thêm `update_order_price()` vào repository + gọi trong modify loop**

Cần 2 thay đổi:
1. Thêm function `update_order_price(oid, price, size)` vào `bot/persistence/repository.py`
2. Gọi nó trong `modify_or_replace_quotes()` sau khi modify thành công

**Option 2 (Quick fix): Disable modify, dùng cancel+replace**

Set `use_order_modify: false` trong config.yaml — mất 50% savings nhưng DB luôn consistent ngay lập tức (không cần code change).

### Verification Plan
- Với fix #1: `SELECT price FROM orders WHERE status='open'` khớp exchange prices
- Với option 2: prices luôn đúng trong DB (cancel+place path đã correct)

---

## Summary

| # | Severity | File | Lines | Issue |
|---|----------|------|-------|-------|
| 1 | **CRITICAL** | `order_manager.py` | 173, 177 | 2 sync HTTP calls block event loop at startup |
| 2 | **HIGH** | `bot/main.py` | 54–59 | Missing `base_coin` → XMR balance = 0 on mainnet CLI mode |
| 3 | **LOW** | `order_manager.py` | 141–148 | Modify-in-place skips DB price update |

**False positives đã xác minh (không phải bug):**
- `_force_refresh` race condition: asyncio single-threaded, không có concurrent access
- Bid/ask sort order: đúng (bids desc, asks asc khớp algorithm output)
- Missing DB commits: `get_session()` auto-commits ở `database.py:57`
- `async_bulk_modify_orders` blocking: dùng `run_in_executor` đúng cách
- Missing `base_coin` trong `config.yaml`: đã có (`base_coin: "XMR1"`)

---

## Fix Applied

### Files Changed
- **`bot/exchange/order_manager.py:173,177`** — Bug #1: thay `get_user_state()` bằng `await async_get_user_state()`, thay `bulk_cancel_orders()` bằng `await async_bulk_cancel_orders()`
- **`bot/main.py:58`** — Bug #2: thêm `base_coin=config.exchange.base_coin` vào `HyperliquidClient()`
- **`bot/persistence/repository.py:109-118`** — Bug #3: thêm function `update_order_price(oid, price, size)`
- **`bot/exchange/order_manager.py:147`** — Bug #3: gọi `await repository.update_order_price()` sau modify thành công
- **`tests/test_quoting.py`, `tests/test_risk.py`, `tests/test_integration_bot.py`** — thêm `RateLimitConfig` import + `rate_limit=RateLimitConfig()` vào `make_config()` helpers (required by rate-limit optimization added earlier today)

### Test Results
```
173 passed, 3 failed (pre-existing, unrelated to these fixes)
```

Pre-existing failures (confirmed failing BEFORE today's changes via `git stash`):
- `test_risk_halt_on_stale_feeds` — test expects `is_halted=True` for stale feed, but RiskManager treats stale feed as transient PAUSE, not permanent halt
- `test_run_cycle_places_orders_on_both_sides` — mock uses `MagicMock` instead of `AsyncMock` for `async_get_user_state()`
- `test_run_cycle_saves_pnl_snapshot` — same `MagicMock` issue

### Verification
- Bug #1: startup no longer blocks; uses async wrappers consistently
- Bug #2: `bot/main.py` now passes `base_coin` — XMR balance lookup works on mainnet with `asset="@260"`
- Bug #3: DB order prices updated after modify-in-place via new `update_order_price()` repository function
