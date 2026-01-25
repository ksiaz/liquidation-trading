"""
HLP18: Exchange Integration.

Order execution infrastructure for Hyperliquid:
- Order construction and submission
- Fill monitoring (WebSocket + polling)
- Position reconciliation
- Slippage tracking
- Error handling
"""

from .types import (
    OrderType,
    OrderSide,
    OrderStatus,
    OrderRequest,
    OrderResponse,
    OrderFill,
    OrderUpdate,
    ExecutionMetrics,
    ReconciliationResult,
    SlippageEstimate,
)

from .order_executor import OrderExecutor
from .fill_tracker import FillTracker
from .position_reconciler import PositionReconciler
from .slippage_tracker import SlippageTracker, SlippageConfig, LiquidityState
from .asset_metadata import (
    AssetMetadataService,
    AssetInfo,
    get_asset_metadata_service,
    reset_asset_metadata_service,
)
from .mark_price_service import (
    MarkPriceService,
    MarkPriceEntry,
    FreshnessConfig,
    get_mark_price_service,
    reset_mark_price_service,
)

__all__ = [
    # Types
    'OrderType',
    'OrderSide',
    'OrderStatus',
    'OrderRequest',
    'OrderResponse',
    'OrderFill',
    'OrderUpdate',
    'ExecutionMetrics',
    'ReconciliationResult',
    'SlippageEstimate',
    # Components
    'OrderExecutor',
    'FillTracker',
    'PositionReconciler',
    'SlippageTracker',
    'SlippageConfig',
    'LiquidityState',
    # Asset Metadata (P1)
    'AssetMetadataService',
    'AssetInfo',
    'get_asset_metadata_service',
    'reset_asset_metadata_service',
    # Mark Price (P3)
    'MarkPriceService',
    'MarkPriceEntry',
    'FreshnessConfig',
    'get_mark_price_service',
    'reset_mark_price_service',
]
