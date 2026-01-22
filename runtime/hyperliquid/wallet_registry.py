"""
Dynamic Wallet Registry

Manages whale wallet discovery, tracking, and pruning.
Wallets are stored in SQLite with activity timestamps.

Usage:
    registry = WalletRegistry(db_path)
    await registry.refresh_from_hyperdash()  # Discover new whales
    await registry.update_activity()          # Check which are active
    wallets = registry.get_active_wallets()   # Get for tracking
"""

import sqlite3
import time
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Import the static lists as fallback
from .whale_wallets import SYSTEM_WALLETS, WHALE_WALLETS, VAULT_WALLETS, WalletInfo


@dataclass
class TrackedWallet:
    """Wallet with tracking metadata."""
    address: str
    label: str
    wallet_type: str  # SYSTEM, WHALE, VAULT, DISCOVERED
    source: str       # manual, hyperdash, liquidation, etc.
    position_value: float
    last_active: float  # timestamp
    first_seen: float
    notes: str = ""


class WalletRegistry:
    """
    Dynamic wallet registry with automatic discovery and pruning.

    Features:
    - SQLite storage for persistence
    - Automatic refresh from Hyperdash
    - Activity-based pruning (removes inactive wallets)
    - Tiered tracking (prioritize large positions)
    """

    # Tier thresholds (USD) - LOWERED for better liquidation coverage
    TIER_1_THRESHOLD = 10_000_000   # >$10M - always track
    TIER_2_THRESHOLD = 1_000_000    # >$1M - track with lower priority
    TIER_3_THRESHOLD = 50_000       # >$50k - lowered to catch smaller leveraged positions

    # Pruning settings
    INACTIVE_DAYS = 7  # Remove after 7 days of no activity
    MAX_TRACKED_WALLETS = 500  # Limit to avoid API overload

    def __init__(self, db_path: str = "wallet_registry.db"):
        self.db_path = db_path
        self._logger = logging.getLogger("WalletRegistry")
        self._init_db()
        self._load_static_wallets()

    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                address TEXT PRIMARY KEY,
                label TEXT,
                wallet_type TEXT,
                source TEXT,
                position_value REAL DEFAULT 0,
                last_active REAL,
                first_seen REAL,
                notes TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_value
            ON wallets(position_value DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_active
            ON wallets(last_active DESC)
        """)
        conn.commit()
        conn.close()

    def _load_static_wallets(self):
        """Load static wallets from whale_wallets.py into registry."""
        conn = sqlite3.connect(self.db_path)
        now = time.time()

        # System wallets (never pruned)
        for w in SYSTEM_WALLETS:
            conn.execute("""
                INSERT OR IGNORE INTO wallets
                (address, label, wallet_type, source, first_seen, last_active, notes)
                VALUES (?, ?, 'SYSTEM', 'static', ?, ?, ?)
            """, (w.address.lower(), w.label, now, now, w.notes))

        # Curated whale wallets
        for w in WHALE_WALLETS:
            conn.execute("""
                INSERT OR IGNORE INTO wallets
                (address, label, wallet_type, source, first_seen, last_active, notes)
                VALUES (?, ?, 'WHALE', 'curated', ?, ?, ?)
            """, (w.address.lower(), w.label, now, now, w.notes))

        # Vault wallets
        for w in VAULT_WALLETS:
            conn.execute("""
                INSERT OR IGNORE INTO wallets
                (address, label, wallet_type, source, first_seen, last_active, notes)
                VALUES (?, ?, 'VAULT', 'static', ?, ?, ?)
            """, (w.address.lower(), w.label, now, now, w.notes))

        conn.commit()
        conn.close()
        self._logger.info("Loaded static wallets into registry")

    # =========================================================================
    # Wallet Management
    # =========================================================================

    def add_wallet(
        self,
        address: str,
        label: str = None,
        wallet_type: str = "DISCOVERED",
        source: str = "unknown",
        notes: str = ""
    ):
        """Add a wallet to the registry."""
        addr = address.lower()
        label = label or f"Wallet-{addr[:8]}"
        now = time.time()

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO wallets
            (address, label, wallet_type, source, first_seen, last_active, notes)
            VALUES (?, ?, ?, ?,
                COALESCE((SELECT first_seen FROM wallets WHERE address = ?), ?),
                ?, ?)
        """, (addr, label, wallet_type, source, addr, now, now, notes))
        conn.commit()
        conn.close()

    def add_wallets_batch(self, addresses: List[str], source: str = "hyperdash"):
        """Add multiple wallets efficiently."""
        now = time.time()
        conn = sqlite3.connect(self.db_path)

        for i, addr in enumerate(addresses):
            addr = addr.lower()
            label = f"{source.capitalize()}-{i+1:03d}"
            conn.execute("""
                INSERT OR IGNORE INTO wallets
                (address, label, wallet_type, source, first_seen, last_active)
                VALUES (?, ?, 'DISCOVERED', ?, ?, ?)
            """, (addr, label, source, now, now))

        conn.commit()
        conn.close()
        self._logger.info(f"Added {len(addresses)} wallets from {source}")

    def update_activity(self, address: str, position_value: float):
        """Update wallet activity (called when position data received)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE wallets
            SET position_value = ?, last_active = ?
            WHERE address = ?
        """, (position_value, time.time(), address.lower()))
        conn.commit()
        conn.close()

    def update_activities_batch(self, updates: List[Tuple[str, float]]):
        """Batch update wallet activities."""
        now = time.time()
        conn = sqlite3.connect(self.db_path)

        for addr, position_value in updates:
            conn.execute("""
                UPDATE wallets
                SET position_value = ?, last_active = ?
                WHERE address = ?
            """, (position_value, now, addr.lower()))

        conn.commit()
        conn.close()

    # =========================================================================
    # Querying
    # =========================================================================

    def get_active_wallets(self, min_position: float = 0) -> List[TrackedWallet]:
        """Get wallets with recent activity and minimum position size."""
        cutoff = time.time() - (self.INACTIVE_DAYS * 24 * 3600)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address, label, wallet_type, source, position_value,
                   last_active, first_seen, notes
            FROM wallets
            WHERE (last_active > ? OR wallet_type IN ('SYSTEM', 'VAULT'))
              AND (position_value >= ? OR wallet_type IN ('SYSTEM', 'VAULT'))
            ORDER BY position_value DESC
            LIMIT ?
        """, (cutoff, min_position, self.MAX_TRACKED_WALLETS))

        wallets = []
        for row in cursor:
            wallets.append(TrackedWallet(
                address=row[0],
                label=row[1],
                wallet_type=row[2],
                source=row[3],
                position_value=row[4] or 0,
                last_active=row[5] or 0,
                first_seen=row[6] or 0,
                notes=row[7] or ""
            ))

        conn.close()
        return wallets

    def get_tier1_wallets(self) -> List[str]:
        """Get addresses of Tier 1 whales (>$10M positions)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address FROM wallets
            WHERE position_value >= ?
            ORDER BY position_value DESC
        """, (self.TIER_1_THRESHOLD,))
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    def get_all_addresses(self) -> List[str]:
        """Get all tracked addresses."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT address FROM wallets")
        addresses = [row[0] for row in cursor]
        conn.close()
        return addresses

    def get_wallet_count(self) -> Dict[str, int]:
        """Get wallet counts by type."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT wallet_type, COUNT(*)
            FROM wallets
            GROUP BY wallet_type
        """)
        counts = {row[0]: row[1] for row in cursor}
        conn.close()
        return counts

    # =========================================================================
    # Pruning
    # =========================================================================

    def prune_inactive(self) -> int:
        """Remove wallets inactive for too long (except SYSTEM/VAULT)."""
        cutoff = time.time() - (self.INACTIVE_DAYS * 24 * 3600)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            DELETE FROM wallets
            WHERE last_active < ?
              AND wallet_type NOT IN ('SYSTEM', 'VAULT', 'WHALE')
              AND position_value < ?
        """, (cutoff, self.TIER_3_THRESHOLD))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            self._logger.info(f"Pruned {deleted} inactive wallets")
        return deleted

    # =========================================================================
    # Live Discovery (from real-time data)
    # =========================================================================

    def add_from_liquidation(
        self,
        address: str,
        liquidation_value: float,
        coin: str = ""
    ) -> bool:
        """
        Add wallet discovered from a liquidation event.

        Only adds if liquidation is large enough to indicate whale activity.

        Args:
            address: Wallet address that was liquidated
            liquidation_value: USD value of liquidation
            coin: Coin that was liquidated (for notes)

        Returns:
            True if wallet was added, False if too small
        """
        # Minimum liquidation to consider - LOWERED for better coverage
        MIN_LIQUIDATION = 20_000  # $20k liquidation (lowered from $50k)

        if liquidation_value < MIN_LIQUIDATION:
            return False

        addr = address.lower()

        # Check if already tracked
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT address FROM wallets WHERE address = ?",
            (addr,)
        )
        exists = cursor.fetchone() is not None

        if not exists:
            now = time.time()
            notes = f"Liquidated ${liquidation_value:,.0f}"
            if coin:
                notes += f" on {coin}"

            conn.execute("""
                INSERT INTO wallets
                (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                VALUES (?, ?, 'DISCOVERED', 'liquidation', ?, ?, ?, ?)
            """, (addr, f"Liq-{addr[:8]}", liquidation_value, now, now, notes))
            conn.commit()
            self._logger.info(f"Discovered whale from liquidation: {addr[:12]}... (${liquidation_value:,.0f})")

        conn.close()
        return not exists

    def add_from_large_trade(
        self,
        address: str,
        trade_value: float,
        coin: str = "",
        side: str = ""
    ) -> bool:
        """
        Add wallet discovered from a large trade.

        Args:
            address: Wallet address that made the trade
            trade_value: USD value of trade
            coin: Coin traded
            side: BUY or SELL

        Returns:
            True if wallet was added, False if too small or exists
        """
        # Minimum trade to consider - LOWERED for better coverage
        MIN_TRADE = 50_000  # $50k single trade (lowered from $100k)

        if trade_value < MIN_TRADE:
            return False

        addr = address.lower()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT address FROM wallets WHERE address = ?",
            (addr,)
        )
        exists = cursor.fetchone() is not None

        if not exists:
            now = time.time()
            notes = f"Trade ${trade_value:,.0f}"
            if coin:
                notes += f" {coin}"
            if side:
                notes += f" ({side})"

            conn.execute("""
                INSERT INTO wallets
                (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                VALUES (?, ?, 'DISCOVERED', 'trade', ?, ?, ?, ?)
            """, (addr, f"Trade-{addr[:8]}", trade_value, now, now, notes))
            conn.commit()
            self._logger.info(f"Discovered whale from trade: {addr[:12]}... (${trade_value:,.0f})")

        conn.close()
        return not exists

    def add_from_position_snapshot(
        self,
        address: str,
        position_value: float,
        coin: str = ""
    ) -> bool:
        """
        Add wallet discovered from observing a large position.

        Args:
            address: Wallet address with large position
            position_value: Total position value in USD
            coin: Primary coin (for notes)

        Returns:
            True if wallet was added/updated
        """
        # Minimum position to track
        if position_value < self.TIER_3_THRESHOLD:
            return False

        addr = address.lower()
        now = time.time()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT address, position_value FROM wallets WHERE address = ?",
            (addr,)
        )
        row = cursor.fetchone()

        if row is None:
            # New wallet
            notes = f"Position ${position_value:,.0f}"
            if coin:
                notes += f" ({coin})"

            conn.execute("""
                INSERT INTO wallets
                (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                VALUES (?, ?, 'DISCOVERED', 'position', ?, ?, ?, ?)
            """, (addr, f"Pos-{addr[:8]}", position_value, now, now, notes))
            self._logger.info(f"Discovered whale from position: {addr[:12]}... (${position_value:,.0f})")
            added = True
        else:
            # Update existing
            conn.execute("""
                UPDATE wallets
                SET position_value = ?, last_active = ?
                WHERE address = ?
            """, (position_value, now, addr))
            added = False

        conn.commit()
        conn.close()
        return added

    def get_recent_discoveries(self, hours: float = 24) -> List[TrackedWallet]:
        """Get wallets discovered in the last N hours."""
        cutoff = time.time() - (hours * 3600)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT address, label, wallet_type, source, position_value,
                   last_active, first_seen, notes
            FROM wallets
            WHERE first_seen > ?
              AND source IN ('liquidation', 'trade', 'position')
            ORDER BY first_seen DESC
        """, (cutoff,))

        wallets = []
        for row in cursor:
            wallets.append(TrackedWallet(
                address=row[0],
                label=row[1],
                wallet_type=row[2],
                source=row[3],
                position_value=row[4] or 0,
                last_active=row[5] or 0,
                first_seen=row[6] or 0,
                notes=row[7] or ""
            ))

        conn.close()
        return wallets

    # =========================================================================
    # Discovery (Hyperdash Scraping)
    # =========================================================================

    async def refresh_from_hyperdash(self):
        """
        Scrape Hyperdash for new whale addresses.

        This should be run periodically (every 4-6 hours).
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            import re
            import json

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

            driver = webdriver.Chrome(options=options)

            try:
                driver.get("https://hyperdash.info/top-traders")
                await asyncio.sleep(8)

                # Scroll to load content
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1)

                # Extract from network logs
                logs = driver.get_log('performance')
                addresses = set()

                for entry in logs:
                    try:
                        log = json.loads(entry['message'])['message']
                        if log.get('method') == 'Network.responseReceived':
                            url = log['params']['response']['url']
                            request_id = log['params']['requestId']

                            if 'graphql' in url or 'hyperliquid' in url:
                                try:
                                    body = driver.execute_cdp_cmd(
                                        'Network.getResponseBody',
                                        {'requestId': request_id}
                                    )
                                    if body and 'body' in body:
                                        found = re.findall(r'0x[a-fA-F0-9]{40}', body['body'])
                                        addresses.update(found)
                                except:
                                    pass
                    except:
                        pass

                if addresses:
                    self.add_wallets_batch(list(addresses), source="hyperdash")
                    self._logger.info(f"Discovered {len(addresses)} addresses from Hyperdash")

            finally:
                driver.quit()

        except Exception as e:
            self._logger.error(f"Hyperdash refresh failed: {e}")

    async def verify_positions(self, client) -> int:
        """
        Verify wallet positions using Hyperliquid API.

        Args:
            client: HyperliquidClient instance

        Returns:
            Number of wallets with active positions
        """
        addresses = self.get_all_addresses()
        updates = []
        active_count = 0

        for addr in addresses:
            try:
                state = await client.get_clearinghouse_state(addr)
                if state:
                    total_value = 0
                    for pos in state.positions.values():
                        total_value += pos.position_value

                    updates.append((addr, total_value))
                    if total_value > 0:
                        active_count += 1

                await asyncio.sleep(0.05)  # Rate limit
            except:
                pass

        self.update_activities_batch(updates)
        self._logger.info(f"Verified {len(addresses)} wallets, {active_count} active")
        return active_count


# Convenience function for scheduled refresh
async def scheduled_refresh(registry: WalletRegistry, client, interval_hours: float = 4):
    """
    Background task to periodically refresh wallet registry.

    Args:
        registry: WalletRegistry instance
        client: HyperliquidClient instance
        interval_hours: Hours between refreshes
    """
    while True:
        try:
            # Discover new wallets
            await registry.refresh_from_hyperdash()

            # Verify positions
            await registry.verify_positions(client)

            # Prune inactive
            registry.prune_inactive()

        except Exception as e:
            logging.error(f"Scheduled refresh failed: {e}")

        # Wait for next refresh
        await asyncio.sleep(interval_hours * 3600)
