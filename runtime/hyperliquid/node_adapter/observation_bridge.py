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
from typing import Optional, Dict, Callable, Awaitable

from .action_extractor import PriceEvent, LiquidationEvent, OrderActivity

logger = logging.getLogger(__name__)

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
    ):
        """
        Initialize bridge.

        Args:
            observation_system: ObservationSystem instance (governance layer)
            position_state_manager: Optional PositionStateManager for position tracking
            min_order_notional: Minimum USD value to forward orders (default $10k)
        """
        self._obs = observation_system
        self._psm = position_state_manager
        self._min_order_notional = min_order_notional

        # Track prices for position manager
        self._latest_prices: Dict[str, float] = {}

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
        """
        try:
            payload = {
                'oracle_price': event.oracle_price,
                'mark_price': event.mark_price,
                'timestamp': event.timestamp,
            }

            self._obs.ingest_observation(
                timestamp=event.timestamp,
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

        Converts to observation format and forwards to M1.
        """
        try:
            payload = {
                'wallet_address': event.wallet_address,
                'liquidated_size': event.liquidated_size,
                'liquidation_price': event.liquidation_price,
                'side': event.side,
                'value': event.value,
                'timestamp': event.timestamp,
            }

            self._obs.ingest_observation(
                timestamp=event.timestamp,
                symbol=event.symbol,
                event_type='HL_LIQUIDATION',
                payload=payload,
            )

            self._liquidations_forwarded += 1

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

            payload = {
                'wallet_address': event.wallet,
                'side': event.side,
                'size': event.size,
                'notional': event.notional,
                'is_reduce_only': event.is_reduce_only,
                'timestamp': event.timestamp,
            }

            self._obs.ingest_observation(
                timestamp=event.timestamp,
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
        """
        try:
            symbol = position_data.get('symbol', '')

            self._obs.ingest_observation(
                timestamp=position_data.get('timestamp', 0),
                symbol=symbol,
                event_type='HL_POSITION',
                payload=position_data,
            )

            self._positions_forwarded += 1

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding position event: {e}")

    async def _handle_proximity_alert(self, alert) -> None:
        """
        Handle proximity alert from PositionStateManager.

        Called when a position crosses a tier threshold.
        """
        try:
            self._proximity_alerts += 1

            # Log the alert
            logger.warning(
                f"Proximity Alert: {alert.wallet[:10]}... {alert.coin} "
                f"{alert.old_tier.value} -> {alert.new_tier.value} "
                f"({alert.proximity_pct:.2f}% to liquidation, ${alert.position_value:,.0f})"
            )

            # Could also ingest as a special event type if needed
            # For now, just log - the position update will be ingested separately

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

        return metrics


def create_integrated_node(
    observation_system,
    config=None,
    enable_position_tracking: bool = False,  # Disabled by default - requires API integration
    min_position_value: float = 1000.0,
    focus_coins: list = None,
):
    """
    Factory function to create fully wired node integration.

    Args:
        observation_system: ObservationSystem instance
        config: Optional NodeAdapterConfig
        enable_position_tracking: Whether to enable position state tracking
            NOTE: Position tracking from state file is disabled by default.
            The abci_state.rmp only contains raw position data (size, balance)
            but not derived values (entry_price, liquidation_price, margin).
            For full position tracking, use Hyperliquid API integration instead.
        min_position_value: Minimum position value to track (default $1000)
        focus_coins: Only track these coins (None = all)

    Returns:
        Tuple of (DirectNodeIntegration, ObservationBridge, Optional[PositionStateManager])

    Usage:
        integration, bridge, psm = create_integrated_node(obs_system)
        if psm:
            await psm.start()
        await integration.start()
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
