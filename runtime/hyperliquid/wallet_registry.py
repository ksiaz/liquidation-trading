"""
Dynamic Wallet Registry

Manages whale wallet discovery, tracking, and pruning.
Wallets are stored in PostgreSQL with activity timestamps.

Usage:
    registry = WalletRegistry()
    await registry.refresh_from_hyperdash()  # Discover new whales
    await registry.update_activity()          # Check which are active
    wallets = registry.get_active_wallets()   # Get for tracking
"""

import time
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from runtime.logging.pg_pool import get_conn, put_conn

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
    - PostgreSQL storage for persistence
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

    def __init__(self, **kwargs):
        self._logger = logging.getLogger("WalletRegistry")
        self._load_static_wallets()

    def _load_static_wallets(self):
        """Load static wallets from whale_wallets.py into registry."""
        conn = get_conn()
        try:
            now = time.time()
            cur = conn.cursor()

            # System wallets (never pruned)
            for w in SYSTEM_WALLETS:
                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, first_seen, last_active, notes)
                    VALUES (%s, %s, 'SYSTEM', 'static', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (w.address.lower(), w.label, now, now, w.notes))

            # Curated whale wallets
            for w in WHALE_WALLETS:
                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, first_seen, last_active, notes)
                    VALUES (%s, %s, 'WHALE', 'curated', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (w.address.lower(), w.label, now, now, w.notes))

            # Vault wallets
            for w in VAULT_WALLETS:
                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, first_seen, last_active, notes)
                    VALUES (%s, %s, 'VAULT', 'static', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (w.address.lower(), w.label, now, now, w.notes))

            conn.commit()
            self._logger.info("Loaded static wallets into registry")
        finally:
            put_conn(conn)

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

        conn = get_conn()
        try:
            conn.cursor().execute("""
                INSERT INTO wallet_registry
                (address, label, wallet_type, source, first_seen, last_active, notes)
                VALUES (%s, %s, %s, %s,
                    COALESCE((SELECT first_seen FROM wallet_registry WHERE address = %s), %s),
                    %s, %s)
                ON CONFLICT (address) DO UPDATE SET
                    label = EXCLUDED.label,
                    wallet_type = EXCLUDED.wallet_type,
                    source = EXCLUDED.source,
                    last_active = EXCLUDED.last_active,
                    notes = EXCLUDED.notes
            """, (addr, label, wallet_type, source, addr, now, now, notes))
            conn.commit()
        finally:
            put_conn(conn)

    def add_wallets_batch(self, addresses: List[str], source: str = "hyperdash"):
        """Add multiple wallets efficiently."""
        now = time.time()
        conn = get_conn()
        try:
            cur = conn.cursor()
            for i, addr in enumerate(addresses):
                addr = addr.lower()
                label = f"{source.capitalize()}-{i+1:03d}"
                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, first_seen, last_active)
                    VALUES (%s, %s, 'DISCOVERED', %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (addr, label, source, now, now))

            conn.commit()
            self._logger.info(f"Added {len(addresses)} wallets from {source}")
        finally:
            put_conn(conn)

    def update_activity(self, address: str, position_value: float):
        """Update wallet activity (called when position data received)."""
        conn = get_conn()
        try:
            conn.cursor().execute("""
                UPDATE wallet_registry
                SET position_value = %s, last_active = %s
                WHERE address = %s
            """, (position_value, time.time(), address.lower()))
            conn.commit()
        finally:
            put_conn(conn)

    def update_activities_batch(self, updates: List[Tuple[str, float]]):
        """Batch update wallet activities."""
        now = time.time()
        conn = get_conn()
        try:
            cur = conn.cursor()
            for addr, position_value in updates:
                cur.execute("""
                    UPDATE wallet_registry
                    SET position_value = %s, last_active = %s
                    WHERE address = %s
                """, (position_value, now, addr.lower()))

            conn.commit()
        finally:
            put_conn(conn)

    # =========================================================================
    # Querying
    # =========================================================================

    def get_active_wallets(self, min_position: float = 0) -> List[TrackedWallet]:
        """Get wallets with recent activity and minimum position size."""
        cutoff = time.time() - (self.INACTIVE_DAYS * 24 * 3600)

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address, label, wallet_type, source, position_value,
                       last_active, first_seen, notes
                FROM wallet_registry
                WHERE (last_active > %s OR wallet_type IN ('SYSTEM', 'VAULT'))
                  AND (position_value >= %s OR wallet_type IN ('SYSTEM', 'VAULT'))
                ORDER BY position_value DESC
                LIMIT %s
            """, (cutoff, min_position, self.MAX_TRACKED_WALLETS))

            wallets = []
            for row in cur.fetchall():
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
            return wallets
        finally:
            put_conn(conn)

    def get_tier1_wallets(self) -> List[str]:
        """Get addresses of Tier 1 whales (>$10M positions)."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address FROM wallet_registry
                WHERE position_value >= %s
                ORDER BY position_value DESC
            """, (self.TIER_1_THRESHOLD,))
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_all_addresses(self) -> List[str]:
        """Get all tracked addresses."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT address FROM wallet_registry")
            return [row[0] for row in cur.fetchall()]
        finally:
            put_conn(conn)

    def get_wallet_count(self) -> Dict[str, int]:
        """Get wallet counts by type."""
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT wallet_type, COUNT(*)
                FROM wallet_registry
                GROUP BY wallet_type
            """)
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            put_conn(conn)

    # =========================================================================
    # Pruning
    # =========================================================================

    def prune_inactive(self) -> int:
        """Remove wallets inactive for too long (except SYSTEM/VAULT)."""
        cutoff = time.time() - (self.INACTIVE_DAYS * 24 * 3600)

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM wallet_registry
                WHERE last_active < %s
                  AND wallet_type NOT IN ('SYSTEM', 'VAULT', 'WHALE')
                  AND position_value < %s
            """, (cutoff, self.TIER_3_THRESHOLD))

            deleted = cur.rowcount
            conn.commit()

            if deleted > 0:
                self._logger.info(f"Pruned {deleted} inactive wallets")
            return deleted
        finally:
            put_conn(conn)

    # =========================================================================
    # Live Discovery (from real-time data)
    # =========================================================================

    def add_from_liquidation(
        self,
        address: str,
        liquidation_value: float,
        coin: str = ""
    ) -> bool:
        """Add wallet discovered from a liquidation event."""
        MIN_LIQUIDATION = 20_000

        if liquidation_value < MIN_LIQUIDATION:
            return False

        addr = address.lower()

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT address FROM wallet_registry WHERE address = %s",
                (addr,)
            )
            exists = cur.fetchone() is not None

            if not exists:
                now = time.time()
                notes = f"Liquidated ${liquidation_value:,.0f}"
                if coin:
                    notes += f" on {coin}"

                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                    VALUES (%s, %s, 'DISCOVERED', 'liquidation', %s, %s, %s, %s)
                """, (addr, f"Liq-{addr[:8]}", liquidation_value, now, now, notes))
                conn.commit()
                self._logger.info(f"Discovered whale from liquidation: {addr[:12]}... (${liquidation_value:,.0f})")

            return not exists
        finally:
            put_conn(conn)

    def add_from_large_trade(
        self,
        address: str,
        trade_value: float,
        coin: str = "",
        side: str = ""
    ) -> bool:
        """Add wallet discovered from a large trade."""
        MIN_TRADE = 50_000

        if trade_value < MIN_TRADE:
            return False

        addr = address.lower()

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT address FROM wallet_registry WHERE address = %s",
                (addr,)
            )
            exists = cur.fetchone() is not None

            if not exists:
                now = time.time()
                notes = f"Trade ${trade_value:,.0f}"
                if coin:
                    notes += f" {coin}"
                if side:
                    notes += f" ({side})"

                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                    VALUES (%s, %s, 'DISCOVERED', 'trade', %s, %s, %s, %s)
                """, (addr, f"Trade-{addr[:8]}", trade_value, now, now, notes))
                conn.commit()
                self._logger.info(f"Discovered whale from trade: {addr[:12]}... (${trade_value:,.0f})")

            return not exists
        finally:
            put_conn(conn)

    def add_from_position_snapshot(
        self,
        address: str,
        position_value: float,
        coin: str = ""
    ) -> bool:
        """Add wallet discovered from observing a large position."""
        if position_value < self.TIER_3_THRESHOLD:
            return False

        addr = address.lower()
        now = time.time()

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT address, position_value FROM wallet_registry WHERE address = %s",
                (addr,)
            )
            row = cur.fetchone()

            if row is None:
                notes = f"Position ${position_value:,.0f}"
                if coin:
                    notes += f" ({coin})"

                cur.execute("""
                    INSERT INTO wallet_registry
                    (address, label, wallet_type, source, position_value, first_seen, last_active, notes)
                    VALUES (%s, %s, 'DISCOVERED', 'position', %s, %s, %s, %s)
                """, (addr, f"Pos-{addr[:8]}", position_value, now, now, notes))
                self._logger.info(f"Discovered whale from position: {addr[:12]}... (${position_value:,.0f})")
                added = True
            else:
                cur.execute("""
                    UPDATE wallet_registry
                    SET position_value = %s, last_active = %s
                    WHERE address = %s
                """, (position_value, now, addr))
                added = False

            conn.commit()
            return added
        finally:
            put_conn(conn)

    def get_recent_discoveries(self, hours: float = 24) -> List[TrackedWallet]:
        """Get wallets discovered in the last N hours."""
        cutoff = time.time() - (hours * 3600)

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT address, label, wallet_type, source, position_value,
                       last_active, first_seen, notes
                FROM wallet_registry
                WHERE first_seen > %s
                  AND source IN ('liquidation', 'trade', 'position')
                ORDER BY first_seen DESC
            """, (cutoff,))

            wallets = []
            for row in cur.fetchall():
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
            return wallets
        finally:
            put_conn(conn)

    # =========================================================================
    # Discovery (Hyperdash Scraping)
    # =========================================================================

    async def refresh_from_hyperdash(self):
        """Scrape Hyperdash for new whale addresses."""
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

                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    await asyncio.sleep(1)

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
        """Verify wallet positions using Hyperliquid API."""
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

                await asyncio.sleep(0.05)
            except:
                pass

        self.update_activities_batch(updates)
        self._logger.info(f"Verified {len(addresses)} wallets, {active_count} active")
        return active_count


async def scheduled_refresh(registry: WalletRegistry, client, interval_hours: float = 4):
    """Background task to periodically refresh wallet registry."""
    while True:
        try:
            await registry.refresh_from_hyperdash()
            await registry.verify_positions(client)
            registry.prune_inactive()
        except Exception as e:
            logging.error(f"Scheduled refresh failed: {e}")

        await asyncio.sleep(interval_hours * 3600)
