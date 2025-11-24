#!/usr/bin/env python3
"""Debug MON kimchi premium opportunity generation"""
import asyncio
from app.connectors.upbit_spot import UpbitSpotConnector
from app.connectors.bithumb_spot import BithumbSpotConnector
from app.connectors.binance_perp import BinancePerpConnector
from app.connectors.fx_rates import KRWUSDForexConnector
from app.core.config import get_settings

async def main():
    print("=" * 80)
    print("Debugging MON Kimchi Premium Opportunity Generation")
    print("=" * 80)

    # Initialize connectors
    upbit = UpbitSpotConnector(["MON/USDT"])
    binance_perp = BinancePerpConnector(["MON/USDT"])
    fx = KRWUSDForexConnector()

    # Fetch data
    print("\nFetching market data...")
    upbit_quotes = await upbit.fetch_quotes()
    binance_quotes = await binance_perp.fetch_quotes()
    fx_quotes = await fx.fetch_quotes()

    print(f"\nUpbit quotes: {len(upbit_quotes)}")
    for q in upbit_quotes:
        print(f"  {q.exchange} {q.symbol} (venue={q.venue_type}): bid={q.bid}, ask={q.ask}, quote_curr={q.quote_currency}")

    print(f"\nBinance Perp quotes: {len(binance_quotes)}")
    for q in binance_quotes:
        print(f"  {q.exchange} {q.symbol} (venue={q.venue_type}): bid={q.bid}, ask={q.ask}, quote_curr={q.quote_currency}")

    print(f"\nFX quotes: {len(fx_quotes)}")
    for q in fx_quotes:
        print(f"  {q.exchange}: {q.bid}")

    # Check config
    settings = get_settings()
    print(f"\nConfiguration:")
    print(f"  TETHER_BOT_CURVE: {settings.tether_bot_curve}")
    print(f"  MIN_KIMCHI_ALLOCATION_PCT: {settings.min_kimchi_allocation_pct}")
    print(f"  KIMCHI_DEVIATION_THRESHOLD_PCT: {settings.kimchi_deviation_threshold_pct}")

    # Close connectors
    await upbit.close()
    await binance_perp.close()
    await fx.close()

    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
