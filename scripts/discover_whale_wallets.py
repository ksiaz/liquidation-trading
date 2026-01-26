#!/usr/bin/env python3
"""
Whale Wallet Discovery Script

Verifies known wallets and discovers new ones from:
1. Hyperliquid clearinghouse state (position verification)
2. Large position analysis
3. Liquidation event tracking

Usage:
    python scripts/discover_whale_wallets.py

Output:
    - Verified active wallets (with positions)
    - New wallet suggestions
    - Code snippets to add to whale_wallets.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.hyperliquid.client import HyperliquidClient
from runtime.hyperliquid.whale_wallets import (
    get_all_tracked_wallets,
    get_whale_wallets,
    get_system_wallets,
    WalletInfo
)


async def verify_wallet(client: HyperliquidClient, address: str) -> dict:
    """Verify a wallet and get its position summary."""
    try:
        state = await client.get_clearinghouse_state(address)
        if not state:
            return {'address': address, 'status': 'NO_DATA', 'positions': 0, 'value': 0}

        # state is a WalletState object with positions dict
        total_value = 0.0
        coins = []

        for coin, position in state.positions.items():
            value = position.position_value
            if value > 0:
                total_value += value
                side = "L" if position.position_size > 0 else "S"
                coins.append(f"{coin}({side}): ${value:,.0f}")

        return {
            'address': address,
            'status': 'ACTIVE' if total_value > 0 else 'EMPTY',
            'positions': len(state.positions),
            'value': total_value,
            'coins': coins[:5]  # Top 5 coins
        }
    except Exception as e:
        return {'address': address, 'status': f'ERROR: {e}', 'positions': 0, 'value': 0}


async def main():
    print("=" * 70)
    print("HYPERLIQUID WHALE WALLET DISCOVERY")
    print("=" * 70)
    print()

    # Initialize client
    client = HyperliquidClient()
    await client.start()  # Initialize HTTP session

    # Get all tracked wallets
    all_wallets = get_all_tracked_wallets()
    print(f"Checking {len(all_wallets)} tracked wallets...\n")

    # Verify each wallet
    active_wallets = []
    empty_wallets = []
    error_wallets = []

    for wallet_info in all_wallets:
        result = await verify_wallet(client, wallet_info.address)
        result['label'] = wallet_info.label
        result['type'] = wallet_info.wallet_type

        if result['status'] == 'ACTIVE':
            active_wallets.append(result)
        elif result['status'] == 'EMPTY':
            empty_wallets.append(result)
        else:
            error_wallets.append(result)

        # Progress indicator
        status_char = '.' if result['status'] in ['ACTIVE', 'EMPTY'] else '!'
        print(status_char, end='', flush=True)

        # Rate limit
        await asyncio.sleep(0.2)

    print("\n")

    # Report results
    print("-" * 70)
    print("ACTIVE WALLETS (with positions)")
    print("-" * 70)
    for w in sorted(active_wallets, key=lambda x: -x['value']):
        print(f"  {w['label']:<25} | ${w['value']:>15,.0f} | {w['positions']} positions")
        if w['coins']:
            print(f"    {', '.join(w['coins'][:3])}")

    print()
    print("-" * 70)
    print("EMPTY WALLETS (no current positions)")
    print("-" * 70)
    for w in empty_wallets:
        print(f"  {w['label']:<25} | {w['address'][:20]}...")

    if error_wallets:
        print()
        print("-" * 70)
        print("ERRORS")
        print("-" * 70)
        for w in error_wallets:
            print(f"  {w['label']:<25} | {w['status']}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Active wallets:  {len(active_wallets)}")
    print(f"  Empty wallets:   {len(empty_wallets)}")
    print(f"  Errors:          {len(error_wallets)}")
    total_value = sum(w['value'] for w in active_wallets)
    print(f"  Total tracked value: ${total_value:,.0f}")
    print()

    await client.stop()


if __name__ == '__main__':
    # Windows event loop fix
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
