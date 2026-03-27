# Wagyu Market Maker Bot v2.4.1

Automated market making bot for XMR1/USDC on the Hyperliquid spot DEX, with a real-time Next.js monitoring dashboard.

**Algorithm:** Avellaneda-Stoikov with CALM/VOLATILE regime switching
**Exchange:** Hyperliquid (via Wagyu interface)
**Pair:** XMR1/USDC

---

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Node.js 18+ and npm
- A Hyperliquid API wallet (EIP-712 keypair)

---

## Setup

### 1. Clone & Install

```bash
# Install Python dependencies
make install

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure

```bash
# Copy config templates
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
HL_PRIVATE_KEY=0x...     # API wallet private key
HL_WALLET_ADDRESS=0x...  # API wallet address
```

Edit `config/config.yaml` to tune trading parameters (spread, inventory limits, risk controls).

### 3. Set HODL Benchmark (optional)

Records your starting portfolio for the Bot vs HODL comparison chart:
```bash
poetry run python scripts/set_benchmark.py
```

---

## Running

### Full Stack (recommended)

```bash
# Terminal 1: Start the bot + FastAPI server
make server

# Terminal 2: Start the Next.js dashboard
make dev
```

Dashboard available at: `http://localhost:3000`

### Bot Only (no dashboard)

```bash
make bot
```

### Development

```bash
make install    # Install all dependencies
make typecheck  # Run mypy (Python) + tsc (TypeScript)
make test       # Run pytest unit tests
make clean      # Remove __pycache__, .mypy_cache, .next
```

---

## Testnet vs Mainnet

**Testnet** (default in `config.example.yaml`):
```yaml
exchange:
  api_url: "https://api.hyperliquid-testnet.xyz"
  ws_url: "wss://api.hyperliquid-testnet.xyz/ws"
```

**Mainnet**:
```yaml
exchange:
  api_url: "https://api.hyperliquid.xyz"
  ws_url: "wss://api.hyperliquid.xyz/ws"
```

---

## Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **Overview** | Portfolio value, PnL, position, price chart, PnL chart, Bot vs HODL chart |
| **Health** | Feed connectivity (HL + Kraken), latency, error log |
| **Fills** | Paginated fill history with side, price, size, fee, maker/taker |
| **Orders** | Live open orders with age |
| **Report** | Daily PnL breakdown table with Sharpe, win rate, export to `.txt` |

---

## Configuration Reference

```yaml
algorithm:
  name: "avellaneda_stoikov"  # Options: simple_spread, avellaneda_stoikov, glft

avellaneda_stoikov:
  gamma_calm: 0.04      # Risk aversion in calm market (lower = tighter spreads)
  gamma_volatile: 0.08  # Risk aversion in volatile market

trading:
  cycle_interval_seconds: 2.0
  order_levels: 3               # Bid + ask levels per cycle
  level_sizes: [50, 100, 200]   # USDC notional per level

inventory:
  max_position_xmr: 10.0     # Max XMR position before halting direction
  skew_factor: 0.5            # Inventory skew strength

risk:
  daily_loss_limit_usdc: 50.0  # Halt if daily PnL < -50 USDC
  max_drawdown_pct: 5.0        # Halt if portfolio drops 5% from session start
  stale_feed_seconds: 5.0      # Halt if no price update for 5 seconds
```

---

## Scripts

```bash
# Record HODL benchmark (run once before starting bot)
poetry run python scripts/set_benchmark.py

# Generate daily PnL report from SQLite (no server needed)
poetry run python scripts/daily_report.py --days 30

# Save report to file
poetry run python scripts/daily_report.py --days 30 --output report.txt

# Backtest on historical price CSV
poetry run python scripts/backtest.py --csv prices.csv
```

---

## Architecture

```
[KrakenFeed] [HyperliquidFeed]
       ↓
  PriceAggregator
       ↓
  VolatilityEstimator → InventoryManager → QuoteCalculator (Avellaneda-Stoikov)
       ↓
  RiskManager → OrderManager → Hyperliquid Exchange API (ALO orders)
       ↓
  Repository → SQLite (fills, snapshots, PnL)
       ↓
  EventBus → FastAPI WebSocketHub → Next.js Dashboard
```

---

## Security Notes

- **Never commit `.env`** — it is gitignored by default
- Use an **API wallet** (separate keypair) rather than your main wallet private key
- The API wallet must be authorized on your main Hyperliquid wallet
- The dashboard has no authentication — run only on localhost, never expose publicly
