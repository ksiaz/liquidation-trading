#!/usr/bin/env python3
"""
Emergency Order Cancellation Script.

Cancels all open orders across all symbols.
Use this when the trading system is unresponsive or in an emergency.

Usage:
    python cancel_orders.py                # Interactive confirmation
    python cancel_orders.py --all          # Cancel all without confirmation
    python cancel_orders.py --dry-run      # Show what would be cancelled
    python cancel_orders.py --symbol BTC   # Cancel specific symbol only
    python cancel_orders.py --stops-only   # Only cancel stop orders
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


async def get_open_orders(
    client: HyperliquidClient,
    symbol: Optional[str] = None,
) -> List[dict]:
    """Get all open orders from exchange."""
    try:
        orders = await client.get_open_orders(symbol)
        return orders
    except Exception as e:
        logger.error(f"Failed to get orders: {e}")
        raise


async def cancel_order(
    client: HyperliquidClient,
    order_id: str,
    symbol: str,
    dry_run: bool = False,
) -> bool:
    """Cancel a single order."""
    logger.info(f"Cancelling order {order_id} for {symbol}")

    if dry_run:
        logger.info(f"  [DRY RUN] Would cancel {order_id}")
        return True

    try:
        await client.cancel_order(symbol, order_id)
        logger.info(f"  Cancelled {order_id}")
        return True
    except Exception as e:
        logger.error(f"  Failed to cancel {order_id}: {e}")
        return False


async def cancel_all_orders(
    client: HyperliquidClient,
    symbol_filter: Optional[str] = None,
    stops_only: bool = False,
    cancel_all: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Cancel all open orders.

    Args:
        client: Exchange client
        symbol_filter: If set, only cancel orders for this symbol
        stops_only: If True, only cancel stop orders
        cancel_all: If True, skip confirmation prompt
        dry_run: If True, don't actually cancel, just show what would be cancelled

    Returns:
        Summary of cancellation results
    """
    # Get orders
    logger.info("Fetching open orders...")
    orders = await get_open_orders(client, symbol_filter)

    if stops_only:
        orders = [o for o in orders if o.get('order_type', '').lower() in ('stop', 'stop_limit', 'stop_market')]

    if not orders:
        logger.info("No open orders found.")
        return {'cancelled': 0, 'failed': 0, 'orders': []}

    # Display orders
    logger.info(f"\nFound {len(orders)} open order(s):")
    for order in orders:
        order_id = order.get('order_id', 'UNKNOWN')
        symbol = order.get('symbol', 'UNKNOWN')
        order_type = order.get('order_type', 'unknown')
        side = order.get('side', 'unknown')
        size = order.get('size', 0)
        price = order.get('price', 0)
        logger.info(f"  {order_id}: {symbol} {side} {abs(size):.6f} @ {price:.2f} ({order_type})")

    # Confirm unless --all
    if not cancel_all and not dry_run:
        print("\n" + "="*50)
        print("WARNING: This will CANCEL ALL listed orders!")
        print("="*50)
        response = input("\nType 'CANCEL ALL' to confirm: ")
        if response.strip() != 'CANCEL ALL':
            logger.info("Aborted by user.")
            return {'cancelled': 0, 'failed': 0, 'orders': [], 'aborted': True}

    # Cancel each order
    results = {'cancelled': 0, 'failed': 0, 'orders': []}

    for order in orders:
        order_id = order.get('order_id', 'UNKNOWN')
        symbol = order.get('symbol', 'UNKNOWN')

        success = await cancel_order(client, order_id, symbol, dry_run)

        if success:
            results['cancelled'] += 1
        else:
            results['failed'] += 1

        results['orders'].append({
            'order_id': order_id,
            'symbol': symbol,
            'cancelled': success,
        })

        # Small delay between cancels to avoid rate limiting
        if not dry_run:
            await asyncio.sleep(0.05)

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"SUMMARY: Cancelled {results['cancelled']}, Failed {results['failed']}")
    if dry_run:
        logger.info("(DRY RUN - no actual cancellations)")
    logger.info(f"{'='*50}")

    return results


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Emergency order cancellation script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python cancel_orders.py                 # Cancel all with confirmation
    python cancel_orders.py --all           # Cancel all without confirmation
    python cancel_orders.py --dry-run       # Show what would be cancelled
    python cancel_orders.py --symbol BTC    # Cancel only BTC orders
    python cancel_orders.py --stops-only    # Only cancel stop orders
        """
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Skip confirmation prompt and cancel all',
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be cancelled without actually cancelling',
    )
    parser.add_argument(
        '--symbol', '-s',
        type=str,
        default=None,
        help='Only cancel orders for this symbol',
    )
    parser.add_argument(
        '--stops-only',
        action='store_true',
        help='Only cancel stop orders',
    )
    args = parser.parse_args()

    # Log startup
    logger.info("="*50)
    logger.info("EMERGENCY ORDER CANCELLATION")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info(f"Cancel all: {args.all}")
    if args.symbol:
        logger.info(f"Symbol filter: {args.symbol}")
    if args.stops_only:
        logger.info("Stops only: True")
    logger.info("="*50)

    # Create client
    try:
        client = HyperliquidClient()
    except Exception as e:
        logger.error(f"Failed to create client: {e}")
        sys.exit(1)

    # Cancel orders
    try:
        results = await cancel_all_orders(
            client,
            symbol_filter=args.symbol,
            stops_only=args.stops_only,
            cancel_all=args.all,
            dry_run=args.dry_run,
        )

        if results.get('aborted'):
            sys.exit(1)
        if results['failed'] > 0:
            sys.exit(2)

    except Exception as e:
        logger.error(f"Emergency cancellation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
