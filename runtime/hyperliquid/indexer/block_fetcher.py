"""
Hyperliquid Block Fetcher

Fetches Hyperliquid transaction data via REST API.

Primary method: REST API trade discovery (discovers addresses from trades)
Fallback: S3 blocks (requires authentication, may not be available)

Constitutional compliance:
- Only fetches raw transaction data
- No interpretation or filtering
- Pure data retrieval
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Any
import aiohttp

# Optional imports for S3 and compression
try:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    import lz4.frame
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


@dataclass
class BlockFetcherConfig:
    """Configuration for block fetcher."""
    # S3 settings
    s3_bucket: str = "hl-mainnet-evm-blocks"
    s3_region: str = "eu-west-2"  # Hyperliquid uses eu-west-2

    # Block range settings
    start_block: Optional[int] = None  # None = auto-detect from latest
    lookback_blocks: int = 500_000  # ~7 days at 1.2s/block

    # Batch settings
    batch_size: int = 100  # Blocks per batch
    max_concurrent_fetches: int = 10  # Parallel S3 requests

    # Checkpoint settings
    checkpoint_path: str = "indexer_checkpoint.json"
    checkpoint_interval: int = 1000  # Save progress every N blocks

    # REST API settings (for live blocks)
    api_url: str = "https://api.hyperliquid.xyz"
    request_timeout: float = 30.0

    # Rate limiting
    s3_delay: float = 0.01  # Delay between S3 requests
    api_delay: float = 0.1  # Delay between API requests


@dataclass
class Block:
    """Parsed block data."""
    block_num: int
    timestamp: float
    transactions: List[Dict[str, Any]]
    raw_data: Optional[bytes] = None

    @property
    def tx_count(self) -> int:
        return len(self.transactions)


class BlockFetcher:
    """
    Hyperliquid block fetcher.

    Fetches blocks from:
    1. S3 for historical blocks (MessagePack + LZ4)
    2. REST API for latest blocks

    Usage:
        fetcher = BlockFetcher(config)
        await fetcher.start()

        # Fetch historical range
        async for block in fetcher.fetch_block_range(start, end):
            process(block)

        # Stream live blocks
        async for block in fetcher.stream_new_blocks():
            process(block)
    """

    def __init__(self, config: Optional[BlockFetcherConfig] = None):
        self.config = config or BlockFetcherConfig()
        self._logger = logging.getLogger("BlockFetcher")

        # Validate dependencies
        if not HAS_BOTO3:
            self._logger.warning("boto3 not installed - S3 fetching disabled")
        if not HAS_LZ4:
            self._logger.warning("lz4 not installed - block decompression disabled")
        if not HAS_MSGPACK:
            self._logger.warning("msgpack not installed - block parsing disabled")

        # State
        self._session: Optional[aiohttp.ClientSession] = None
        self._s3_client = None
        self._running = False
        self._latest_block: int = 0
        self._checkpoint: Dict = {}

    async def start(self):
        """Initialize fetcher resources."""
        self._running = True

        # HTTP session for REST API
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.request_timeout)
        )

        # S3 client (anonymous access)
        if HAS_BOTO3:
            self._s3_client = boto3.client(
                's3',
                region_name=self.config.s3_region,
                config=Config(signature_version=UNSIGNED)
            )

        # Load checkpoint
        self._load_checkpoint()

        # Get latest block number
        self._latest_block = await self._get_latest_block_num()
        self._logger.info(f"Latest block: {self._latest_block}")

    async def stop(self):
        """Clean up resources."""
        self._running = False
        if self._session:
            await self._session.close()
        self._save_checkpoint()

    # =========================================================================
    # Checkpoint Management
    # =========================================================================

    def _load_checkpoint(self):
        """Load checkpoint from file."""
        path = Path(self.config.checkpoint_path)
        if path.exists():
            try:
                with open(path, 'r') as f:
                    self._checkpoint = json.load(f)
                self._logger.info(f"Loaded checkpoint: block {self._checkpoint.get('last_indexed_block', 0)}")
            except Exception as e:
                self._logger.warning(f"Failed to load checkpoint: {e}")
                self._checkpoint = {}
        else:
            self._checkpoint = {}

    def _save_checkpoint(self):
        """Save checkpoint to file."""
        try:
            with open(self.config.checkpoint_path, 'w') as f:
                json.dump(self._checkpoint, f)
        except Exception as e:
            self._logger.error(f"Failed to save checkpoint: {e}")

    def save_progress(self, block_num: int):
        """Save indexing progress."""
        self._checkpoint['last_indexed_block'] = block_num
        self._checkpoint['timestamp'] = time.time()

        if block_num % self.config.checkpoint_interval == 0:
            self._save_checkpoint()
            self._logger.info(f"Checkpoint saved at block {block_num}")

    def get_last_indexed_block(self) -> int:
        """Get last indexed block from checkpoint."""
        return self._checkpoint.get('last_indexed_block', 0)

    # =========================================================================
    # Block Number Discovery
    # =========================================================================

    async def _get_latest_block_num(self) -> int:
        """Get the latest block number from REST API."""
        try:
            payload = {"type": "meta"}
            async with self._session.post(
                f"{self.config.api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Meta response contains block info
                    universe = data.get('universe', [])
                    if universe:
                        # Try to extract block from first asset
                        pass
        except Exception as e:
            self._logger.debug(f"Meta request failed: {e}")

        # Fallback: probe S3 to find latest block
        return await self._probe_latest_s3_block()

    async def _probe_latest_s3_block(self) -> int:
        """
        Binary search S3 to find the latest block.

        S3 key format: blocks/{block_num}.msgpack.lz4
        """
        if not self._s3_client:
            return 0

        # Start with an estimate (blocks are ~1.2s, chain started ~2023)
        # Rough estimate: 30M blocks as of 2025
        low = 0
        high = 50_000_000

        while low < high:
            mid = (low + high + 1) // 2

            if await self._block_exists_s3(mid):
                low = mid
            else:
                high = mid - 1

        return low

    async def _block_exists_s3(self, block_num: int) -> bool:
        """Check if block exists in S3."""
        try:
            key = self._get_s3_key(block_num)
            self._s3_client.head_object(
                Bucket=self.config.s3_bucket,
                Key=key
            )
            return True
        except:
            return False

    def _get_s3_key(self, block_num: int) -> str:
        """Get S3 key for a block number."""
        # Hyperliquid uses format: blocks/{block_num}.msgpack.lz4
        return f"blocks/{block_num}.msgpack.lz4"

    # =========================================================================
    # S3 Block Fetching
    # =========================================================================

    async def fetch_block_s3(self, block_num: int) -> Optional[Block]:
        """
        Fetch a single block from S3.

        Returns parsed Block or None on error.
        """
        if not self._s3_client or not HAS_LZ4 or not HAS_MSGPACK:
            return None

        try:
            key = self._get_s3_key(block_num)

            # Fetch from S3
            response = self._s3_client.get_object(
                Bucket=self.config.s3_bucket,
                Key=key
            )
            compressed_data = response['Body'].read()

            # Decompress LZ4
            data = lz4.frame.decompress(compressed_data)

            # Parse MessagePack
            block_data = msgpack.unpackb(data, raw=False)

            # Extract transactions
            txs = block_data.get('transactions', [])
            if isinstance(txs, dict):
                txs = list(txs.values())

            # Get timestamp
            timestamp = block_data.get('timestamp', 0)
            if isinstance(timestamp, str):
                timestamp = float(timestamp) / 1000  # ms to s

            return Block(
                block_num=block_num,
                timestamp=timestamp,
                transactions=txs,
                raw_data=data
            )

        except self._s3_client.exceptions.NoSuchKey:
            return None
        except Exception as e:
            self._logger.debug(f"Failed to fetch block {block_num}: {e}")
            return None

    async def fetch_block_range(
        self,
        start: int,
        end: int
    ) -> AsyncIterator[Block]:
        """
        Fetch a range of blocks from S3.

        Yields blocks in order from start to end.
        Uses parallel fetching for efficiency.
        """
        self._logger.info(f"Fetching blocks {start} to {end} ({end - start + 1} blocks)")

        current = start
        while current <= end and self._running:
            # Fetch batch in parallel
            batch_end = min(current + self.config.batch_size - 1, end)
            tasks = []

            for block_num in range(current, batch_end + 1):
                tasks.append(self.fetch_block_s3(block_num))
                if len(tasks) >= self.config.max_concurrent_fetches:
                    # Wait for batch
                    results = await asyncio.gather(*tasks)
                    for block in results:
                        if block:
                            yield block
                            self.save_progress(block.block_num)
                    tasks = []
                    await asyncio.sleep(self.config.s3_delay)

            # Process remaining tasks
            if tasks:
                results = await asyncio.gather(*tasks)
                for block in results:
                    if block:
                        yield block
                        self.save_progress(block.block_num)

            current = batch_end + 1

            # Progress logging
            if current % 10000 == 0:
                progress = (current - start) / (end - start + 1) * 100
                self._logger.info(f"Progress: {progress:.1f}% ({current}/{end})")

    async def fetch_latest_blocks(self, count: int) -> List[Block]:
        """Fetch the N most recent blocks."""
        if self._latest_block == 0:
            self._latest_block = await self._get_latest_block_num()

        start = max(0, self._latest_block - count + 1)
        blocks = []

        async for block in self.fetch_block_range(start, self._latest_block):
            blocks.append(block)

        return blocks

    # =========================================================================
    # REST API Block Fetching (for live/recent blocks)
    # =========================================================================

    async def fetch_block_api(self, block_num: int) -> Optional[Block]:
        """
        Fetch a block via REST API (for recent blocks not yet in S3).

        Note: Hyperliquid REST API may have limited block history.
        """
        try:
            # Hyperliquid info API can return block data
            payload = {
                "type": "blockDetails",
                "blockNumber": block_num
            }

            async with self._session.post(
                f"{self.config.api_url}/info",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                if not data:
                    return None

                txs = data.get('transactions', [])
                timestamp = data.get('timestamp', time.time())

                return Block(
                    block_num=block_num,
                    timestamp=timestamp,
                    transactions=txs
                )

        except Exception as e:
            self._logger.debug(f"API block fetch failed: {e}")
            return None

    # =========================================================================
    # Live Block Streaming
    # =========================================================================

    async def stream_new_blocks(self) -> AsyncIterator[Block]:
        """
        Stream new blocks as they are produced.

        Polls for new blocks and yields them in order.
        """
        last_seen = self._latest_block or await self._get_latest_block_num()
        self._logger.info(f"Starting live stream from block {last_seen}")

        while self._running:
            try:
                # Check for new blocks
                current_latest = await self._get_latest_block_num()

                if current_latest > last_seen:
                    # Fetch new blocks
                    for block_num in range(last_seen + 1, current_latest + 1):
                        block = await self.fetch_block_s3(block_num)
                        if not block:
                            block = await self.fetch_block_api(block_num)

                        if block:
                            yield block
                            last_seen = block_num
                            self._latest_block = block_num

                # Wait before next poll (Hyperliquid ~1.2s block time)
                await asyncio.sleep(1.0)

            except Exception as e:
                self._logger.error(f"Live stream error: {e}")
                await asyncio.sleep(5.0)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_start_block(self) -> int:
        """
        Determine starting block for indexing.

        Priority:
        1. Checkpoint (resume from last indexed)
        2. Config start_block
        3. Latest - lookback
        """
        # Resume from checkpoint
        checkpoint_block = self.get_last_indexed_block()
        if checkpoint_block > 0:
            return checkpoint_block + 1

        # Use config start block
        if self.config.start_block:
            return self.config.start_block

        # Default: latest - lookback
        return max(0, self._latest_block - self.config.lookback_blocks)

    async def get_block_count(self) -> int:
        """Get total number of blocks to index."""
        start = self.get_start_block()
        return self._latest_block - start + 1

    def get_stats(self) -> Dict:
        """Get fetcher statistics."""
        return {
            "latest_block": self._latest_block,
            "last_indexed": self.get_last_indexed_block(),
            "has_s3": HAS_BOTO3 and self._s3_client is not None,
            "has_lz4": HAS_LZ4,
            "has_msgpack": HAS_MSGPACK
        }

    # =========================================================================
    # Trade-Based Discovery (Primary Method)
    # =========================================================================

    async def discover_addresses_from_trades(
        self,
        coins: List[str] = None,
        lookback_hours: float = 24.0
    ) -> AsyncIterator[tuple]:
        """
        Discover addresses from recent trades via REST API.

        This is the primary discovery method since S3 isn't publicly accessible.

        Yields:
            (address, coin, volume, timestamp) tuples
        """
        if coins is None:
            coins = ["BTC", "ETH", "SOL", "HYPE", "XRP", "DOGE", "AVAX", "BNB"]

        seen_addresses = set()

        for coin in coins:
            if not self._running:
                break

            try:
                payload = {"type": "recentTrades", "coin": coin}

                async with self._session.post(
                    f"{self.config.api_url}/info",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        continue

                    trades = await response.json()

                    for trade in trades:
                        users = trade.get('users', [])
                        px = float(trade.get('px', 0))
                        sz = float(trade.get('sz', 0))
                        volume = px * sz
                        timestamp = trade.get('time', time.time() * 1000) / 1000

                        for addr in users:
                            if addr and addr.lower() not in seen_addresses:
                                seen_addresses.add(addr.lower())
                                yield (addr.lower(), coin, volume, timestamp)

                await asyncio.sleep(self.config.api_delay)

            except Exception as e:
                self._logger.debug(f"Trade discovery error for {coin}: {e}")

    async def discover_all_addresses(
        self,
        coins: List[str] = None,
        min_volume: float = 0
    ) -> set:
        """
        Discover all addresses from recent trades.

        Returns:
            Set of discovered addresses
        """
        addresses = set()

        async for addr, coin, volume, timestamp in self.discover_addresses_from_trades(coins):
            if volume >= min_volume:
                addresses.add(addr)

        return addresses
