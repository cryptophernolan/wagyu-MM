# Bug Report

## Status
RESOLVED

## Bug Title
3 bugs found: short PnL not realized on buy-close, risk boundary conditions use strict inequality, and greenlet DLL missing on Python 3.14

---

## Bug 1: InventoryManager — Short Position PnL Not Realized on Buy-Close

### Bug Description
When a short position is closed via a `buy` fill, `realized_pnl` stays at 0. The `on_fill("buy")` branch only handles building long positions and flipping from short-to-long, but never calls PnL realization for the closed short portion.

### Steps to Reproduce
```python
inv = InventoryManager()
inv.on_fill("sell", Decimal("150.0"), Decimal("1.0"), Decimal("0"))  # short at $150
inv.on_fill("buy", Decimal("140.0"), Decimal("1.0"), Decimal("0"))   # cover at $140
# Expected: realized_pnl = $10, position = 0
# Actual:   realized_pnl = $0,  position = 0
```

### Root Cause Analysis
`bot/engine/inventory.py:43-52` — The `buy` branch:
```
if side == "buy":
    new_position = self._xmr_position + size
    if new_position > 0:            ← only enters this block for longs
        update VWAP
    self._xmr_position = new_position   ← position updated but NO PnL realized
```

When `_xmr_position = -1` (short) and we buy 1:
- `new_position = 0` → condition `> 0` is False → skips VWAP update (correct)
- Position becomes 0 (correct)
- **But `realized_pnl` is never touched** — missing the "close short" PnL path

```
on_fill("buy") current flow:
  position = -1 (short, avg_entry=150)
  new_position = -1 + 1 = 0
  0 > 0 → False → skip VWAP update
  position ← 0
  ❌ PnL NEVER REALIZED
```

### Proposed Fix (Recommended)
Add a short-close PnL path inside `on_fill("buy")` before updating position:

```python
# In on_fill, "buy" branch, before self._xmr_position = new_position:
if self._xmr_position < Decimal("0"):
    # Closing (or reducing) a short position → realize PnL
    closed = min(size, abs(self._xmr_position))
    pnl_delta = (self._avg_entry_price - price) * closed - fee
    self._realized_pnl += pnl_delta
```

**Files to change:** `bot/engine/inventory.py` (lines 43-52)

### Verification
- `test_iv_09_sell_from_flat_creates_short_position` must pass
- Existing `test_sell_fill_realizes_profit` must still pass (long close path unchanged)

---

## Bug 2: RiskManager — Boundary Conditions Use Strict Inequality (< / >)

### Bug Description
Both the daily loss limit check and the max drawdown check use strict inequality, so a position exactly AT the configured limit does NOT trigger a halt. The correct circuit breaker behavior is to halt at-or-beyond the limit.

### Root Cause Analysis
`bot/risk/risk_manager.py:80` — Daily loss check:
```python
if daily_pnl < -self._config.risk.daily_loss_limit_usdc:   # strict <
```
When `daily_pnl == -50.0` and `limit == 50.0`: `-50.0 < -50.0` → False → **no halt**

`bot/risk/risk_manager.py:94` — Drawdown check:
```python
if drawdown_pct > self._config.risk.max_drawdown_pct:   # strict >
```
When `drawdown == 5.0%` and `max == 5.0%`: `5.0 > 5.0` → False → **no halt**

### Proposed Fix (Recommended)
Change both comparisons to non-strict:

```python
# Daily loss: halt when AT or BEYOND the limit
if daily_pnl <= -self._config.risk.daily_loss_limit_usdc:

# Drawdown: halt when AT or BEYOND the limit
if drawdown_pct >= self._config.risk.max_drawdown_pct:
```

**Files to change:** `bot/risk/risk_manager.py` (lines 80 and 94)

**Impact:** RM-03 (currently passing, daily_pnl=-60 < -50 → also satisfies <=) still passes.

---

## Bug 3: greenlet DLL Missing on Python 3.14 / Windows

### Bug Description
9 integration tests were skipped because `greenlet` failed to import with `ImportError: DLL load failed while importing _greenlet`. SQLAlchemy async requires greenlet for its async bridge.

### Root Cause Analysis
greenlet 3.3.2 `.pyd` file requires `MSVCP140.dll` and `api-ms-win-crt-*.dll` which are not in `PATH` on this Python 3.14 / Windows install (Visual C++ Redistributable not installed system-wide). `conftest.py` was adding `vcruntime140.dll` directories but not the greenlet package directory where `MSVCP140.dll` is now co-located.

### Fix Applied (Already Done)
1. Copied required DLLs into `site-packages/greenlet/`: `MSVCP140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`, all `api-ms-win-crt-*.dll`
2. Updated `conftest.py` to call `os.add_dll_directory(greenlet_package_dir)` when `MSVCP140.dll` is present there

**Result:** All 9 previously-skipped repository tests now pass.

---

## Summary of Findings

| ID | File | Type | Status |
|----|------|------|--------|
| Bug 1 | `bot/engine/inventory.py:43` | Logic bug — missing PnL path | Needs fix |
| Bug 2 | `bot/risk/risk_manager.py:80,94` | Off-by-one — strict vs non-strict | Needs fix |
| Bug 3 | `conftest.py` + greenlet DLL | Environment/infra | **Fixed** |

### Test Suite Status Before Fixes
- **173 passed, 3 failed** (out of 176 total)
- Failures: `test_iv_09`, `test_rm_08`, `test_rm_10`

### Missing Test Files (Now Created)
- `tests/test_math_utils.py` — MU-01 through MU-06 (18 tests)
- `tests/test_feeds.py` — PA-01 through PA-05 + edge cases (13 tests)

### Missing Edge Cases (Now Added to Existing Files)
- `test_quoting.py` — QT-10 (GLFT valid), QT-11 (tiny price), QT-12 (sigma=0)
- `test_inventory.py` — IV-09 (short close PnL), IV-10 (fee deduction), IV-11 (5-fill VWAP)
- `test_volatility.py` — VL-07 (window eviction), VL-08 (single price), VL-09 (threshold transitions)
- `test_risk.py` — RM-08 (boundary halt), RM-09 (just under), RM-10 (drawdown boundary)

### Frontend Status
TypeScript check (`tsc --noEmit`): **0 errors** — frontend is clean.

---

## Fix Applied

### Files Changed
- **`bot/engine/inventory.py`** — Added short-close PnL realization in `on_fill("buy")` branch. When `xmr_position < 0`, closed portion is now computed and `realized_pnl` updated before position changes.
- **`bot/risk/risk_manager.py`** — Changed `daily_pnl < -limit` to `daily_pnl <= -limit` (line 80); changed `drawdown_pct > max_pct` to `drawdown_pct >= max_pct` (line 94).
- **`conftest.py`** — Added `os.add_dll_directory(greenlet_package_dir)` to fix greenlet DLL loading on Python 3.14/Windows.
- **`tests/test_math_utils.py`** — Created: MU-01 through MU-06 + extras (18 tests)
- **`tests/test_feeds.py`** — Created: PA-01 through PA-05 + extras (13 tests)
- **`tests/test_quoting.py`** — Added QT-10/11/12 edge cases
- **`tests/test_inventory.py`** — Added IV-09/10/11 edge cases
- **`tests/test_volatility.py`** — Added VL-07/08/09 edge cases
- **`tests/test_risk.py`** — Added RM-08/09/10 boundary cases

### Test Results
```
176 passed, 0 failed, 0 skipped
```
Up from 116 passed / 9 skipped (previously) and 173 passed / 3 failed (after new tests added before fixes).

### Verification
- Bug 1 (IV-09): `realized_pnl = $10` after short-close confirmed ✓
- Bug 2 (RM-08, RM-10): halt triggers at exactly the configured limit ✓
- Bug 3 (greenlet): all 9 repository integration tests now pass ✓
- Frontend TypeScript: `tsc --noEmit` returns 0 errors ✓

---

# Session 2 — Testnet E2E Testing (2026-03-26)

## Status: 4 Bugs Found and Fixed

---

## Bug 4: WS userFills Snapshot Replays Historical Fills on Connect

### Bug Description
Every time the bot starts, Hyperliquid's `userFills` WebSocket subscription sends back a snapshot of recent fills. The bot processed these historical fills as new fills, inflating the InventoryManager position each restart.

### Root Cause
`bot/exchange/ws_client.py:_dispatch()` processed all `userFills` messages including the initial snapshot. Example: fill OID `50430105739` (buy 100 PURR) was saved to DB on every server restart, accumulating 15+ duplicate fills.

### Fix Applied
- Added `isSnapshot` check: if `data.get("isSnapshot")` is True, skip immediately
- Added time-based guard: if `fill.get("time") < self._session_start_ms`, skip (secondary guard for list-format snapshots)
- Set `self._session_start_ms` at `__init__` time to filter any fills with timestamps before bot start

**File changed:** `bot/exchange/ws_client.py`

---

## Bug 5: `get_user_state()` Returns 0 for Spot Balances

### Bug Description
Portfolio value showed 0 USDC and 0 PURR despite wallet having 531.86 USDC and 99.93 PURR.

### Root Cause
`bot/exchange/hyperliquid_client.py:get_user_state()` called SDK's `info.user_state()` which returns **perp** account state. The `crossMarginSummary.accountValue` is the perp account balance (0 for spot-only wallets). The `spotState` key does not exist in the perp response.

### Fix Applied
Changed to call `spotClearinghouseState` REST endpoint directly:
```python
resp = requests.post(api_url + '/info',
    json={'type': 'spotClearinghouseState', 'user': wallet_address}, timeout=10)
# Parse balances list for USDC and base_coin (PURR or XMR1)
```

**File changed:** `bot/exchange/hyperliquid_client.py`

---

## Bug 6: Kraken Feed Blends XMR Price into PURR Fair Price

### Bug Description
On testnet, `config.exchange.kraken_symbol = ""` (disabled) but `server/main.py` always instantiated `KrakenFeed()` with default symbol `"XMR/USDT"`. The aggregator blended XMR/USDT ($342) with PURR/USDC ($4.65) giving `fair_price = $173` and `portfolio_value = $155,987`.

### Fix Applied
In `server/main.py`, check `config.exchange.kraken_symbol` before creating KrakenFeed:
```python
feeds = [hl_feed]
if config.exchange.kraken_symbol:
    kraken_feed = KrakenFeed(symbol=config.exchange.kraken_symbol)
    feeds.append(kraken_feed)
```

**File changed:** `server/main.py`

---

## Bug 7: `bulk_place_orders()` Crashes on Rate-Limit Error Response

### Bug Description
When Hyperliquid returns `{"status": "err", "response": "Too many cumulative requests..."}`, the response parsing code crashed with `AttributeError: 'str' object has no attribute 'get'`.

### Root Cause
```python
statuses = result.get("response", {}).get("data", {}).get("statuses", [])
```
When `result["response"]` is a string (error message), calling `.get()` on it fails.

### Fix Applied
Added top-level error check before parsing response structure:
```python
if result.get("status") == "err":
    logger.warning("bulk_orders exchange error", error=str(result.get("response", ""))[:300])
    return []
response_field = result.get("response", {})
if not isinstance(response_field, dict):
    logger.warning("bulk_orders unexpected response format", ...)
    return []
```

**File changed:** `bot/exchange/hyperliquid_client.py`

---

## Testnet Rate Limit Issue (Not a Code Bug)

Wallet `0xAd8fbA51` exceeded Hyperliquid's cumulative maker order request quota after many test sessions. The quota formula appears to be: `allowed = 10000 + taker_volume_usdc_traded`. With 13665 requests used and only $1125 taker volume (allowing 11125), the deficit is ~2540 requests.

**Impact:** Cycles 2+ cannot place orders; cycle 1 (first cycle per session) works correctly.

**Not a code bug.** Workaround: use a fresh wallet with no request history, OR trade ~$2540 more taker volume on testnet.

**Verified E2E with cycle 1:**
- 6 ALO orders placed (3 bids + 3 asks) ✓
- Correct market = PURR/USDC ✓
- Correct prices: bids at ~4.45, asks at ~4.85 ✓
- Orders appear in Hyperliquid testnet UI ✓

---

## Session 2 Summary

| ID | File | Type | Status |
|----|------|------|--------|
| Bug 4 | `bot/exchange/ws_client.py` | WS snapshot replay | **Fixed** |
| Bug 5 | `bot/exchange/hyperliquid_client.py` | Wrong API endpoint for spot balances | **Fixed** |
| Bug 6 | `server/main.py` | Kraken feed always enabled ignoring config | **Fixed** |
| Bug 7 | `bot/exchange/hyperliquid_client.py` | Crash on error response from exchange | **Fixed** |
| — | Testnet wallet | Cumulative request quota exceeded | Not a code bug |

**Test suite:** 176 passed, 0 failed (unchanged)
