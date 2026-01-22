"""
Hyperliquid Blockchain Indexer

Indexes Hyperliquid L1 blocks from S3 to discover ALL wallet addresses,
then tracks their positions for liquidation proximity calculation.

Components:
- BlockFetcher: Fetches blocks from S3 (LZ4 + msgpack)
- TransactionParser: Extracts wallet addresses from transactions
- IndexedWalletStore: SQLite storage for discovered wallets
- BatchPositionPoller: Tiered polling of wallet positions
- IndexerCoordinator: Orchestrates all components

Constitutional compliance:
- Only factual observations (addresses, txs, positions)
- No predictions or semantic labels
- Pure structural data collection
"""

from .block_fetcher import BlockFetcher, BlockFetcherConfig, Block
from .tx_parser import TransactionParser, ParsedTransaction, AddressStats
from .indexed_wallets import IndexedWalletStore
from .batch_poller import BatchPositionPoller, PollerConfig
from .coordinator import IndexerCoordinator, IndexerConfig

__all__ = [
    "BlockFetcher",
    "BlockFetcherConfig",
    "Block",
    "TransactionParser",
    "ParsedTransaction",
    "AddressStats",
    "IndexedWalletStore",
    "BatchPositionPoller",
    "PollerConfig",
    "IndexerCoordinator",
    "IndexerConfig",
]
