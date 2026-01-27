#!/usr/bin/env python3
"""
Start Hyperliquid Node Adapter

Run this script in WSL to start the node adapter service.
The adapter streams blocks from the node and exposes events via TCP.

Usage:
    # Basic (localhost only)
    python start_node_adapter.py

    # Allow external connections
    python start_node_adapter.py --host 0.0.0.0

    # Custom port
    python start_node_adapter.py --port 8091

    # With verbose logging
    python start_node_adapter.py --log-interval 100

    # Test mode (stdout only, no TCP)
    python start_node_adapter.py --test

Requirements:
    - Python 3.8+
    - Hyperliquid node running and synced
    - inotify_simple (optional, for efficient file watching)

Install dependencies:
    pip install inotify_simple  # Linux only, optional
"""

import asyncio
import argparse
import sys
import os

# Add node_adapter directory to path first (before project root)
# This avoids importing the parent hyperliquid package which has aiohttp dependency
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
node_adapter_path = os.path.join(project_root, 'runtime', 'hyperliquid', 'node_adapter')

# Insert node_adapter at position 0 so it takes priority
sys.path.insert(0, node_adapter_path)

# Import from node_adapter modules directly
import config as adapter_config
import metrics as adapter_metrics
import asset_mapping
import replica_streamer
import action_extractor
import sync_monitor
import adapter as node_adapter

NodeAdapterConfig = adapter_config.NodeAdapterConfig
AdapterMetrics = adapter_metrics.AdapterMetrics
ReplicaCmdStreamer = replica_streamer.ReplicaCmdStreamer
BlockActionExtractor = action_extractor.BlockActionExtractor
SyncMonitor = sync_monitor.SyncMonitor
HyperliquidNodeAdapter = node_adapter.HyperliquidNodeAdapter


async def test_mode(config: NodeAdapterConfig):
    """
    Test mode - print events to stdout without TCP server.
    Useful for verifying the adapter works before deploying.
    """
    print("=" * 60)
    print("NODE ADAPTER TEST MODE")
    print("=" * 60)
    print(f"Data path: {config.node_data_path}")
    print(f"State path: {config.node_state_path}")
    print()

    # Check sync status
    print("Checking sync status...")
    sync_monitor = SyncMonitor(config.node_state_path)
    status = sync_monitor.get_status()

    if status:
        print(f"  Block height: {status.height}")
        print(f"  Consensus time: {status.consensus_time}")
        print(f"  Lag: {status.lag_seconds:.2f}s")
        print(f"  Synced: {status.is_synced}")
    else:
        print("  WARNING: Could not read sync status")
        print("  Make sure the node is running and paths are correct")

    print()

    # Test streaming
    print("Testing block streaming...")
    streamer = ReplicaCmdStreamer(
        f"{config.node_data_path}/replica_cmds",
        start_from_end=True,
    )

    try:
        await streamer.start()
    except Exception as e:
        print(f"  ERROR: Could not start streamer: {e}")
        return

    print(f"  Current file: {streamer.metrics.current_file}")
    print()

    # Extract some events
    print("Extracting events from blocks...")
    extractor = BlockActionExtractor(
        extract_orders=config.extract_orders,
        focus_coins=config.focus_coins if config.focus_coins else None,
    )

    blocks_processed = 0
    price_events_total = 0
    liq_events_total = 0

    print()
    print("Streaming blocks (Ctrl+C to stop)...")
    print("-" * 60)

    try:
        async for block_json in streamer.stream_blocks():
            price_events, liq_events, order_activities = \
                extractor.extract_from_block(block_json)

            blocks_processed += 1
            price_events_total += len(price_events)
            liq_events_total += len(liq_events)

            # Print SetGlobalAction prices (first few)
            if price_events:
                print(f"\n[Block {blocks_processed}] SetGlobalAction with {len(price_events)} prices")
                for pe in price_events[:5]:  # First 5
                    print(f"  {pe.symbol}: oracle={pe.oracle_price:.4f}, mark={pe.mark_price:.4f if pe.mark_price else 'N/A'}")
                if len(price_events) > 5:
                    print(f"  ... and {len(price_events) - 5} more")

            # Print liquidations (all - these are rare and important)
            for le in liq_events:
                print(f"\n[Block {blocks_processed}] LIQUIDATION DETECTED!")
                print(f"  Wallet: {le.wallet_address[:16]}...")
                print(f"  Symbol: {le.symbol}")
                print(f"  Side: {le.side}")
                print(f"  Size: {le.liquidated_size}")
                print(f"  Price: {le.liquidation_price}")
                print(f"  Value: ${le.value:,.2f}")

            # Print order activity summary
            if order_activities and blocks_processed % 100 == 0:
                print(f"\n[Block {blocks_processed}] {len(order_activities)} orders in this block")

            # Periodic summary
            if blocks_processed % 1000 == 0:
                print(f"\n--- Summary: {blocks_processed} blocks, "
                      f"{price_events_total} prices, {liq_events_total} liquidations ---")

    except KeyboardInterrupt:
        print("\n\nStopped by user")
    finally:
        await streamer.stop()

    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print(f"  Blocks processed: {blocks_processed}")
    print(f"  Price events: {price_events_total}")
    print(f"  Liquidation events: {liq_events_total}")
    print("=" * 60)


async def run_adapter(config: NodeAdapterConfig):
    """Run the full adapter with TCP server."""
    adapter = HyperliquidNodeAdapter(config)

    try:
        await adapter.start()

        print()
        print("=" * 60)
        print("NODE ADAPTER RUNNING")
        print("=" * 60)
        print(f"TCP server: {config.tcp_host}:{config.tcp_port}")
        print(f"Data path: {config.node_data_path}")
        print()
        print("Connect from Windows:")
        print(f"  nc {config.tcp_host} {config.tcp_port}")
        print()
        print("Press Ctrl+C to stop")
        print("=" * 60)
        print()

        # Run until interrupted
        while True:
            await asyncio.sleep(1.0)

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        await adapter.stop()


def main():
    parser = argparse.ArgumentParser(
        description='Hyperliquid Node Adapter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run adapter with default settings
    python start_node_adapter.py

    # Test mode - print events to stdout
    python start_node_adapter.py --test

    # Custom paths (if node installed elsewhere)
    python start_node_adapter.py --data-path /opt/hl/data --state-path /opt/hl/hyperliquid_data
        """
    )

    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='TCP server host (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8090,
        help='TCP server port (default: 8090)'
    )
    parser.add_argument(
        '--data-path',
        default='~/hl/data',
        help='Path to node data directory (default: ~/hl/data)'
    )
    parser.add_argument(
        '--state-path',
        default='~/hl/hyperliquid_data',
        help='Path to node state directory (default: ~/hl/hyperliquid_data)'
    )
    parser.add_argument(
        '--log-interval',
        type=int,
        default=1000,
        help='Log every N blocks (0 to disable, default: 1000)'
    )
    parser.add_argument(
        '--no-orders',
        action='store_true',
        help='Disable order extraction (reduces processing)'
    )
    parser.add_argument(
        '--focus-coins',
        nargs='+',
        help='Only extract for specific coins (e.g., BTC ETH SOL)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode - print events to stdout without TCP server'
    )

    args = parser.parse_args()

    config = NodeAdapterConfig(
        node_data_path=args.data_path,
        node_state_path=args.state_path,
        tcp_host=args.host,
        tcp_port=args.port,
        log_block_interval=args.log_interval,
        extract_orders=not args.no_orders,
        focus_coins=args.focus_coins or [],
    )

    if args.test:
        asyncio.run(test_mode(config))
    else:
        asyncio.run(run_adapter(config))


if __name__ == '__main__':
    main()
