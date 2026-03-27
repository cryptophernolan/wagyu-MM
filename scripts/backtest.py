#!/usr/bin/env python3
"""Offline backtest: simulate AS market maker on historical XMR price data."""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class BacktestConfig:
    gamma: float = 0.04
    spread_min_bps: float = 2.0
    level_sizes: list[float] = field(default_factory=lambda: [50.0, 100.0, 200.0])
    max_position_xmr: float = 10.0
    fill_probability: float = 0.3  # Probability a quote level gets filled per tick
    maker_fee_bps: float = 1.0


@dataclass
class SimPosition:
    xmr: float = 0.0
    usdc: float = 0.0
    avg_entry: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    fill_count: int = 0


def load_prices(csv_path: str) -> list[tuple[float, float]]:
    """Load (timestamp, price) from CSV. Expects columns: timestamp, close."""
    prices: list[tuple[float, float]] = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = float(row.get("timestamp", row.get("time", "0")))
            price = float(row.get("close", row.get("price", "0")))
            if price > 0:
                prices.append((ts, price))
    return prices


def compute_vol(prices: list[tuple[float, float]], window: int = 30) -> float:
    """Compute annualised realised volatility from the last *window* observations."""
    if len(prices) < 2:
        return 0.001
    recent = prices[-window:]
    log_returns = [
        math.log(recent[i][1] / recent[i - 1][1]) for i in range(1, len(recent))
    ]
    if not log_returns:
        return 0.001
    mean = sum(log_returns) / len(log_returns)
    var = sum((r - mean) ** 2 for r in log_returns) / max(len(log_returns) - 1, 1)
    # Annualise: assume ~2-second tick → 365 * 24 * 1800 obs/year
    return math.sqrt(var) * math.sqrt(365 * 24 * 1800)


def simulate_tick(
    price: float,
    position: SimPosition,
    cfg: BacktestConfig,
    sigma: float,
    T: float = 1 / 365,
) -> None:
    """Simulate one price tick: compute AS quotes and probabilistically fill levels."""
    gamma = cfg.gamma
    inventory = position.xmr

    # AS reservation price
    reservation = price - inventory * gamma * (sigma**2) * T
    half_spread = max(
        (gamma * sigma**2 * T / 2 + (1 / gamma) * math.log(1 + gamma)),
        cfg.spread_min_bps / 10000.0,
    )
    bid = reservation * (1 - half_spread)
    ask = reservation * (1 + half_spread)

    # Simulate fills probabilistically for each level
    for i, size_usdc in enumerate(cfg.level_sizes):
        extra = (cfg.spread_min_bps / 10000.0) * i
        bid_i = bid * (1 - extra)
        ask_i = ask * (1 + extra)
        size_xmr = size_usdc / max(bid_i, 0.01)

        # Buy fill: only if we haven't hit max long
        if (
            random.random() < cfg.fill_probability
            and abs(position.xmr) < cfg.max_position_xmr
        ):
            fee = size_usdc * cfg.maker_fee_bps / 10000.0
            new_pos = position.xmr + size_xmr
            position.avg_entry = (
                position.avg_entry * position.xmr + bid_i * size_xmr
            ) / max(new_pos, 0.0001)
            position.xmr = new_pos
            position.total_fees += fee
            position.fill_count += 1

        # Sell fill: only if we have long inventory to close
        if random.random() < cfg.fill_probability and position.xmr > 0:
            fee = size_usdc * cfg.maker_fee_bps / 10000.0
            filled = min(size_xmr, position.xmr)
            pnl = (ask_i - position.avg_entry) * filled
            position.realized_pnl += pnl + fee
            position.xmr -= filled
            position.total_fees += fee
            position.fill_count += 1


def run_backtest(
    prices: list[tuple[float, float]], cfg: BacktestConfig
) -> SimPosition:
    """Run the full simulation over all price ticks."""
    pos = SimPosition(usdc=1000.0)
    for i, (_, price) in enumerate(prices):
        sigma = compute_vol(prices[: i + 1])
        simulate_tick(price, pos, cfg, sigma)
    return pos


def print_results(pos: SimPosition, cfg: BacktestConfig, n_days: int) -> None:
    total_pnl = pos.realized_pnl
    print("=" * 50)
    print("BACKTEST RESULTS — Avellaneda-Stoikov MM")
    print("=" * 50)
    print(f"Days simulated:   {n_days}")
    print(f"Total fills:      {pos.fill_count}")
    print(f"Realized PnL:     ${total_pnl:.2f}")
    print(f"Fee rebates:      ${pos.total_fees:.2f}")
    print(f"Net PnL:          ${total_pnl + pos.total_fees:.2f}")
    print(f"Final XMR pos:    {pos.xmr:.4f}")
    if n_days > 0:
        print(f"Avg/day PnL:      ${(total_pnl + pos.total_fees) / n_days:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest AS market maker on historical prices"
    )
    parser.add_argument(
        "--csv", required=True, help="CSV file with timestamp,close columns"
    )
    parser.add_argument("--gamma", type=float, default=0.04, help="Risk aversion gamma")
    parser.add_argument(
        "--days", type=int, default=0, help="Override days count for output"
    )
    args = parser.parse_args()

    if not Path(args.csv).exists():
        print(f"Error: {args.csv} not found", file=sys.stderr)
        sys.exit(1)

    prices = load_prices(args.csv)
    if not prices:
        print("No price data loaded", file=sys.stderr)
        sys.exit(1)

    cfg = BacktestConfig(gamma=args.gamma)
    pos = run_backtest(prices, cfg)

    n_days = args.days or max(1, int((prices[-1][0] - prices[0][0]) / 86400))
    print_results(pos, cfg, n_days)


if __name__ == "__main__":
    main()
