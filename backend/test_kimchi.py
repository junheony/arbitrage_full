#!/usr/bin/env python3
"""Test script to debug kimchi premium generation"""
import asyncio
import sys
from collections import defaultdict

from app.connectors.binance_spot import BinanceSpotConnector
from app.connectors.upbit_spot import UpbitSpotConnector
from app.connectors.fx_rates import KRWUSDForexConnector
from app.core.config import get_settings


async def main():
    settings = get_settings()

    print("=" * 60)
    print("KIMCHI PREMIUM DEBUG TEST")
    print("=" * 60)

    # Initialize connectors
    fx_conn = KRWUSDForexConnector()
    binance = BinanceSpotConnector(settings.trading_symbols)
    upbit = UpbitSpotConnector(settings.trading_symbols)

    # Fetch quotes
    print("\n1. Fetching FX rate...")
    fx_quotes = await fx_conn.fetch_quotes()
    if fx_quotes:
        fx_rate = fx_quotes[0].mid_price
        print(f"   USD/KRW rate: {fx_rate:.2f}")
    else:
        print("   ERROR: No FX quotes!")
        return

    print("\n2. Fetching Binance spot quotes...")
    binance_quotes = await binance.fetch_quotes()
    print(f"   Found {len(binance_quotes)} Binance quotes")

    print("\n3. Fetching Upbit spot quotes...")
    upbit_quotes = await upbit.fetch_quotes()
    print(f"   Found {len(upbit_quotes)} Upbit quotes")

    # Organize quotes
    global_quotes = defaultdict(list)
    krw_quotes = defaultdict(list)

    for q in binance_quotes:
        if q.quote_currency in {"USDT", "USD"}:
            global_quotes[q.base_asset].append(q)

    for q in upbit_quotes:
        if q.quote_currency == "KRW":
            krw_quotes[q.base_asset].append(q)

    print(f"\n4. Found {len(global_quotes)} assets on Binance (USD pairs)")
    print(f"   Found {len(krw_quotes)} assets on Upbit (KRW pairs)")

    # Calculate premiums for overlapping assets
    print("\n5. Calculating kimchi premiums:")
    print(f"   Min allocation threshold: {settings.min_kimchi_allocation_pct}%")
    print(f"   Allocation curve: {settings.tether_bot_curve}")

    common_assets = set(global_quotes.keys()) & set(krw_quotes.keys())
    print(f"\n6. Common assets: {len(common_assets)}")

    results = []
    for asset in sorted(common_assets)[:10]:  # Test first 10
        global_quote = global_quotes[asset][0]
        krw_quote = krw_quotes[asset][0]

        global_mid = global_quote.mid_price
        krw_mid_usd = krw_quote.mid_price / fx_rate
        premium_pct = (krw_mid_usd - global_mid) / global_mid * 100

        # Calculate allocation
        allocation_fraction = evaluate_allocation(premium_pct, settings.tether_bot_curve)
        allocation_pct = allocation_fraction * 100

        passed_filter = allocation_pct >= settings.min_kimchi_allocation_pct

        results.append({
            'asset': asset,
            'premium_pct': premium_pct,
            'allocation_pct': allocation_pct,
            'passed': passed_filter,
        })

    print("\n" + "=" * 80)
    print(f"{'Asset':<10} {'Premium %':>12} {'Allocation %':>15} {'Passed Filter':>15}")
    print("=" * 80)
    for r in results:
        status = "✓ YES" if r['passed'] else "✗ NO"
        print(f"{r['asset']:<10} {r['premium_pct']:>12.4f} {r['allocation_pct']:>15.2f} {status:>15}")

    passed_count = sum(1 for r in results if r['passed'])
    print("=" * 80)
    print(f"Total tested: {len(results)}, Passed filter: {passed_count}")

    # Cleanup
    await fx_conn.close()
    await binance.close()
    await upbit.close()


def evaluate_allocation(premium_pct: float, curve: list) -> float:
    """Evaluate allocation based on piecewise linear curve"""
    if not curve:
        return 0.0

    if premium_pct <= curve[0][0]:
        return clamp(curve[0][1])

    for idx in range(1, len(curve)):
        left = curve[idx - 1]
        right = curve[idx]
        if premium_pct <= right[0]:
            span = right[0] - left[0]
            if span == 0:
                return clamp(right[1])
            weight = (premium_pct - left[0]) / span
            value = left[1] + weight * (right[1] - left[1])
            return clamp(value)

    return clamp(curve[-1][1])


def clamp(value: float) -> float:
    """Clamp value between 0 and 1"""
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
