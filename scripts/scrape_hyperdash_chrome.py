#!/usr/bin/env python3
"""Scrape whale addresses from Hyperdash using Chrome with request interception."""
import re
import time
import json
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def scrape_hyperdash():
    """Scrape Hyperdash with network request capture."""

    print("=" * 80)
    print("SCRAPING HYPERDASH - CAPTURING API RESPONSES")
    print("=" * 80)
    print()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    print("Starting Chrome...")
    driver = webdriver.Chrome(options=options)

    all_addresses = set()

    try:
        print("Loading Hyperdash...")
        driver.get("https://hyperdash.info/top-traders")

        # Wait and scroll
        time.sleep(8)
        for _ in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        time.sleep(3)

        # Get network logs
        print("\nExtracting API responses...")
        logs = driver.get_log('performance')

        graphql_responses = []
        hyperliquid_responses = []

        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']
                method = log.get('method', '')

                # Capture response bodies
                if method == 'Network.responseReceived':
                    url = log['params']['response']['url']
                    request_id = log['params']['requestId']

                    if 'graphql' in url or 'hyperliquid' in url:
                        try:
                            # Get response body
                            body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                            if body and 'body' in body:
                                content = body['body']
                                # Look for addresses
                                addresses = re.findall(r'0x[a-fA-F0-9]{40}', content)
                                if addresses:
                                    print(f"  Found {len(addresses)} addresses in {url[:50]}...")
                                    all_addresses.update(addresses)

                                # Save for debugging
                                if 'graphql' in url:
                                    graphql_responses.append(content)
                                else:
                                    hyperliquid_responses.append(content)
                        except:
                            pass

            except Exception as e:
                pass

        # Also check page source
        html = driver.page_source
        page_addresses = re.findall(r'0x[a-fA-F0-9]{40}', html)
        if page_addresses:
            print(f"  Found {len(page_addresses)} addresses in page HTML")
            all_addresses.update(page_addresses)

        # Save GraphQL responses for analysis
        if graphql_responses:
            with open("hyperdash_graphql_responses.json", "w") as f:
                for resp in graphql_responses:
                    f.write(resp + "\n---\n")
            print(f"\nSaved {len(graphql_responses)} GraphQL responses")

        if hyperliquid_responses:
            with open("hyperdash_hl_responses.json", "w") as f:
                for resp in hyperliquid_responses:
                    f.write(resp + "\n---\n")
            print(f"Saved {len(hyperliquid_responses)} Hyperliquid API responses")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        driver.quit()

    # Results
    if all_addresses:
        unique = sorted(list(all_addresses))
        print(f"\n{'=' * 80}")
        print(f"FOUND {len(unique)} UNIQUE ADDRESSES")
        print("=" * 80)

        for i, addr in enumerate(unique[:30], 1):
            print(f"{i:2}. {addr}")

        # Save to file
        with open("hyperdash_addresses.txt", "w") as f:
            for addr in unique:
                f.write(f"{addr}\n")
        print(f"\nSaved to hyperdash_addresses.txt")

        # Generate code
        print("\n" + "=" * 80)
        print("CODE FOR whale_wallets.py:")
        print("=" * 80)
        for i, addr in enumerate(unique[:20], 1):
            print(f'''    WalletInfo(
        address="{addr.lower()}",
        label="Hyperdash-{i:03d}",
        wallet_type="WHALE",
        notes="From Hyperdash top traders"
    ),''')
    else:
        print("\nNo addresses found.")
        print("\nAlternative: Visit https://hyperdash.info/top-traders manually")
        print("and paste addresses here when prompted.")


if __name__ == "__main__":
    scrape_hyperdash()
