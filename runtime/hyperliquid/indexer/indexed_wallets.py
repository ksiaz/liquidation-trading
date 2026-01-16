"""
Indexed Wallet Store

SQLite storage for blockchain-indexed wallet addresses.
Stores metadata about discovered wallets: first/last block, volume, activity.

Designed to scale to 100,000+ addresses while maintaining query performance.

Constitutional compliance:
- Only stores factual data (addresses, blocks, volumes)
- No scoring, ranking, or importance labels
- Pure structural storage
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class IndexedWallet:
    """Wallet discovered through blockchain indexing."""
    address: str
    first_block_seen: int
    last_block_seen: int
    first_seen_timestamp: float
    last_seen_timestamp: float
    total_tx_count: int
    total_volume_usd: float
    coins_traded: List[str]
    is_active: bool  # Has open positions
    position_value: float
    last_position_check: float
    created_at: float
    updated_at: float


class IndexedWalletStore:
    """
    SQLite-backed store for indexed wallets.

    Features:
    - Efficient batch inserts for indexing
    - Tiered querying (by volume, activity, recency)
    - Position tracking integration
    - Automatic pruning of inactive wallets

    Schema:
        indexed_wallets (
            address TEXT PRIMARY KEY,
            first_block_seen INTEGER,
            last_block_seen INTEGER,
            first_seen_timestamp REAL,
            last_seen_timestamp REAL,
            total_tx_count INTEGER,
            total_volume_usd REAL,
            coins_traded TEXT,  -- JSON array
            is_active INTEGER,
            position_value REAL,
            last_position_check REAL,
            created_at REAL,
            updated_at REAL
        )
    """

    # Tiering thresholds (USD volume)
    TIER_1_VOLUME = 10_000_000   # >$10M total volume
    TIER_2_VOLUME = 1_000_000    # >$1M total volume
    TIER_3_VOLUME = 100_000      # >$100k total volume

    def __init__(self, db_path: str = "indexed_wallets.db"):
        self.db_path = db_path
        self._logger = logging.getLogger("IndexedWalletStore")
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)

        # Main wallets table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexed_wallets (
                address TEXT PRIMARY KEY,
                first_block_seen INTEGER,
                last_block_seen INTEGER,
                first_seen_timestamp REAL,
                last_seen_timestamp REAL,
                total_tx_count INTEGER DEFAULT 0,
                total_volume_usd REAL DEFAULT 0,
                coins_traded TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 0,
                position_value REAL DEFAULT 0,
                last_position_check REAL DEFAULT 0,
                created_at REAL,
                updated_at REAL
            )
        """)

        # Indexes for efficient queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_volume
            ON indexed_wallets(total_volume_usd DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_block
            ON indexed_wallets(last_block_seen DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_value
            ON indexed_wallets(position_value DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_active
            ON indexed_wallets(is_active)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_check
            ON indexed_wallets(last_position_check)
        """)

        # Indexing stats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexing_stats (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            )
        """)

        # Individual positions table for liquidation tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL,
                position_size REAL,
                position_value REAL,
                leverage REAL,
                liquidation_price REAL,
                margin_used REAL,
                unrealized_pnl REAL,
                distance_to_liq_pct REAL,
                daily_volume REAL DEFAULT 0,
                impact_score REAL DEFAULT 0,
                updated_at REAL,
                UNIQUE(wallet_address, coin)
            )
        """)

        # Add columns if they don't exist (migration)
        try:
            conn.execute("ALTER TABLE positions ADD COLUMN daily_volume REAL DEFAULT 0")
        except:
            pass
        try:
            conn.execute("ALTER TABLE positions ADD COLUMN impact_score REAL DEFAULT 0")
        except:
            pass

        # Index for fast liquidation proximity queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_liq_distance
            ON positions(distance_to_liq_pct ASC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_value
            ON positions(position_value DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_impact
            ON positions(impact_score DESC)
        """)

        conn.commit()
        conn.close()
        self._logger.info(f"Initialized indexed wallet store: {self.db_path}")

    # =========================================================================
    # Wallet Management
    # =========================================================================

    def add_wallet(
        self,
        address: str,
        block_num: int,
        timestamp: float,
        volume: float = 0,
        coins: List[str] = None
    ) -> bool:
        """
        Add or update a wallet from blockchain data.

        Returns True if this is a new wallet.
        """
        addr = address.lower()
        coins = coins or []
        now = time.time()

        conn = sqlite3.connect(self.db_path)

        # Check if exists
        cursor = conn.execute(
            "SELECT address, coins_traded, total_tx_count, total_volume_usd FROM indexed_wallets WHERE address = ?",
            (addr,)
        )
        row = cursor.fetchone()

        if row is None:
            # New wallet
            conn.execute("""
                INSERT INTO indexed_wallets
                (address, first_block_seen, last_block_seen, first_seen_timestamp,
                 last_seen_timestamp, total_tx_count, total_volume_usd, coins_traded,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (addr, block_num, block_num, timestamp, timestamp,
                  volume, json.dumps(coins), now, now))
            conn.commit()
            conn.close()
            return True
        else:
            # Update existing
            existing_coins = json.loads(row[1]) if row[1] else []
            all_coins = list(set(existing_coins + coins))

            conn.execute("""
                UPDATE indexed_wallets
                SET last_block_seen = MAX(last_block_seen, ?),
                    last_seen_timestamp = MAX(last_seen_timestamp, ?),
                    total_tx_count = total_tx_count + 1,
                    total_volume_usd = total_volume_usd + ?,
                    coins_traded = ?,
                    updated_at = ?
                WHERE address = ?
            """, (block_num, timestamp, volume, json.dumps(all_coins), now, addr))
            conn.commit()
            conn.close()
            return False

    def add_wallets_batch(
        self,
        wallets: List[Tuple[str, int, float, float, List[str]]]
    ) -> Tuple[int, int]:
        """
        Batch add wallets.

        Args:
            wallets: List of (address, block_num, timestamp, volume, coins)

        Returns:
            (new_count, updated_count)
        """
        if not wallets:
            return (0, 0)

        now = time.time()
        new_count = 0
        updated_count = 0

        conn = sqlite3.connect(self.db_path)

        # Get existing addresses
        addresses = [w[0].lower() for w in wallets]
        placeholders = ','.join('?' * len(addresses))
        cursor = conn.execute(
            f"SELECT address FROM indexed_wallets WHERE address IN ({placeholders})",
            addresses
        )
        existing = {row[0] for row in cursor}

        # Separate new vs update
        for addr, block_num, timestamp, volume, coins in wallets:
            addr = addr.lower()
            coins_json = json.dumps(coins) if coins else '[]'

            if addr in existing:
                conn.execute("""
                    UPDATE indexed_wallets
                    SET last_block_seen = MAX(last_block_seen, ?),
                        last_seen_timestamp = MAX(last_seen_timestamp, ?),
                        total_tx_count = total_tx_count + 1,
                        total_volume_usd = total_volume_usd + ?,
                        updated_at = ?
                    WHERE address = ?
                """, (block_num, timestamp, volume, now, addr))
                updated_count += 1
            else:
                conn.execute("""
                    INSERT INTO indexed_wallets
                    (address, first_block_seen, last_block_seen, first_seen_timestamp,
                     last_seen_timestamp, total_tx_count, total_volume_usd, coins_traded,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """, (addr, block_num, block_num, timestamp, timestamp,
                      volume, coins_json, now, now))
                new_count += 1

        conn.commit()
        conn.close()

        return (new_count, updated_count)

    def update_position(
        self,
        address: str,
        position_value: float,
        is_active: bool = None
    ):
        """Update position data for a wallet."""
        addr = address.lower()
        now = time.time()

        if is_active is None:
            is_active = position_value > 0

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE indexed_wallets
            SET position_value = ?,
                is_active = ?,
                last_position_check = ?,
                updated_at = ?
            WHERE address = ?
        """, (position_value, int(is_active), now, now, addr))
        conn.commit()
        conn.close()

    def update_positions_batch(
        self,
        updates: List[Tuple[str, float]]
    ):
        """Batch update positions."""
        if not updates:
            return

        now = time.time()
        conn = sqlite3.connect(self.db_path)

        for addr, value in updates:
            conn.execute("""
                UPDATE indexed_wallets
                SET position_value = ?,
                    is_active = ?,
                    last_position_check = ?,
                    updated_at = ?
                WHERE address = ?
            """, (value, int(value > 0), now, now, addr.lower()))

        conn.commit()
        conn.close()

    def save_position(
        self,
        wallet_address: str,
        coin: str,
        side: str,
        entry_price: float,
        position_size: float,
        position_value: float,
        leverage: float,
        liquidation_price: float,
        margin_used: float,
        unrealized_pnl: float,
        current_price: float,
        daily_volume: float = 0
    ):
        """Save individual position with liquidation data and impact score."""
        addr = wallet_address.lower()
        now = time.time()

        # Calculate distance to liquidation
        if current_price > 0 and liquidation_price > 0:
            distance_pct = abs(current_price - liquidation_price) / current_price * 100
        else:
            distance_pct = 999.0

        # Calculate impact score = position_value / daily_volume
        # Higher score = more market impact when liquidated
        if daily_volume > 0:
            impact_score = (position_value / daily_volume) * 100  # As percentage of daily volume
        else:
            impact_score = 0

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO positions
            (wallet_address, coin, side, entry_price, position_size, position_value,
             leverage, liquidation_price, margin_used, unrealized_pnl,
             distance_to_liq_pct, daily_volume, impact_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (addr, coin, side, entry_price, position_size, position_value,
              leverage, liquidation_price, margin_used, unrealized_pnl,
              distance_pct, daily_volume, impact_score, now))
        conn.commit()
        conn.close()

    def remove_position(self, wallet_address: str, coin: str):
        """Remove a closed position."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "DELETE FROM positions WHERE wallet_address = ? AND coin = ?",
            (wallet_address.lower(), coin)
        )
        conn.commit()
        conn.close()

    def get_positions_by_liquidation_proximity(
        self,
        max_distance_pct: float = 5.0,
        limit: int = 50
    ) -> List[Dict]:
        """Get positions closest to liquidation."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT wallet_address, coin, side, entry_price, position_size,
                   position_value, leverage, liquidation_price, margin_used,
                   unrealized_pnl, distance_to_liq_pct, updated_at
            FROM positions
            WHERE distance_to_liq_pct <= ?
            ORDER BY distance_to_liq_pct ASC
            LIMIT ?
        """, (max_distance_pct, limit))
        results = [dict(row) for row in cursor]
        conn.close()
        return results

    def get_all_positions(self, limit: int = 100) -> List[Dict]:
        """Get all positions sorted by distance to liquidation."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT wallet_address, coin, side, entry_price, position_size,
                   position_value, leverage, liquidation_price, margin_used,
                   unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
            FROM positions
            ORDER BY distance_to_liq_pct ASC
            LIMIT ?
        """, (limit,))
        results = [dict(row) for row in cursor]
        conn.close()
        return results

    def get_positions_by_impact(
        self,
        max_distance_pct: float = 10.0,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get positions sorted by potential market impact.

        Only includes positions within max_distance_pct of liquidation.
        Sorted by impact_score DESC (highest impact first).

        Impact = position_value / daily_volume (% of daily volume)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT wallet_address, coin, side, entry_price, position_size,
                   position_value, leverage, liquidation_price, margin_used,
                   unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
            FROM positions
            WHERE distance_to_liq_pct <= ? AND impact_score > 0
            ORDER BY impact_score DESC
            LIMIT ?
        """, (max_distance_pct, limit))
        results = [dict(row) for row in cursor]
        conn.close()
        return results

    def get_positions_count(self) -> int:
        """Get total number of tracked positions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM positions")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    # =========================================================================
    # Querying
    # =========================================================================

    def get_wallet(self, address: str) -> Optional[IndexedWallet]:
        """Get wallet by address."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT * FROM indexed_wallets WHERE address = ?",
            (address.lower(),)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_wallet(row)
        return None

    def get_wallets_by_volume(
        self,
        min_volume: float = 0,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets sorted by total volume."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM indexed_wallets
            WHERE total_volume_usd >= ?
            ORDER BY total_volume_usd DESC
            LIMIT ?
        """, (min_volume, limit))
        wallets = [self._row_to_wallet(row) for row in cursor]
        conn.close()
        return wallets

    def get_wallets_by_position(
        self,
        min_position: float = 0,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets sorted by position value."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM indexed_wallets
            WHERE position_value >= ?
            ORDER BY position_value DESC
            LIMIT ?
        """, (min_position, limit))
        wallets = [self._row_to_wallet(row) for row in cursor]
        conn.close()
        return wallets

    def get_active_wallets(self, limit: int = 1000) -> List[IndexedWallet]:
        """Get wallets with active positions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM indexed_wallets
            WHERE is_active = 1
            ORDER BY position_value DESC
            LIMIT ?
        """, (limit,))
        wallets = [self._row_to_wallet(row) for row in cursor]
        conn.close()
        return wallets

    def get_recently_active(
        self,
        min_block: int,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets active after a certain block."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM indexed_wallets
            WHERE last_block_seen >= ?
            ORDER BY last_block_seen DESC
            LIMIT ?
        """, (min_block, limit))
        wallets = [self._row_to_wallet(row) for row in cursor]
        conn.close()
        return wallets

    def get_wallets_needing_check(
        self,
        max_age_seconds: float = 300,
        limit: int = 100
    ) -> List[str]:
        """Get addresses that need position check (oldest first)."""
        cutoff = time.time() - max_age_seconds

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address FROM indexed_wallets
            WHERE last_position_check < ?
            ORDER BY last_position_check ASC
            LIMIT ?
        """, (cutoff, limit))
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    def get_tier1_addresses(self) -> List[str]:
        """Get Tier 1 addresses (>$10M volume)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address FROM indexed_wallets
            WHERE total_volume_usd >= ?
            ORDER BY total_volume_usd DESC
        """, (self.TIER_1_VOLUME,))
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    def get_tier2_addresses(self) -> List[str]:
        """Get Tier 2 addresses (>$1M volume)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address FROM indexed_wallets
            WHERE total_volume_usd >= ? AND total_volume_usd < ?
            ORDER BY total_volume_usd DESC
        """, (self.TIER_2_VOLUME, self.TIER_1_VOLUME))
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    def get_all_addresses(self) -> List[str]:
        """Get all tracked addresses."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT address FROM indexed_wallets")
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    # =========================================================================
    # Stats and Maintenance
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get store statistics."""
        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute("SELECT COUNT(*) FROM indexed_wallets")
        total = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM indexed_wallets WHERE is_active = 1")
        active = cursor.fetchone()[0]

        cursor = conn.execute(f"SELECT COUNT(*) FROM indexed_wallets WHERE total_volume_usd >= {self.TIER_1_VOLUME}")
        tier1 = cursor.fetchone()[0]

        cursor = conn.execute(f"SELECT COUNT(*) FROM indexed_wallets WHERE total_volume_usd >= {self.TIER_2_VOLUME}")
        tier2 = cursor.fetchone()[0]

        cursor = conn.execute("SELECT SUM(total_volume_usd) FROM indexed_wallets")
        total_volume = cursor.fetchone()[0] or 0

        cursor = conn.execute("SELECT SUM(position_value) FROM indexed_wallets WHERE is_active = 1")
        total_positions = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_wallets": total,
            "active_wallets": active,
            "tier1_wallets": tier1,
            "tier2_plus_wallets": tier2,
            "total_volume_usd": total_volume,
            "total_position_value_usd": total_positions
        }

    def save_indexing_stat(self, key: str, value: str):
        """Save an indexing statistic."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO indexing_stats (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, time.time()))
        conn.commit()
        conn.close()

    def get_indexing_stat(self, key: str) -> Optional[str]:
        """Get an indexing statistic."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT value FROM indexing_stats WHERE key = ?",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def prune_inactive(
        self,
        min_volume: float = 1000,
        min_tx_count: int = 2,
        inactive_days: int = 30
    ) -> int:
        """
        Remove low-activity wallets to manage database size.

        Keeps:
        - Wallets with active positions
        - Wallets with volume > min_volume
        - Wallets with tx_count > min_tx_count

        Returns number of wallets pruned.
        """
        cutoff_timestamp = time.time() - (inactive_days * 24 * 3600)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            DELETE FROM indexed_wallets
            WHERE is_active = 0
              AND total_volume_usd < ?
              AND total_tx_count < ?
              AND last_seen_timestamp < ?
        """, (min_volume, min_tx_count, cutoff_timestamp))

        pruned = cursor.rowcount
        conn.commit()
        conn.close()

        if pruned > 0:
            self._logger.info(f"Pruned {pruned} inactive wallets")

        return pruned

    # =========================================================================
    # Helpers
    # =========================================================================

    def _row_to_wallet(self, row) -> IndexedWallet:
        """Convert database row to IndexedWallet."""
        return IndexedWallet(
            address=row[0],
            first_block_seen=row[1],
            last_block_seen=row[2],
            first_seen_timestamp=row[3] or 0,
            last_seen_timestamp=row[4] or 0,
            total_tx_count=row[5] or 0,
            total_volume_usd=row[6] or 0,
            coins_traded=json.loads(row[7]) if row[7] else [],
            is_active=bool(row[8]),
            position_value=row[9] or 0,
            last_position_check=row[10] or 0,
            created_at=row[11] or 0,
            updated_at=row[12] or 0
        )
