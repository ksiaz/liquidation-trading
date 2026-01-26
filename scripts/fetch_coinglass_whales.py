#!/usr/bin/env python3
"""Try to fetch whale addresses from CoinGlass."""
import asyncio
import sys
import aiohttp

async def try_coinglass_endpoints(session):
    """Try various CoinGlass API endpoints."""

    endpoints = [
        "https://open-api.coinglass.com/public/v2/indicator/top_long_short_account_ratio",
        "https://open-api.coinglass.com/public/v2/liquidation/v2/history",
        "https://open-api.coinglass.com/public/v2/hyperliquid/whale",
        "https://fapi.coinglass.com/api/hyperliquid/whale/positions",
        "https://fapi.coinglass.com/api/hyperliquid/address/list",
    ]

    for url in endpoints:
        try:
            async with session.get(
                url,
                headers={
                    "accept": "application/json",
                    "User-Agent": "Mozilla/5.0"
                },
                params={"exchange": "Hyperliquid", "symbol": "BTC"}
            ) as response:
                print(f"{url}")
                print(f"  Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"  Data keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
                    if isinstance(data, dict) and "data" in data:
                        sample = data["data"][:2] if isinstance(data["data"], list) else data["data"]
                        print(f"  Sample: {sample}")
                print()
        except Exception as e:
            print(f"{url}")
            print(f"  Error: {e}")
            print()

async def main():
    print("Attempting to fetch whale data from CoinGlass...\n")

    async with aiohttp.ClientSession() as session:
        await try_coinglass_endpoints(session)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
