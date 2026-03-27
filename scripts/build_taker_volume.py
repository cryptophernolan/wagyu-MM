"""Build taker volume on testnet to unlock maker request quota.

Usage:
    python scripts/build_taker_volume.py [--rounds N] [--size HYPE_PER_ROUND]

Each round does: buy SIZE HYPE (taker) then sell SIZE HYPE (taker).
Each $1 of volume adds 1 to nRequestsCap.
"""
from __future__ import annotations

import argparse
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any

import requests as _requests
from dotenv import load_dotenv
import os, sys

load_dotenv()

API_URL = "https://api.hyperliquid-testnet.xyz"
ASSET = "@1035"
BASE_COIN = "HYPE"
PRICE_TICK = Decimal("0.001")
SIZE_STEP = Decimal("0.01")
SLIPPAGE_PCT = Decimal("0.02")  # 2% slippage to ensure taker fill


def round_price(p: Decimal, is_buy: bool) -> float:
    """Round price to tick size, adding slippage for taker fill."""
    if is_buy:
        rounded = (p * (1 + SLIPPAGE_PCT) / PRICE_TICK).quantize(Decimal("1"), rounding=ROUND_DOWN) * PRICE_TICK
    else:
        rounded = (p * (1 - SLIPPAGE_PCT) / PRICE_TICK).quantize(Decimal("1"), rounding=ROUND_DOWN) * PRICE_TICK
    return float(rounded)


def get_mid_price() -> Decimal:
    resp = _requests.post(f"{API_URL}/info", json={"type": "allMids"}, timeout=10)
    mids = resp.json()
    price_str = mids.get(ASSET, "0")
    return Decimal(str(price_str))


def get_rate_limit(wallet: str) -> dict[str, Any]:
    resp = _requests.post(f"{API_URL}/info", json={"type": "userRateLimit", "user": wallet}, timeout=10)
    return resp.json()  # type: ignore[no-any-return]


def get_balances(wallet: str) -> tuple[Decimal, Decimal]:
    resp = _requests.post(f"{API_URL}/info", json={"type": "spotClearinghouseState", "user": wallet}, timeout=10)
    balances = {b["coin"]: Decimal(str(b["total"])) for b in resp.json().get("balances", [])}
    return balances.get("USDC", Decimal("0")), balances.get(BASE_COIN, Decimal("0"))


def place_order(exchange: Any, asset: str, is_buy: bool, size: float, price: float) -> Any:
    """Place a taker (IOC) order."""
    order_spec = {
        "coin": asset,
        "is_buy": is_buy,
        "sz": size,
        "limit_px": price,
        "order_type": {"limit": {"tif": "Ioc"}},  # IOC = taker, cancel remainder
        "reduce_only": False,
    }
    return exchange.order(order_spec["coin"], order_spec["is_buy"], order_spec["sz"],
                          order_spec["limit_px"], order_spec["order_type"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build taker volume on testnet")
    parser.add_argument("--rounds", type=int, default=2, help="Number of buy+sell round trips")
    parser.add_argument("--size", type=float, default=9.0, help="HYPE per round trip")
    args = parser.parse_args()

    private_key = os.getenv("HL_PRIVATE_KEY", "")
    wallet = os.getenv("HL_WALLET_ADDRESS", "")
    if not private_key or not wallet:
        print("ERROR: HL_PRIVATE_KEY and HL_WALLET_ADDRESS must be set in .env")
        sys.exit(1)

    # Initialize SDK
    try:
        import eth_account
        from hyperliquid.exchange import Exchange  # type: ignore[import-untyped]

        account = eth_account.Account.from_key(private_key)

        # Pre-filter spot_meta
        raw_spot: dict[str, Any] = _requests.post(
            f"{API_URL}/info", json={"type": "spotMeta"}, timeout=10
        ).json()
        num_tokens = len(raw_spot.get("tokens", []))
        raw_spot["universe"] = [
            u for u in raw_spot.get("universe", [])
            if all(t < num_tokens for t in u.get("tokens", []))
        ]
        exchange = Exchange(account, API_URL, account_address=wallet, spot_meta=raw_spot)
    except ImportError:
        print("ERROR: hyperliquid-python-sdk not installed")
        sys.exit(1)

    rl = get_rate_limit(wallet)
    print(f"\nInitial state:")
    print(f"  cumVlm:        ${float(rl['cumVlm']):.2f}")
    print(f"  nRequestsUsed: {rl['nRequestsUsed']}")
    print(f"  nRequestsCap:  {rl['nRequestsCap']}")
    deficit = rl['nRequestsUsed'] - rl['nRequestsCap']
    print(f"  Deficit:       {deficit} requests = ${deficit:.0f} volume needed")

    usdc, hype = get_balances(wallet)
    mid = get_mid_price()
    print(f"  USDC: ${usdc:.2f}, {BASE_COIN}: {hype:.4f}, Price: ${mid:.4f}")
    print(f"  Total: ${float(usdc + hype * mid):.2f}")

    size = Decimal(str(args.size))
    required_usdc = size * mid * Decimal("1.03")  # 3% buffer for slippage+fees
    if usdc < required_usdc:
        size_from_usdc = (usdc / mid / Decimal("1.03")).quantize(SIZE_STEP, rounding=ROUND_DOWN)
        print(f"\nWARN: Not enough USDC for {args.size} HYPE. Reducing to {size_from_usdc} HYPE")
        size = size_from_usdc

    print(f"\nPlan: {args.rounds} round trips × {size} HYPE = ~${float(size * mid * 2 * args.rounds):.0f} volume")
    est_volume = float(size * mid * 2 * args.rounds)
    est_fees = est_volume * 0.00035  # 3.5bps taker each side
    print(f"  Estimated taker fees: ~${est_fees:.2f}")
    print(f"  New cumVlm after: ~${float(rl['cumVlm']) + est_volume:.0f}")
    print(f"  New nRequestsCap: ~{int(float(rl['nRequestsCap'])) + int(est_volume)}")

    proceed = input("\nProceed? [y/N]: ").strip().lower()
    if proceed != "y":
        print("Aborted.")
        return

    total_volume = Decimal("0")
    for round_num in range(1, args.rounds + 1):
        print(f"\n--- Round {round_num}/{args.rounds} ---")
        mid = get_mid_price()
        usdc, hype = get_balances(wallet)
        print(f"  Mid price: ${mid:.4f}  USDC: ${usdc:.2f}  {BASE_COIN}: {hype:.4f}")

        # Adjust size if not enough USDC
        actual_size = size
        if usdc < actual_size * mid * Decimal("1.02"):
            actual_size = (usdc / mid / Decimal("1.02")).quantize(SIZE_STEP, rounding=ROUND_DOWN)
            print(f"  Adjusted size to {actual_size} HYPE due to USDC balance")

        if actual_size < Decimal("0.11"):  # min notional $10
            print(f"  Size too small ({actual_size}), skipping buy")
        else:
            # BUY (taker — IOC above market)
            buy_price = round_price(mid, is_buy=True)
            print(f"  BUY  {actual_size} HYPE @ ${buy_price:.3f} (taker IOC)...")
            try:
                result = exchange.order(ASSET, True, float(actual_size), buy_price,
                                        {"limit": {"tif": "Ioc"}})
                print(f"  BUY result: {str(result)[:200]}")
                total_volume += actual_size * mid
            except Exception as e:
                print(f"  BUY ERROR: {e}")

        time.sleep(2)  # brief pause
        mid = get_mid_price()
        usdc2, hype2 = get_balances(wallet)
        print(f"  After buy: USDC: ${usdc2:.2f}  {BASE_COIN}: {hype2:.4f}")

        # SELL (taker — IOC below market)
        sell_size = (hype2 - Decimal("0.05")).quantize(SIZE_STEP, rounding=ROUND_DOWN)
        if sell_size < Decimal("0.11"):
            print(f"  Not enough {BASE_COIN} to sell ({hype2:.4f}), skipping")
        else:
            sell_price = round_price(mid, is_buy=False)
            print(f"  SELL {sell_size} HYPE @ ${sell_price:.3f} (taker IOC)...")
            try:
                result = exchange.order(ASSET, False, float(sell_size), sell_price,
                                        {"limit": {"tif": "Ioc"}})
                print(f"  SELL result: {str(result)[:200]}")
                total_volume += sell_size * mid
            except Exception as e:
                print(f"  SELL ERROR: {e}")

        time.sleep(2)

    # Final state
    rl2 = get_rate_limit(wallet)
    usdc_f, hype_f = get_balances(wallet)
    mid_f = get_mid_price()
    print(f"\n=== Final state ===")
    print(f"  cumVlm:        ${float(rl2['cumVlm']):.2f}  (+${float(rl2['cumVlm']) - float(rl['cumVlm']):.2f})")
    print(f"  nRequestsUsed: {rl2['nRequestsUsed']}")
    print(f"  nRequestsCap:  {rl2['nRequestsCap']}")
    surplus = rl2['nRequestsCap'] - rl2['nRequestsUsed']
    print(f"  Surplus:       {surplus} ({'UNLOCKED ✓' if surplus > 0 else 'still locked'})")
    print(f"  USDC: ${usdc_f:.2f}, {BASE_COIN}: {hype_f:.4f}")
    print(f"  Total: ${float(usdc_f + hype_f * mid_f):.2f}")


if __name__ == "__main__":
    main()
