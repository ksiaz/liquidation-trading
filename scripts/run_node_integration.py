#!/usr/bin/env python3
"""
Node Adapter Integration Runner

Connects the WSL node adapter to the observation system:
1. WindowsNodeConnector: TCP client to WSL adapter
2. PositionStateManager: Tiered position refresh with proximity tracking
3. ObservationSystemConnector: Routes events to M1-M5

Usage:
    # Make sure WSL adapter is running first:
    # wsl python3 /mnt/d/liquidation-trading/scripts/wsl_tcp_adapter.py --host 0.0.0.0

    # Then run this on Windows:
    python scripts/run_node_integration.py

    # Or with options:
    python scripts/run_node_integration.py --symbols BTC,ETH,SOL --host 127.0.0.1 --port 8090
"""

import asyncio
import argparse
import time
import sys
import os

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from typing import Optional, List
from observation.governance import ObservationSystem
from runtime.hyperliquid.windows_connector import (
    WindowsNodeConnector,
    ObservationSystemConnector,
    ConnectorMetrics,
)
from runtime.hyperliquid.node_adapter.config import WindowsConnectorConfig
from runtime.hyperliquid.node_adapter.position_state import (
    PositionStateManager,
    PositionCache,
    ProximityAlert,
    RefreshTier,
)


class IntegrationRunner:
    """
    Main integration runner that orchestrates all components.
    """

    def __init__(
        self,
        symbols: List[str],
        tcp_host: str = '127.0.0.1',
        tcp_port: int = 8090,
        state_path: str = '~/hl/hyperliquid_data',
        enable_position_tracking: bool = True,
    ):
        """
        Initialize integration runner.

        Args:
            symbols: List of symbols to track (e.g., ['BTC', 'ETH', 'SOL'])
            tcp_host: Host for TCP connection to WSL adapter
            tcp_port: Port for TCP connection
            state_path: Path to hyperliquid state in WSL
            enable_position_tracking: Whether to enable position state tracking
        """
        self._symbols = symbols

        # Create observation system
        self._obs = ObservationSystem(allowed_symbols=symbols)

        # Create connector config
        self._config = WindowsConnectorConfig(
            tcp_host=tcp_host,
            tcp_port=tcp_port,
        )

        # Create position state manager if enabled
        # NOTE: Position tracking requires reading abci_state.rmp from WSL
        # which isn't directly accessible from Windows. For full position
        # tracking, run the PositionStateManager in WSL alongside the adapter.
        self._position_manager: Optional[PositionStateManager] = None
        if enable_position_tracking:
            # Try to access state path - only works if WSL filesystem is mounted
            wsl_mount_path = state_path.replace('/root/', '//wsl$/Ubuntu/root/')
            try:
                self._position_manager = PositionStateManager(
                    state_path=wsl_mount_path,
                    focus_coins=symbols,
                    min_position_value=1000.0,  # Track positions >= $1000
                )
                # Set up alert callback
                self._position_manager.on_proximity_alert = self._handle_proximity_alert
            except Exception as e:
                print(f"NOTE: Position tracking disabled - cannot access WSL state: {e}")
                self._position_manager = None

        # Create connector
        self._connector = ObservationSystemConnector(
            observation_system=self._obs,
            config=self._config,
            position_state_manager=self._position_manager,
        )

        # Stats tracking
        self._start_time = 0.0
        self._last_stats_time = 0.0
        self._stats_interval = 30.0  # Print stats every 30 seconds

    async def start(self) -> None:
        """Start the integration."""
        self._start_time = time.time()
        self._last_stats_time = self._start_time

        print("=" * 60)
        print("NODE ADAPTER INTEGRATION")
        print("=" * 60)
        print(f"Symbols: {', '.join(self._symbols)}")
        print(f"TCP Target: {self._config.tcp_host}:{self._config.tcp_port}")
        print(f"Position Tracking: {'Enabled' if self._position_manager else 'Disabled'}")
        print()

        # Start connector
        await self._connector.start()

        # Wait for connection
        print("Connecting to WSL adapter...")
        connected = await self._connector.wait_connected(timeout=30.0)

        if not connected:
            print("ERROR: Failed to connect to WSL adapter")
            print("Make sure the adapter is running in WSL:")
            print("  wsl python3 /mnt/d/liquidation-trading/scripts/wsl_tcp_adapter.py --host 0.0.0.0")
            return

        print("Connected!")
        print()
        print("Receiving events (Ctrl+C to stop)...")
        print("-" * 60)

        # Run main loop
        try:
            while True:
                await asyncio.sleep(1.0)
                await self._print_stats()
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """Stop the integration."""
        print("\nShutting down...")
        await self._connector.stop()

    async def _print_stats(self) -> None:
        """Print periodic stats."""
        now = time.time()
        if now - self._last_stats_time < self._stats_interval:
            return

        self._last_stats_time = now
        elapsed = now - self._start_time
        metrics = self._connector.metrics

        print()
        print(f"--- Stats ({elapsed:.0f}s uptime) ---")
        print(f"  Events: {metrics.events_received} ({metrics.events_per_second:.1f}/s)")
        print(f"  Prices: {metrics.price_events}")
        print(f"  Liquidations: {metrics.liquidation_events}")
        print(f"  Order Activity: {metrics.order_activity_events}")

        # Position stats if available
        if self._position_manager:
            pm = self._position_manager
            print(f"  Positions Tracked: {pm.metrics.positions_cached}")
            print(f"  Critical (<0.5%): {pm.metrics.critical_positions}")
            print(f"  Watchlist (<2%): {pm.metrics.watchlist_positions}")

        # Price samples
        prices = self._connector._connector.get_all_prices()
        if prices:
            sample_coins = ['BTC', 'ETH', 'SOL']
            price_str = ', '.join(
                f"{c}=${prices.get(c, 0):,.0f}"
                for c in sample_coins if c in prices
            )
            print(f"  Prices: {price_str}")

        print()

    async def _handle_proximity_alert(self, alert: ProximityAlert) -> None:
        """Handle proximity alert from position manager."""
        tier_emoji = {
            RefreshTier.CRITICAL: "🚨",
            RefreshTier.WATCHLIST: "⚠️",
            RefreshTier.MONITORED: "📊",
            RefreshTier.DISCOVERY: "🔍",
        }

        emoji = tier_emoji.get(alert.new_tier, "")
        direction = "↑" if alert.new_tier.value < alert.old_tier.value else "↓"

        print(f"{emoji} PROXIMITY ALERT: {alert.wallet[:10]}... {alert.coin}")
        print(f"   {direction} {alert.old_tier.value} -> {alert.new_tier.value}")
        print(f"   Distance to liquidation: {alert.proximity_pct:.2f}%")
        print(f"   Position value: ${alert.position_value:,.0f}")
        print()


async def main():
    parser = argparse.ArgumentParser(
        description='Node Adapter Integration Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python scripts/run_node_integration.py

    # Custom symbols
    python scripts/run_node_integration.py --symbols BTC,ETH,SOL,DOGE

    # Connect to different port
    python scripts/run_node_integration.py --port 8091

    # Disable position tracking (just stream events)
    python scripts/run_node_integration.py --no-positions
        """
    )

    parser.add_argument(
        '--symbols',
        default='BTC,ETH,SOL,BNB,XRP,DOGE,ADA,AVAX,LINK,UNI',
        help='Comma-separated list of symbols to track'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='TCP host for WSL adapter (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8090,
        help='TCP port for WSL adapter (default: 8090)'
    )
    parser.add_argument(
        '--state-path',
        default='~/hl/hyperliquid_data',
        help='Path to Hyperliquid state'
    )
    parser.add_argument(
        '--no-positions',
        action='store_true',
        help='Disable position state tracking'
    )

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(',')]

    runner = IntegrationRunner(
        symbols=symbols,
        tcp_host=args.host,
        tcp_port=args.port,
        state_path=args.state_path,
        enable_position_tracking=not args.no_positions,
    )

    try:
        await runner.start()
    except KeyboardInterrupt:
        pass
    finally:
        await runner.stop()


if __name__ == '__main__':
    asyncio.run(main())
