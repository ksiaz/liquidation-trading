"""
Observation Bridge

Connects DirectNodeIntegration to the Observation System (M1/Governance).
Converts node events to observation layer format.

Usage:
    from observation.governance import ObservationSystem

    obs_system = ObservationSystem(...)
    integration, bridge = create_integrated_node(obs_system)
    await integration.start()
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Dict, Callable, Awaitable, List

from .action_extractor import PriceEvent, LiquidationEvent, OrderActivity
from runtime.hyperliquid.types import LiquidationProximity

logger = logging.getLogger(__name__)


# ==============================================================================
# Liquidation Burst Aggregator
# ==============================================================================

@dataclass
class LiquidationBurst:
    """
    Aggregated liquidation activity over a time window.

    Compatible with external_policy.ep2_strategy_cascade_sniper.LiquidationBurst.
    """
    symbol: str
    total_volume: float          # Total liquidation volume in window
    long_liquidations: float     # Volume of long liquidations
    short_liquidations: float    # Volume of short liquidations
    liquidation_count: int       # Number of liquidation events
    window_start: float          # Window start timestamp
    window_end: float            # Window end timestamp


class LiquidationBurstAggregator:
    """
    Aggregates individual liquidation events into bursts over a rolling window.

    Used to provide LiquidationBurst data to the cascade state machine without
    requiring external websocket connections (e.g., Binance).

    Usage:
        aggregator = LiquidationBurstAggregator(window_sec=10.0)
        aggregator.add_event(liq_event)
        burst = aggregator.get_burst('BTCUSDT')
    """

    def __init__(
        self,
        window_sec: float = 10.0,
        min_burst_volume: float = 10_000.0,  # Minimum volume to report as burst
        max_symbols: int = 500,              # Max symbols to track (memory guard)
        inactive_prune_sec: float = 300.0,   # Prune symbols inactive for 5 min
    ):
        """
        Initialize aggregator.

        Args:
            window_sec: Rolling window size in seconds (default 10s)
            min_burst_volume: Minimum total volume to report as burst (default $10k)
            max_symbols: Maximum symbols to track (memory guard)
            inactive_prune_sec: Remove symbols inactive longer than this
        """
        self._window_sec = window_sec
        self._min_burst_volume = min_burst_volume
        self._max_symbols = max_symbols
        self._inactive_prune_sec = inactive_prune_sec

        # Events by symbol: symbol -> list of (timestamp, side, value)
        self._events: Dict[str, List[tuple]] = defaultdict(list)

        # Last activity per symbol (for pruning)
        self._last_activity: Dict[str, float] = {}

        # Metrics
        self._events_received = 0
        self._bursts_generated = 0
        self._symbols_pruned = 0

    def add_event(self, event: LiquidationEvent) -> None:
        """
        Add a liquidation event to the aggregator.

        Args:
            event: LiquidationEvent from node
        """
        self._events_received += 1

        # Extract coin from symbol (BTCUSDT -> BTC)
        symbol = event.symbol
        if symbol.endswith('USDT'):
            symbol = symbol[:-4] + 'USDT'  # Normalize

        # Memory guard: check symbol limit before adding new
        if symbol not in self._events and len(self._events) >= self._max_symbols:
            self._prune_inactive()
            # If still at limit, skip
            if len(self._events) >= self._max_symbols:
                return

        self._events[symbol].append((
            event.timestamp,
            event.side,  # 'long' or 'short'
            event.value,
        ))
        self._last_activity[symbol] = event.timestamp

        # Clean old events
        self._cleanup_old_events(symbol)

    def _cleanup_old_events(self, symbol: str) -> None:
        """Remove events outside the window."""
        now = time.time()
        cutoff = now - self._window_sec

        self._events[symbol] = [
            (ts, side, val) for ts, side, val in self._events[symbol]
            if ts >= cutoff
        ]

    def get_burst(self, symbol: str) -> Optional[LiquidationBurst]:
        """
        Get current liquidation burst for a symbol.

        Returns:
            LiquidationBurst if activity exceeds minimum, None otherwise
        """
        if symbol not in self._events:
            return None

        # Clean old events first
        self._cleanup_old_events(symbol)

        events = self._events[symbol]
        if not events:
            return None

        now = time.time()

        # Aggregate
        total_volume = 0.0
        long_liqs = 0.0
        short_liqs = 0.0
        oldest_ts = now
        newest_ts = 0.0

        for ts, side, val in events:
            total_volume += val
            if side == 'long':
                long_liqs += val
            else:
                short_liqs += val
            oldest_ts = min(oldest_ts, ts)
            newest_ts = max(newest_ts, ts)

        # Check minimum threshold
        if total_volume < self._min_burst_volume:
            return None

        self._bursts_generated += 1

        return LiquidationBurst(
            symbol=symbol,
            total_volume=total_volume,
            long_liquidations=long_liqs,
            short_liquidations=short_liqs,
            liquidation_count=len(events),
            window_start=oldest_ts,
            window_end=newest_ts,
        )

    def get_all_bursts(self) -> Dict[str, LiquidationBurst]:
        """Get bursts for all symbols with activity."""
        bursts = {}
        for symbol in list(self._events.keys()):
            burst = self.get_burst(symbol)
            if burst:
                bursts[symbol] = burst
        return bursts

    def _prune_inactive(self) -> int:
        """Remove symbols inactive longer than threshold."""
        now = time.time()
        cutoff = now - self._inactive_prune_sec
        to_remove = []

        for symbol, last_time in self._last_activity.items():
            if last_time < cutoff:
                to_remove.append(symbol)

        for symbol in to_remove:
            self._events.pop(symbol, None)
            self._last_activity.pop(symbol, None)
            self._symbols_pruned += 1

        return len(to_remove)

    def prune_stale(self) -> int:
        """
        Public method to prune stale symbols.

        Call periodically to prevent memory growth.
        """
        return self._prune_inactive()

    def get_metrics(self) -> Dict:
        """Get aggregator metrics."""
        return {
            'events_received': self._events_received,
            'bursts_generated': self._bursts_generated,
            'symbols_tracked': len(self._events),
            'window_sec': self._window_sec,
            'symbols_pruned': self._symbols_pruned,
            'max_symbols': self._max_symbols,
        }


class _TrackerAdapter:
    """
    Adapter to make PositionStateManager look like PositionTracker for governance.

    Governance accesses _hl_collector._tracker.get_positions(coin) to retrieve
    position data for M4 primitive computation.
    """

    def __init__(self, psm):
        self._psm = psm

    def get_positions(self, coin: str) -> list:
        """
        Get positions for a coin in the format governance expects.

        Returns list of objects with: position_size, position_value, leverage, liquidation_price
        """
        positions = self._psm.get_positions_by_coin(coin)

        # Convert to dict format governance expects
        result = []
        for pos in positions:
            # Estimate leverage from margin/value ratio
            leverage = 1.0
            if pos.margin > 0:
                leverage = pos.position_value / pos.margin

            result.append({
                'position_size': pos.size,
                'position_value': pos.position_value,
                'leverage': leverage,
                'liquidation_price': pos.liquidation_price,
            })
        return result


class NodeProximityProvider:
    """
    Adapter to make PositionStateManager compatible with governance.set_hyperliquid_source().

    This provides the same interface as HyperliquidCollector for proximity data:
    - get_proximity(coin) -> LiquidationProximity
    - _tracker.get_positions(coin) -> list of position dicts
    - get_burst(symbol) -> LiquidationBurst (for cascade triggering)

    Usage:
        psm = PositionStateManager(...)
        provider = NodeProximityProvider(psm)
        governance.set_hyperliquid_source(provider)
    """

    def __init__(self, psm, burst_aggregator: Optional[LiquidationBurstAggregator] = None):
        """
        Initialize provider.

        Args:
            psm: PositionStateManager instance
            burst_aggregator: Optional LiquidationBurstAggregator for cascade triggering
        """
        self._psm = psm
        self._tracker = _TrackerAdapter(psm)
        self._burst_aggregator = burst_aggregator

    def get_proximity(self, coin: str) -> Optional[LiquidationProximity]:
        """
        Get liquidation proximity for a coin.

        Args:
            coin: Coin symbol (e.g., "BTC")

        Returns:
            LiquidationProximity or None if no positions at risk
        """
        return self._psm.get_coin_proximity(coin)

    def get_all_proximity(self) -> Dict[str, LiquidationProximity]:
        """Get proximity for all tracked coins."""
        result = {}

        # Get unique coins from all positions
        coins = set()
        for pos in self._psm.get_all_positions():
            coins.add(pos.coin)

        # Compute proximity for each
        for coin in coins:
            proximity = self._psm.get_coin_proximity(coin)
            if proximity:
                result[coin] = proximity

        return result

    def get_burst(self, symbol: str) -> Optional[LiquidationBurst]:
        """
        Get current liquidation burst for a symbol.

        Used by cascade state machine to detect trigger conditions.

        Args:
            symbol: Symbol to get burst for (e.g., 'BTCUSDT')

        Returns:
            LiquidationBurst if activity exceeds threshold, None otherwise
        """
        if self._burst_aggregator:
            return self._burst_aggregator.get_burst(symbol)
        return None

    def get_all_bursts(self) -> Dict[str, LiquidationBurst]:
        """Get all active liquidation bursts."""
        if self._burst_aggregator:
            return self._burst_aggregator.get_all_bursts()
        return {}

# Minimum notional value to forward orders to M1
MIN_ORDER_NOTIONAL = 10_000.0  # $10k


class ObservationBridge:
    """
    Bridge between node adapter and observation system.

    Converts PriceEvent/LiquidationEvent from the node adapter
    to the format expected by ObservationSystem.ingest_observation().

    Also manages PositionStateManager for position tracking.
    """

    def __init__(
        self,
        observation_system,
        position_state_manager=None,
        min_order_notional: float = MIN_ORDER_NOTIONAL,
        burst_window_sec: float = 10.0,
        min_burst_volume: float = 10_000.0,
    ):
        """
        Initialize bridge.

        Args:
            observation_system: ObservationSystem instance (governance layer)
            position_state_manager: Optional PositionStateManager for position tracking
            min_order_notional: Minimum USD value to forward orders (default $10k)
            burst_window_sec: Liquidation burst aggregation window (default 10s)
            min_burst_volume: Minimum volume to report as burst (default $10k)
        """
        self._obs = observation_system
        self._psm = position_state_manager
        self._min_order_notional = min_order_notional

        # Track prices for position manager
        self._latest_prices: Dict[str, float] = {}

        # Liquidation burst aggregator for cascade triggering
        self._burst_aggregator = LiquidationBurstAggregator(
            window_sec=burst_window_sec,
            min_burst_volume=min_burst_volume,
        )

        # Metrics
        self._prices_forwarded = 0
        self._liquidations_forwarded = 0
        self._orders_forwarded = 0
        self._orders_filtered = 0
        self._positions_forwarded = 0
        self._proximity_alerts = 0
        self._errors = 0

        # Wire up position state manager callbacks if provided
        if self._psm:
            self._psm.on_position_update = self._handle_position_update
            self._psm.on_proximity_alert = self._handle_proximity_alert

    def on_price(self, event: PriceEvent) -> None:
        """
        Handle price event from node.

        Converts to observation format and forwards to M1.
        Also updates PositionStateManager with new prices.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        Original event.timestamp preserved in payload for data accuracy.
        """
        try:
            # Use wall clock for governance freshness check
            # Node timestamps are from when events occurred on HL network,
            # which can be "in the past" relative to Binance-driven system_time
            now = time.time()

            payload = {
                'oracle_price': event.oracle_price,
                'mark_price': event.mark_price,
                'timestamp': event.timestamp,  # Original timestamp for data accuracy
            }

            self._obs.ingest_observation(
                timestamp=now,  # Wall clock for governance validation
                symbol=event.symbol,
                event_type='HL_PRICE',
                payload=payload,
            )

            self._prices_forwarded += 1

            # Track price for position manager
            self._latest_prices[event.symbol] = event.oracle_price

            # Update position manager with new prices (batched)
            # We update every price event - PSM handles the proximity calculation
            if self._psm and self._prices_forwarded % 50 == 0:
                # Batch update every ~50 prices to reduce overhead
                self._psm.update_prices(self._latest_prices)

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding price event: {e}")

    def on_liquidation(self, event: LiquidationEvent) -> None:
        """
        Handle liquidation event from node.

        Converts to observation format, forwards to M1, and aggregates for bursts.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        Original event.timestamp preserved in payload for data accuracy.
        """
        try:
            # Use wall clock for governance freshness check
            # Node timestamps are from when events occurred on HL network,
            # which can be "in the past" relative to Binance-driven system_time
            now = time.time()

            payload = {
                'wallet_address': event.wallet_address,
                'liquidated_size': event.liquidated_size,
                'liquidation_price': event.liquidation_price,
                'side': event.side,
                'value': event.value,
                'timestamp': event.timestamp,  # Original timestamp for data accuracy
            }

            self._obs.ingest_observation(
                timestamp=now,  # Wall clock for governance validation
                symbol=event.symbol,
                event_type='HL_LIQUIDATION',
                payload=payload,
            )

            self._liquidations_forwarded += 1

            # Add to burst aggregator for cascade triggering
            self._burst_aggregator.add_event(event)

            # Log liquidations - these are important
            logger.info(
                f"Liquidation: {event.symbol} {event.side} "
                f"${event.value:,.0f} @ {event.liquidation_price}"
            )

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding liquidation event: {e}")

    def on_order_activity(self, event: OrderActivity) -> None:
        """
        Handle order activity from node.

        Filters orders by notional value and forwards large orders (>$10k) to M1.
        Also notifies PositionStateManager for position refresh triggers.
        """
        try:
            # Notify position manager for potential position refresh
            if self._psm:
                asyncio.create_task(
                    self._psm.on_order_activity(event.wallet, event.coin)
                )

            # Filter by notional value for M1 forwarding
            if event.notional < self._min_order_notional:
                self._orders_filtered += 1
                return

            # Use wall clock for governance freshness check
            now = time.time()

            payload = {
                'wallet_address': event.wallet,
                'side': event.side,
                'size': event.size,
                'notional': event.notional,
                'is_reduce_only': event.is_reduce_only,
                'timestamp': event.timestamp,  # Original timestamp for data accuracy
            }

            self._obs.ingest_observation(
                timestamp=now,  # Wall clock for governance validation
                symbol=event.coin,
                event_type='HL_ORDER',
                payload=payload,
            )

            self._orders_forwarded += 1

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding order event: {e}")

    async def _handle_position_update(self, position_data: Dict) -> None:
        """
        Handle position update from PositionStateManager.

        Called when position state changes (new position, closed, or refreshed).

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            # Use wall clock for governance freshness check
            now = time.time()
            symbol = position_data.get('symbol', '')

            self._obs.ingest_observation(
                timestamp=now,  # Wall clock for governance validation
                symbol=symbol,
                event_type='HL_POSITION',
                payload=position_data,  # Original timestamp preserved in payload
            )

            self._positions_forwarded += 1

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding position event: {e}")

    async def _handle_proximity_alert(self, alert) -> None:
        """
        Handle proximity alert from PositionStateManager.

        Called when a position crosses a tier threshold.
        Logs the alert for monitoring. Does NOT create M2 nodes - per M2 constitutional
        spec, nodes should only be created from ACTUAL liquidations, not proximity alerts.
        Proximity data is used by CASCADE_SNIPER for cluster detection, not for zone creation.
        """
        try:
            self._proximity_alerts += 1

            # Log the alert for monitoring
            logger.warning(
                f"Proximity Alert: {alert.wallet[:10]}... {alert.coin} "
                f"{alert.old_tier.value} -> {alert.new_tier.value} "
                f"({alert.proximity_pct:.2f}% to liquidation, ${alert.position_value:,.0f})"
            )

            # NOTE: Previously this created M2 nodes from proximity alerts, but this
            # violated the M2 constitutional spec which states:
            # "Nodes are created ONLY on liquidation events."
            # Proximity alerts are predictions (positions that MIGHT liquidate),
            # not observations (positions that DID liquidate).
            # This caused the geometry strategy to create zones from noise.

        except Exception as e:
            self._errors += 1
            logger.error(f"Error handling proximity alert: {e}")

    def get_metrics(self) -> dict:
        """Get bridge metrics."""
        metrics = {
            'prices_forwarded': self._prices_forwarded,
            'liquidations_forwarded': self._liquidations_forwarded,
            'orders_forwarded': self._orders_forwarded,
            'orders_filtered': self._orders_filtered,
            'positions_forwarded': self._positions_forwarded,
            'proximity_alerts': self._proximity_alerts,
            'errors': self._errors,
        }

        # Add position manager metrics if available
        if self._psm:
            metrics['position_manager'] = {
                'positions_cached': self._psm.metrics.positions_cached,
                'wallets_tracked': self._psm.metrics.wallets_tracked,
                'critical_positions': self._psm.metrics.critical_positions,
                'watchlist_positions': self._psm.metrics.watchlist_positions,
            }

        # Add burst aggregator metrics
        metrics['burst_aggregator'] = self._burst_aggregator.get_metrics()

        return metrics

    def get_burst(self, symbol: str) -> Optional[LiquidationBurst]:
        """
        Get current liquidation burst for a symbol.

        Used by cascade state machine to determine if trigger threshold is met.

        Args:
            symbol: Symbol to get burst for (e.g., 'BTCUSDT')

        Returns:
            LiquidationBurst if activity exceeds minimum threshold, None otherwise
        """
        return self._burst_aggregator.get_burst(symbol)

    def get_all_bursts(self) -> Dict[str, LiquidationBurst]:
        """
        Get all current liquidation bursts.

        Returns:
            Dict of symbol -> LiquidationBurst for all active bursts
        """
        return self._burst_aggregator.get_all_bursts()

    def get_proximity_provider(self) -> Optional[NodeProximityProvider]:
        """
        Get proximity provider for governance integration.

        Returns:
            NodeProximityProvider that can be passed to governance.set_hyperliquid_source()
            or None if position tracking is not enabled.

        The provider includes:
        - Proximity data (positions at risk)
        - Burst data (aggregated liquidations for cascade triggering)
        """
        if self._psm:
            return NodeProximityProvider(self._psm, self._burst_aggregator)
        return None


def create_integrated_node(
    observation_system,
    config=None,
    enable_position_tracking: bool = False,  # Disabled by default - requires state file parsing
    min_position_value: float = 1000.0,
    focus_coins: list = None,
):
    """
    Factory function to create fully wired node integration.

    Args:
        observation_system: ObservationSystem instance (governance layer)
        config: Optional NodeAdapterConfig
        enable_position_tracking: Whether to enable position state tracking
            NOTE: Position tracking requires msgpack and state file parsing.
            When enabled, automatically wires proximity provider to governance
            for M4 cascade primitive computation.
        min_position_value: Minimum position value to track (default $1000)
        focus_coins: Only track these coins (None = all)

    Returns:
        Tuple of (DirectNodeIntegration, ObservationBridge, Optional[PositionStateManager])

    When position tracking is enabled:
        - PositionStateManager reads positions from abci_state.rmp
        - Proximity provider is automatically wired to governance
        - M4 primitives (LiquidationCascadeProximity) become available
        - Cascade Sniper strategy can operate

    Usage:
        integration, bridge, psm = create_integrated_node(
            obs_system,
            enable_position_tracking=True
        )
        if psm:
            await psm.start()  # Do initial position discovery
        await integration.start()  # Start streaming prices/liquidations
    """
    from .direct_integration import DirectNodeIntegration
    from .config import NodeAdapterConfig
    from .position_state import PositionStateManager, MSGPACK_AVAILABLE

    cfg = config or NodeAdapterConfig()

    # Create position state manager if enabled and msgpack available
    psm = None
    if enable_position_tracking and MSGPACK_AVAILABLE:
        try:
            import os
            state_path = os.path.expanduser(cfg.node_state_path)
            psm = PositionStateManager(
                state_path=state_path,
                min_position_value=min_position_value,
                focus_coins=focus_coins,
            )
            logger.info(f"Position tracking enabled (state: {state_path})")
        except Exception as e:
            logger.warning(f"Could not enable position tracking: {e}")
            psm = None
    elif enable_position_tracking and not MSGPACK_AVAILABLE:
        logger.warning("Position tracking disabled - msgpack not installed")

    # Create bridge with position manager
    bridge = ObservationBridge(
        observation_system,
        position_state_manager=psm,
    )

    # Create integration
    integration = DirectNodeIntegration(
        on_price=bridge.on_price,
        on_liquidation=bridge.on_liquidation,
        on_order_activity=bridge.on_order_activity,
        config=cfg,
    )

    # Wire proximity provider to governance if position tracking is enabled
    if psm and hasattr(observation_system, 'set_hyperliquid_source'):
        provider = bridge.get_proximity_provider()
        if provider:
            observation_system.set_hyperliquid_source(provider)
            logger.info("Proximity provider wired to observation system")

    return integration, bridge, psm


async def run_integrated_node(
    observation_system,
    config=None,
    enable_position_tracking: bool = True,
):
    """
    Convenience function to run integrated node with position tracking.

    Handles starting both the integration and position manager.

    Args:
        observation_system: ObservationSystem instance
        config: Optional NodeAdapterConfig
        enable_position_tracking: Whether to enable position tracking

    Returns:
        Tuple of (DirectNodeIntegration, ObservationBridge, Optional[PositionStateManager])
    """
    integration, bridge, psm = create_integrated_node(
        observation_system,
        config=config,
        enable_position_tracking=enable_position_tracking,
    )

    # Start position manager first (needs to do initial discovery)
    if psm:
        await psm.start()

    # Start integration
    await integration.start()

    return integration, bridge, psm
