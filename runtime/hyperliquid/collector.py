"""
Hyperliquid Collector Service

Runs alongside the Binance collector to:
1. Track wallet positions in real-time
2. Calculate liquidation proximity
3. Feed "priming" data to the strategy layer

Constitutional compliance:
- Only factual observations
- No predictions or semantic labels
- Data for priming, not decision-making
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

from .client import HyperliquidClient, ClientConfig
from .position_tracker import PositionTracker, TrackerConfig
from .types import LiquidationProximity, WalletState, SystemWallets
from runtime.logging.execution_db import ResearchDatabase
from memory.m4_cascade_momentum import CascadeMomentumTracker, MomentumPhase, phase_to_string

# Optional indexer import
try:
    from .indexer import IndexerCoordinator, IndexerConfig
    HAS_INDEXER = True
except ImportError:
    HAS_INDEXER = False
    IndexerCoordinator = None
    IndexerConfig = None


# Default coins to track (match Binance symbols where possible)
DEFAULT_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX"]


@dataclass
class HyperliquidCollectorConfig:
    """Configuration for Hyperliquid collector."""
    # Connection
    use_testnet: bool = False

    # Tracking
    proximity_threshold: float = 0.005  # 0.5% - the key threshold
    min_position_value: float = 1000.0  # Minimum USD to track

    # Polling intervals
    wallet_poll_interval: float = 5.0  # How often to poll REST API
    price_poll_interval: float = 1.0  # How often to update prices
    proximity_log_interval: float = 10.0  # How often to log proximity

    # System wallet tracking
    track_hlp_vault: bool = True  # Track the liquidator vault

    # Additional wallets to track (from leaderboard, whale lists, etc.)
    additional_wallets: List[str] = None

    # Dynamic wallet discovery
    enable_dynamic_discovery: bool = False  # Enable live wallet discovery
    discovery_min_trade_value: float = 100_000.0  # Min trade value for discovery
    trade_discovery_interval: float = 900.0  # Seconds between trade scans (15 min)

    # Blockchain indexer settings
    enable_indexer: bool = False  # Enable blockchain indexer for full wallet discovery
    indexer_lookback_blocks: int = 500_000  # ~7 days of history
    indexer_db_path: str = "indexed_wallets.db"
    indexer_checkpoint_path: str = "indexer_checkpoint.json"


class HyperliquidCollector:
    """
    Hyperliquid data collector service.

    Responsibilities:
    1. Maintain WebSocket connection for real-time prices
    2. Poll wallet positions at intervals
    3. Calculate and log liquidation proximity
    4. Emit cascade alerts when thresholds crossed
    """

    def __init__(
        self,
        db: ResearchDatabase,
        config: Optional[HyperliquidCollectorConfig] = None
    ):
        self._config = config or HyperliquidCollectorConfig()
        self._logger = logging.getLogger("HyperliquidCollector")
        self._db = db
        self._running = False

        # Initialize client
        client_config = ClientConfig(
            use_testnet=self._config.use_testnet,
            reconnect_delay=1.0,
            max_reconnect_delay=60.0
        )
        self._client = HyperliquidClient(client_config)

        # Initialize position tracker
        tracker_config = TrackerConfig(
            proximity_thresholds=(0.005, 0.01, 0.02, 0.05),
            default_threshold=self._config.proximity_threshold,
            min_position_value=self._config.min_position_value,
            poll_interval=self._config.wallet_poll_interval,
            track_system_wallets=self._config.track_hlp_vault,
            use_dynamic_registry=self._config.enable_dynamic_discovery,
            registry_min_position=self._config.discovery_min_trade_value
        )
        self._tracker = PositionTracker(self._client, tracker_config)

        # Track previous positions for liquidation detection
        self._previous_positions: Dict[str, Dict[str, float]] = {}  # wallet -> {coin: value}

        # Callbacks for external consumers
        self._on_proximity_update: Optional[Callable] = None
        self._on_cascade_alert: Optional[Callable] = None

        # State tracking
        self._last_proximity_log: Dict[str, float] = {}  # coin -> timestamp

        # Cascade momentum tracker for exhaustion detection
        self._momentum_tracker = CascadeMomentumTracker()

        # Blockchain indexer (optional)
        self._indexer: Optional['IndexerCoordinator'] = None

    async def start(self):
        """Start the Hyperliquid collector."""
        self._running = True
        self._logger.info("Starting Hyperliquid collector...")

        # Start client
        await self._client.start()

        # Add tracked wallets from database
        await self._load_tracked_wallets()

        # Add additional wallets from config
        if self._config.additional_wallets:
            for wallet in self._config.additional_wallets:
                self._tracker.add_wallet(wallet)
                self._db.add_hl_tracked_wallet(wallet, "CONFIG", "From config")

        # Setup callbacks
        self._client.set_position_callback(self._on_wallet_update)
        self._client.set_mids_callback(self._on_price_update)
        self._client.set_liquidation_callback(self._on_liquidation_event)
        self._tracker.set_proximity_callback(self._on_proximity_calculated)
        self._tracker.set_cascade_callback(self._on_cascade_detected)

        # Start tasks
        asyncio.create_task(self._client.run_websocket())
        asyncio.create_task(self._poll_wallets_loop())
        asyncio.create_task(self._log_proximity_loop())

        # Start trade discovery if enabled
        if self._config.enable_dynamic_discovery:
            asyncio.create_task(self._trade_discovery_loop())
            self._logger.info("Trade-based whale discovery enabled")

        # Start blockchain indexer if enabled
        if self._config.enable_indexer and HAS_INDEXER:
            await self._start_indexer()
        elif self._config.enable_indexer and not HAS_INDEXER:
            self._logger.warning("Indexer enabled but dependencies not installed (boto3, lz4, msgpack)")

        self._logger.info(f"Hyperliquid collector started - tracking {len(self._tracker._tracked_wallets)} wallets")

    async def stop(self):
        """Stop the collector."""
        self._running = False
        if self._indexer:
            await self._indexer.stop()
        await self._client.stop()
        self._logger.info("Hyperliquid collector stopped")

    async def _start_indexer(self):
        """Start the blockchain indexer for full wallet discovery."""
        indexer_config = IndexerConfig(
            lookback_blocks=self._config.indexer_lookback_blocks,
            db_path=self._config.indexer_db_path,
            checkpoint_path=self._config.indexer_checkpoint_path,
            tier1_interval=5.0,
            tier2_interval=30.0,
            tier3_interval=300.0
        )

        self._indexer = IndexerCoordinator(self._client, indexer_config)

        # Setup callbacks to integrate with position tracker
        self._indexer.set_position_update_callback(self._on_indexed_position_update)
        self._indexer.set_wallet_discovered_callback(self._on_wallet_discovered)

        await self._indexer.start()
        self._logger.info("Blockchain indexer started")

    async def _on_indexed_position_update(self, wallet_state: WalletState):
        """Handle position update from indexer."""
        # Forward to position tracker
        self._tracker.on_wallet_update(wallet_state)

        # Also add to our tracked wallets if not already
        addr = wallet_state.address.lower()
        if addr not in self._tracker._tracked_wallets:
            self._tracker.add_wallet(addr)

    async def _on_wallet_discovered(self, address: str, block_num: int):
        """Handle new wallet discovered by indexer."""
        # Add to position tracker for monitoring
        self._tracker.add_wallet(address)
        self._logger.debug(f"Indexer discovered wallet: {address[:12]}... (block {block_num})")

    async def _load_tracked_wallets(self):
        """Load tracked wallets from database."""
        wallets = self._db.get_hl_tracked_wallets(active_only=True)
        for wallet in wallets:
            self._tracker.add_wallet(wallet['wallet_address'])

    async def _poll_wallets_loop(self):
        """Periodically poll all tracked wallets."""
        self._logger.info(f"Poll loop started, tracking {len(self._tracker._tracked_wallets)} wallets")
        while self._running:
            try:
                await self._tracker.update_all_wallets()
            except Exception as e:
                self._logger.debug(f"Wallet poll error: {e}")

            await asyncio.sleep(self._config.wallet_poll_interval)

    async def _log_proximity_loop(self):
        """Periodically log proximity data to database."""
        while self._running:
            try:
                for coin, proximity in self._tracker.get_all_proximity().items():
                    # Check if enough time passed since last log
                    last_log = self._last_proximity_log.get(coin, 0)
                    if time.time() - last_log >= self._config.proximity_log_interval:
                        self._log_proximity_to_db(proximity)
                        self._last_proximity_log[coin] = time.time()
            except Exception as e:
                self._logger.debug(f"Proximity log error: {e}")

            await asyncio.sleep(self._config.proximity_log_interval)

    async def _trade_discovery_loop(self):
        """Periodically scan trades for new whale wallets."""
        while self._running:
            try:
                new_count = await self._tracker.discover_from_live_trades(
                    coins=DEFAULT_COINS,
                    min_trade_value=self._config.discovery_min_trade_value
                )
                if new_count > 0:
                    self._logger.info(
                        f"Trade discovery: found {new_count} new whales, "
                        f"now tracking {len(self._tracker._tracked_wallets)}"
                    )
            except Exception as e:
                self._logger.debug(f"Trade discovery error: {e}")

            await asyncio.sleep(self._config.trade_discovery_interval)

    def _detect_liquidation(self, wallet_state: WalletState):
        """
        Detect potential liquidations by comparing with previous positions.

        Liquidation indicators:
        1. Position completely gone (full liquidation)
        2. Position size dropped >50% suddenly (partial liquidation)
        3. Position value dropped significantly while price stable
        """
        wallet = wallet_state.address.lower()
        current_positions = {
            coin: {
                'value': pos.position_value,
                'size': pos.abs_size,
                'side': pos.side.value
            }
            for coin, pos in wallet_state.positions.items()
        }

        # Check previous positions
        previous = self._previous_positions.get(wallet, {})

        for coin, prev_data in previous.items():
            prev_value = prev_data.get('value', 0)
            prev_size = prev_data.get('size', 0)
            prev_side = prev_data.get('side', '')

            if prev_value < 10000:  # Skip small positions
                continue

            current = current_positions.get(coin)

            # Case 1: Position completely gone
            if current is None:
                self._logger.info(
                    f"LIQUIDATION (full): {wallet[:12]}... {coin} {prev_side} "
                    f"${prev_value:,.0f} -> CLOSED"
                )
                liquidated_value = prev_value

            # Case 2: Position size dropped >50% (partial liquidation)
            elif current and prev_size > 0:
                current_size = current.get('size', 0)
                size_reduction = (prev_size - current_size) / prev_size

                if size_reduction > 0.5:  # >50% reduction
                    liquidated_value = prev_value - current.get('value', 0)
                    self._logger.info(
                        f"LIQUIDATION (partial): {wallet[:12]}... {coin} {prev_side} "
                        f"size {prev_size:.4f} -> {current_size:.4f} "
                        f"(-{size_reduction*100:.0f}%, ${liquidated_value:,.0f})"
                    )
                else:
                    continue  # Normal position change, not liquidation

            else:
                continue

            # Add to discovery if significant
            if self._config.enable_dynamic_discovery and liquidated_value > 50000:
                self._tracker.on_liquidation_event(
                    wallet,
                    coin,
                    liquidated_value,
                    prev_side
                )

        # Update previous state
        self._previous_positions[wallet] = current_positions

    async def _on_wallet_update(self, wallet_state: WalletState):
        """Handle wallet position update from WebSocket."""
        # Detect potential liquidations before updating tracker
        self._detect_liquidation(wallet_state)

        self._tracker.on_wallet_update(wallet_state)

        # Log individual positions
        for coin, position in wallet_state.positions.items():
            price = self._client.get_mid_price(coin)
            distance = position.distance_to_liquidation(price) if price else None

            self._db.log_hl_position(
                timestamp=position.timestamp,
                wallet_address=position.wallet_address,
                coin=coin,
                side=position.side.value,
                position_size=position.abs_size,
                entry_price=position.entry_price,
                liquidation_price=position.liquidation_price,
                leverage=position.leverage,
                margin_used=position.margin_used,
                unrealized_pnl=position.unrealized_pnl,
                position_value=position.position_value,
                distance_to_liquidation_pct=distance
            )

    async def _on_price_update(self, prices: Dict[str, float]):
        """Handle price update from WebSocket."""
        self._tracker.on_price_update(prices)

        # Trigger proximity recalculation (updates cache properly)
        await self._tracker.trigger_proximity_recalc()

    async def _on_liquidation_event(self, event: Dict):
        """Handle real-time asset context update from WebSocket.

        Uses CascadeMomentumTracker to detect:
        - Cascade building (accelerating OI drops)
        - Cascade exhaustion (decelerating, then idle)
        """
        coin = event.get('coin', 'UNKNOWN')
        oi_change_pct = event.get('oi_change_pct', 0)
        is_liq_signal = event.get('is_liquidation_signal', False)
        mark_price = event.get('mark_price')

        # Track state for phase transition logging
        if not hasattr(self, '_last_phase'):
            self._last_phase = {}

        # Record event in momentum tracker
        observation = self._momentum_tracker.record_event(
            coin=coin,
            oi_change_pct=oi_change_pct,
            is_liquidation_signal=is_liq_signal
        )

        # Detect phase transitions
        prev_phase = self._last_phase.get(coin)
        current_phase = observation.phase

        if prev_phase != current_phase:
            self._last_phase[coin] = current_phase

            # Log significant phase transitions
            if current_phase == MomentumPhase.ACCELERATING:
                self._logger.warning(
                    f"[CASCADE_BUILDING] {coin}: Rate={observation.oi_change_rate_5s:.3f}%/s, "
                    f"Accel={observation.acceleration:.4f}"
                )

            elif current_phase == MomentumPhase.DECELERATING:
                self._logger.info(
                    f"[CASCADE_SLOWING] {coin}: Rate={observation.oi_change_rate_5s:.3f}%/s, "
                    f"Peak was {observation.peak_rate:.3f}%/s, "
                    f"Duration={observation.cascade_duration_sec:.1f}s"
                )

            elif current_phase == MomentumPhase.EXHAUSTED:
                self._logger.warning(
                    f"[CASCADE_EXHAUSTED] {coin} @ {mark_price}: "
                    f"Total OI dropped={observation.total_oi_dropped:.2f}%, "
                    f"Duration={observation.cascade_duration_sec:.1f}s, "
                    f"Peak rate={observation.peak_rate:.3f}%/s"
                )

        # Log active cascade metrics periodically
        if current_phase in (MomentumPhase.ACCELERATING, MomentumPhase.STEADY):
            if observation.liquidation_signals_5s >= 2:
                self._logger.info(
                    f"[CASCADE_ACTIVE] {coin}: {observation.liquidation_signals_5s} signals/5s, "
                    f"Rate={observation.oi_change_rate_5s:.3f}%/s"
                )

    async def _on_proximity_calculated(self, proximity: LiquidationProximity):
        """Handle proximity calculation result."""
        # Only log if there are positions at risk
        if proximity.total_positions_at_risk > 0:
            self._logger.debug(
                f"Proximity: {proximity.coin} @ ${proximity.current_price:,.0f} - "
                f"{proximity.total_positions_at_risk} positions, "
                f"${proximity.total_value_at_risk:,.0f} at risk "
                f"(L:{proximity.long_positions_count}, S:{proximity.short_positions_count})"
            )

        # Forward to external callback
        if self._on_proximity_update:
            await self._on_proximity_update(proximity)

    async def _on_cascade_detected(self, proximity: LiquidationProximity):
        """Handle cascade alert."""
        # Determine dominant side
        dominant_side = "LONG" if proximity.long_positions_value > proximity.short_positions_value else "SHORT"
        closest = proximity.long_closest_liquidation if dominant_side == "LONG" else proximity.short_closest_liquidation

        self._logger.warning(
            f"CASCADE ALERT: {proximity.coin} - "
            f"{proximity.total_positions_at_risk} positions, "
            f"${proximity.total_value_at_risk:,.0f} at risk, "
            f"dominant={dominant_side}, closest_liq=${closest:,.0f}"
        )

        # Log to database
        self._db.log_hl_cascade_event(
            timestamp=proximity.timestamp,
            coin=proximity.coin,
            event_type="CASCADE_ALERT",
            current_price=proximity.current_price,
            threshold_pct=proximity.threshold_pct,
            positions_at_risk=proximity.total_positions_at_risk,
            value_at_risk=proximity.total_value_at_risk,
            dominant_side=dominant_side,
            closest_liquidation=closest,
            notes=f"L:{proximity.long_positions_count}/{proximity.long_positions_value:.0f} "
                  f"S:{proximity.short_positions_count}/{proximity.short_positions_value:.0f}"
        )

        # Forward to external callback
        if self._on_cascade_alert:
            await self._on_cascade_alert(proximity)

    def _log_proximity_to_db(self, proximity: LiquidationProximity):
        """Log proximity data to database."""
        self._db.log_hl_liquidation_proximity(
            timestamp=proximity.timestamp,
            coin=proximity.coin,
            current_price=proximity.current_price,
            threshold_pct=proximity.threshold_pct,
            long_positions_count=proximity.long_positions_count,
            long_positions_size=proximity.long_positions_size,
            long_positions_value=proximity.long_positions_value,
            long_avg_distance_pct=proximity.long_avg_distance_pct,
            long_closest_liquidation=proximity.long_closest_liquidation,
            short_positions_count=proximity.short_positions_count,
            short_positions_size=proximity.short_positions_size,
            short_positions_value=proximity.short_positions_value,
            short_avg_distance_pct=proximity.short_avg_distance_pct,
            short_closest_liquidation=proximity.short_closest_liquidation,
            total_positions_at_risk=proximity.total_positions_at_risk,
            total_value_at_risk=proximity.total_value_at_risk
        )

    # =========================================================================
    # External API
    # =========================================================================

    def add_wallet(self, wallet_address: str, wallet_type: str = None, label: str = None):
        """Add a wallet to track."""
        self._tracker.add_wallet(wallet_address)
        self._db.add_hl_tracked_wallet(wallet_address, wallet_type, label)

    def get_proximity(self, coin: str) -> Optional[LiquidationProximity]:
        """Get current liquidation proximity for a coin."""
        return self._tracker.get_proximity(coin)

    def get_all_proximity(self) -> Dict[str, LiquidationProximity]:
        """Get liquidation proximity for all coins."""
        return self._tracker.get_all_proximity()

    def get_summary(self) -> Dict:
        """Get collector summary."""
        summary = {
            **self._tracker.get_summary(),
            'running': self._running,
            'prices_tracked': len(self._client._mid_prices),
            'indexer_enabled': self._indexer is not None
        }

        if self._indexer:
            summary['indexer'] = self._indexer.get_stats()

        return summary

    def set_proximity_callback(self, callback: Callable):
        """Set callback for proximity updates."""
        self._on_proximity_update = callback

    def set_cascade_callback(self, callback: Callable):
        """Set callback for cascade alerts."""
        self._on_cascade_alert = callback
