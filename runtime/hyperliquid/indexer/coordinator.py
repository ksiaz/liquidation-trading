"""
Indexer Coordinator

Orchestrates all indexer components:
- Block Fetcher: Fetches blocks from S3
- Transaction Parser: Extracts addresses
- Indexed Wallet Store: Stores discovered wallets
- Batch Position Poller: Polls wallet positions

Modes:
- Backfill: Index historical blocks to discover addresses
- Live: Stream new blocks and track positions in real-time

Constitutional compliance:
- Only factual data operations
- No predictions or interpretations
- Pure structural orchestration
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ..client import HyperliquidClient
from ..types import WalletState, LiquidationProximity
from .block_fetcher import BlockFetcher, BlockFetcherConfig
from .tx_parser import TransactionParser
from .indexed_wallets import IndexedWalletStore
from .batch_poller import BatchPositionPoller, PollerConfig


@dataclass
class IndexerConfig:
    """Configuration for the indexer coordinator."""
    # Block fetching
    s3_bucket: str = "hl-mainnet-evm-blocks"
    lookback_blocks: int = 500_000  # ~7 days
    live_tail: bool = True

    # Position polling
    tier1_interval: float = 5.0
    tier2_interval: float = 30.0
    tier3_interval: float = 300.0
    max_requests_per_minute: int = 1000

    # Storage
    db_path: str = "indexed_wallets.db"
    checkpoint_path: str = "indexer_checkpoint.json"

    # Backfill settings
    backfill_batch_size: int = 1000  # Blocks per batch
    backfill_workers: int = 4  # Parallel block processing

    # Integration
    min_position_for_tracking: float = 1000.0  # $1k minimum


class IndexerCoordinator:
    """
    Orchestrates the complete indexing pipeline.

    Lifecycle:
    1. start() - Initialize components, begin backfill
    2. Backfill completes - Continue with live indexing
    3. Position polling runs continuously
    4. stop() - Graceful shutdown

    Usage:
        coordinator = IndexerCoordinator(client, db, config)
        await coordinator.start()
        # ... runs continuously ...
        await coordinator.stop()
    """

    def __init__(
        self,
        client: HyperliquidClient,
        config: Optional[IndexerConfig] = None
    ):
        self.config = config or IndexerConfig()
        self._client = client
        self._logger = logging.getLogger("IndexerCoordinator")

        # Components (initialized in start())
        self._fetcher: Optional[BlockFetcher] = None
        self._parser: Optional[TransactionParser] = None
        self._store: Optional[IndexedWalletStore] = None
        self._poller: Optional[BatchPositionPoller] = None

        # State
        self._running = False
        self._backfill_complete = False
        self._stats = {
            "blocks_indexed": 0,
            "addresses_discovered": 0,
            "positions_tracked": 0,
            "start_time": 0,
            "backfill_time": 0
        }

        # Callbacks
        self._on_wallet_discovered: Optional[Callable] = None
        self._on_position_update: Optional[Callable] = None
        self._on_proximity_update: Optional[Callable] = None

    async def start(self):
        """
        Start the indexer.

        1. Initialize all components
        2. Start backfill task
        3. Start position polling
        """
        self._running = True
        self._stats["start_time"] = time.time()
        self._logger.info("Starting Hyperliquid indexer...")

        # Initialize components
        await self._init_components()

        # Start background tasks
        asyncio.create_task(self._backfill_task())
        asyncio.create_task(self._live_index_task())

        # Start position polling
        await self._poller.start()

        self._logger.info("Indexer started successfully")

    async def stop(self):
        """Stop the indexer gracefully."""
        self._running = False

        if self._poller:
            await self._poller.stop()
        if self._fetcher:
            await self._fetcher.stop()

        self._logger.info("Indexer stopped")

    # =========================================================================
    # Initialization
    # =========================================================================

    async def _init_components(self):
        """Initialize all indexer components."""
        # Block fetcher
        fetcher_config = BlockFetcherConfig(
            s3_bucket=self.config.s3_bucket,
            lookback_blocks=self.config.lookback_blocks,
            checkpoint_path=self.config.checkpoint_path
        )
        self._fetcher = BlockFetcher(fetcher_config)
        await self._fetcher.start()

        # Transaction parser
        self._parser = TransactionParser()

        # Wallet store
        self._store = IndexedWalletStore(self.config.db_path)

        # Position poller
        poller_config = PollerConfig(
            tier1_interval=self.config.tier1_interval,
            tier2_interval=self.config.tier2_interval,
            tier3_interval=self.config.tier3_interval,
            max_requests_per_minute=self.config.max_requests_per_minute
        )
        self._poller = BatchPositionPoller(
            self._client,
            self._store,
            poller_config
        )

        # Setup callbacks
        self._poller.set_position_callback(self._on_position_polled)

        self._logger.info("All components initialized")

    # =========================================================================
    # Backfill Task
    # =========================================================================

    async def _backfill_task(self):
        """
        Discover addresses from trades via REST API.

        Primary discovery method - S3 blocks are not publicly accessible.
        """
        self._logger.info("Starting address discovery from trades...")

        try:
            # Discover addresses from recent trades
            batch_addresses = []
            coins_scanned = 0

            async for addr, coin, volume, timestamp in self._fetcher.discover_addresses_from_trades():
                if not self._running:
                    break

                batch_addresses.append((
                    addr,
                    0,  # block_num not available from trades
                    timestamp,
                    volume,
                    [coin]
                ))

                # Batch insert
                if len(batch_addresses) >= 100:
                    new, updated = self._store.add_wallets_batch(batch_addresses)
                    self._stats["addresses_discovered"] += new
                    batch_addresses = []

                    self._logger.info(
                        f"Discovery progress: {self._stats['addresses_discovered']:,} addresses"
                    )

            # Insert remaining
            if batch_addresses:
                new, _ = self._store.add_wallets_batch(batch_addresses)
                self._stats["addresses_discovered"] += new

            self._backfill_complete = True
            self._stats["backfill_time"] = time.time() - self._stats["start_time"]

            self._logger.info(
                f"Initial discovery complete: {self._stats['addresses_discovered']:,} addresses "
                f"in {self._stats['backfill_time']:.1f}s"
            )

            # Initialize poller with discovered addresses
            await self._poller._initialize_queue()

        except Exception as e:
            self._logger.error(f"Address discovery failed: {e}")
            self._backfill_complete = True  # Allow live discovery to continue

    # =========================================================================
    # Live Indexing Task
    # =========================================================================

    async def _live_index_task(self):
        """
        Continuously discover new addresses from trades.

        Runs continuously after initial discovery completes.
        """
        # Wait for initial discovery to complete
        while not self._backfill_complete and self._running:
            await asyncio.sleep(5.0)

        if not self._running:
            return

        self._logger.info("Starting live address discovery...")

        # Discovery interval (seconds)
        discovery_interval = 300  # 5 minutes

        while self._running:
            try:
                # Discover new addresses from recent trades
                new_count = 0
                async for addr, coin, volume, timestamp in self._fetcher.discover_addresses_from_trades():
                    if not self._running:
                        break

                    is_new = self._store.add_wallet(
                        addr,
                        0,  # block_num
                        timestamp,
                        volume,
                        [coin]
                    )

                    if is_new:
                        new_count += 1
                        self._stats["addresses_discovered"] += 1

                        # Add to poller
                        self._poller.add_wallet(addr)

                        # Callback
                        if self._on_wallet_discovered:
                            await self._on_wallet_discovered(addr, 0)

                if new_count > 0:
                    self._logger.info(f"Live discovery: found {new_count} new addresses")

                # Wait before next discovery cycle
                await asyncio.sleep(discovery_interval)

            except Exception as e:
                self._logger.error(f"Live discovery error: {e}")
                await asyncio.sleep(60)  # Wait before retry

    # =========================================================================
    # Position Tracking
    # =========================================================================

    async def _on_position_polled(self, state: WalletState):
        """Handle position update from poller."""
        total_value = sum(
            pos.position_value for pos in state.positions.values()
        )

        if total_value >= self.config.min_position_for_tracking:
            self._stats["positions_tracked"] += 1

            # Forward to external callback
            if self._on_position_update:
                await self._on_position_update(state)

    # =========================================================================
    # External API
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get indexer statistics."""
        runtime = time.time() - self._stats["start_time"] if self._stats["start_time"] > 0 else 0

        return {
            "running": self._running,
            "backfill_complete": self._backfill_complete,
            "blocks_indexed": self._stats["blocks_indexed"],
            "addresses_discovered": self._stats["addresses_discovered"],
            "positions_tracked": self._stats["positions_tracked"],
            "runtime_seconds": runtime,
            "backfill_time_seconds": self._stats["backfill_time"],
            "fetcher": self._fetcher.get_stats() if self._fetcher else {},
            "parser": self._parser.get_stats() if self._parser else {},
            "store": self._store.get_stats() if self._store else {},
            "poller": self._poller.get_stats() if self._poller else {}
        }

    def get_store(self) -> IndexedWalletStore:
        """Get the indexed wallet store."""
        return self._store

    def get_poller(self) -> BatchPositionPoller:
        """Get the position poller."""
        return self._poller

    def set_wallet_discovered_callback(self, callback: Callable):
        """Set callback for new wallet discovery."""
        self._on_wallet_discovered = callback

    def set_position_update_callback(self, callback: Callable):
        """Set callback for position updates."""
        self._on_position_update = callback
        if self._poller:
            self._poller.set_position_callback(callback)

    # =========================================================================
    # Manual Operations
    # =========================================================================

    async def force_poll_address(self, address: str) -> Optional[WalletState]:
        """Force immediate poll of a specific address."""
        return await self._client.get_clearinghouse_state(address)

    async def poll_all_active(self) -> Dict[str, WalletState]:
        """Poll all wallets with known active positions."""
        active_wallets = self._store.get_active_wallets()
        addresses = [w.address for w in active_wallets]
        return await self._poller.poll_batch(addresses)

    def prune_inactive_wallets(self):
        """Remove inactive wallets from store."""
        if self._store:
            return self._store.prune_inactive()
        return 0
