"""
Risk Management Type Definitions

Data structures for risk management.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExitReason(Enum):
    """
    Exit reason codes.
    
    Used for logging and analysis.
    """
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TAKE_PROFIT_HIT = "TAKE_PROFIT_HIT"
    SETUP_INVALIDATED = "SETUP_INVALIDATED"
    REGIME_CHANGED = "REGIME_CHANGED"
    MANUAL_EXIT = "MANUAL_EXIT"


@dataclass(frozen=True)
class RiskParameters:
    """
    Risk management parameters.
    
    INVARIANT: Immutable configuration.
    """
    max_risk_per_trade_pct: float = 1.0  # 1% account risk per trade
    min_reward_risk_ratio: float = 2.0  # Minimum 2:1 R:R
    max_position_size_pct: float = 10.0  # Max 10% of account in position


@dataclass
class Position:
    """
    Active position record.
    
    Mutable - tracks position state.
    """
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float  # Position size in base currency
    side: str  # 'long' or 'short'
    entry_time: float
    strategy: str  # 'SLBRS' or 'EFFCS'
    
    def calculate_pnl(self, current_price: float) -> float:
        """Calculate current P&L."""
        if self.side == 'long':
            return (current_price - self.entry_price) * self.size
        else:  # short
            return (self.entry_price - current_price) * self.size
    
    def get_reward_risk_ratio(self) -> float:
        """Calculate reward:risk ratio."""
        if self.side == 'long':
            risk = self.entry_price - self.stop_loss
            reward = self.take_profit - self.entry_price
        else:  # short
            risk = self.stop_loss - self.entry_price
            reward = self.entry_price - self.take_profit
        
        if risk == 0:
            return 0.0
        
        return reward / risk


@dataclass
class PositionExit:
    """
    Position exit record.
    
    Immutable exit snapshot for logging.
    """
    exit_price: float
    exit_time: float
    pnl: float
    reason: ExitReason
    position: Position
    
    def get_exit_summary(self) -> str:
        """Get human-readable exit summary."""
        return (
            f"{self.position.strategy} {self.position.side} "
            f"@ {self.position.entry_price:.2f} → {self.exit_price:.2f} "
            f"| PnL: {self.pnl:.2f} | Reason: {self.reason.value}"
        )
