"""
Position State Manager

Intelligent position state management with tiered refresh.

Key insight: Once we know a position's liquidation_price, we can calculate
proximity using just oracle price updates. We only need to re-read position
state when we suspect it changed (order activity, liquidation, etc.).

Refresh Tiers:
- CRITICAL (<0.5%): Re-read if ANY order activity detected for wallet
- WATCHLIST (<2%): Refresh every 5s OR on order activity
- MONITORED (<5%): Refresh every 30s
- DISCOVERY: Full state scan every 60s to find new positions
"""

import asyncio
import time
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable, Awaitable
from collections import defaultdict

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

from .asset_mapping import get_coin_name, PRIORITY_COINS
from .metrics import PositionStateMetrics
from .streaming_parser import StreamingStateParser, StreamingParserConfig

# Import LiquidationProximity for governance compatibility
from runtime.hyperliquid.types import LiquidationProximity


class RefreshTier(Enum):
    """Position refresh tier based on proximity to liquidation."""
    CRITICAL = "CRITICAL"      # <0.5% - highest priority
    WATCHLIST = "WATCHLIST"    # <2% - high priority
    MONITORED = "MONITORED"    # <5% - medium priority
    DISCOVERY = "DISCOVERY"    # >5% - low priority (found in scans)


@dataclass
class PositionCache:
    """
    Cached position data with proximity tracking.

    The liquidation_price is the key field - it enables real-time
    proximity calculation without re-reading state.
    """
    wallet: str
    coin: str
    size: float                    # Signed (positive=long, negative=short)
    entry_price: float
    liquidation_price: float       # Key field for proximity calc
    margin: float
    side: str                      # "LONG" or "SHORT"
    last_read: float               # When position was last read from state
    last_proximity: float = 0.0    # Last calculated proximity
    refresh_tier: RefreshTier = RefreshTier.DISCOVERY

    @property
    def position_value(self) -> float:
        """Calculate position value in USD."""
        return abs(self.size) * self.entry_price

    def calculate_proximity(self, current_price: float) -> float:
        """
        Calculate distance to liquidation as percentage.

        Returns positive value if safe, negative if past liquidation.
        """
        if self.liquidation_price <= 0 or current_price <= 0:
            return float('inf')  # Can't calculate

        if self.side == "LONG":
            # Long: liquidated when price drops to liq_price
            proximity = (current_price - self.liquidation_price) / current_price
        else:
            # Short: liquidated when price rises to liq_price
            proximity = (self.liquidation_price - current_price) / current_price

        return proximity

    def to_dict(self) -> Dict:
        """Convert to event dict for emission."""
        return {
            'timestamp': self.last_read,
            'symbol': self.coin,
            'wallet_address': self.wallet,
            'position_size': self.size,
            'entry_price': self.entry_price,
            'liquidation_price': self.liquidation_price,
            'leverage': self.position_value / self.margin if self.margin > 0 else 0,
            'margin_used': self.margin,
            'position_value': self.position_value,
            'side': self.side,
            'proximity_pct': self.last_proximity * 100,
            'refresh_tier': self.refresh_tier.value,
            'event_type': 'HL_POSITION',
            'exchange': 'HYPERLIQUID',
        }


@dataclass
class ProximityAlert:
    """Alert when position crosses proximity threshold."""
    wallet: str
    coin: str
    side: str
    proximity_pct: float
    liquidation_price: float
    position_value: float
    old_tier: RefreshTier
    new_tier: RefreshTier
    timestamp: float


class PositionStateManager:
    """
    Intelligent position state management with tiered refresh.

    Caches positions and calculates proximity in real-time using
    oracle prices, only re-reading state when necessary.
    """

    def __init__(
        self,
        state_path: str,
        # Threshold percentages for tiers
        critical_threshold: float = 0.005,    # 0.5%
        watchlist_threshold: float = 0.02,    # 2%
        monitored_threshold: float = 0.05,    # 5%
        # Refresh intervals
        watchlist_interval: float = 5.0,
        monitored_interval: float = 30.0,
        discovery_interval: float = 60.0,
        # Filters
        min_position_value: float = 1000.0,   # Minimum USD to track
        focus_coins: Optional[List[str]] = None,
        # Memory optimization
        skip_initial_scan: bool = True,       # Skip memory-heavy initial scan (default: True for safety)
        # Batch discovery (memory-safe alternative to full_discovery_scan)
        discovery_batch_size: int = 500,      # Wallets per batch
        discovery_batch_interval: float = 10.0,  # Seconds between batches
        enable_fills_bootstrap: bool = True,  # Bootstrap from node_fills on startup
        fills_bootstrap_hours: int = 6,       # Hours of fills to read for bootstrap
        node_data_path: Optional[str] = None,  # Path to node data (for fills bootstrap)
    ):
        """
        Initialize position state manager.

        Args:
            state_path: Path to hyperliquid_data directory (contains abci_state.rmp)
            critical_threshold: Proximity threshold for CRITICAL tier
            watchlist_threshold: Proximity threshold for WATCHLIST tier
            monitored_threshold: Proximity threshold for MONITORED tier
            watchlist_interval: Refresh interval for WATCHLIST positions
            monitored_interval: Refresh interval for MONITORED positions
            discovery_interval: Interval for full discovery scans
            min_position_value: Minimum position value to track
            focus_coins: Only track these coins (None = all)
            skip_initial_scan: Skip the initial discovery scan to save memory (~5GB)
            discovery_batch_size: Number of wallets to process per batch
            discovery_batch_interval: Seconds between batch discovery cycles
            enable_fills_bootstrap: Whether to bootstrap from node_fills on startup
            fills_bootstrap_hours: Hours of fills history to read for bootstrap
            node_data_path: Path to node data directory (for fills bootstrap)
        """
        self._state_path = state_path
        self._state_file = os.path.join(state_path, "abci_state.rmp")

        # Thresholds
        self._critical_threshold = critical_threshold
        self._watchlist_threshold = watchlist_threshold
        self._monitored_threshold = monitored_threshold

        # Intervals
        self._watchlist_interval = watchlist_interval
        self._monitored_interval = monitored_interval
        self._discovery_interval = discovery_interval

        # Filters
        self._min_position_value = min_position_value
        self._focus_coins = set(focus_coins) if focus_coins else None
        self._skip_initial_scan = skip_initial_scan

        # Batch discovery settings
        self._discovery_batch_size = discovery_batch_size
        self._discovery_batch_interval = discovery_batch_interval
        self._enable_fills_bootstrap = enable_fills_bootstrap
        self._fills_bootstrap_hours = fills_bootstrap_hours
        self._node_data_path = node_data_path or os.path.expanduser("~/hl/data")

        # Memory guards
        self._max_cached_positions = 50_000
        self._max_cached_wallets = 10_000

        # Position cache: wallet -> coin -> PositionCache
        self._cache: Dict[str, Dict[str, PositionCache]] = defaultdict(dict)

        # Tier tracking: tier -> set of (wallet, coin) tuples
        self._by_tier: Dict[RefreshTier, Set[Tuple[str, str]]] = {
            RefreshTier.CRITICAL: set(),
            RefreshTier.WATCHLIST: set(),
            RefreshTier.MONITORED: set(),
            RefreshTier.DISCOVERY: set(),
        }

        # Latest prices
        self._prices: Dict[str, float] = {}

        # Timing
        self._last_discovery_scan = 0.0
        self._last_watchlist_refresh = 0.0
        self._last_monitored_refresh = 0.0
        self._last_discovery_batch = 0.0

        # Streaming parser for memory-safe batch discovery
        self._streaming_parser = StreamingStateParser(
            self._state_file,
            StreamingParserConfig(
                batch_size=discovery_batch_size,
                min_position_value=min_position_value,
                focus_coins=self._focus_coins,
            )
        )

        # Metrics
        self.metrics = PositionStateMetrics()

        # Callbacks
        self.on_proximity_alert: Optional[Callable[[ProximityAlert], Awaitable[None]]] = None
        self.on_position_update: Optional[Callable[[Dict], Awaitable[None]]] = None

        # Running state
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None

        # Asset metadata (populated on first state read)
        self._sz_decimals: Dict[int, int] = {}
        self._oracle_prices: Dict[int, float] = {}

        # NOTE: Cached state removed in 2026-01-31 memory safety refactor.
        # The 5-10GB cached state caused OOM. Now using streaming parser instead.

    async def start(self) -> None:
        """Start the position state manager."""
        if self._running:
            return

        self._running = True

        # Bootstrap from fills if enabled (memory-safe alternative to full_discovery_scan)
        if self._enable_fills_bootstrap:
            print("[PositionStateManager] Bootstrapping from node_fills...")
            await self.bootstrap_from_fills()

        # Mark discovery times to prevent immediate full scans
        self._last_discovery_scan = time.time()
        self._last_discovery_batch = time.time()

        # Start refresh loop (uses incremental batch discovery, NOT full_discovery_scan)
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        """Stop the position state manager."""
        self._running = False

        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

    def prune_empty_wallets(self) -> int:
        """
        Remove empty wallet entries from cache (memory guard).

        Call periodically to clean up wallets with no positions.

        Returns number of wallets pruned.
        """
        empty_wallets = [
            wallet for wallet, positions in self._cache.items()
            if not positions
        ]

        for wallet in empty_wallets:
            del self._cache[wallet]

        return len(empty_wallets)

    def prune_stale_prices(self, keep_coins: Optional[set] = None) -> int:
        """
        Remove prices for coins not in cache (memory guard).

        Args:
            keep_coins: Optional set of coins to always keep. If None,
                       keeps only coins that have positions in cache.

        Returns number of prices pruned.
        """
        if keep_coins is None:
            # Get all coins with active positions
            keep_coins = set()
            for wallet_positions in self._cache.values():
                keep_coins.update(wallet_positions.keys())

        to_remove = [coin for coin in self._prices.keys() if coin not in keep_coins]

        for coin in to_remove:
            del self._prices[coin]

        return len(to_remove)

    def estimate_memory_bytes(self) -> int:
        """
        Estimate current memory usage of position cache.

        Rough estimates:
        - PositionCache object: ~500 bytes (strings, floats, refs)
        - Wallet dict entry: ~100 bytes overhead
        - Price entry: ~50 bytes

        Returns:
            Estimated memory usage in bytes
        """
        position_count = sum(len(p) for p in self._cache.values())
        wallet_count = len(self._cache)
        price_count = len(self._prices)

        return (position_count * 500) + (wallet_count * 100) + (price_count * 50)

    def enforce_memory_limits(self) -> int:
        """
        Evict low-priority positions if cache limits exceeded.

        Eviction priority (lowest tier first):
        1. DISCOVERY tier positions
        2. MONITORED tier positions
        Never evicts CRITICAL or WATCHLIST.

        Returns:
            Number of positions evicted
        """
        position_count = sum(len(p) for p in self._cache.values())
        wallet_count = len(self._cache)

        # Check if limits exceeded
        if position_count <= self._max_cached_positions and wallet_count <= self._max_cached_wallets:
            return 0

        evicted = 0

        # Evict DISCOVERY tier first
        if position_count > self._max_cached_positions:
            to_evict = position_count - self._max_cached_positions
            for wallet, coin in list(self._by_tier[RefreshTier.DISCOVERY]):
                if evicted >= to_evict:
                    break

                if wallet in self._cache and coin in self._cache[wallet]:
                    del self._cache[wallet][coin]
                    self._by_tier[RefreshTier.DISCOVERY].discard((wallet, coin))
                    evicted += 1

                    # Clean up empty wallet
                    if not self._cache[wallet]:
                        del self._cache[wallet]

        # If still over, evict MONITORED tier
        position_count = sum(len(p) for p in self._cache.values())
        if position_count > self._max_cached_positions:
            to_evict = position_count - self._max_cached_positions
            for wallet, coin in list(self._by_tier[RefreshTier.MONITORED]):
                if evicted >= to_evict:
                    break

                if wallet in self._cache and coin in self._cache[wallet]:
                    del self._cache[wallet][coin]
                    self._by_tier[RefreshTier.MONITORED].discard((wallet, coin))
                    evicted += 1

                    if not self._cache[wallet]:
                        del self._cache[wallet]

        if evicted > 0:
            print(f"[PositionStateManager] Memory limit enforced: evicted {evicted} positions")

        return evicted

    def update_prices(self, prices: Dict[str, float]) -> List[ProximityAlert]:
        """
        Update oracle prices and recalculate all proximities.

        Called on every SetGlobalAction (~every 3s).

        Args:
            prices: Dict of symbol -> oracle_price

        Returns:
            List of proximity alerts for positions that crossed thresholds
        """
        self._prices.update(prices)
        alerts = []

        for wallet, positions in self._cache.items():
            for coin, cached in positions.items():
                price = self._prices.get(coin)
                if not price:
                    continue

                # Calculate new proximity
                new_proximity = cached.calculate_proximity(price)
                old_proximity = cached.last_proximity
                cached.last_proximity = new_proximity

                # Determine new tier
                old_tier = cached.refresh_tier
                new_tier = self._determine_tier(new_proximity)

                # Check for tier change
                if new_tier != old_tier:
                    cached.refresh_tier = new_tier

                    # Update tier tracking
                    self._by_tier[old_tier].discard((wallet, coin))
                    self._by_tier[new_tier].add((wallet, coin))

                    # Create alert
                    alert = ProximityAlert(
                        wallet=wallet,
                        coin=coin,
                        side=cached.side,
                        proximity_pct=new_proximity * 100,
                        liquidation_price=cached.liquidation_price,
                        position_value=cached.position_value,
                        old_tier=old_tier,
                        new_tier=new_tier,
                        timestamp=time.time(),
                    )
                    alerts.append(alert)

                    # Update metrics
                    if self._tier_priority(new_tier) > self._tier_priority(old_tier):
                        self.metrics.tier_promotions += 1
                    else:
                        self.metrics.tier_demotions += 1

        # Emit alerts
        for alert in alerts:
            self.metrics.proximity_alerts_emitted += 1
            if self.on_proximity_alert:
                asyncio.create_task(self._safe_callback(
                    self.on_proximity_alert, alert
                ))

        return alerts

    def get_proximity(self, wallet: str, coin: str) -> Optional[float]:
        """Get cached proximity for a position."""
        positions = self._cache.get(wallet)
        if not positions:
            return None
        cached = positions.get(coin)
        return cached.last_proximity if cached else None

    def get_position(self, wallet: str, coin: str) -> Optional[PositionCache]:
        """Get cached position."""
        positions = self._cache.get(wallet)
        return positions.get(coin) if positions else None

    def get_positions_by_tier(self, tier: RefreshTier) -> List[PositionCache]:
        """Get all positions in a specific tier."""
        result = []
        for wallet, coin in self._by_tier[tier]:
            cached = self._cache.get(wallet, {}).get(coin)
            if cached:
                result.append(cached)
        return result

    def get_critical_positions(self) -> List[PositionCache]:
        """Get all CRITICAL tier positions."""
        return self.get_positions_by_tier(RefreshTier.CRITICAL)

    def get_all_positions(self) -> List[PositionCache]:
        """Get all cached positions."""
        result = []
        for wallet, positions in self._cache.items():
            result.extend(positions.values())
        return result

    def get_positions_by_coin(self, coin: str) -> List[PositionCache]:
        """
        Get all positions for a specific coin.

        Args:
            coin: Coin symbol (e.g., "BTC")

        Returns:
            List of PositionCache for the coin
        """
        result = []
        for wallet, positions in self._cache.items():
            if coin in positions:
                result.append(positions[coin])
        return result

    def get_coin_proximity(
        self,
        coin: str,
        threshold_pct: float = 0.02,
    ) -> Optional[LiquidationProximity]:
        """
        Compute aggregate liquidation proximity for a coin.

        This aggregates all positions within threshold_pct of liquidation
        and returns a LiquidationProximity object compatible with governance.

        Args:
            coin: Coin symbol (e.g., "BTC")
            threshold_pct: Proximity threshold (default 0.02 = 2%)

        Returns:
            LiquidationProximity or None if no positions at risk
        """
        positions = self.get_positions_by_coin(coin)
        if not positions:
            return None

        # Get current price from stored prices
        current_price = self._prices.get(coin, 0.0)
        if not current_price:
            # Fallback to entry price if no oracle price
            for pos in positions:
                if pos.entry_price > 0:
                    current_price = pos.entry_price
                    break
        if not current_price:
            return None

        # Aggregate by side
        long_positions = []
        short_positions = []
        now = time.time()

        for pos in positions:
            if pos.liquidation_price <= 0:
                continue

            # Calculate proximity
            proximity = pos.calculate_proximity(current_price)

            if proximity > threshold_pct:
                continue  # Not at risk

            pos_data = {
                'size': abs(pos.size),
                'value': pos.position_value,
                'liq_price': pos.liquidation_price,
                'distance_pct': proximity,
            }

            if pos.side == 'LONG':
                long_positions.append(pos_data)
            elif pos.side == 'SHORT':
                short_positions.append(pos_data)

        total_count = len(long_positions) + len(short_positions)
        if total_count == 0:
            return None

        # Compute long aggregates
        long_count = len(long_positions)
        long_size = sum(p['size'] for p in long_positions)
        long_value = sum(p['value'] for p in long_positions)
        long_closest = min((p['liq_price'] for p in long_positions), default=None)
        long_avg_dist = (
            sum(p['distance_pct'] for p in long_positions) / long_count
            if long_count > 0 else 0.0
        )

        # Compute short aggregates
        short_count = len(short_positions)
        short_size = sum(p['size'] for p in short_positions)
        short_value = sum(p['value'] for p in short_positions)
        short_closest = max((p['liq_price'] for p in short_positions), default=None)
        short_avg_dist = (
            sum(p['distance_pct'] for p in short_positions) / short_count
            if short_count > 0 else 0.0
        )

        return LiquidationProximity(
            coin=coin,
            current_price=current_price,
            threshold_pct=threshold_pct,
            long_positions_count=long_count,
            long_positions_size=long_size,
            long_positions_value=long_value,
            long_avg_distance_pct=long_avg_dist,
            long_closest_liquidation=long_closest,
            short_positions_count=short_count,
            short_positions_size=short_size,
            short_positions_value=short_value,
            short_avg_distance_pct=short_avg_dist,
            short_closest_liquidation=short_closest,
            total_positions_at_risk=total_count,
            total_value_at_risk=long_value + short_value,
            timestamp=now,
        )

    def has_position(self, wallet: str, coin: Optional[str] = None) -> bool:
        """Check if wallet has cached position(s)."""
        positions = self._cache.get(wallet)
        if not positions:
            return False
        if coin:
            return coin in positions
        return len(positions) > 0

    async def on_order_activity(self, wallet: str, coin: str) -> None:
        """
        Handle order activity for a wallet/coin.

        If position is CRITICAL or WATCHLIST, trigger immediate refresh.
        """
        cached = self._cache.get(wallet, {}).get(coin)
        if not cached:
            return

        if cached.refresh_tier in (RefreshTier.CRITICAL, RefreshTier.WATCHLIST):
            # Trigger immediate refresh
            await self.refresh_position(wallet, coin)
            self.metrics.targeted_refreshes += 1

    async def refresh_position(self, wallet: str, coin: str) -> Optional[PositionCache]:
        """
        Refresh a single position from state file.

        This is a targeted read - much faster than full scan.
        """
        # Read position from state
        position_data = await self._read_position_from_state(wallet, coin)

        if position_data is None:
            # Position closed
            if wallet in self._cache and coin in self._cache[wallet]:
                old = self._cache[wallet][coin]
                self._by_tier[old.refresh_tier].discard((wallet, coin))
                del self._cache[wallet][coin]

                # Clean up empty wallet dict (memory guard)
                if not self._cache[wallet]:
                    del self._cache[wallet]

                # Emit closed position event
                if self.on_position_update:
                    event = {
                        'timestamp': time.time(),
                        'symbol': coin,
                        'wallet_address': wallet,
                        'position_size': 0,
                        'side': 'CLOSED',
                        'event_type': 'HL_POSITION',
                        'exchange': 'HYPERLIQUID',
                    }
                    asyncio.create_task(self._safe_callback(
                        self.on_position_update, event
                    ))
            return None

        # Update cache
        return await self._update_cache_from_data(wallet, coin, position_data)

    async def refresh_watchlist(self) -> List[PositionCache]:
        """Refresh all WATCHLIST tier positions."""
        self.metrics.watchlist_refreshes += 1
        updated = []

        for wallet, coin in list(self._by_tier[RefreshTier.WATCHLIST]):
            cached = await self.refresh_position(wallet, coin)
            if cached:
                updated.append(cached)

        self._last_watchlist_refresh = time.time()
        return updated

    async def refresh_monitored(self) -> List[PositionCache]:
        """Refresh all MONITORED tier positions."""
        updated = []

        for wallet, coin in list(self._by_tier[RefreshTier.MONITORED]):
            cached = await self.refresh_position(wallet, coin)
            if cached:
                updated.append(cached)

        self._last_monitored_refresh = time.time()
        return updated

    async def full_discovery_scan(self) -> List[PositionCache]:
        """
        Full state scan to discover new at-risk positions.

        Runs less frequently (every 60s default).
        """
        self.metrics.discovery_scans += 1
        start_time = time.time()

        discovered = []

        try:
            # Parse full state file
            all_positions = await self._parse_full_state()

            for wallet, wallet_positions in all_positions.items():
                for coin, pos_data in wallet_positions.items():
                    # Check focus filter
                    if self._focus_coins and coin not in self._focus_coins:
                        continue

                    # Check minimum value
                    value = abs(pos_data['size']) * pos_data['entry']
                    if value < self._min_position_value:
                        continue

                    # Update cache
                    cached = await self._update_cache_from_data(wallet, coin, pos_data)
                    if cached:
                        discovered.append(cached)

            # Update metrics
            self.metrics.positions_cached = sum(
                len(positions) for positions in self._cache.values()
            )
            self.metrics.wallets_tracked = len(self._cache)
            self.metrics.critical_positions = len(self._by_tier[RefreshTier.CRITICAL])
            self.metrics.watchlist_positions = len(self._by_tier[RefreshTier.WATCHLIST])
            self.metrics.monitored_positions = len(self._by_tier[RefreshTier.MONITORED])

        except Exception as e:
            print(f"[PositionStateManager] Discovery scan error: {e}")

        self._last_discovery_scan = time.time()
        self.metrics.last_discovery_scan_time = self._last_discovery_scan
        self.metrics.last_discovery_scan_duration_ms = (time.time() - start_time) * 1000

        return discovered

    async def incremental_discovery_batch(self, batch_size: Optional[int] = None) -> int:
        """
        Discover positions in batches using streaming parser.

        This is the memory-safe alternative to full_discovery_scan().
        Processes a batch of wallets, then releases memory.

        Args:
            batch_size: Override default batch size

        Returns:
            Number of positions discovered in this batch
        """
        start_time = time.time()

        # Get next batch of wallets
        wallets, is_complete = self._streaming_parser.get_next_discovery_batch()

        if not wallets:
            self._last_discovery_batch = time.time()
            return 0

        discovered = 0

        try:
            # Process positions for this batch
            for wallet, coin, pos_data in self._streaming_parser.iter_positions_batch(wallets):
                cached = await self._update_cache_from_data(wallet, coin, pos_data)
                if cached:
                    discovered += 1

            # Update metrics
            self.metrics.positions_cached = sum(
                len(positions) for positions in self._cache.values()
            )
            self.metrics.wallets_tracked = len(self._cache)
            self.metrics.critical_positions = len(self._by_tier[RefreshTier.CRITICAL])
            self.metrics.watchlist_positions = len(self._by_tier[RefreshTier.WATCHLIST])
            self.metrics.monitored_positions = len(self._by_tier[RefreshTier.MONITORED])

        except Exception as e:
            print(f"[PositionStateManager] Batch discovery error: {e}")

        self._last_discovery_batch = time.time()

        # Log progress periodically
        current, total = self._streaming_parser.get_discovery_progress()
        if is_complete:
            print(f"[PositionStateManager] Discovery cycle complete: {self.metrics.positions_cached} positions cached")

        return discovered

    async def bootstrap_from_fills(self, hours: Optional[int] = None) -> int:
        """
        Bootstrap position cache from recent liquidations in node_fills.

        Wallets that were recently liquidated likely have other at-risk positions.
        This provides immediate position discovery without loading the full state file.

        Args:
            hours: Hours of history to read (default: self._fills_bootstrap_hours)

        Returns:
            Number of positions discovered
        """
        import json
        from datetime import datetime, timedelta
        from pathlib import Path

        hours = hours or self._fills_bootstrap_hours
        fills_dir = Path(self._node_data_path) / "node_fills" / "hourly"

        if not fills_dir.exists():
            print(f"[PositionStateManager] node_fills directory not found: {fills_dir}")
            return 0

        # Collect unique wallets from recent liquidations
        liquidated_wallets: Set[str] = set()
        cutoff = datetime.now() - timedelta(hours=hours)

        try:
            # Iterate through recent date directories
            for date_dir in sorted(fills_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue

                # Check if directory is within our time window
                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y%m%d")
                    if dir_date.date() < cutoff.date():
                        break
                except ValueError:
                    continue

                # Read fills files in this directory
                for fills_file in sorted(date_dir.iterdir(), reverse=True):
                    if not fills_file.is_file():
                        continue

                    try:
                        with open(fills_file, 'r') as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue

                                try:
                                    data = json.loads(line)
                                    if isinstance(data, list) and len(data) >= 2:
                                        wallet = data[0]
                                        fill_data = data[1]

                                        # Check if this is a liquidation
                                        if isinstance(fill_data, dict) and 'liquidation' in fill_data:
                                            liquidated_wallets.add(wallet)

                                            # Also add the liquidated user
                                            liq_info = fill_data['liquidation']
                                            if isinstance(liq_info, dict):
                                                liq_user = liq_info.get('liquidatedUser')
                                                if liq_user:
                                                    liquidated_wallets.add(liq_user)

                                except (json.JSONDecodeError, TypeError):
                                    continue

                    except Exception as e:
                        print(f"[PositionStateManager] Error reading fills file {fills_file}: {e}")
                        continue

        except Exception as e:
            print(f"[PositionStateManager] Error bootstrapping from fills: {e}")

        if not liquidated_wallets:
            print(f"[PositionStateManager] No liquidations found in past {hours}h")
            return 0

        print(f"[PositionStateManager] Found {len(liquidated_wallets)} wallets from recent liquidations")

        # Now load positions for these wallets
        discovered = 0

        try:
            for wallet, coin, pos_data in self._streaming_parser.iter_positions_batch(list(liquidated_wallets)):
                cached = await self._update_cache_from_data(wallet, coin, pos_data)
                if cached:
                    discovered += 1

            # Update metrics
            self.metrics.positions_cached = sum(
                len(positions) for positions in self._cache.values()
            )
            self.metrics.wallets_tracked = len(self._cache)
            self.metrics.critical_positions = len(self._by_tier[RefreshTier.CRITICAL])
            self.metrics.watchlist_positions = len(self._by_tier[RefreshTier.WATCHLIST])
            self.metrics.monitored_positions = len(self._by_tier[RefreshTier.MONITORED])

        except Exception as e:
            print(f"[PositionStateManager] Error loading positions for liquidated wallets: {e}")

        print(f"[PositionStateManager] Bootstrap complete: {discovered} positions from {len(liquidated_wallets)} wallets")

        return discovered

    # ==================== Internal Methods ====================

    def _determine_tier(self, proximity: float) -> RefreshTier:
        """Determine refresh tier based on proximity."""
        if proximity < self._critical_threshold:
            return RefreshTier.CRITICAL
        elif proximity < self._watchlist_threshold:
            return RefreshTier.WATCHLIST
        elif proximity < self._monitored_threshold:
            return RefreshTier.MONITORED
        else:
            return RefreshTier.DISCOVERY

    def _tier_priority(self, tier: RefreshTier) -> int:
        """Get numeric priority for tier (higher = more urgent)."""
        return {
            RefreshTier.CRITICAL: 4,
            RefreshTier.WATCHLIST: 3,
            RefreshTier.MONITORED: 2,
            RefreshTier.DISCOVERY: 1,
        }.get(tier, 0)

    def _get_oracle_price_by_coin(self, coin: str) -> float:
        """Get oracle price by coin name (looks up asset ID)."""
        # First check the live prices from bridge updates
        if coin in self._prices:
            return self._prices[coin]

        # Fall back to oracle prices from state file (keyed by asset ID)
        # Need to reverse lookup: coin name -> asset ID
        from .asset_mapping import COIN_TO_ASSET_ID
        asset_id = COIN_TO_ASSET_ID.get(coin)
        if asset_id is not None and asset_id in self._oracle_prices:
            return self._oracle_prices[asset_id]

        return 0

    async def _update_cache_from_data(
        self,
        wallet: str,
        coin: str,
        pos_data: Dict
    ) -> Optional[PositionCache]:
        """Update cache from parsed position data."""
        try:
            size = pos_data['size']
            side = "LONG" if size > 0 else "SHORT"

            # Get current price for proximity calculation
            # Try live prices first, then oracle prices from state
            price = self._get_oracle_price_by_coin(coin)

            cached = PositionCache(
                wallet=wallet,
                coin=coin,
                size=size,
                entry_price=pos_data['entry'],
                liquidation_price=pos_data['liq'],
                margin=pos_data['margin'],
                side=side,
                last_read=time.time(),
            )

            # Calculate proximity if price and liq price available
            if price > 0 and pos_data['liq'] > 0:
                cached.last_proximity = cached.calculate_proximity(price)
                cached.refresh_tier = self._determine_tier(cached.last_proximity)
            else:
                cached.refresh_tier = RefreshTier.DISCOVERY

            # Update tier tracking
            old_cached = self._cache.get(wallet, {}).get(coin)
            if old_cached:
                self._by_tier[old_cached.refresh_tier].discard((wallet, coin))

            self._cache[wallet][coin] = cached
            self._by_tier[cached.refresh_tier].add((wallet, coin))

            # Emit update
            if self.on_position_update:
                asyncio.create_task(self._safe_callback(
                    self.on_position_update, cached.to_dict()
                ))

            return cached

        except Exception:
            return None

    async def _read_position_from_state(
        self,
        wallet: str,
        coin: str
    ) -> Optional[Dict]:
        """
        Read a single position from state file.

        TODO: Optimize to seek directly to wallet if possible.
        For now, does targeted search through state.
        """
        if not MSGPACK_AVAILABLE:
            return None

        try:
            # Run in thread pool (blocking I/O)
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._read_position_sync,
                wallet,
                coin
            )
        except Exception:
            return None

    # NOTE: _get_cached_state was removed in 2026-01-31 memory safety refactor.
    # The 5-10GB cached state caused OOM. Now using streaming parser instead.
    # See incremental_discovery_batch() and bootstrap_from_fills() for memory-safe alternatives.

    def _read_position_sync(self, target_wallet: str, target_coin: str) -> Optional[Dict]:
        """
        Synchronously read position from state file.

        Uses streaming parser for memory-safe access (loads, reads, releases).
        """
        # Use streaming parser to get position for specific wallet/coin
        result = self._streaming_parser.get_position_for_wallet(target_wallet, target_coin)

        if result is None:
            return None

        # If we got a single position back (coin was specified)
        if isinstance(result, dict) and 'size' in result:
            return result

        # If we got all positions for wallet, extract the one we want
        if isinstance(result, dict) and target_coin in result:
            return result[target_coin]

        return None

    async def _parse_full_state(self) -> Dict[str, Dict[str, Dict]]:
        """Parse full state file for discovery scan."""
        if not MSGPACK_AVAILABLE:
            return {}

        try:
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._parse_full_state_sync
            )
        except Exception:
            return {}

    def _parse_full_state_sync(self) -> Dict[str, Dict[str, Dict]]:
        """
        Synchronously parse full state file.

        WARNING: This method loads the entire state file (5-10GB in memory).
        Use incremental_discovery_batch() for memory-safe discovery instead.

        Position data is in: perp_dexs[0].clearinghouse.user_states.user_to_state
        Each user has: p.p = [[asset_id, {s, e, l, M, f}], ...]

        Structure:
        - s: size (scaled by 10^szDecimals, negative for short)
        - e: entry notional (scaled by 1e6)
        - l: leverage info - {I: {l: leverage, u: margin_adj}} for isolated, {C: n} for cross
        - M: margin table ID
        - f: funding info {a, o, c}
        """
        import gc

        if not os.path.exists(self._state_file):
            return {}

        try:
            with open(self._state_file, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)
        except Exception:
            return {}

        positions = {}

        try:
            exchange = data.get('exchange', {})
            perp_dexs = exchange.get('perp_dexs', [])

            if not perp_dexs:
                return {}

            main_dex = perp_dexs[0]
            ch = main_dex.get('clearinghouse', {})

            # Get asset metadata for scaling
            meta = ch.get('meta', {})
            universe = meta.get('universe', [])
            self._sz_decimals = {i: u.get('szDecimals', 0) for i, u in enumerate(universe)}

            # Get oracle prices
            # Formula: price = raw_px / 10^(6 - szDecimals)
            oracle = ch.get('oracle', {})
            pxs = oracle.get('pxs', [])
            self._oracle_prices = {}
            for asset_id, px_data in enumerate(pxs):
                if px_data and isinstance(px_data, list) and px_data:
                    raw_px = px_data[0].get('px', 0)
                    sz_dec = self._sz_decimals.get(asset_id, 0)
                    scale = 10 ** (6 - sz_dec)
                    self._oracle_prices[asset_id] = raw_px / scale

            # Get user states
            us = ch.get('user_states', {})
            users_with_positions = set(us.get('users_with_positions', []))
            user_to_state = us.get('user_to_state', [])

            # Build user state map
            user_state_map = {}
            for item in user_to_state:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    user_state_map[item[0]] = item[1]

            # Process users with positions
            for wallet in users_with_positions:
                user_data = user_state_map.get(wallet)
                if not user_data or not isinstance(user_data, dict):
                    continue

                p_data = user_data.get('p', {})
                pos_list = p_data.get('p', [])

                wallet_positions = {}

                for pos_item in pos_list:
                    if not isinstance(pos_item, list) or len(pos_item) < 2:
                        continue

                    asset_id = pos_item[0]
                    pos = pos_item[1]

                    if not isinstance(pos, dict):
                        continue

                    pos_data = self._extract_position_data(asset_id, pos)
                    if pos_data and abs(pos_data['size']) > 0.0001:
                        coin = get_coin_name(asset_id)
                        wallet_positions[coin] = pos_data

                if wallet_positions:
                    positions[wallet] = wallet_positions

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            # Release memory from parsed state (important: don't cache this!)
            if 'data' in dir():
                data.clear()
            gc.collect()

        return positions

    def _extract_position_data(self, asset_id: int, pos: Dict) -> Optional[Dict]:
        """
        Extract position data from state structure.

        Position structure: {s, e, l, M, f}
        - s: size (scaled by 10^szDecimals)
        - e: entry notional (scaled by 1e6)
        - l: {I: {l: leverage, u: margin_adj}} or {C: n}
        - M: margin table ID

        Liquidation price formula (isolated):
        liq_price = entry_price - side * (margin - maint_margin) / |size| / correction
        where correction = 1 - side / maintenance_leverage
        """
        s = pos.get('s', 0)
        if not s:
            return None

        # Get scaling
        sz_dec = self._sz_decimals.get(asset_id, 0)
        size = s / (10 ** sz_dec)

        # Entry notional (scaled by 1e6)
        entry_ntl = pos.get('e', 0) / 1e6

        # Leverage info
        l_data = pos.get('l', {})
        is_isolated = 'I' in l_data

        if is_isolated:
            leverage = l_data['I'].get('l', 1)
            margin_adj = l_data['I'].get('u', 0) / 1e6  # Unrealized margin adjustment
        else:
            leverage = l_data.get('C', 1)
            margin_adj = 0

        # Calculate entry price
        entry_price = entry_ntl / abs(size) if size != 0 else 0

        # Get oracle price for liquidation calculation
        oracle_price = self._oracle_prices.get(asset_id, 0)

        # Calculate liquidation price
        # Formula from Hyperliquid docs:
        # liq_price = entry_price - side * margin_available / |size| / correction
        # where correction = 1 - side / maintenance_leverage
        # and maintenance_leverage = max_leverage * 2 (i.e., half the margin requirement)
        liq_price = 0
        margin = entry_ntl / leverage if leverage > 0 else entry_ntl

        if leverage > 0 and abs(size) > 0:
            side = 1 if size > 0 else -1

            # Maintenance margin is typically half of initial margin (2x the leverage)
            maint_leverage = leverage * 2
            maint_margin = entry_ntl / maint_leverage

            # Correction factor
            correction = 1 - side / maint_leverage

            if correction != 0:
                # For isolated: margin is per-position
                # For cross: margin is shared, but we estimate using position's initial margin
                # Note: Cross margin liq price is less accurate as it depends on account equity
                margin_available = margin - maint_margin
                liq_price = entry_price - side * margin_available / abs(size) / correction

                # Sanity check: liq price should make sense
                # For LONG: liq < entry, For SHORT: liq > entry
                if size > 0 and liq_price >= entry_price:
                    liq_price = 0
                elif size < 0 and liq_price <= entry_price:
                    liq_price = 0
                elif liq_price <= 0 or liq_price > 1e12:
                    liq_price = 0

        return {
            'size': size,
            'entry': entry_price,
            'liq': liq_price,
            'margin': margin,
            'leverage': leverage,
            'is_isolated': is_isolated,
        }

    async def _refresh_loop(self) -> None:
        """Background loop for periodic refreshes."""
        while self._running:
            try:
                now = time.time()

                # Check watchlist refresh
                if now - self._last_watchlist_refresh >= self._watchlist_interval:
                    if self._by_tier[RefreshTier.WATCHLIST]:
                        await self.refresh_watchlist()

                # Check monitored refresh
                if now - self._last_monitored_refresh >= self._monitored_interval:
                    if self._by_tier[RefreshTier.MONITORED]:
                        await self.refresh_monitored()

                # Incremental batch discovery (memory-safe alternative to full_discovery_scan)
                # Processes a batch of wallets every discovery_batch_interval seconds
                if now - self._last_discovery_batch >= self._discovery_batch_interval:
                    await self.incremental_discovery_batch()

                    # Enforce memory limits after discovery
                    self.enforce_memory_limits()

                # Sleep a bit
                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _safe_callback(self, callback, *args):
        """Safely call a callback."""
        try:
            await callback(*args)
        except Exception:
            pass
