#!/usr/bin/env python3
"""Fetch supported symbols from all exchanges."""
import asyncio
import httpx

async def fetch_binance():
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.binance.com/api/v3/exchangeInfo')
        data = resp.json()
        symbols = set()
        for s in data['symbols']:
            if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT':
                symbols.add(s['baseAsset'])
        return symbols

async def fetch_okx():
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://www.okx.com/api/v5/public/instruments?instType=SPOT')
        data = resp.json()
        symbols = set()
        for inst in data.get('data', []):
            if inst['quoteCcy'] == 'USDT' and inst['state'] == 'live':
                symbols.add(inst['baseCcy'])
        return symbols

async def fetch_upbit():
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.upbit.com/v1/market/all')
        data = resp.json()
        symbols = set()
        for market in data:
            if market['market'].startswith('KRW-'):
                symbols.add(market['market'].replace('KRW-', ''))
        return symbols

async def fetch_bithumb():
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.bithumb.com/public/ticker/ALL_KRW')
        data = resp.json()
        symbols = set()
        for k in data.get('data', {}).keys():
            if k != 'date':
                symbols.add(k)
        return symbols

async def main():
    binance, okx, upbit, bithumb = await asyncio.gather(
        fetch_binance(), fetch_okx(), fetch_upbit(), fetch_bithumb(),
        return_exceptions=True
    )

    print(f"Binance: {len(binance) if not isinstance(binance, Exception) else 'ERROR'}")
    print(f"OKX: {len(okx) if not isinstance(okx, Exception) else 'ERROR'}")
    print(f"Upbit: {len(upbit) if not isinstance(upbit, Exception) else 'ERROR'}")
    print(f"Bithumb: {len(bithumb) if not isinstance(bithumb, Exception) else 'ERROR'}")

    if isinstance(bithumb, Exception):
        print(f"Bithumb error: {bithumb}")
        bithumb = set()

    # Find intersection: coins supported by ALL exchanges
    global_exchanges = binance & okx
    korean_exchanges = upbit & bithumb
    common = global_exchanges & korean_exchanges

    # Filter out stablecoins and wrapped tokens
    excluded = {
        'USDT', 'USDC', 'DAI', 'USDS', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'USDE', 'PYUSD', 'FDUSD',
        'WBTC', 'WETH', 'WSTETH', 'STETH', 'RETH', 'CBETH', 'WBNB', 'WBETH', 'BETH',
    }

    filtered = sorted([s for s in common if s not in excluded])

    print(f"\nCommon symbols (global & korean, excluding stablecoins/wrapped): {len(filtered)}")
    print(','.join(filtered))

    # Get top 100 market cap coins
    top_100 = [
        'BTC', 'ETH', 'XRP', 'BNB', 'SOL', 'DOGE', 'ADA', 'TRX', 'LINK', 'AVAX',
        'BCH', 'DOT', 'SHIB', 'LTC', 'UNI', 'NEAR', 'APT', 'ICP', 'HBAR', 'FIL',
        'ARB', 'VET', 'ATOM', 'ETC', 'XLM', 'ALGO', 'AAVE', 'ENA', 'PEPE', 'TON',
        'SUI', 'XMR', 'ONDO', 'WLD', 'RENDER', 'POL', 'TAO', 'BONK', 'FLOKI', 'GALA',
        'MATIC', 'OP', 'DYDX', 'STRK', 'EIGEN', 'SAND', 'MANA', 'AXS', 'RUNE', 'BLUR',
        'FTM', 'ENS', 'CHZ', 'PENDLE', 'SEI', 'BEAM', 'ZEC', 'JASMY', 'KAS', 'FLOW',
        'MEME', 'THETA', 'FET', 'SUPER', 'CORE', 'DOGS', 'INJ', 'ROSE', 'EGLD', 'GRT',
        'ASTR', 'PYTH', 'JUP', 'WIF', 'ZETA', 'BOME', 'ZK', 'ZRO', 'NOT', 'IO',
        'CFX', 'CKB', 'HIVE', 'STEEM', 'MASK', 'TIA', 'ARKM', 'ORDI', 'WAVES', 'SATS',
        'CELO', 'CAKE', 'KAVA', 'GMT', 'SAGA', 'PORTAL', 'MEW', 'W', 'MYRO', 'BIGTIME'
    ]

    # Intersection with top 100
    tradeable_top100 = sorted([s for s in top_100 if s in filtered])

    print(f"\nTop 100 market cap coins tradeable on all 4 exchanges: {len(tradeable_top100)}")
    print(','.join(tradeable_top100))

if __name__ == '__main__':
    asyncio.run(main())
