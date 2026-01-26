"""
HLP18: Exchange Types.

Order and execution types for Hyperliquid integration.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum, auto


class OrderType(Enum):
    """Order types supported by Hyperliquid."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    POST_ONLY = "post_only"
    IOC = "ioc"  # Immediate or Cancel


class OrderSide(Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Order lifecycle states."""
    PENDING = auto()      # Created locally, not yet submitted
    SUBMITTED = auto()    # Sent to exchange
    ACKNOWLEDGED = auto() # Exchange confirmed receipt
    PARTIAL = auto()      # Some fills received
    FILLED = auto()       # Completely filled
    CANCELED = auto()     # Canceled (by us or exchange)
    REJECTED = auto()     # Exchange rejected
    EXPIRED = auto()      # Time in force expired
    FAILED = auto()       # Submission failed


class FillType(Enum):
    """Type of fill."""
    MAKER = auto()   # Provided liquidity
    TAKER = auto()   # Took liquidity


class ReconciliationAction(Enum):
    """Actions for position reconciliation."""
    NONE = auto()           # No action needed
    SYNC_LOCAL = auto()     # Update local state to match exchange
    EMERGENCY_CLOSE = auto() # Unknown position - close immediately
    RESET_STATE = auto()    # Position closed externally - reset local
    ADJUST_STOP = auto()    # Adjust stop order for actual size


@dataclass
class OrderRequest:
    """Order submission request."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    size: float
    price: Optional[float] = None      # For limit/stop-limit
    stop_price: Optional[float] = None # For stop orders
    reduce_only: bool = False
    post_only: bool = False
    client_order_id: Optional[str] = None
    strategy_id: Optional[str] = None
    event_id: Optional[str] = None
    expected_price: Optional[float] = None  # For slippage tracking
    max_slippage_pct: float = 0.5  # Default 50 bps
    # AUDIT-P0-12: Flag for cascade-triggered orders (different fill thresholds)
    is_cascade: bool = False

    def __post_init__(self):
        if self.client_order_id is None:
            self.client_order_id = f"ord_{int(time.time() * 1000000)}"


@dataclass
class OrderResponse:
    """Response from order submission."""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PENDING
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    timestamp_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    raw_response: Optional[Dict] = None


@dataclass
class OrderFill:
    """Individual fill event."""
    order_id: str
    fill_id: str
    symbol: str
    side: OrderSide
    price: float
    size: float
    fill_type: FillType
    fee: float
    timestamp_ns: int
    cumulative_size: float = 0.0  # Total filled so far
    remaining_size: float = 0.0   # Remaining to fill


@dataclass
class OrderUpdate:
    """Order status update."""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    status: OrderStatus
    filled_size: float = 0.0
    average_price: float = 0.0
    remaining_size: float = 0.0
    timestamp_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    fills: List[OrderFill] = field(default_factory=list)


@dataclass
class SlippageEstimate:
    """Pre-trade slippage estimation."""
    symbol: str
    side: OrderSide
    size: float
    mid_price: float
    estimated_fill_price: float
    estimated_slippage_pct: float
    available_liquidity: float
    depth_levels_consumed: int
    is_acceptable: bool
    reason: str = ""


@dataclass
class ExecutionMetrics:
    """Execution performance metrics."""
    total_orders: int = 0
    successful_orders: int = 0
    rejected_orders: int = 0
    timeout_orders: int = 0

    total_fills: int = 0
    partial_fills: int = 0

    total_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    avg_slippage_bps: float = 0.0

    avg_fill_latency_ms: float = 0.0
    max_fill_latency_ms: float = 0.0
    p99_fill_latency_ms: float = 0.0

    reconciliation_mismatches: int = 0

    def add_order(self, success: bool, rejected: bool = False, timeout: bool = False):
        """Record an order."""
        self.total_orders += 1
        if success:
            self.successful_orders += 1
        elif rejected:
            self.rejected_orders += 1
        elif timeout:
            self.timeout_orders += 1

    def add_fill(self, slippage_bps: float, latency_ms: float, partial: bool = False):
        """Record a fill."""
        self.total_fills += 1
        if partial:
            self.partial_fills += 1

        self.total_slippage_bps += slippage_bps
        self.max_slippage_bps = max(self.max_slippage_bps, slippage_bps)
        self.avg_slippage_bps = self.total_slippage_bps / self.total_fills

        self.max_fill_latency_ms = max(self.max_fill_latency_ms, latency_ms)
        # Update running average
        prev_total = self.avg_fill_latency_ms * (self.total_fills - 1)
        self.avg_fill_latency_ms = (prev_total + latency_ms) / self.total_fills


@dataclass
class ReconciliationResult:
    """Result of position reconciliation."""
    symbol: str
    expected_size: float
    actual_size: float
    action: ReconciliationAction
    discrepancy: float = 0.0
    message: str = ""
    timestamp_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))


@dataclass
class ExecutionLog:
    """Execution event log entry."""
    event_type: str  # 'order_submitted', 'order_filled', 'order_rejected', etc.
    timestamp_ns: int
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[OrderSide] = None
    size: Optional[float] = None
    price: Optional[float] = None
    fill_price: Optional[float] = None
    slippage_bps: Optional[float] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    details: Dict = field(default_factory=dict)
