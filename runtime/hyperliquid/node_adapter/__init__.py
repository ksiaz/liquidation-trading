"""
Hyperliquid Node Adapter

Production adapter between Hyperliquid node (WSL) and observation system.
Extracts prices, liquidations, and positions with minimal latency.

Components:
- ReplicaCmdStreamer: inotify-based file streaming for replica_cmds
- BlockActionExtractor: Parse SetGlobalAction, forceOrder, order actions
- SyncMonitor: Node sync status monitoring
- HyperliquidNodeAdapter: Main orchestrator with TCP server

Usage:
    # In WSL, run as service:
    python -m runtime.hyperliquid.node_adapter.adapter --host 127.0.0.1 --port 8090

    # Or programmatically:
    from runtime.hyperliquid.node_adapter import HyperliquidNodeAdapter, NodeAdapterConfig

    config = NodeAdapterConfig()
    adapter = HyperliquidNodeAdapter(config)
    await adapter.start()
"""

from .config import NodeAdapterConfig, WindowsConnectorConfig
from .metrics import AdapterMetrics, StreamerMetrics, ExtractorMetrics, PositionStateMetrics
from .asset_mapping import (
    ASSET_ID_TO_COIN,
    COIN_TO_ASSET_ID,
    PRIORITY_ASSETS,
    PRIORITY_COINS,
    get_coin_name,
    get_asset_id,
)
from .replica_streamer import ReplicaCmdStreamer
from .action_extractor import (
    BlockActionExtractor,
    PriceEvent,
    LiquidationEvent,
    OrderActivity,
)
from .sync_monitor import SyncMonitor, SyncStatus
from .adapter import HyperliquidNodeAdapter
from .position_state import (
    PositionStateManager,
    PositionCache,
    ProximityAlert,
    RefreshTier,
)

__all__ = [
    # Config
    'NodeAdapterConfig',
    'WindowsConnectorConfig',

    # Metrics
    'AdapterMetrics',
    'StreamerMetrics',
    'ExtractorMetrics',
    'PositionStateMetrics',

    # Asset mapping
    'ASSET_ID_TO_COIN',
    'COIN_TO_ASSET_ID',
    'PRIORITY_ASSETS',
    'PRIORITY_COINS',
    'get_coin_name',
    'get_asset_id',

    # Components
    'ReplicaCmdStreamer',
    'BlockActionExtractor',
    'SyncMonitor',
    'HyperliquidNodeAdapter',

    # Types
    'PriceEvent',
    'LiquidationEvent',
    'OrderActivity',
    'SyncStatus',

    # Position State
    'PositionStateManager',
    'PositionCache',
    'ProximityAlert',
    'RefreshTier',
]
