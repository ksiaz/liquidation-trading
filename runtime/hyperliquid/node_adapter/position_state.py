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

        # Metrics
        self.metrics = PositionStateMetrics()

        # Callbacks
        self.on_proximity_alert: Optional[Callable[[ProximityAlert], Awaitable[None]]] = None
        self.on_position_update: Optional[Callable[[Dict], Awaitable[None]]] = None

        # Running state
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the position state manager."""
        if self._running:
            return

        self._running = True

        # Initial discovery scan
        await self.full_discovery_scan()

        # Start refresh loop
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
            price = self._prices.get(coin)

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

            # Calculate proximity if price available
            if price:
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

    def _read_position_sync(self, target_wallet: str, target_coin: str) -> Optional[Dict]:
        """Synchronously read position from state file."""
        if not os.path.exists(self._state_file):
            return None

        try:
            with open(self._state_file, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)

            blp = data.get('exchange', {}).get('blp', {})
            users = blp.get('u', [])

            for item in users:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue

                wallet = item[0]
                if wallet != target_wallet:
                    continue

                user_data = item[1]
                if not isinstance(user_data, dict):
                    continue

                t = user_data.get('t', [])
                for asset_data in t:
                    if not isinstance(asset_data, list) or len(asset_data) < 2:
                        continue

                    asset_id = asset_data[0]
                    coin = get_coin_name(asset_id)

                    if coin != target_coin:
                        continue

                    pos_list = asset_data[1]
                    return self._extract_position_data(pos_list)

            return None  # Position not found

        except Exception:
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
        """Synchronously parse full state file."""
        if not os.path.exists(self._state_file):
            return {}

        positions = {}

        try:
            with open(self._state_file, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)

            blp = data.get('exchange', {}).get('blp', {})
            users = blp.get('u', [])

            for item in users:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue

                wallet = item[0]
                user_data = item[1]

                if not isinstance(user_data, dict):
                    continue

                t = user_data.get('t', [])
                wallet_positions = {}

                for asset_data in t:
                    if not isinstance(asset_data, list) or len(asset_data) < 2:
                        continue

                    asset_id = asset_data[0]
                    coin = get_coin_name(asset_id)
                    pos_list = asset_data[1]

                    pos_data = self._extract_position_data(pos_list)
                    if pos_data and abs(pos_data['size']) > 0.0001:
                        wallet_positions[coin] = pos_data

                if wallet_positions:
                    positions[wallet] = wallet_positions

        except Exception:
            pass

        return positions

    def _extract_position_data(self, pos_list) -> Optional[Dict]:
        """Extract position data from state structure."""
        if not isinstance(pos_list, list):
            return None

        # pos_list[0] = long position, pos_list[1] = short position
        for i, pos in enumerate(pos_list[:2]):
            if not isinstance(pos, dict):
                continue

            s = pos.get('s', 0)
            if not s or abs(s) < 1e6:  # Minimum 0.01 size
                continue

            size = s / 1e8
            if i == 1:
                size = -size  # Short positions are negative

            return {
                'size': size,
                'entry': pos.get('e', 0) / 1e8,
                'liq': pos.get('l', 0) / 1e8,
                'margin': pos.get('m', 0) / 1e6,
            }

        return None

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

                # Check discovery scan
                if now - self._last_discovery_scan >= self._discovery_interval:
                    await self.full_discovery_scan()

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
