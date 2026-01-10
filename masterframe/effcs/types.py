"""
EFFCS Type Definitions

Data structures for EFFCS momentum strategy.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EFFCSState(Enum):
    """
    EFFCS state machine states.
    
    INVARIANT: States follow sequence.
    """
    DISABLED = "DISABLED"
    IMPULSE_DETECTED = "IMPULSE_DETECTED"
    PULLBACK_MONITORING = "PULLBACK_MONITORING"
    ENTRY_ARMED = "ENTRY_ARMED"
    IN_POSITION = "IN_POSITION"


class ImpulseDirection(Enum):
    """
    Impulse move direction.
    
    BULLISH: Upward price move
    BEARISH: Downward price move
    """
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class Impulse:
    """
    Detected impulse move.
    
    INVARIANT: Immutable impulse snapshot.
    INVARIANT: Direction determines trade side.
    """
    direction: ImpulseDirection
    start_price: float
    end_price: float
    displacement: float  # Absolute displacement
    start_time: float
    end_time: float
    liquidation_zscore: Optional[float]
    oi_delta: Optional[float]
    atr: float  # ATR at detection time
    
    def get_impulse_range(self) -> float:
        """Get impulse price range."""
        return abs(self.end_price - self.start_price)


@dataclass(frozen=True)
class Pullback:
    """
    Pullback from impulse.
    
    INVARIANT: Tracks pullback depth and volume.
    """
    impulse: Impulse
    start_price: float  # Pullback start (impulse end)
    current_price: float
    depth_percent: float  # % of impulse retraced
    avg_volume: float  # Average volume during pullback
    impulse_avg_volume: float  # Average volume during impulse
    
    def is_shallow(self, max_depth: float = 30.0) -> bool:
        """Check if pullback is shallow enough."""
        return self.depth_percent <= max_depth
    
    def is_volume_decreasing(self) -> bool:
        """Check if pullback volume decreased."""
        return self.avg_volume < self.impulse_avg_volume


@dataclass(frozen=True)
class EFFCSSetup:
    """
    EFFCS trade setup.
    
    INVARIANT: Entry direction matches impulse direction.
    """
    impulse: Impulse
    pullback: Pullback
    entry_price: float
    stop_loss: float
    take_profit: float
    side: str  # 'long' or 'short'
    setup_time: float
    
    def get_reward_risk_ratio(self) -> float:
        """Calculate reward:risk ratio."""
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        if risk == 0:
            return 0.0
        return reward / risk


@dataclass
class Position:
    """
    Active EFFCS position.
    
    Mutable - tracks position state.
    """
    setup: EFFCSSetup
    entry_time: float
    entry_price: float
    current_pnl: float
    is_active: bool
    
    def update_pnl(self, current_price: float) -> None:
        """Update current P&L."""
        if self.setup.side == 'long':
            self.current_pnl = current_price - self.entry_price
        else:  # short
            self.current_pnl = self.entry_price - current_price
