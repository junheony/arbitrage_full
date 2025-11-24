#!/usr/bin/env python3
"""Check Upbit MON response directly"""
import asyncio
import httpx


async def check_upbit_mon():
    print("Checking Upbit MON API response...")
    print("=" * 80)

    client = httpx.AsyncClient(timeout=5.0)

    try:
        # Get MON orderbook from Upbit
        response = await client.get(
            "https://api.upbit.com/v1/orderbook",
            params={"markets": "KRW-MON"}
        )
        print(f"Status: {response.status_code}")
        print(f"Response:\n{response.text}\n")

        if response.status_code == 200:
            data = response.json()
            if data:
                print(f"Number of markets: {len(data)}")
                for market in data:
                    print(f"\nMarket: {market.get('market')}")
                    print(f"Timestamp: {market.get('timestamp')}")
                    if market.get('orderbook_units'):
                        print(f"Orderbook units: {len(market['orderbook_units'])}")
                        first_level = market['orderbook_units'][0]
                        print(f"Bid: {first_level.get('bid_price')}")
                        print(f"Ask: {first_level.get('ask_price')}")
                    else:
                        print("No orderbook_units in response")
            else:
                print("Empty response array")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.aclose()

    print("\n" + "=" * 80)
    print("Now checking Bithumb MON...")
    print("=" * 80)

    client = httpx.AsyncClient(timeout=5.0)
    try:
        response = await client.get("https://api.bithumb.com/public/orderbook/MON_KRW")
        print(f"Status: {response.status_code}")
        print(f"Response:\n{response.text}\n")

        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            if data.get('data'):
                print(f"Bids: {len(data['data'].get('bids', []))}")
                print(f"Asks: {len(data['data'].get('asks', []))}")
                if data['data'].get('bids'):
                    print(f"Best bid: {data['data']['bids'][0]}")
                if data['data'].get('asks'):
                    print(f"Best ask: {data['data']['asks'][0]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(check_upbit_mon())
