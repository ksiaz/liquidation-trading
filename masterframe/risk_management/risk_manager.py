"""
Risk Manager

Centralized risk management and position control.

RULES:
- Only one position at a time
- No scaling, pyramiding, or averaging
- Validate R:R before entry
- Immediate exit on invalidation
"""

from typing import Optional, List
from .types import ExitReason, RiskParameters, Position, PositionExit


class RiskManager:
    """
    Centralized risk management.
    
    INVARIANT: Only one position at a time.
    INVARIANT: No scaling, pyramiding, or averaging.
    INVARIANT: Minimum R:R enforced before entry.
    """
    
    def __init__(self, risk_params: RiskParameters, account_balance: float):
        """
        Initialize risk manager.
        
        Args:
            risk_params: Risk parameters
            account_balance: Current account balance
        """
        self.risk_params = risk_params
        self.account_balance = account_balance
        self.current_position: Optional[Position] = None
        self.exit_history: List[PositionExit] = []
    
    def validate_setup(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        side: str
    ) -> bool:
        """
        Validate setup before entry.
        
        Args:
            entry_price: Proposed entry price
            stop_loss: Stop loss level
            take_profit: Take profit level
            side: 'long' or 'short'
        
        Returns:
            True if setup valid
        
        RULE: Stop and target must exist.
        RULE: R:R must meet minimum (2:1).
        """
        # Calculate risk and reward
        if side == 'long':
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
        else:  # short
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
        
        # Risk and reward must be positive
        if risk <= 0 or reward <= 0:
            return False
        
        # Check R:R ratio
        rr_ratio = reward / risk
        if rr_ratio < self.risk_params.min_reward_risk_ratio:
            return False
        
        return True
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float
    ) -> float:
        """
        Calculate position size based on risk.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss level
        
        Returns:
            Position size in base currency
        
        RULE: Risk per trade = account_balance × max_risk_pct.
        RULE: Cap at max position size.
        """
        # Calculate risk amount
        risk_amount = self.account_balance * (self.risk_params.max_risk_per_trade_pct / 100.0)
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit == 0:
            return 0.0
        
        # Position size = risk amount / risk per unit
        position_size = risk_amount / risk_per_unit
        
        # Cap at max position size (% of account)
        max_size = self.account_balance * (self.risk_params.max_position_size_pct / 100.0) / entry_price
        position_size = min(position_size, max_size)
        
        return position_size
    
    def enter_position(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        side: str,
        strategy: str,
        current_time: float
    ) -> Optional[Position]:
        """
        Enter position.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss level
            take_profit: Take profit level
            side: 'long' or 'short'
            strategy: 'SLBRS' or 'EFFCS'
            current_time: Current timestamp
        
        Returns:
            Position if entry allowed, None otherwise
        
        RULE: Only one position at a time.
        RULE: Validate setup first.
        RULE: Calculate size based on risk.
        """
        # Check if already in position
        if self.current_position is not None:
            return None
        
        # Validate setup
        if not self.validate_setup(entry_price, stop_loss, take_profit, side):
            return None
        
        # Calculate size
        size = self.calculate_position_size(entry_price, stop_loss)
        
        if size <= 0:
            return None
        
        # Create position
        position = Position(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size=size,
            side=side,
            entry_time=current_time,
            strategy=strategy
        )
        
        self.current_position = position
        return position
    
    def check_exit(
        self,
        current_price: float,
        invalidated: bool = False,
        regime_changed: bool = False
    ) -> Optional[ExitReason]:
        """
        Check if position should exit.
        
        Args:
            current_price: Current market price
            invalidated: Setup invalidated flag
            regime_changed: Regime changed flag
        
        Returns:
            ExitReason if should exit, None otherwise
        
        RULE: Immediate exit on invalidation (highest priority).
        RULE: Exit on stop/target hit.
        RULE: Exit on regime change.
        """
        if not self.current_position:
            return None
        
        pos = self.current_position
        
        # PRIORITY 1: Invalidation (highest priority)
        if invalidated:
            return ExitReason.SETUP_INVALIDATED
        
        # PRIORITY 2: Regime change
        if regime_changed:
            return ExitReason.REGIME_CHANGED
        
        # PRIORITY 3: Stop loss
        if pos.side == 'long':
            if current_price <= pos.stop_loss:
                return ExitReason.STOP_LOSS_HIT
        else:  # short
            if current_price >= pos.stop_loss:
                return ExitReason.STOP_LOSS_HIT
        
        # PRIORITY 4: Take profit
        if pos.side == 'long':
            if current_price >= pos.take_profit:
                return ExitReason.TAKE_PROFIT_HIT
        else:  # short
            if current_price <= pos.take_profit:
                return ExitReason.TAKE_PROFIT_HIT
        
        return None
    
    def exit_position(
        self,
        exit_price: float,
        exit_time: float,
        reason: ExitReason
    ) -> Optional[PositionExit]:
        """
        Exit current position.
        
        Args:
            exit_price: Exit price
            exit_time: Exit timestamp
            reason: Exit reason
        
        Returns:
            PositionExit record
        
        RULE: Market exit only (no limit orders).
        RULE: Record exit reason.
        RULE: Calculate final P&L.
        """
        if not self.current_position:
            return None
        
        pos = self.current_position
        
        # Calculate P&L
        pnl = pos.calculate_pnl(exit_price)
        
        # Create exit record
        exit_record = PositionExit(
            exit_price=exit_price,
            exit_time=exit_time,
            pnl=pnl,
            reason=reason,
            position=pos
        )
        
        # Log exit
        self.exit_history.append(exit_record)
        
        # Update account balance
        self.account_balance += pnl
        
        # Clear position
        self.current_position = None
        
        return exit_record
    
    def get_current_position(self) -> Optional[Position]:
        """Get current position."""
        return self.current_position
    
    def is_in_position(self) -> bool:
        """Check if in position."""
        return self.current_position is not None
    
    def get_exit_history(self) -> List[PositionExit]:
        """Get exit history."""
        return self.exit_history
    
    def get_account_balance(self) -> float:
        """Get current account balance."""
        return self.account_balance
    
    def reset(self) -> None:
        """Reset risk manager (clear position and history)."""
        self.current_position = None
        self.exit_history.clear()
