# Hyperliquid Blockchain Indexer

## Overview

The Hyperliquid Indexer discovers ALL wallet addresses by indexing Hyperliquid L1 blockchain data from S3, then tracks their positions to provide comprehensive liquidation proximity data.

**Problem:** Current wallet discovery methods (Hyperdash scraping, trade detection) only capture ~500 wallets, missing thousands of active traders.

**Solution:** Index the blockchain to discover every wallet that has ever traded, then poll their positions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Hyperliquid Indexer                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ Block Fetcher│───►│ TX Parser    │───►│ Indexed Wallet   │   │
│  │ (S3 + REST)  │    │ (extract     │    │ Store (SQLite)   │   │
│  │              │    │  addresses)  │    │                  │   │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                   │              │
│                                                   ▼              │
│                                          ┌──────────────────┐   │
│                                          │ Batch Position   │   │
│                                          │ Poller           │   │
│                                          └────────┬─────────┘   │
│                                                   │              │
│                                                   ▼              │
│                                          ┌──────────────────┐   │
│                                          │ Existing         │   │
│                                          │ Collector/Tracker│   │
│                                          └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Block Fetcher (`runtime/hyperliquid/indexer/block_fetcher.py`)

Fetches Hyperliquid L1 blocks from AWS S3.

**Data source:** `s3://hl-mainnet-evm-blocks/` (public, no auth needed)
**Format:** MessagePack + LZ4 compressed

**Configuration:**
```python
BlockFetcherConfig(
    s3_bucket="hl-mainnet-evm-blocks",
    lookback_blocks=500_000,  # ~7 days of history
    batch_size=100,           # Blocks per batch
    checkpoint_interval=1000  # Save progress every N blocks
)
```

### 2. Transaction Parser (`runtime/hyperliquid/indexer/tx_parser.py`)

Extracts wallet addresses from block transactions.

**Transaction types parsed:**
- `order` - Trader placing/canceling orders
- `liquidation` - Address being liquidated
- `withdraw` / `deposit` - User transfers
- `vault_*` - Vault operator actions

### 3. Indexed Wallet Store (`runtime/hyperliquid/indexer/indexed_wallets.py`)

SQLite storage for discovered wallets with blockchain metadata.

**Schema:**
```sql
indexed_wallets (
    address TEXT PRIMARY KEY,
    first_block_seen INTEGER,
    last_block_seen INTEGER,
    total_tx_count INTEGER,
    total_volume_usd REAL,
    coins_traded TEXT,  -- JSON array
    is_active INTEGER,  -- Has open positions
    position_value REAL,
    last_position_check REAL
)
```

### 4. Batch Position Poller (`runtime/hyperliquid/indexer/batch_poller.py`)

Efficiently polls thousands of wallets for positions with tiered priority.

**Polling tiers:**
| Tier | Position Size | Poll Interval |
|------|---------------|---------------|
| 1    | >$1M          | 5 seconds     |
| 2    | >$100k        | 30 seconds    |
| 3    | All others    | 5 minutes     |

**Rate limiting:** Stays under 1000 requests/minute

### 5. Indexer Coordinator (`runtime/hyperliquid/indexer/coordinator.py`)

Orchestrates all components and integrates with existing collector.

---

## Configuration

```python
from runtime.hyperliquid.indexer import IndexerConfig, IndexerCoordinator

config = IndexerConfig(
    # Block fetching
    lookback_blocks=500_000,      # How far back to index
    live_tail=True,               # Follow new blocks

    # Position polling
    tier1_interval=5.0,           # Poll >$1M positions every 5s
    tier2_interval=30.0,          # Poll >$100k every 30s
    tier3_interval=300.0,         # Poll others every 5 min

    # Storage
    db_path="indexed_wallets.db",
    checkpoint_path="indexer_checkpoint.json"
)

indexer = IndexerCoordinator(config, db)
await indexer.start()
```

---

## Data Flow

1. **Block Fetching:** Blocks fetched from S3, decompressed (LZ4), parsed (msgpack)
2. **Address Extraction:** Wallet addresses extracted from transactions
3. **Storage:** Addresses stored in SQLite with metadata (volume, tx count)
4. **Position Polling:** Wallets polled for positions via REST API
5. **Integration:** Position data fed to existing PositionTracker/Collector
6. **Dashboard:** Liquidation proximity displayed in UI

---

## Why Not Binance?

This indexer architecture is Hyperliquid-specific because:

| Feature | Hyperliquid | Binance |
|---------|-------------|---------|
| Data location | Public blockchain | Private database |
| Position visibility | All positions on-chain | Only your own |
| Wallet discovery | Index all transactions | Impossible |
| Pre-liquidation data | Can see positions at risk | Only see after liquidation |

Binance is a centralized exchange - there's no blockchain to index.

---

## Performance Expectations

- **Backfill:** ~2-4 hours for 7 days of history
- **Live indexing:** Keeps up with 1.2s block time
- **Wallet discovery:** Expects 10,000+ unique addresses
- **API rate:** Stays under 1000 requests/minute

---

## Dependencies

```
boto3>=1.26.0      # S3 access
lz4>=4.0.0         # Block decompression
msgpack>=1.0.0     # Block parsing
```

---

## Files

```
runtime/hyperliquid/indexer/
├── __init__.py           # Package exports
├── block_fetcher.py      # S3 fetching, decompression
├── tx_parser.py          # Transaction parsing
├── indexed_wallets.py    # SQLite storage
├── batch_poller.py       # Position polling
└── coordinator.py        # Orchestration
```

---

## Constitutional Compliance

This indexer adheres to system constitutional requirements:

- **Only factual observations:** Addresses, transactions, positions
- **No predictions:** Does not predict liquidations
- **No semantic labels:** No "strong", "weak", "confidence"
- **Pure structural data:** Wallet addresses and their positions
