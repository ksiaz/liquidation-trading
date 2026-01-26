#!/usr/bin/env python3
"""Scrape whale addresses from Hyperdash."""
import asyncio
import sys
import re
import json
import aiohttp

async def find_api_endpoints():
    """Search for API endpoints in page source."""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
    }

    async with aiohttp.ClientSession() as session:
        # Fetch main page and look for API URLs
        async with session.get("https://hyperdash.info/top-traders", headers=headers) as response:
            if response.status == 200:
                text = await response.text()

                # Look for API endpoints in JS
                api_patterns = [
                    r'https?://[^"\s]+api[^"\s]*',
                    r'"/api/[^"]+',
                    r'fetch\(["\']([^"\']+)',
                    r'axios\.[a-z]+\(["\']([^"\']+)',
                ]

                print("Looking for API endpoints in page source...")
                for pattern in api_patterns:
                    matches = re.findall(pattern, text)
                    if matches:
                        for m in matches[:5]:
                            print(f"  Found: {m}")

                # Look for _next/data which Next.js apps use
                next_data = re.findall(r'/_next/data/[^"]+\.json', text)
                if next_data:
                    print(f"\nNext.js data endpoints found:")
                    for url in set(next_data):
                        print(f"  {url}")

                # Look for __NEXT_DATA__ which contains initial props
                next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', text)
                if next_data_match:
                    try:
                        data = json.loads(next_data_match.group(1))
                        print("\n__NEXT_DATA__ found!")

                        # Navigate to find trader data
                        props = data.get("props", {}).get("pageProps", {})
                        print(f"pageProps keys: {list(props.keys())}")

                        # Look for addresses in the data
                        data_str = json.dumps(data)
                        addresses = re.findall(r'0x[a-fA-F0-9]{40}', data_str)
                        if addresses:
                            unique = list(set(addresses))
                            print(f"\nFound {len(unique)} addresses in __NEXT_DATA__:")
                            for addr in unique[:30]:
                                print(f"  {addr}")
                    except json.JSONDecodeError:
                        print("Could not parse __NEXT_DATA__")

async def try_hyperdash_api():
    """Try common API patterns for Hyperdash."""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://hyperdash.info",
        "Referer": "https://hyperdash.info/top-traders",
    }

    # Common API patterns for Next.js apps
    api_urls = [
        "https://hyperdash.info/api/traders",
        "https://hyperdash.info/api/top-traders",
        "https://hyperdash.info/api/leaderboard",
        "https://hyperdash.info/api/alpha-traders",
        "https://hyperdash.info/api/whales",
        "https://api.hyperdash.info/traders",
        "https://api.hyperdash.info/v1/traders",
        "https://api.hyperdash.info/leaderboard",
    ]

    print("\n" + "=" * 80)
    print("Trying API endpoints...")
    print("=" * 80)

    async with aiohttp.ClientSession() as session:
        for url in api_urls:
            try:
                async with session.get(url, headers=headers, timeout=5) as response:
                    status = response.status
                    if status == 200:
                        text = await response.text()
                        addresses = re.findall(r'0x[a-fA-F0-9]{40}', text)
                        if addresses:
                            print(f"\n{url}: {status} - Found {len(set(addresses))} addresses!")
                            for addr in list(set(addresses))[:10]:
                                print(f"  {addr}")
                        else:
                            print(f"{url}: {status} - No addresses")
                    else:
                        print(f"{url}: {status}")
            except Exception as e:
                print(f"{url}: Error - {type(e).__name__}")

async def main():
    print("=" * 80)
    print("SCRAPING HYPERDASH FOR WHALE ADDRESSES")
    print("=" * 80)
    print()

    await find_api_endpoints()
    await try_hyperdash_api()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
