#!/usr/bin/env python3
"""
Test client for the Node Adapter.

Connects to the TCP adapter and prints received events.
"""

import asyncio
import json
import time


async def main():
    host = '127.0.0.1'
    port = 8090

    print(f"Connecting to adapter at {host}:{port}...")

    try:
        reader, writer = await asyncio.open_connection(host, port)
        print("Connected!")

        events = 0
        prices = 0
        liquidations = 0
        start = time.time()

        while True:
            line = await reader.readline()
            if not line:
                print("Connection closed")
                break

            events += 1
            event = json.loads(line.decode())
            event_type = event.get('event_type', '')

            if event_type == 'CONNECTED':
                print(f"Server: {event}")
            elif event_type == 'HL_PRICE':
                prices += 1
                if prices <= 5 or prices % 100 == 0:
                    print(f"PRICE: {event.get('symbol')} = ${event.get('oracle_price'):.2f}")
            elif event_type == 'HL_LIQUIDATION':
                liquidations += 1
                print(f"LIQUIDATION: {event.get('symbol')} {event.get('side')} "
                      f"${event.get('notional'):,.0f}")
            elif event_type == 'HL_ORDER':
                pass  # Skip regular orders for cleaner output

            # Stats every 10 seconds
            elapsed = time.time() - start
            if elapsed > 10 and events % 500 == 0:
                print(f"--- Stats: {events} events, {prices} prices, "
                      f"{liquidations} liquidations, {events/elapsed:.1f}/sec ---")

    except ConnectionRefusedError:
        print(f"Connection refused - is the adapter running?")
        print(f"Start it with: python scripts/windows_node_adapter.py")
    except KeyboardInterrupt:
        print("\nDisconnected")


if __name__ == '__main__':
    asyncio.run(main())
