"""
Direct Node Integration

Simplified integration for native Ubuntu - no TCP bridge needed.
Reads directly from node files and feeds to observation system.

Usage:
    integration = DirectNodeIntegration(observation_system)
    await integration.start()
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from .action_extractor import BlockActionExtractor, PriceEvent, LiquidationEvent, OrderActivity
from .config import NodeAdapterConfig
from .sync_monitor import SyncMonitor

logger = logging.getLogger(__name__)


class DirectNodeIntegration:
    """
    Direct integration between Hyperliquid node and observation system.

    No TCP, no bridge - just reads files and calls callbacks.
    """

    def __init__(
        self,
        on_price: Optional[Callable[[PriceEvent], None]] = None,
        on_liquidation: Optional[Callable[[LiquidationEvent], None]] = None,
        on_order_activity: Optional[Callable[[OrderActivity], None]] = None,
        config: Optional[NodeAdapterConfig] = None,
    ):
        """
        Initialize direct integration.

        Args:
            on_price: Callback for price events (SetGlobalAction)
            on_liquidation: Callback for liquidation events (forceOrder)
            on_order_activity: Callback for order activity
            config: Optional configuration override
        """
        self._config = config or NodeAdapterConfig()
        self._on_price = on_price
        self._on_liquidation = on_liquidation
        self._on_order_activity = on_order_activity

        # Expand ~ in paths
        self._data_path = Path(os.path.expanduser(self._config.node_data_path))
        self._state_path = Path(os.path.expanduser(self._config.node_state_path))

        # Components
        self._extractor = BlockActionExtractor(
            extract_orders=self._config.extract_orders,
            extract_cancels=self._config.extract_cancels,
            focus_coins=self._config.focus_coins or None,
        )
        self._sync_monitor = SyncMonitor(self._state_path)

        # State
        self._running = False
        self._current_session: Optional[Path] = None
        self._current_file: Optional[Path] = None
        self._file_position: int = 0

        # Metrics
        self._blocks_processed = 0
        self._prices_emitted = 0
        self._liquidations_emitted = 0

    async def start(self) -> None:
        """Start the integration loop."""
        if self._running:
            logger.warning("Integration already running")
            return

        self._running = True
        logger.info(f"Starting direct node integration from {self._data_path}")

        try:
            await self._run_loop()
        except asyncio.CancelledError:
            logger.info("Integration cancelled")
        except Exception as e:
            logger.error(f"Integration error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the integration."""
        self._running = False

    def get_sync_status(self) -> dict:
        """Get current sync status."""
        return self._sync_monitor.get_status()

    def get_metrics(self) -> dict:
        """Get integration metrics."""
        return {
            'blocks_processed': self._blocks_processed,
            'prices_emitted': self._prices_emitted,
            'liquidations_emitted': self._liquidations_emitted,
            'current_session': str(self._current_session) if self._current_session else None,
            'current_file': str(self._current_file) if self._current_file else None,
        }

    async def _run_loop(self) -> None:
        """Main processing loop."""
        replica_cmds_path = self._data_path / "replica_cmds"

        while self._running:
            try:
                # Find latest session directory
                session = self._find_latest_session(replica_cmds_path)
                if not session:
                    logger.debug("No session directory found, waiting...")
                    await asyncio.sleep(1.0)
                    continue

                if session != self._current_session:
                    logger.info(f"New session: {session.name}")
                    self._current_session = session
                    self._current_file = None
                    self._file_position = 0

                # Find latest date directory
                date_dir = self._find_latest_date_dir(session)
                if not date_dir:
                    await asyncio.sleep(0.5)
                    continue

                # Find latest block file
                block_file = self._find_latest_block_file(date_dir)
                if not block_file:
                    await asyncio.sleep(0.5)
                    continue

                # If new file, reset position
                if block_file != self._current_file:
                    if self._current_file:
                        logger.debug(f"New block file: {block_file.name}")
                    self._current_file = block_file
                    self._file_position = 0

                # Read new lines from file
                await self._process_file()

                # Small sleep to prevent busy loop
                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                await asyncio.sleep(1.0)

    def _find_latest_session(self, replica_cmds_path: Path) -> Optional[Path]:
        """Find the latest session directory."""
        if not replica_cmds_path.exists():
            return None

        sessions = sorted(replica_cmds_path.iterdir(), reverse=True)
        for session in sessions:
            if session.is_dir() and session.name.startswith('20'):
                return session
        return None

    def _find_latest_date_dir(self, session: Path) -> Optional[Path]:
        """Find the latest date directory in session."""
        date_dirs = sorted(session.iterdir(), reverse=True)
        for d in date_dirs:
            if d.is_dir() and d.name.isdigit():
                return d
        return None

    def _find_latest_block_file(self, date_dir: Path) -> Optional[Path]:
        """Find the latest block file in date directory."""
        files = sorted(date_dir.iterdir(), reverse=True)
        for f in files:
            if f.is_file() and f.name.isdigit():
                return f
        return None

    async def _process_file(self) -> None:
        """Process new lines from current block file."""
        if not self._current_file or not self._current_file.exists():
            return

        try:
            file_size = self._current_file.stat().st_size
            if file_size <= self._file_position:
                return  # No new data

            with open(self._current_file, 'r') as f:
                f.seek(self._file_position)

                for line in f:
                    if not line.strip():
                        continue

                    # Pass raw JSON string to extractor
                    await self._process_block(line)

                self._file_position = f.tell()

        except Exception as e:
            logger.error(f"Error processing file: {e}")

    async def _process_block(self, block_json: str) -> None:
        """Process a single block and emit events."""
        self._blocks_processed += 1

        # Extract events (extractor expects JSON string)
        prices, liquidations, orders = self._extractor.extract_from_block(block_json)

        # Emit price events
        if self._on_price:
            for price in prices:
                try:
                    self._on_price(price)
                    self._prices_emitted += 1
                except Exception as e:
                    logger.error(f"Error in price callback: {e}")

        # Emit liquidation events
        if self._on_liquidation:
            for liq in liquidations:
                try:
                    self._on_liquidation(liq)
                    self._liquidations_emitted += 1
                except Exception as e:
                    logger.error(f"Error in liquidation callback: {e}")

        # Emit order activity
        if self._on_order_activity:
            for order in orders:
                try:
                    self._on_order_activity(order)
                except Exception as e:
                    logger.error(f"Error in order callback: {e}")

        # Log progress periodically
        if self._blocks_processed % self._config.log_block_interval == 0:
            logger.info(
                f"Processed {self._blocks_processed} blocks, "
                f"{self._prices_emitted} prices, "
                f"{self._liquidations_emitted} liquidations"
            )


async def run_standalone(
    on_price: Optional[Callable[[PriceEvent], None]] = None,
    on_liquidation: Optional[Callable[[LiquidationEvent], None]] = None,
) -> None:
    """
    Run integration standalone (for testing).

    Example:
        async def handle_price(p):
            print(f"Price: {p.symbol} = {p.oracle_price}")

        await run_standalone(on_price=handle_price)
    """
    integration = DirectNodeIntegration(
        on_price=on_price,
        on_liquidation=on_liquidation,
    )
    await integration.start()


if __name__ == "__main__":
    # Simple test - print events
    import sys

    def print_price(p: PriceEvent):
        print(f"[PRICE] {p.symbol}: oracle={p.oracle_price}, mark={p.mark_price}")

    def print_liq(l: LiquidationEvent):
        print(f"[LIQ] {l.symbol} {l.side} ${l.value:.0f} @ {l.liquidation_price}")

    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(run_standalone(
            on_price=print_price,
            on_liquidation=print_liq,
        ))
    except KeyboardInterrupt:
        print("\nStopped")
