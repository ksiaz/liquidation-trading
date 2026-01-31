#!/usr/bin/env python3
"""
Emergency Position Closure Script.

Closes all open positions at market price.
Use this when the trading system is unresponsive or in an emergency.

Usage:
    python close_positions.py                # Interactive confirmation
    python close_positions.py --force        # No confirmation
    python close_positions.py --dry-run      # Show what would be closed
    python close_positions.py --symbol BTC   # Close specific symbol only
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime.hyperliquid.client import HyperliquidClient


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


async def get_open_positions(client: HyperliquidClient) -> List[dict]:
    """Get all open positions from exchange."""
    try:
        positions = await client.get_positions()
        return [p for p in positions if abs(p.get('size', 0)) > 0]
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
        raise


async def close_position(
    client: HyperliquidClient,
    symbol: str,
    size: float,
    side: str,
    dry_run: bool = False,
) -> bool:
    """Close a single position at market."""
    # To close, we need opposite side order
    close_side = "sell" if side == "long" else "buy"

    logger.info(f"Closing {symbol}: {abs(size):.6f} {side} -> {close_side} market order")

    if dry_run:
        logger.info(f"  [DRY RUN] Would close {symbol}")
        return True

    try:
        result = await client.place_market_order(
            symbol=symbol,
            side=close_side,
            size=abs(size),
            reduce_only=True,
        )
        logger.info(f"  Closed {symbol}: order_id={result.get('order_id', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"  Failed to close {symbol}: {e}")
        return False


async def close_all_positions(
    client: HyperliquidClient,
    symbol_filter: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Close all open positions.

    Args:
        client: Exchange client
        symbol_filter: If set, only close positions matching this symbol
        force: If True, skip confirmation prompt
        dry_run: If True, don't actually close, just show what would be closed

    Returns:
        Summary of closure results
    """
    # Get positions
    logger.info("Fetching open positions...")
    positions = await get_open_positions(client)

    if symbol_filter:
        positions = [p for p in positions if symbol_filter.upper() in p.get('symbol', '').upper()]

    if not positions:
        logger.info("No open positions found.")
        return {'closed': 0, 'failed': 0, 'positions': []}

    # Display positions
    logger.info(f"\nFound {len(positions)} open position(s):")
    for pos in positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        size = pos.get('size', 0)
        side = 'long' if size > 0 else 'short'
        entry = pos.get('entry_price', 0)
        pnl = pos.get('unrealized_pnl', 0)
        logger.info(f"  {symbol}: {abs(size):.6f} {side} @ {entry:.2f} (PnL: ${pnl:.2f})")

    # Confirm unless forced
    if not force and not dry_run:
        print("\n" + "="*50)
        print("WARNING: This will close ALL listed positions at MARKET!")
        print("="*50)
        response = input("\nType 'CLOSE ALL' to confirm: ")
        if response.strip() != 'CLOSE ALL':
            logger.info("Aborted by user.")
            return {'closed': 0, 'failed': 0, 'positions': [], 'aborted': True}

    # Close each position
    results = {'closed': 0, 'failed': 0, 'positions': []}

    for pos in positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        size = pos.get('size', 0)
        side = 'long' if size > 0 else 'short'

        success = await close_position(client, symbol, size, side, dry_run)

        if success:
            results['closed'] += 1
        else:
            results['failed'] += 1

        results['positions'].append({
            'symbol': symbol,
            'size': abs(size),
            'side': side,
            'closed': success,
        })

        # Small delay between closes to avoid rate limiting
        if not dry_run:
            await asyncio.sleep(0.1)

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"SUMMARY: Closed {results['closed']}, Failed {results['failed']}")
    if dry_run:
        logger.info("(DRY RUN - no actual orders placed)")
    logger.info(f"{'='*50}")

    return results


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Emergency position closure script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python close_positions.py                 # Close all with confirmation
    python close_positions.py --force         # Close all without confirmation
    python close_positions.py --dry-run       # Show what would be closed
    python close_positions.py --symbol BTC    # Close only BTC positions
        """
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Skip confirmation prompt',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be closed without actually closing',
    )
    parser.add_argument(
        '--symbol', '-s',
        type=str,
        default=None,
        help='Only close positions matching this symbol',
    )
    args = parser.parse_args()

    # Log startup
    logger.info("="*50)
    logger.info("EMERGENCY POSITION CLOSURE")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info(f"Force: {args.force}")
    if args.symbol:
        logger.info(f"Symbol filter: {args.symbol}")
    logger.info("="*50)

    # Create client
    try:
        client = HyperliquidClient()
    except Exception as e:
        logger.error(f"Failed to create client: {e}")
        sys.exit(1)

    # Close positions
    try:
        results = await close_all_positions(
            client,
            symbol_filter=args.symbol,
            force=args.force,
            dry_run=args.dry_run,
        )

        if results.get('aborted'):
            sys.exit(1)
        if results['failed'] > 0:
            sys.exit(2)

    except Exception as e:
        logger.error(f"Emergency closure failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
