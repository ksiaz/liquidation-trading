"""
Direct Node Integration

Simplified integration for native Ubuntu - no TCP bridge needed.
Reads directly from node files and feeds to observation system.

Usage:
    integration = DirectNodeIntegration(observation_system)
    await integration.start()

Data sources:
- replica_cmds: Block data with SetGlobalAction (prices), orders
- node_trades: Trade fills including liquidations (trade_dir_override: "LiquidatedMarket")
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from .action_extractor import BlockActionExtractor, PriceEvent, LiquidationEvent, OrderActivity
from .config import NodeAdapterConfig
from .sync_monitor import SyncMonitor

logger = logging.getLogger(__name__)


class TradeFileReader:
    """
    Reads trade fills from node_trades directory.

    Liquidations are identified by trade_dir_override: "LiquidatedMarket"

    Trade file format (NDJSON):
    {
        "coin": "BTC",
        "side": "B",  # B=buy, A=ask/sell
        "time": "2026-01-27T05:03:22.622306903",
        "px": "97500.0",
        "sz": "1.5",
        "trade_dir_override": "LiquidatedMarket" | "Na",
        "side_info": [
            {"user": "0x...", "start_pos": "-17.23", "oid": 123, ...},
            {"user": "0x...", "start_pos": "10.5", "oid": 456, ...}
        ]
    }
    """

    def __init__(self, data_path: Path, catchup_hours: int = 6):
        """
        Initialize trade file reader.

        Args:
            data_path: Path to ~/hl/data
            catchup_hours: Number of past hours to read on startup for catch-up
        """
        self._data_path = data_path
        self._current_hour_file: Optional[Path] = None
        self._file_position: int = 0
        self._liquidations_found = 0
        self._processed_files: set = set()  # Track files we've fully read
        self._catchup_hours = catchup_hours

    def read_new_liquidations(self) -> list[LiquidationEvent]:
        """Read new liquidation trades from node_trades."""
        liquidations = []

        trades_dir = self._data_path / "node_trades" / "hourly"
        if not trades_dir.exists():
            return liquidations

        # Find latest date directory
        date_dirs = sorted(trades_dir.iterdir(), reverse=True)
        if not date_dirs:
            return liquidations

        latest_date = date_dirs[0]
        if not latest_date.is_dir():
            return liquidations

        # Get all hour files sorted by hour
        hour_files = sorted(
            [f for f in latest_date.iterdir() if f.is_file() and f.name.isdigit()],
            key=lambda f: int(f.name)
        )
        if not hour_files:
            return liquidations

        # On first run, catch up recent hours
        if not self._processed_files and self._catchup_hours > 0:
            catchup_files = hour_files[-self._catchup_hours:]
            for f in catchup_files[:-1]:  # All except last (which we'll tail)
                if f not in self._processed_files:
                    liqs = self._read_file_liquidations(f, from_position=0)
                    liquidations.extend(liqs)
                    self._processed_files.add(f)
                    logger.info(f"Catch-up: {f.name} -> {len(liqs)} liquidations")

        # Now tail the latest file
        latest_hour = hour_files[-1]

        # Check if file changed
        if latest_hour != self._current_hour_file:
            logger.debug(f"New trade file: {latest_hour}")
            self._current_hour_file = latest_hour
            self._file_position = 0

        # Read new lines from latest file
        liqs = self._read_file_liquidations(latest_hour, from_position=self._file_position)
        liquidations.extend(liqs)

        return liquidations

    def _read_file_liquidations(self, file_path: Path, from_position: int = 0) -> list[LiquidationEvent]:
        """Read liquidations from a specific file."""
        liquidations = []

        try:
            file_size = file_path.stat().st_size
            if file_size <= from_position:
                return liquidations

            with open(file_path, 'r') as f:
                f.seek(from_position)

                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        trade = json.loads(line)

                        # Only extract liquidations
                        if trade.get('trade_dir_override') == 'LiquidatedMarket':
                            liq = self._parse_liquidation(trade)
                            if liq:
                                liquidations.append(liq)
                                self._liquidations_found += 1
                    except json.JSONDecodeError:
                        continue

                # Update position only for the tailed file
                if file_path == self._current_hour_file:
                    self._file_position = f.tell()

        except Exception as e:
            logger.error(f"Error reading trade file {file_path}: {e}")

        return liquidations

    def _parse_liquidation(self, trade: Dict) -> Optional[LiquidationEvent]:
        """Parse a liquidation trade into LiquidationEvent."""
        try:
            coin = trade.get('coin', 'UNKNOWN')
            side = trade.get('side', '')  # B=buy, A=sell
            time_str = trade.get('time', '')
            px = float(trade.get('px', 0))
            sz = float(trade.get('sz', 0))

            # Parse timestamp
            timestamp = self._parse_timestamp(time_str)

            # Get liquidated user (first in side_info with the closing order)
            side_info = trade.get('side_info', [])
            if not side_info:
                return None

            # The liquidated user is the one whose position is being closed
            # Their start_pos tells us if they were long or short
            liquidated_user = side_info[0]
            wallet = liquidated_user.get('user', '')
            start_pos = float(liquidated_user.get('start_pos', 0))

            # Determine side from position being closed
            # If start_pos is negative, they were short (being closed by buying)
            # If start_pos is positive, they were long (being closed by selling)
            if start_pos < 0:
                position_side = 'SHORT'
            elif start_pos > 0:
                position_side = 'LONG'
            else:
                position_side = 'UNKNOWN'

            value = px * sz

            return LiquidationEvent(
                timestamp=timestamp,
                symbol=coin,
                wallet_address=wallet,
                liquidated_size=sz,
                liquidation_price=px,
                side=position_side,
                value=value,
            )
        except Exception as e:
            logger.debug(f"Error parsing liquidation: {e}")
            return None

    def _parse_timestamp(self, time_str: str) -> float:
        """Parse ISO timestamp to Unix seconds."""
        if not time_str:
            import time
            return time.time()

        try:
            # Truncate nanoseconds to microseconds
            clean_str = time_str[:26]
            dt = datetime.fromisoformat(clean_str)
            return dt.timestamp()
        except Exception:
            import time
            return time.time()

    @property
    def liquidations_found(self) -> int:
        return self._liquidations_found


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
        self._trade_reader = TradeFileReader(self._data_path)

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
            'liquidations_from_trades': self._trade_reader.liquidations_found,
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

                # Read liquidations from trade files
                await self._process_trade_liquidations()

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

    async def _process_trade_liquidations(self) -> None:
        """Process liquidations from node_trades files."""
        if not self._on_liquidation:
            return

        liquidations = self._trade_reader.read_new_liquidations()

        for liq in liquidations:
            try:
                self._on_liquidation(liq)
                self._liquidations_emitted += 1
            except Exception as e:
                logger.error(f"Error in liquidation callback: {e}")

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
        if self._config.log_block_interval > 0 and self._blocks_processed % self._config.log_block_interval == 0:
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
