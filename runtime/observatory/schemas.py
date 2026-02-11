"""
Observatory API Schemas - Immutable Response Types.

CONSTITUTIONAL CONSTRAINT: These are read-only data transfer objects.
No methods that modify system state.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# =========================================
# Enums
# =========================================

class MandateType(str, Enum):
    """Mandate type classification."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BLOCK = "BLOCK"


class Direction(str, Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class StabilityStatusEnum(str, Enum):
    """Stability observer status levels."""
    STABLE = "STABLE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ZoneType(str, Enum):
    """M2 zone type."""
    DEMAND = "demand"
    SUPPLY = "supply"


# =========================================
# Response Models
# =========================================

class ExecutionCycleResponse(BaseModel):
    """Execution cycle record."""
    id: int
    timestamp: float
    observation_status: str
    m2_active_nodes: Optional[int] = None

    class Config:
        from_attributes = True


class MandateResponse(BaseModel):
    """Mandate record."""
    id: int
    cycle_id: int
    policy_evaluation_id: Optional[int] = None
    symbol: str
    mandate_type: str
    direction: Optional[str] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: float

    class Config:
        from_attributes = True


class ArbitrationRoundResponse(BaseModel):
    """Arbitration round record."""
    id: int
    cycle_id: int
    symbol: str
    mandate_count: Optional[int] = None
    winning_mandate_id: Optional[int] = None
    action_taken: Optional[str] = None
    theorem_applied: Optional[str] = None
    timestamp: Optional[float] = None

    class Config:
        from_attributes = True


class ZoneResponse(BaseModel):
    """M2 zone record."""
    id: int
    cycle_id: Optional[int] = None
    node_id: str
    symbol: str
    zone_type: str = Field(alias='zone_type')
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    strength: Optional[float] = None
    created_at: Optional[float] = None
    invalidated_at: Optional[float] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class LiquidationResponse(BaseModel):
    """Liquidation event record."""
    id: int
    timestamp: float
    symbol: str
    side: Optional[str] = None
    size: Optional[float] = None
    price: Optional[float] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class PositionResponse(BaseModel):
    """HL position record."""
    id: int
    timestamp: float
    wallet_address: str
    coin: str
    side: str
    size: Optional[float] = None
    entry_price: Optional[float] = None
    liquidation_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None

    class Config:
        from_attributes = True


class CascadeEventResponse(BaseModel):
    """Cascade event record."""
    id: int
    timestamp: float
    coin: str
    event_type: str
    current_price: Optional[float] = None
    positions_at_risk: Optional[int] = None
    value_at_risk: Optional[float] = None

    class Config:
        from_attributes = True


# =========================================
# Aggregated Responses
# =========================================

class StabilityIssue(BaseModel):
    """Stability issue record."""
    issue: str
    symbol: str
    severity: str
    timestamp: Optional[datetime] = None


class StabilityResponse(BaseModel):
    """Stability observer status."""
    status: StabilityStatusEnum
    total_mandates: int = 0
    total_actions: int = 0
    issues_total: int = 0
    recent_issues: List[Dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """System health status."""
    status: str = "UNKNOWN"
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    uptime_seconds: float = 0.0
    cycles_completed: int = 0
    last_cycle_at: Optional[float] = None


class MandateCountsResponse(BaseModel):
    """Mandate counts by type."""
    entry: int = 0
    exit: int = 0
    block: int = 0
    total: int = 0


class TableCountsResponse(BaseModel):
    """Database table row counts."""
    execution_cycles: int = 0
    mandates: int = 0
    arbitration_rounds: int = 0
    m2_nodes: int = 0
    liquidation_events: int = 0
    hl_positions: int = 0


# =========================================
# Snapshot Response
# =========================================

class ObservatorySnapshot(BaseModel):
    """Point-in-time snapshot of observatory state.

    Captures current state across all observable dimensions.
    """
    timestamp: datetime
    stability: StabilityResponse
    health: HealthResponse
    mandate_counts: MandateCountsResponse
    table_counts: TableCountsResponse
    active_zones_count: int = 0
    recent_liquidations_count: int = 0


# =========================================
# Ghost Trade Response
# =========================================

class GhostTradeResponse(BaseModel):
    """Ghost trade (paper trade) record."""
    id: int
    trade_id: str
    cycle_id: Optional[int] = None
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: float
    position_side: str
    is_entry: bool
    pnl: Optional[float] = None
    account_balance_after: float
    winning_policy_name: Optional[str] = None
    holding_duration_sec: Optional[float] = None
    exit_reason: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class GhostSummaryResponse(BaseModel):
    """Ghost trading summary statistics."""
    total_trades: int = 0
    total_entries: int = 0
    total_exits: int = 0
    total_realized_pnl: float = 0.0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    current_balance: float = 1000.0


# =========================================
# Error Response
# =========================================

class ErrorResponse(BaseModel):
    """API error response."""
    error: str
    detail: Optional[str] = None
