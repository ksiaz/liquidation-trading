#!/usr/bin/env python3
"""
Run the Hyperliquid Node Adapter Client

This connects to the adapter service running in WSL and
streams events to the observation system.

Make sure the adapter service is running in WSL first:
    wsl python3 /mnt/d/liquidation-trading/scripts/run_adapter_service.py

Then run this on Windows:
    python scripts/run_adapter_client.py
"""

import sys
import time
import asyncio
import argparse
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from runtime.hyperliquid.adapter_client.client import AdapterClient

# Add protos to path
protos_path = project_root / 'runtime/hyperliquid/adapter_service/protos'
sys.path.insert(0, str(protos_path))

import adapter_pb2


# Counters for display
price_count = 0
action_count = 0
liq_count = 0
last_prices = {}


def on_price(event: adapter_pb2.MarketPriceEvent):
    """Handle price event."""
    global price_count, last_prices
    price_count += 1
    last_prices[event.asset] = event.oracle_price


def on_action(event: adapter_pb2.ActionEvent):
    """Handle action event."""
    global action_count, liq_count
    action_count += 1

    if event.is_liquidation:
        liq_count += 1
        side = 'LONG' if event.side == adapter_pb2.SIDE_SELL else 'SHORT'
        value = event.size * event.price
        print(f"  LIQ: {event.asset} {side} ${value:,.0f} @ ${event.price:,.2f}")


async def main():
    global price_count, action_count, liq_count, last_prices

    parser = argparse.ArgumentParser(description='Hyperliquid Node Adapter Client')
    parser.add_argument('--host', default='localhost', help='Adapter host')
    parser.add_argument('--port', type=int, default=50051, help='Adapter port')
    parser.add_argument(
        '--assets',
        default='',
        help='Comma-separated list of assets to filter (empty = all)'
    )

    args = parser.parse_args()

    assets = [a.strip() for a in args.assets.split(',') if a.strip()] or None

    print("=" * 60)
    print("HYPERLIQUID NODE ADAPTER CLIENT")
    print("=" * 60)
    print(f"Connecting to: {args.host}:{args.port}")
    print(f"Asset filter: {assets if assets else 'ALL'}")
    print()

    # Create client
    client = AdapterClient(host=args.host, port=args.port)

    # Set up callbacks
    client.on_price = on_price
    client.on_action = on_action

    # Connect
    connected = await client.connect()
    if not connected:
        print("Failed to connect. Is the adapter service running in WSL?")
        print()
        print("Start the adapter in WSL with:")
        print("  wsl python3 /mnt/d/liquidation-trading/scripts/run_adapter_service.py")
        return

    # Start streaming
    await client.start_streaming(
        assets=assets,
        stream_prices=True,
        stream_actions=True,
    )

    print()
    print("Streaming events (Ctrl+C to stop)...")
    print("-" * 60)

    # Print stats periodically
    start_time = time.time()
    last_stats_time = start_time

    try:
        while True:
            await asyncio.sleep(1.0)

            now = time.time()
            if now - last_stats_time >= 10.0:  # Every 10 seconds
                last_stats_time = now
                elapsed = now - start_time

                print()
                print(f"--- Stats ({elapsed:.0f}s) ---")
                print(f"  Prices: {price_count} ({price_count/elapsed:.1f}/s)")
                print(f"  Actions: {action_count}")
                print(f"  Liquidations: {liq_count}")

                # Sample prices
                sample = ['BTC', 'ETH', 'SOL']
                price_str = ', '.join(
                    f"{a}=${last_prices.get(a, 0):,.0f}"
                    for a in sample if a in last_prices
                )
                if price_str:
                    print(f"  Latest: {price_str}")
                print()

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await client.disconnect()

    print()
    print("Final stats:")
    print(f"  Total events: {price_count + action_count}")
    print(f"  Price events: {price_count}")
    print(f"  Action events: {action_count}")
    print(f"  Liquidations: {liq_count}")


if __name__ == '__main__':
    asyncio.run(main())
