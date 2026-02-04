"""
Node Client - gRPC client for HL Node Adapter.

Provides event subscription for prices, liquidations, and fills from the
out-of-process node adapter.
"""

from .subscriber import NodeSubscriber, PriceCallback, LiquidationCallback, FillCallback
from .types import PriceEvent, LiquidationEvent, FillEvent, SyncStatus, SyncStatusCode
from .bridge import NodeBridge, create_node_bridge

__all__ = [
    'NodeSubscriber',
    'PriceCallback',
    'LiquidationCallback',
    'FillCallback',
    'PriceEvent',
    'LiquidationEvent',
    'FillEvent',
    'SyncStatus',
    'SyncStatusCode',
    'NodeBridge',
    'create_node_bridge',
]
