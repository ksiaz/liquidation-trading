"""
Observation Bridge

Connects DirectNodeIntegration to the Observation System (M1/Governance).
Converts node events to observation layer format.

Usage:
    from observation.governance import ObservationSystem

    obs_system = ObservationSystem(...)
    bridge = ObservationBridge(obs_system)

    integration = DirectNodeIntegration(
        on_price=bridge.on_price,
        on_liquidation=bridge.on_liquidation,
    )
"""

import logging
from typing import Optional

from .action_extractor import PriceEvent, LiquidationEvent, OrderActivity

logger = logging.getLogger(__name__)


class ObservationBridge:
    """
    Bridge between node adapter and observation system.

    Converts PriceEvent/LiquidationEvent from the node adapter
    to the format expected by ObservationSystem.ingest_observation().
    """

    def __init__(self, observation_system):
        """
        Initialize bridge.

        Args:
            observation_system: ObservationSystem instance (governance layer)
        """
        self._obs = observation_system

        # Metrics
        self._prices_forwarded = 0
        self._liquidations_forwarded = 0
        self._errors = 0

    def on_price(self, event: PriceEvent) -> None:
        """
        Handle price event from node.

        Converts to observation format and forwards to M1.
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

        except Exception as e:
            self._errors += 1
            logger.error(f"Error forwarding liquidation event: {e}")

    def on_order_activity(self, event: OrderActivity) -> None:
        """
        Handle order activity from node.

        Currently not forwarded to observation (used for position tracking).
        Could be extended to track position changes.
        """
        # Order activity is for position state tracking, not observation
        # May be used later for HL_POSITION events
        pass

    def get_metrics(self) -> dict:
        """Get bridge metrics."""
        return {
            'prices_forwarded': self._prices_forwarded,
            'liquidations_forwarded': self._liquidations_forwarded,
            'errors': self._errors,
        }


def create_integrated_node(observation_system, config=None):
    """
    Factory function to create fully wired node integration.

    Args:
        observation_system: ObservationSystem instance
        config: Optional NodeAdapterConfig

    Returns:
        Tuple of (DirectNodeIntegration, ObservationBridge)

    Usage:
        integration, bridge = create_integrated_node(obs_system)
        await integration.start()
    """
    from .direct_integration import DirectNodeIntegration
    from .config import NodeAdapterConfig

    bridge = ObservationBridge(observation_system)

    integration = DirectNodeIntegration(
        on_price=bridge.on_price,
        on_liquidation=bridge.on_liquidation,
        on_order_activity=bridge.on_order_activity,
        config=config or NodeAdapterConfig(),
    )

    return integration, bridge
