"""
HLP19: Analytics Types.

Data structures for trade journaling and performance tracking.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum, auto


class TradeOutcome(Enum):
    """Trade result classification."""
    WIN = auto()
    LOSS = auto()
    BREAKEVEN = auto()
    OPEN = auto()  # Still open


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = auto()       # Informational only
    WARNING = auto()    # Potential issue
    ERROR = auto()      # Issue requiring attention
    CRITICAL = auto()   # Immediate action required
    EMERGENCY = auto()  # System safety at risk


class MetricCategory(Enum):
    """Metric categories."""
    HEALTH = auto()       # System health
    PERFORMANCE = auto()  # Trading performance
    OPERATIONAL = auto()  # Resource usage
    BUSINESS = auto()     # Capital/PnL


@dataclass
class TradeRecord:
    """Complete record of a single trade."""
    trade_id: str
    symbol: str
    strategy: str
    direction: str  # LONG or SHORT

    # Entry details
    entry_time_ns: int
    entry_price: float
    entry_size: float
    entry_order_id: str
    entry_slippage_bps: float = 0.0

    # Exit details (filled when trade closes)
    exit_time_ns: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # TARGET, STOP, MANUAL, TIMEOUT
    exit_order_id: Optional[str] = None
    exit_slippage_bps: float = 0.0

    # Stop/target
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_order_id: Optional[str] = None
    target_order_id: Optional[str] = None

    # PnL
    realized_pnl: float = 0.0
    fees: float = 0.0
    net_pnl: float = 0.0

    # Context
    event_id: Optional[str] = None
    regime: Optional[str] = None
    notes: str = ""

    # Metadata
    created_at: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))

    @property
    def outcome(self) -> TradeOutcome:
        """Determine trade outcome."""
        if self.exit_time_ns is None:
            return TradeOutcome.OPEN
        if self.net_pnl > 0:
            return TradeOutcome.WIN
        elif self.net_pnl < 0:
            return TradeOutcome.LOSS
        else:
            return TradeOutcome.BREAKEVEN

    @property
    def hold_time_ms(self) -> Optional[float]:
        """Calculate hold time in milliseconds."""
        if self.exit_time_ns is None:
            return None
        return (self.exit_time_ns - self.entry_time_ns) / 1_000_000

    @property
    def r_multiple(self) -> Optional[float]:
        """Calculate R-multiple (reward relative to risk)."""
        if self.stop_price is None or self.exit_price is None:
            return None
        risk = abs(self.entry_price - self.stop_price)
        if risk == 0:
            return None
        reward = self.exit_price - self.entry_price
        if self.direction == "SHORT":
            reward = -reward
        return reward / risk

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'strategy': self.strategy,
            'direction': self.direction,
            'entry_time_ns': self.entry_time_ns,
            'entry_price': self.entry_price,
            'entry_size': self.entry_size,
            'entry_order_id': self.entry_order_id,
            'entry_slippage_bps': self.entry_slippage_bps,
            'exit_time_ns': self.exit_time_ns,
            'exit_price': self.exit_price,
            'exit_reason': self.exit_reason,
            'exit_order_id': self.exit_order_id,
            'exit_slippage_bps': self.exit_slippage_bps,
            'stop_price': self.stop_price,
            'target_price': self.target_price,
            'realized_pnl': self.realized_pnl,
            'fees': self.fees,
            'net_pnl': self.net_pnl,
            'outcome': self.outcome.name,
            'hold_time_ms': self.hold_time_ms,
            'r_multiple': self.r_multiple,
            'event_id': self.event_id,
            'regime': self.regime,
            'notes': self.notes,
        }


@dataclass
class PerformanceSnapshot:
    """Point-in-time performance metrics."""
    timestamp_ns: int

    # Trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    open_trades: int = 0

    # Win rate
    win_rate: float = 0.0
    rolling_win_rate_20: float = 0.0  # Last 20 trades

    # PnL
    total_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0

    # Win/loss metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    win_loss_ratio: float = 0.0
    profit_factor: float = 0.0

    # Risk metrics
    sharpe_ratio_30d: float = 0.0
    sharpe_ratio_90d: float = 0.0
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    days_in_drawdown: int = 0

    # Timing
    avg_hold_time_ms: float = 0.0
    avg_r_multiple: float = 0.0

    # Per-strategy breakdown
    by_strategy: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class MetricValue:
    """Single metric measurement."""
    name: str
    value: float
    category: MetricCategory
    timestamp_ns: int
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage."""
        return {
            'name': self.name,
            'value': self.value,
            'category': self.category.name,
            'timestamp_ns': self.timestamp_ns,
            'tags': self.tags,
            'unit': self.unit,
        }


@dataclass
class Alert:
    """Alert record."""
    alert_id: str
    level: AlertLevel
    category: str  # e.g., 'health', 'performance', 'risk'
    message: str
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp_ns: int = field(default_factory=lambda: int(time.time() * 1_000_000_000))
    acknowledged: bool = False
    resolved: bool = False
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'alert_id': self.alert_id,
            'level': self.level.name,
            'category': self.category,
            'message': self.message,
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'timestamp_ns': self.timestamp_ns,
            'acknowledged': self.acknowledged,
            'resolved': self.resolved,
            'details': self.details,
        }


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: str  # YYYY-MM-DD
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0
    fees: float = 0.0
    net_pnl: float = 0.0
    win_rate: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    starting_capital: float = 0.0
    ending_capital: float = 0.0
    peak_capital: float = 0.0
    drawdown_pct: float = 0.0
