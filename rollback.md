# Rollback Guide — Rate Limit Optimization

**Ngày thay đổi:** 2026-03-30
**Mục đích thay đổi:** Giảm tiêu thụ Hyperliquid order ops từ ~518,400/ngày xuống còn ~1,000-3,000/ngày để phù hợp với giới hạn 10,000 ops/ngày, bằng cách thêm dead-band filtering, force-refresh on fill, timer fallback, và order modify-in-place.

---

## Các file đã thay đổi

| File | Backup |
|------|--------|
| `bot/engine/market_maker.py` | `bot/engine/market_maker.py.bak` |
| `bot/exchange/order_manager.py` | `bot/exchange/order_manager.py.bak` |
| `bot/exchange/hyperliquid_client.py` | `bot/exchange/hyperliquid_client.py.bak` |
| `bot/config.py` | `bot/config.py.bak` |
| `config/config.example.yaml` | `config/config.example.yaml.bak` |
| `config/config.yaml` | `config/config.yaml.bak` |

---

## Cách rollback (khôi phục về phiên bản cũ)

### Rollback toàn bộ (khuyến nghị)

Chạy lệnh sau trong terminal tại thư mục `MarketMaker/`:

```bash
cp bot/engine/market_maker.py.bak     bot/engine/market_maker.py
cp bot/exchange/order_manager.py.bak  bot/exchange/order_manager.py
cp bot/exchange/hyperliquid_client.py.bak bot/exchange/hyperliquid_client.py
cp bot/config.py.bak                  bot/config.py
cp config/config.example.yaml.bak    config/config.example.yaml
cp config/config.yaml.bak            config/config.yaml
```

Trên Windows (Command Prompt / PowerShell):
```powershell
copy bot\engine\market_maker.py.bak     bot\engine\market_maker.py
copy bot\exchange\order_manager.py.bak  bot\exchange\order_manager.py
copy bot\exchange\hyperliquid_client.py.bak bot\exchange\hyperliquid_client.py
copy bot\config.py.bak                  bot\config.py
copy config\config.example.yaml.bak    config\config.example.yaml
copy config\config.yaml.bak            config\config.yaml
```

### Rollback từng file riêng lẻ

Nếu chỉ muốn rollback một file cụ thể (ví dụ chỉ market_maker.py):

```bash
cp bot/engine/market_maker.py.bak bot/engine/market_maker.py
```

---

## Tóm tắt những gì đã thay đổi

### `bot/config.py`
- **Thêm:** class `RateLimitConfig` với 3 tham số:
  - `deadband_bps` — ngưỡng giá dịch chuyển (bps) để trigger refresh
  - `max_refresh_interval_seconds` — thời gian tối đa giữa 2 lần refresh (fallback timer)
  - `use_order_modify` — dùng modify-in-place thay vì cancel+replace
- **Thêm:** `rate_limit: RateLimitConfig` vào `AppConfig`

### `config/config.example.yaml` và `config/config.yaml`
- **Thêm:** section `rate_limit:` với các giá trị mặc định

### `bot/exchange/hyperliquid_client.py`
- **Thêm:** dataclass `ModifyRequest`
- **Thêm:** method `modify_order_sync()` — gọi SDK modify_order cho 1 lệnh
- **Thêm:** method `async_bulk_modify_orders()` — modify nhiều lệnh song song

### `bot/exchange/order_manager.py`
- **Thêm:** method `modify_or_replace_quotes()` — thử modify-in-place nếu có thể, fallback sang cancel+place
- `cancel_all()` + `place_quotes()` giữ nguyên, không thay đổi

### `bot/engine/market_maker.py`
- **Thêm fields:** `_last_quoted_price`, `_last_refresh_time`, `_force_refresh`
- **Thêm method:** `_should_refresh()` — logic dead-band + force + timer
- **Sửa:** `_on_fill()` — set `_force_refresh = True` khi có fill
- **Sửa:** `run_cycle()` — chỉ refresh orders nếu `_should_refresh()` trả True; dùng `modify_or_replace_quotes`

---

## Logic dead-band hoạt động như thế nào

```
Mỗi cycle (~3 giây):
  ├── Kiểm tra _should_refresh():
  │   ├── _force_refresh == True?  → REFRESH (vừa có fill)
  │   ├── Không có open orders?    → REFRESH
  │   ├── Thời gian > max_refresh_interval? → REFRESH (fallback mỗi 60s)
  │   └── |fair_price - last_quoted_price| > deadband_bps? → REFRESH
  │
  ├── Nếu REFRESH:
  │   ├── Thử modify-in-place (nếu use_order_modify=true và số levels khớp)
  │   └── Fallback: cancel_all() + place_quotes()
  │
  └── Nếu KHÔNG REFRESH:
      └── Bỏ qua bước order, chỉ emit state/snapshot
```

**Ước tính tiêu thụ sau tối ưu:**
- Trước: 43,200 cycles × 12 ops = **518,400 ops/ngày**
- Sau (dead-band 5 bps): ~200–500 refreshes × 6 ops (modify) = **~1,200–3,000 ops/ngày**
- Dư thoải mái trong giới hạn 10,000 ops/ngày

---

---

---

# Rollback Guide — Autonomous Agent Health Monitoring

**Git tag:** `v2.4.1-pre-agents`
**Created:** 2026-03-30
**What it captures:** Complete codebase state before adding the autonomous agent health monitoring system.

## What Was Added (Changes to Undo)

| File | Change Type |
|------|------------|
| `bot/agents/__init__.py` | NEW |
| `bot/agents/base_agent.py` | NEW |
| `bot/agents/cycle_watchdog.py` | NEW |
| `bot/agents/order_integrity.py` | NEW |
| `bot/agents/quote_activity.py` | NEW |
| `bot/agents/exchange_probe.py` | NEW |
| `bot/agents/agent_runner.py` | NEW |
| `server/schemas/api_types.py` | MODIFIED |
| `server/dependencies.py` | MODIFIED |
| `server/routers/health.py` | MODIFIED |
| `server/main.py` | MODIFIED |
| `frontend/src/types/index.ts` | MODIFIED |
| `frontend/src/lib/api.ts` | MODIFIED |
| `frontend/src/store/botStore.ts` | MODIFIED |
| `frontend/src/components/tabs/HealthTab.tsx` | MODIFIED |

## Rollback Options

### Option A — Full rollback to exact pre-agent state (recommended)

```bash
# 1. Stop running containers first
docker compose down

# 2. Reset code to the backup tag
git checkout v2.4.1-pre-agents

# 3. Rebuild and restart
docker compose build
docker compose up -d
```

### Option B — Restore specific server/frontend files only

```bash
# Restore only the backend agent wiring
git checkout v2.4.1-pre-agents -- server/main.py server/schemas/api_types.py \
  server/dependencies.py server/routers/health.py

# Restore frontend
git checkout v2.4.1-pre-agents -- frontend/src/types/index.ts \
  frontend/src/lib/api.ts frontend/src/store/botStore.ts \
  frontend/src/components/tabs/HealthTab.tsx

# Remove new agent module
rm -rf bot/agents/

# Rebuild
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

### Option C — Disable agents without code change

Set `agents.enabled: false` in `config/config.yaml`:

```yaml
agents:
  enabled: false
```

Then restart: `docker compose restart backend`

## Verify Rollback

```bash
docker compose ps
# /api/health/agents should return 404
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health/agents
```

---

## Tuning tham số rate_limit

Chỉnh trong `config/config.yaml`:

```yaml
rate_limit:
  deadband_bps: 5.0              # Tăng lên 8-10 nếu vẫn vượt limit
  max_refresh_interval_seconds: 60.0  # Giảm xuống 30 nếu muốn responsive hơn
  use_order_modify: true         # Đổi false nếu SDK báo lỗi modify
```

- `deadband_bps` thấp (3-4): responsive hơn, tốn ops hơn
- `deadband_bps` cao (8-10): tiết kiệm hơn, quotes ít fresh hơn
- Không nên dùng `deadband_bps > spread_bps/2` vì quotes sẽ stale trước khi fill
