"""
Hyperliquid Position Tracker

Tracks positions across wallets and calculates liquidation proximity.
Core component for the "priming" strategy - knowing what's about to liquidate.

Constitutional compliance:
- Only factual observations
- No predictions or semantic labels
- Pure structural aggregation
"""

import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from collections import defaultdict

from .types import (
    HyperliquidPosition,
    LiquidationProximity,
    PositionSide,
    WalletState,
    SystemWallets
)
from .client import HyperliquidClient
from .whale_wallets import get_all_tracked_wallets, get_whale_wallets
from .wallet_registry import WalletRegistry, TrackedWallet


@dataclass
class TrackerConfig:
    """Configuration for position tracker."""
    # Liquidation proximity thresholds
    proximity_thresholds: tuple = (0.005, 0.01, 0.02, 0.05)  # 0.5%, 1%, 2%, 5%

    # Default threshold for alerts
    default_threshold: float = 0.005  # 0.5%

    # Minimum position value to track (USD)
    min_position_value: float = 1000.0

    # How often to poll REST API for wallets (seconds)
    poll_interval: float = 5.0

    # Track system wallets (HLP, etc.)
    track_system_wallets: bool = True

    # Track whale wallets from registry
    track_whale_wallets: bool = True

    # Use dynamic wallet registry (SQLite-based)
    use_dynamic_registry: bool = False

    # Path to wallet registry database
    registry_db_path: str = "wallet_registry.db"

    # Minimum position value for dynamic wallets
    registry_min_position: float = 100_000.0


class PositionTracker:
    """
    Tracks positions and calculates liquidation proximity.

    Core responsibilities:
    1. Maintain cache of wallet positions
    2. Calculate liquidation distances
    3. Aggregate positions by proximity to liquidation
    4. Emit proximity updates when thresholds are crossed
    """

    def __init__(
        self,
        client: HyperliquidClient,
        config: Optional[TrackerConfig] = None
    ):
        self._client = client
        self._config = config or TrackerConfig()
        self._logger = logging.getLogger("PositionTracker")

        # Position cache: wallet_address -> WalletState
        self._wallet_states: Dict[str, WalletState] = {}

        # Aggregated positions by coin: coin -> List[HyperliquidPosition]
        self._positions_by_coin: Dict[str, List[HyperliquidPosition]] = defaultdict(list)

        # Current prices: coin -> price
        self._prices: Dict[str, float] = {}

        # Latest proximity calculations: coin -> LiquidationProximity
        self._proximity_cache: Dict[str, LiquidationProximity] = {}

        # Callbacks
        self._on_proximity_update: Optional[Callable] = None
        self._on_cascade_alert: Optional[Callable] = None

        # Wallets to track
        self._tracked_wallets: List[str] = []

        # Dynamic wallet registry (optional)
        self._wallet_registry: Optional[WalletRegistry] = None
        if self._config.use_dynamic_registry:
            self._wallet_registry = WalletRegistry(self._config.registry_db_path)

        # Setup wallets
        if self._config.use_dynamic_registry:
            self._setup_from_registry()
        elif self._config.track_system_wallets:
            self._setup_system_wallets()

    def _setup_system_wallets(self):
        """Add system and whale wallets to tracking list."""
        from .whale_wallets import get_system_wallets

        # Always load system wallets
        system_wallets = get_system_wallets()
        for wallet_info in system_wallets:
            self.add_wallet(wallet_info.address)

        whale_count = 0
        # Load whale wallets if enabled
        if self._config.track_whale_wallets:
            whale_wallets = get_whale_wallets()
            for wallet_info in whale_wallets:
                self.add_wallet(wallet_info.address)
            whale_count = len(whale_wallets)

        self._logger.info(
            f"Tracking {len(system_wallets)} system wallets, "
            f"{whale_count} whale wallets"
        )

    def _setup_from_registry(self):
        """Setup wallets from dynamic registry."""
        if not self._wallet_registry:
            return

        # Get active wallets above minimum position threshold
        active_wallets = self._wallet_registry.get_active_wallets(
            min_position=self._config.registry_min_position
        )

        for wallet in active_wallets:
            self.add_wallet(wallet.address)

        self._logger.info(
            f"Loaded {len(active_wallets)} wallets from dynamic registry"
        )

    async def refresh_from_registry(self):
        """
        Refresh wallet list from dynamic registry.

        Call periodically to pick up newly discovered wallets
        and remove inactive ones.
        """
        if not self._wallet_registry:
            self._logger.warning("Dynamic registry not enabled")
            return

        # Get current active wallets
        active_wallets = self._wallet_registry.get_active_wallets(
            min_position=self._config.registry_min_position
        )
        active_addresses = {w.address for w in active_wallets}

        # Add new wallets
        for wallet in active_wallets:
            if wallet.address not in self._tracked_wallets:
                self.add_wallet(wallet.address)
                self._logger.info(
                    f"Added wallet from registry: {wallet.label} "
                    f"(${wallet.position_value:,.0f})"
                )

        # Remove wallets no longer in registry
        to_remove = []
        for tracked in self._tracked_wallets:
            if tracked not in active_addresses:
                # Check if it's a static wallet (don't remove those)
                from .whale_wallets import get_system_wallets
                static_addresses = {w.address.lower() for w in get_system_wallets()}
                if tracked not in static_addresses:
                    to_remove.append(tracked)

        for addr in to_remove:
            self.remove_wallet(addr)
            self._logger.info(f"Removed inactive wallet: {addr[:12]}...")

        self._logger.info(
            f"Registry refresh: {len(active_wallets)} active, "
            f"{len(to_remove)} removed"
        )

    async def discover_new_wallets(self):
        """
        Trigger discovery of new whale wallets via Hyperdash scraping.

        Requires Selenium to be installed.
        """
        if not self._wallet_registry:
            self._logger.warning("Dynamic registry not enabled")
            return

        self._logger.info("Starting wallet discovery from Hyperdash...")
        await self._wallet_registry.refresh_from_hyperdash()

        # Verify discovered wallets have positions
        await self._wallet_registry.verify_positions(self._client)

        # Prune inactive
        pruned = self._wallet_registry.prune_inactive()
        if pruned > 0:
            self._logger.info(f"Pruned {pruned} inactive wallets")

        # Refresh tracker
        await self.refresh_from_registry()

    def get_registry_stats(self) -> Dict:
        """Get statistics from wallet registry."""
        if not self._wallet_registry:
            return {"enabled": False}

        counts = self._wallet_registry.get_wallet_count()
        tier1 = self._wallet_registry.get_tier1_wallets()

        return {
            "enabled": True,
            "wallet_counts": counts,
            "tier1_count": len(tier1),
            "total_tracked": len(self._tracked_wallets)
        }

    async def discover_from_live_trades(
        self,
        coins: List[str] = None,
        min_trade_value: float = 100_000.0
    ) -> int:
        """
        Discover whale addresses from recent large trades.

        Args:
            coins: Coins to scan (default: majors)
            min_trade_value: Minimum trade value to trigger discovery

        Returns:
            Number of new wallets discovered
        """
        if not self._wallet_registry:
            self._logger.warning("Registry not enabled for trade discovery")
            return 0

        discovered = await self._client.discover_whales_from_trades(
            coins=coins,
            min_trade_value=min_trade_value
        )

        new_count = 0
        for whale in discovered:
            added = self._wallet_registry.add_from_large_trade(
                whale['address'],
                whale['trade_value'],
                whale['coin'],
                whale['side']
            )
            if added:
                self.add_wallet(whale['address'])
                new_count += 1

        if new_count > 0:
            self._logger.info(f"Discovered {new_count} whales from live trades")

        return new_count

    # =========================================================================
    # Wallet Management
    # =========================================================================

    def add_wallet(self, wallet_address: str):
        """Add a wallet to track."""
        wallet_lower = wallet_address.lower()
        if wallet_lower not in self._tracked_wallets:
            self._tracked_wallets.append(wallet_lower)
            self._client.add_tracked_wallet(wallet_lower)
            self._logger.debug(f"Tracking wallet: {wallet_lower[:10]}...")

    def add_wallets(self, wallets: List[str]):
        """Add multiple wallets to track."""
        for wallet in wallets:
            self.add_wallet(wallet)

    def remove_wallet(self, wallet_address: str):
        """Remove a wallet from tracking."""
        wallet_lower = wallet_address.lower()
        if wallet_lower in self._tracked_wallets:
            self._tracked_wallets.remove(wallet_lower)
            self._client.remove_tracked_wallet(wallet_lower)
            if wallet_lower in self._wallet_states:
                del self._wallet_states[wallet_lower]

    # =========================================================================
    # Position Updates
    # =========================================================================

    async def update_wallet(self, wallet_address: str) -> Optional[WalletState]:
        """
        Fetch and update state for a specific wallet.

        Returns:
            Updated WalletState or None on error
        """
        state = await self._client.get_clearinghouse_state(wallet_address)
        if state:
            self._wallet_states[wallet_address.lower()] = state
            self._rebuild_position_index()
            await self._recalculate_proximity()
        return state

    async def update_all_wallets(self):
        """Update state for all tracked wallets."""
        for wallet in self._tracked_wallets:
            await self.update_wallet(wallet)

    def on_wallet_update(self, wallet_state: WalletState):
        """
        Handle real-time wallet update from WebSocket.

        Called by HyperliquidClient when webData2 message received.
        """
        self._wallet_states[wallet_state.address.lower()] = wallet_state
        self._rebuild_position_index()
        # Note: proximity recalculation happens on price update

        # Live discovery: add large positions to registry
        if self._wallet_registry:
            total_value = sum(
                pos.position_value for pos in wallet_state.positions.values()
            )
            if total_value >= self._config.registry_min_position:
                # Find largest position for notes
                largest_coin = ""
                if wallet_state.positions:
                    largest = max(
                        wallet_state.positions.values(),
                        key=lambda p: p.position_value
                    )
                    largest_coin = largest.coin

                self._wallet_registry.add_from_position_snapshot(
                    wallet_state.address,
                    total_value,
                    largest_coin
                )

    def on_price_update(self, prices: Dict[str, float]):
        """
        Handle price update.

        Note: Call trigger_proximity_recalc() after this to recalculate proximity.
        (Synchronous method cannot call async _recalculate_proximity directly)
        """
        self._prices.update(prices)
        self._prices_changed = True

    async def trigger_proximity_recalc(self):
        """Trigger proximity recalculation if prices changed."""
        if getattr(self, '_prices_changed', False):
            self._prices_changed = False
            await self._recalculate_proximity()

    def on_liquidation_event(
        self,
        address: str,
        coin: str,
        liquidation_value: float,
        side: str = ""
    ):
        """
        Handle liquidation event - discover whale from liquidation.

        Args:
            address: Wallet that was liquidated
            coin: Coin that was liquidated
            liquidation_value: USD value of liquidation
            side: LONG or SHORT
        """
        if not self._wallet_registry:
            return

        # Add to registry if large enough
        added = self._wallet_registry.add_from_liquidation(
            address,
            liquidation_value,
            coin
        )

        if added:
            # Also start tracking this wallet
            self.add_wallet(address)
            self._logger.info(
                f"Auto-tracking liquidated whale: {address[:12]}... "
                f"(${liquidation_value:,.0f} {coin} {side})"
            )

    def on_large_trade(
        self,
        address: str,
        coin: str,
        trade_value: float,
        side: str = ""
    ):
        """
        Handle large trade event - discover whale from trade.

        Args:
            address: Wallet that made the trade
            coin: Coin traded
            trade_value: USD value of trade
            side: BUY or SELL
        """
        if not self._wallet_registry:
            return

        added = self._wallet_registry.add_from_large_trade(
            address,
            trade_value,
            coin,
            side
        )

        if added:
            self.add_wallet(address)
            self._logger.info(
                f"Auto-tracking whale trader: {address[:12]}... "
                f"(${trade_value:,.0f} {coin} {side})"
            )

    # =========================================================================
    # Position Indexing
    # =========================================================================

    def _rebuild_position_index(self):
        """Rebuild the positions_by_coin index from wallet states."""
        self._positions_by_coin.clear()

        for wallet_state in self._wallet_states.values():
            for coin, position in wallet_state.positions.items():
                # Filter by minimum value
                if position.position_value >= self._config.min_position_value:
                    self._positions_by_coin[coin].append(position)

    def get_positions(self, coin: str) -> List[HyperliquidPosition]:
        """Get all tracked positions for a coin."""
        return self._positions_by_coin.get(coin, [])

    def get_all_positions(self) -> Dict[str, List[HyperliquidPosition]]:
        """Get all tracked positions grouped by coin."""
        return dict(self._positions_by_coin)

    # =========================================================================
    # Liquidation Proximity Calculation
    # =========================================================================

    async def _recalculate_proximity(self):
        """Recalculate liquidation proximity for all coins."""
        for coin in self._positions_by_coin.keys():
            price = self._prices.get(coin)
            if price:
                proximity = self.calculate_proximity(
                    coin,
                    price,
                    self._config.default_threshold
                )
                if proximity:
                    old_proximity = self._proximity_cache.get(coin)
                    self._proximity_cache[coin] = proximity

                    # Emit update if significant change
                    if self._on_proximity_update:
                        await self._on_proximity_update(proximity)

                    # Check for cascade alert conditions
                    await self._check_cascade_alert(proximity, old_proximity)

    def calculate_proximity(
        self,
        coin: str,
        current_price: float,
        threshold_pct: float = 0.005
    ) -> Optional[LiquidationProximity]:
        """
        Calculate liquidation proximity for a coin.

        Aggregates all positions within threshold_pct of their liquidation price.

        Args:
            coin: Coin symbol (e.g., "BTC")
            current_price: Current market price
            threshold_pct: Distance threshold (0.005 = 0.5%)

        Returns:
            LiquidationProximity with aggregated data
        """
        positions = self._positions_by_coin.get(coin, [])
        if not positions or current_price <= 0:
            return None

        # Separate longs and shorts at risk
        longs_at_risk = []
        shorts_at_risk = []

        for pos in positions:
            distance = pos.distance_to_liquidation(current_price)

            if distance <= threshold_pct:
                if pos.side == PositionSide.LONG:
                    # Longs liquidate when price drops (liquidation_price < current_price)
                    if pos.liquidation_price < current_price:
                        longs_at_risk.append((pos, distance))
                else:
                    # Shorts liquidate when price rises (liquidation_price > current_price)
                    if pos.liquidation_price > current_price:
                        shorts_at_risk.append((pos, distance))

        # Aggregate longs
        long_count = len(longs_at_risk)
        long_size = sum(p.abs_size for p, _ in longs_at_risk)
        long_value = sum(p.position_value for p, _ in longs_at_risk)
        long_avg_dist = (
            sum(d for _, d in longs_at_risk) / long_count
            if long_count > 0 else 0.0
        )
        long_closest = (
            min(p.liquidation_price for p, _ in longs_at_risk)
            if longs_at_risk else None
        )

        # Aggregate shorts
        short_count = len(shorts_at_risk)
        short_size = sum(p.abs_size for p, _ in shorts_at_risk)
        short_value = sum(p.position_value for p, _ in shorts_at_risk)
        short_avg_dist = (
            sum(d for _, d in shorts_at_risk) / short_count
            if short_count > 0 else 0.0
        )
        short_closest = (
            max(p.liquidation_price for p, _ in shorts_at_risk)
            if shorts_at_risk else None
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
            total_positions_at_risk=long_count + short_count,
            total_value_at_risk=long_value + short_value,
            timestamp=time.time()
        )

    def get_proximity(self, coin: str) -> Optional[LiquidationProximity]:
        """Get cached liquidation proximity for a coin."""
        return self._proximity_cache.get(coin)

    def get_all_proximity(self) -> Dict[str, LiquidationProximity]:
        """Get all cached liquidation proximity data."""
        return dict(self._proximity_cache)

    # =========================================================================
    # Cascade Detection
    # =========================================================================

    async def _check_cascade_alert(
        self,
        new_proximity: LiquidationProximity,
        old_proximity: Optional[LiquidationProximity]
    ):
        """
        Check if cascade alert should be triggered.

        Alert conditions (structural observations only):
        - Total value at risk increased significantly
        - Number of positions at risk increased
        - Price moved closer to liquidation cluster
        """
        if not self._on_cascade_alert:
            return

        # Minimum thresholds for alert
        MIN_POSITIONS = 5
        MIN_VALUE = 100000  # $100k

        if new_proximity.total_positions_at_risk < MIN_POSITIONS:
            return
        if new_proximity.total_value_at_risk < MIN_VALUE:
            return

        # Check if this is a new cluster or significant change
        should_alert = False

        if old_proximity is None:
            # New cluster detected
            should_alert = True
        else:
            # Significant increase in positions or value
            pos_increase = (
                new_proximity.total_positions_at_risk -
                old_proximity.total_positions_at_risk
            )
            value_increase = (
                new_proximity.total_value_at_risk -
                old_proximity.total_value_at_risk
            )

            if pos_increase >= 3 or value_increase >= 50000:
                should_alert = True

        if should_alert:
            await self._on_cascade_alert(new_proximity)

    # =========================================================================
    # Callbacks
    # =========================================================================

    def set_proximity_callback(self, callback: Callable):
        """Set callback for proximity updates."""
        self._on_proximity_update = callback

    def set_cascade_callback(self, callback: Callable):
        """Set callback for cascade alerts."""
        self._on_cascade_alert = callback

    # =========================================================================
    # Summary Methods
    # =========================================================================

    def get_summary(self) -> Dict:
        """Get summary of tracked positions and proximity."""
        summary = {
            'tracked_wallets': len(self._tracked_wallets),
            'total_positions': sum(len(p) for p in self._positions_by_coin.values()),
            'coins_tracked': list(self._positions_by_coin.keys()),
            'proximity_alerts': {
                coin: prox.total_positions_at_risk
                for coin, prox in self._proximity_cache.items()
                if prox.total_positions_at_risk > 0
            }
        }

        # Add registry stats if enabled
        if self._wallet_registry:
            summary['registry'] = self.get_registry_stats()

        return summary


# =============================================================================
# Scheduled Wallet Refresh
# =============================================================================

import asyncio

async def scheduled_wallet_refresh(
    tracker: PositionTracker,
    interval_hours: float = 4.0,
    discover_new: bool = True,
    trade_discovery_interval: float = 0.25  # 15 minutes
):
    """
    Background task to periodically refresh wallet registry.

    Args:
        tracker: PositionTracker with dynamic registry enabled
        interval_hours: Hours between full refresh cycles (Hyperdash)
        discover_new: If True, scrape Hyperdash for new wallets
        trade_discovery_interval: Hours between trade-based discovery
    """
    logger = logging.getLogger("WalletRefresh")
    last_full_refresh = 0
    last_trade_discovery = 0

    while True:
        try:
            now = asyncio.get_event_loop().time()

            # Trade-based discovery (more frequent)
            if now - last_trade_discovery >= trade_discovery_interval * 3600:
                new_from_trades = await tracker.discover_from_live_trades()
                if new_from_trades > 0:
                    logger.info(f"Trade discovery: {new_from_trades} new whales")
                last_trade_discovery = now

            # Full refresh cycle (less frequent)
            if now - last_full_refresh >= interval_hours * 3600:
                if discover_new:
                    # Full discovery cycle (requires Selenium)
                    await tracker.discover_new_wallets()
                else:
                    # Just refresh from existing registry
                    await tracker.refresh_from_registry()

                stats = tracker.get_registry_stats()
                logger.info(
                    f"Full refresh complete: {stats.get('total_tracked', 0)} tracked"
                )
                last_full_refresh = now

        except Exception as e:
            logger.error(f"Wallet refresh failed: {e}")

        # Check every 5 minutes
        await asyncio.sleep(300)
