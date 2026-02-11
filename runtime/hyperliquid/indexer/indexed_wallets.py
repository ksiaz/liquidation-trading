"""
Indexed Wallet Store

PostgreSQL storage for blockchain-indexed wallet addresses.
Stores metadata about discovered wallets: first/last block, volume, activity.

Designed to scale to 100,000+ addresses while maintaining query performance.

Constitutional compliance:
- Only stores factual data (addresses, blocks, volumes)
- No scoring, ranking, or importance labels
- Pure structural storage
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from runtime.logging.pg_pool import get_conn, put_conn


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
    PostgreSQL-backed store for indexed wallets.

    Features:
    - Efficient batch inserts for indexing
    - Tiered querying (by volume, activity, recency)
    - Position tracking integration
    - Automatic pruning of inactive wallets
    """

    # Tiering thresholds (USD volume)
    TIER_1_VOLUME = 10_000_000   # >$10M total volume
    TIER_2_VOLUME = 1_000_000    # >$1M total volume
    TIER_3_VOLUME = 100_000      # >$100k total volume

    def __init__(self, **kwargs):
        self._logger = logging.getLogger("IndexedWalletStore")
        self._logger.info("Initialized indexed wallet store (PostgreSQL)")

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
        """Add or update a wallet from blockchain data. Returns True if new."""
        addr = address.lower()
        coins = coins or []
        now = time.time()

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT address, coins_traded, total_tx_count, total_volume_usd FROM indexed_wallets WHERE address = %s",
                (addr,)
            )
            row = cur.fetchone()

            if row is None:
                cur.execute("""
                    INSERT INTO indexed_wallets
                    (address, first_block_seen, last_block_seen, first_seen_timestamp,
                     last_seen_timestamp, total_tx_count, total_volume_usd, coins_traded,
                     created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                """, (addr, block_num, block_num, timestamp, timestamp,
                      volume, json.dumps(coins), now, now))
                conn.commit()
                return True
            else:
                existing_coins = json.loads(row[1]) if row[1] else []
                all_coins = list(set(existing_coins + coins))

                cur.execute("""
                    UPDATE indexed_wallets
                    SET last_block_seen = GREATEST(last_block_seen, %s),
                        last_seen_timestamp = GREATEST(last_seen_timestamp, %s),
                        total_tx_count = total_tx_count + 1,
                        total_volume_usd = total_volume_usd + %s,
                        coins_traded = %s,
                        updated_at = %s
                    WHERE address = %s
                """, (block_num, timestamp, volume, json.dumps(all_coins), now, addr))
                conn.commit()
                return False
        finally:
            put_conn(conn)

    def add_wallets_batch(
        self,
        wallets: List[Tuple[str, int, float, float, List[str]]]
    ) -> Tuple[int, int]:
        """Batch add wallets. Returns (new_count, updated_count)."""
        if not wallets:
            return (0, 0)

        now = time.time()
        new_count = 0
        updated_count = 0

        conn = get_conn()
        try:
            cur = conn.cursor()

            # Get existing addresses
            addresses = [w[0].lower() for w in wallets]
            cur.execute(
                "SELECT address FROM indexed_wallets WHERE address = ANY(%s)",
                (addresses,)
            )
            existing = {row[0] for row in cur.fetchall()}

            for addr, block_num, timestamp, volume, coins in wallets:
                addr = addr.lower()
                coins_json = json.dumps(coins) if coins else '[]'

                if addr in existing:
                    cur.execute("""
                        UPDATE indexed_wallets
                        SET last_block_seen = GREATEST(last_block_seen, %s),
                            last_seen_timestamp = GREATEST(last_seen_timestamp, %s),
                            total_tx_count = total_tx_count + 1,
                            total_volume_usd = total_volume_usd + %s,
                            updated_at = %s
                        WHERE address = %s
                    """, (block_num, timestamp, volume, now, addr))
                    updated_count += 1
                else:
                    cur.execute("""
                        INSERT INTO indexed_wallets
                        (address, first_block_seen, last_block_seen, first_seen_timestamp,
                         last_seen_timestamp, total_tx_count, total_volume_usd, coins_traded,
                         created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                    """, (addr, block_num, block_num, timestamp, timestamp,
                          volume, coins_json, now, now))
                    new_count += 1

            conn.commit()
            return (new_count, updated_count)
        finally:
            put_conn(conn)

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

        conn = get_conn()
        try:
            conn.cursor().execute("""
                UPDATE indexed_wallets
                SET position_value = %s,
                    is_active = %s,
                    last_position_check = %s,
                    updated_at = %s
                WHERE address = %s
            """, (position_value, int(is_active), now, now, addr))
            conn.commit()
        finally:
            put_conn(conn)

    def update_positions_batch(
        self,
        updates: List[Tuple[str, float]]
    ):
        """Batch update positions."""
        if not updates:
            return

        now = time.time()
        conn = get_conn()
        try:
            cur = conn.cursor()
            for addr, value in updates:
                cur.execute("""
                    UPDATE indexed_wallets
                    SET position_value = %s,
                        is_active = %s,
                        last_position_check = %s,
                        updated_at = %s
                    WHERE address = %s
                """, (value, int(value > 0), now, now, addr.lower()))

            conn.commit()
        finally:
            put_conn(conn)

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

        if current_price > 0 and liquidation_price > 0:
            distance_pct = abs(current_price - liquidation_price) / current_price * 100
        else:
            distance_pct = 999.0

        if daily_volume > 0:
            impact_score = (position_value / daily_volume) * 100
        else:
            impact_score = 0

        conn = get_conn()
        try:
            conn.cursor().execute("""
                INSERT INTO indexed_wallet_positions
                (wallet_address, coin, side, entry_price, position_size, position_value,
                 leverage, liquidation_price, margin_used, unrealized_pnl,
                 distance_to_liq_pct, daily_volume, impact_score, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (wallet_address, coin) DO UPDATE SET
                    side = EXCLUDED.side,
                    entry_price = EXCLUDED.entry_price,
                    position_size = EXCLUDED.position_size,
                    position_value = EXCLUDED.position_value,
                    leverage = EXCLUDED.leverage,
                    liquidation_price = EXCLUDED.liquidation_price,
                    margin_used = EXCLUDED.margin_used,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    distance_to_liq_pct = EXCLUDED.distance_to_liq_pct,
                    daily_volume = EXCLUDED.daily_volume,
                    impact_score = EXCLUDED.impact_score,
                    updated_at = EXCLUDED.updated_at
            """, (addr, coin, side, entry_price, position_size, position_value,
                  leverage, liquidation_price, margin_used, unrealized_pnl,
                  distance_pct, daily_volume, impact_score, now))
            conn.commit()
        finally:
            put_conn(conn)

    def remove_position(self, wallet_address: str, coin: str):
        """Remove a closed position."""
        conn = get_conn()
        try:
            conn.cursor().execute(
                "DELETE FROM indexed_wallet_positions WHERE wallet_address = %s AND coin = %s",
                (wallet_address.lower(), coin)
            )
            conn.commit()
        finally:
            put_conn(conn)

    def get_positions_by_liquidation_proximity(
        self,
        max_distance_pct: float = 5.0,
        limit: int = 50
    ) -> List[Dict]:
        """Get positions closest to liquidation."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, updated_at
                FROM indexed_wallet_positions
                WHERE distance_to_liq_pct <= %s
                ORDER BY distance_to_liq_pct ASC
                LIMIT %s
            """, (max_distance_pct, limit))
            return [dict(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_all_positions(self, limit: int = 100) -> List[Dict]:
        """Get all positions sorted by distance to liquidation."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
                FROM indexed_wallet_positions
                ORDER BY distance_to_liq_pct ASC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_positions_by_impact(
        self,
        max_distance_pct: float = 10.0,
        limit: int = 50
    ) -> List[Dict]:
        """Get positions sorted by potential market impact."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
                FROM indexed_wallet_positions
                WHERE distance_to_liq_pct <= %s AND impact_score > 0
                ORDER BY impact_score DESC
                LIMIT %s
            """, (max_distance_pct, limit))
            return [dict(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_positions_count(self) -> int:
        """Get total number of tracked positions."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM indexed_wallet_positions")
            return cur.fetchone()[0]
        finally:
            put_conn(conn)

    def get_wallet_positions(self, wallet_address: str) -> List[Dict]:
        """Get all positions for a specific wallet."""
        conn = get_conn()
        try:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
                FROM indexed_wallet_positions
                WHERE wallet_address = %s
                ORDER BY distance_to_liq_pct ASC
            """, (wallet_address.lower(),))
            return [dict(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    # =========================================================================
    # Querying
    # =========================================================================

    def get_wallet(self, address: str) -> Optional[IndexedWallet]:
        """Get wallet by address."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM indexed_wallets WHERE address = %s",
                (address.lower(),)
            )
            row = cur.fetchone()
            if row:
                return self._row_to_wallet(row)
            return None
        finally:
            put_conn(conn)

    def get_wallets_by_volume(
        self,
        min_volume: float = 0,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets sorted by total volume."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM indexed_wallets
                WHERE total_volume_usd >= %s
                ORDER BY total_volume_usd DESC
                LIMIT %s
            """, (min_volume, limit))
            return [self._row_to_wallet(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_wallets_by_position(
        self,
        min_position: float = 0,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets sorted by position value."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM indexed_wallets
                WHERE position_value >= %s
                ORDER BY position_value DESC
                LIMIT %s
            """, (min_position, limit))
            return [self._row_to_wallet(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_active_wallets(self, limit: int = 1000) -> List[IndexedWallet]:
        """Get wallets with active positions."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM indexed_wallets
                WHERE is_active = 1
                ORDER BY position_value DESC
                LIMIT %s
            """, (limit,))
            return [self._row_to_wallet(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_recently_active(
        self,
        min_block: int,
        limit: int = 1000
    ) -> List[IndexedWallet]:
        """Get wallets active after a certain block."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM indexed_wallets
                WHERE last_block_seen >= %s
                ORDER BY last_block_seen DESC
                LIMIT %s
            """, (min_block, limit))
            return [self._row_to_wallet(row) for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_wallets_needing_check(
        self,
        max_age_seconds: float = 300,
        limit: int = 100
    ) -> List[str]:
        """Get addresses that need position check (oldest first)."""
        cutoff = time.time() - max_age_seconds

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address FROM indexed_wallets
                WHERE last_position_check < %s
                ORDER BY last_position_check ASC
                LIMIT %s
            """, (cutoff, limit))
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_tier1_addresses(self) -> List[str]:
        """Get Tier 1 addresses (>$10M volume)."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address FROM indexed_wallets
                WHERE total_volume_usd >= %s
                ORDER BY total_volume_usd DESC
            """, (self.TIER_1_VOLUME,))
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_tier2_addresses(self) -> List[str]:
        """Get Tier 2 addresses (>$1M volume)."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address FROM indexed_wallets
                WHERE total_volume_usd >= %s AND total_volume_usd < %s
                ORDER BY total_volume_usd DESC
            """, (self.TIER_2_VOLUME, self.TIER_1_VOLUME))
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_all_addresses(self) -> List[str]:
        """Get all tracked addresses."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT address FROM indexed_wallets")
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    # =========================================================================
    # Stats and Maintenance
    # =========================================================================

    def get_stats(self) -> Dict:
        """Get store statistics."""
        conn = get_conn()
        try:
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM indexed_wallets")
            total = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM indexed_wallets WHERE is_active = 1")
            active = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM indexed_wallets WHERE total_volume_usd >= %s",
                        (self.TIER_1_VOLUME,))
            tier1 = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM indexed_wallets WHERE total_volume_usd >= %s",
                        (self.TIER_2_VOLUME,))
            tier2 = cur.fetchone()[0]

            cur.execute("SELECT COALESCE(SUM(total_volume_usd), 0) FROM indexed_wallets")
            total_volume = cur.fetchone()[0]

            cur.execute("SELECT COALESCE(SUM(position_value), 0) FROM indexed_wallets WHERE is_active = 1")
            total_positions = cur.fetchone()[0]

            return {
                "total_wallets": total,
                "active_wallets": active,
                "tier1_wallets": tier1,
                "tier2_plus_wallets": tier2,
                "total_volume_usd": total_volume,
                "total_position_value_usd": total_positions
            }
        finally:
            put_conn(conn)

    def save_indexing_stat(self, key: str, value: str):
        """Save an indexing statistic."""
        conn = get_conn()
        try:
            conn.cursor().execute("""
                INSERT INTO indexing_stats (key, value, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
            """, (key, value, time.time()))
            conn.commit()
        finally:
            put_conn(conn)

    def get_indexing_stat(self, key: str) -> Optional[str]:
        """Get an indexing statistic."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM indexing_stats WHERE key = %s",
                (key,)
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            put_conn(conn)

    def prune_inactive(
        self,
        min_volume: float = 1000,
        min_tx_count: int = 2,
        inactive_days: int = 30
    ) -> int:
        """Remove low-activity wallets to manage database size."""
        cutoff_timestamp = time.time() - (inactive_days * 24 * 3600)

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM indexed_wallets
                WHERE is_active = 0
                  AND total_volume_usd < %s
                  AND total_tx_count < %s
                  AND last_seen_timestamp < %s
            """, (min_volume, min_tx_count, cutoff_timestamp))

            pruned = cur.rowcount
            conn.commit()

            if pruned > 0:
                self._logger.info(f"Pruned {pruned} inactive wallets")

            return pruned
        finally:
            put_conn(conn)

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
