"""Risk and Exposure Types.

Data structures for risk management per RISK_EXPOSURE_MATHEMATICS.md.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from runtime.position.types import Direction


@dataclass(frozen=True)
class RiskConfig:
    """System risk configuration (Section 10.2).
    
    All values are constitutional constants - no runtime interpretation.
    """
    # Leverage limits
    L_max: float = 10.0  # Maximum total leverage
    L_target: float = 8.0  # Operational target (soft)
    L_symbol_max: float = 5.0  # Per-symbol maximum
    L_max_net: float = 8.0  # Net directional limit
    
    # Liquidation thresholds
    D_min_safe: float = 0.08  # 8% minimum distance
    D_critical: float = 0.03  # 3% immediate exit
    R_liq_min: float = 0.08  # Portfolio minimum
    
    # Exchange parameters
    MMR_default: float = 0.005  # 0.5% maintenance margin rate
    
    # Operational parameters
    reduction_pct_default: float = 0.5  # 50% default reduction
    safety_factor: float = 0.7  # 70% of max loss tolerance
    
    def validate(self):
        """Validate configuration consistency."""
        assert self.L_target <= self.L_max, "L_target must be <= L_max"
        assert self.L_symbol_max <= self.L_max, "L_symbol_max must be <= L_max"
        assert 0 < self.D_critical < self.D_min_safe, "D_critical must be < D_min_safe"
        assert 0 < self.safety_factor < 1.0, "safety_factor must be in (0, 1)"


@dataclass(frozen=True)
class AccountState:
    """Account state snapshot (Section 2.1).
    
    Raw account data from exchange - no derived semantics.
    """
    equity: Decimal  # E - Total account equity (USD)
    margin_available: Decimal  # Available for new positions
    timestamp: float  # Observation time
    
    def __post_init__(self):
        """Validate account state."""
        if self.equity <= 0:
            raise ValueError(f"Equity must be positive: {self.equity}")
        if self.margin_available < 0:
            raise ValueError(f"Margin cannot be negative: {self.margin_available}")


@dataclass(frozen=True)
class PositionRisk:
    """Risk metrics for a single position (Section 2.1).
    
    All values calculated from raw data - no interpretation.
    """
    symbol: str
    direction: Direction
    quantity: Decimal  # Signed: + for LONG, - for SHORT
    
    # Raw position data
    entry_price: Decimal  # P_entry
    mark_price: Decimal  # P_mark (current)
    
    # Calculated exposure
    exposure: Decimal  # |Q × P_mark|
    notional: Decimal  # Q × P_mark (signed)
    unrealized_pnl: Decimal  # Q × (P_mark - P_entry)
    
    # Liquidation metrics
    liquidation_price: Decimal  # P_liq
    liquidation_distance: float  # D_liq (percentage)
    
    def __post_init__(self):
        """Validate position risk metrics."""
        if self.mark_price <= 0:
            raise ValueError(f"Mark price must be positive: {self.mark_price}")
        if self.entry_price <= 0:
            raise ValueError(f"Entry price must be positive: {self.entry_price}")
        if self.liquidation_distance < 0:
            raise ValueError(f"Liquidation distance cannot be negative: {self.liquidation_distance}")


@dataclass(frozen=True)
class PortfolioRisk:
    """Aggregate portfolio risk metrics (Section 5).
    
    Pure calculations - no judgments or predictions.
    """
    # Leverage
    total_leverage: float  # L_actual = Σ Exposure / E
    
    # Exposure aggregation
    total_exposure: Decimal  # Σ_s Exposure_s
    long_exposure: Decimal  # Σ_{s: D_s = LONG} Exposure_s
    short_exposure: Decimal  # Σ_{s: D_s = SHORT} Exposure_s
    net_exposure: Decimal  # Long - Short
    
    # Liquidation
    min_liquidation_distance: float  # R_liq = min_s(D_liq_s)
    worst_symbol: Optional[str]  # Symbol with min D_liq
    
    # PnL
    total_unrealized_pnl: Decimal  # Σ_s PnL_s
    
    def __post_init__(self):
        """Validate portfolio metrics."""
        if self.total_leverage < 0:
            raise ValueError(f"Leverage cannot be negative: {self.total_leverage}")
        if self.min_liquidation_distance < 0:
            raise ValueError(f"Min liquidation distance cannot be negative: {self.min_liquidation_distance}")


@dataclass(frozen=True)
class ValidationResult:
    """Result of entry validation (Section 11.1)."""
    valid: bool
    reason: Optional[str] = None
    violated_invariant: Optional[str] = None  # I-L1, I-LA1, etc.
    
    @classmethod
    def accept(cls) -> 'ValidationResult':
        """Create acceptance result."""
        return cls(valid=True, reason=None)
    
    @classmethod
    def reject(cls, reason: str, invariant: str) -> 'ValidationResult':
        """Create rejection result."""
        return cls(valid=False, reason=reason, violated_invariant=invariant)
