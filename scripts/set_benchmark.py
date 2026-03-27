#!/usr/bin/env python3
"""CLI script: record initial portfolio snapshot for Bot vs HODL chart."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config import load_config
from bot.exchange.hyperliquid_client import HyperliquidClient
from bot.persistence.database import close_db, create_tables, init_db
from bot.persistence import repository
from bot.utils.logger import setup_logger


async def main() -> None:
    parser = argparse.ArgumentParser(description="Set HODL benchmark for Bot vs HODL chart")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config.env.log_level, config.env.env)

    Path("data").mkdir(exist_ok=True)
    init_db()
    await create_tables()

    client = HyperliquidClient(
        api_url=config.exchange.api_url,
        private_key=config.env.hl_private_key,
        wallet_address=config.env.hl_wallet_address,
        asset=config.exchange.asset,
    )

    try:
        client.initialize()
        user_state = client.get_user_state()
        l2 = client.get_l2_book()
        # Get approximate XMR price from book
        xmr_price = float(l2.bids[0].price) if l2.bids else 0.0
        usdc_balance = float(user_state.usdc_balance)
        xmr_balance = float(user_state.xmr_balance)

        await repository.save_hodl_benchmark(
            {
                "timestamp": datetime.now(timezone.utc),
                "xmr_price": xmr_price,
                "usdc_balance": usdc_balance,
                "xmr_balance": xmr_balance,
            }
        )

        print("Benchmark saved:")
        print(f"  USDC balance: ${usdc_balance:.2f}")
        print(f"  XMR balance:  {xmr_balance:.4f} XMR")
        print(f"  XMR price:    ${xmr_price:.2f}")
        print(f"  Total value:  ${usdc_balance + xmr_balance * xmr_price:.2f}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
