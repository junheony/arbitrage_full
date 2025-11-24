#!/usr/bin/env python3
"""Check MON prices across all exchanges"""
import asyncio
from app.connectors.upbit_spot import UpbitSpotConnector
from app.connectors.bithumb_spot import BithumbSpotConnector
from app.connectors.binance_perp import BinancePerpConnector
from app.connectors.bybit_perp import BybitPerpConnector
from app.connectors.okx_spot import OkxSpotConnector
from app.connectors.fx_rates import KRWUSDForexConnector


async def check_mon_prices():
    print("Checking MON prices across exchanges...")
    print("=" * 80)

    # Initialize connectors
    upbit = UpbitSpotConnector(["MON/USDT"])
    bithumb = BithumbSpotConnector(["MON/USDT"])
    okx = OkxSpotConnector(["MON/USDT"])
    binance_perp = BinancePerpConnector(["MON/USDT"])
    bybit_perp = BybitPerpConnector(["MON/USDT"])
    fx = KRWUSDForexConnector()

    # Fetch quotes
    print("\nFetching quotes...\n")
    upbit_quotes = await upbit.fetch_quotes()
    bithumb_quotes = await bithumb.fetch_quotes()
    okx_quotes = await okx.fetch_quotes()
    binance_perp_quotes = await binance_perp.fetch_quotes()
    bybit_perp_quotes = await bybit_perp.fetch_quotes()
    fx_quotes = await fx.fetch_quotes()

    # Get forex rate
    if fx_quotes:
        fx_rate = fx_quotes[0].bid
        print(f"USD/KRW Rate: {fx_rate:.2f}")
        print()
    else:
        fx_rate = 1400.0
        print("Using fixed USD/KRW rate: 1400.00\n")

    # Display quotes
    print("MON/USDT Quotes:")
    print("-" * 80)

    for quotes, name in [
        (upbit_quotes, "Upbit (KRW)"),
        (bithumb_quotes, "Bithumb (KRW)"),
        (okx_quotes, "OKX (USDT)"),
        (binance_perp_quotes, "Binance Perp"),
        (bybit_perp_quotes, "Bybit Perp"),
    ]:
        for quote in quotes:
            if "MON" in quote.symbol:
                if quote.quote_currency == "KRW":
                    # Convert to USD
                    bid_usd = quote.bid / fx_rate
                    ask_usd = quote.ask / fx_rate
                    print(f"{name:20s} | Bid: ${bid_usd:8.4f} Ask: ${ask_usd:8.4f} (KRW: {quote.bid:,.0f}/{quote.ask:,.0f})")
                else:
                    print(f"{name:20s} | Bid: ${quote.bid:8.4f} Ask: ${quote.ask:8.4f}")

    # Calculate spreads
    print("\n" + "=" * 80)
    print("Kimchi Premium Check (Korean vs International):")
    print("-" * 80)

    # Get Korean prices (in USD)
    upbit_mon = [q for q in upbit_quotes if "MON" in q.symbol]
    bithumb_mon = [q for q in bithumb_quotes if "MON" in q.symbol]

    # Get International prices
    okx_mon = [q for q in okx_quotes if "MON" in q.symbol]
    binance_mon = [q for q in binance_perp_quotes if "MON" in q.symbol]
    bybit_mon = [q for q in bybit_perp_quotes if "MON" in q.symbol]

    if upbit_mon and okx_mon:
        upbit_mid = (upbit_mon[0].bid / fx_rate + upbit_mon[0].ask / fx_rate) / 2
        okx_mid = (okx_mon[0].bid + okx_mon[0].ask) / 2
        spread_pct = ((upbit_mid - okx_mid) / okx_mid) * 100
        spread_bps = spread_pct * 100
        print(f"Upbit vs OKX:    {spread_pct:+.3f}% ({spread_bps:+.1f} bps) | Upbit: ${upbit_mid:.4f}, OKX: ${okx_mid:.4f}")

    if bithumb_mon and okx_mon:
        bithumb_mid = (bithumb_mon[0].bid / fx_rate + bithumb_mon[0].ask / fx_rate) / 2
        okx_mid = (okx_mon[0].bid + okx_mon[0].ask) / 2
        spread_pct = ((bithumb_mid - okx_mid) / okx_mid) * 100
        spread_bps = spread_pct * 100
        print(f"Bithumb vs OKX:  {spread_pct:+.3f}% ({spread_bps:+.1f} bps) | Bithumb: ${bithumb_mid:.4f}, OKX: ${okx_mid:.4f}")

    if upbit_mon and binance_mon:
        upbit_mid = (upbit_mon[0].bid / fx_rate + upbit_mon[0].ask / fx_rate) / 2
        binance_mid = (binance_mon[0].bid + binance_mon[0].ask) / 2
        spread_pct = ((upbit_mid - binance_mid) / binance_mid) * 100
        spread_bps = spread_pct * 100
        print(f"Upbit vs Binance:{spread_pct:+.3f}% ({spread_bps:+.1f} bps) | Upbit: ${upbit_mid:.4f}, Binance: ${binance_mid:.4f}")

    if upbit_mon and bybit_mon:
        upbit_mid = (upbit_mon[0].bid / fx_rate + upbit_mon[0].ask / fx_rate) / 2
        bybit_mid = (bybit_mon[0].bid + bybit_mon[0].ask) / 2
        spread_pct = ((upbit_mid - bybit_mid) / bybit_mid) * 100
        spread_bps = spread_pct * 100
        print(f"Upbit vs Bybit:  {spread_pct:+.3f}% ({spread_bps:+.1f} bps) | Upbit: ${upbit_mid:.4f}, Bybit: ${bybit_mid:.4f}")

    print("\n" + "=" * 80)
    print("Conclusion:")
    print("-" * 80)
    print("Kimchi premium strategy requires spread >= 50 bps (0.5%) for conservative strategy")
    print("Aggressive strategy requires spread >= 20 bps (0.2%)")
    print("=" * 80)

    # Close connectors
    await upbit.close()
    await bithumb.close()
    await okx.close()
    await binance_perp.close()
    await bybit_perp.close()
    await fx.close()


if __name__ == "__main__":
    asyncio.run(check_mon_prices())
