"""Risk Monitor.

Monitors risk invariants and emits mandates when violations detected.
Per RISK_EXPOSURE_MATHEMATICS.md Section 4, 11.
"""

import time
from typing import List, Dict
from decimal import Decimal

from runtime.arbitration.types import Mandate, MandateType
from runtime.position.types import Position, PositionState
from .calculator import RiskCalculator
from .types import RiskConfig, AccountState


class RiskMonitor:
    """Monitors risk invariants and emits protective mandates.
    
    Enforces (Section 3-4):
    - I-L1: Total leverage ≤ L_max
    - I-L2: Per-symbol leverage ≤ L_symbol_max
    - I-LA1: D_liq ≥ D_min_safe (per symbol)
    - I-LA2: R_liq ≥ R_liq_min (portfolio)
    
    Emits mandates (Section 11):
    - EXIT: Critical liquidation risk
    - REDUCE: Approaching limits
    - BLOCK: Hard limits violated
    """
    
    def __init__(self, config: RiskConfig):
        """Initialize with risk configuration."""
        self.config = config
        self.calculator = RiskCalculator(config)
    
    def check_and_emit(
        self,
        account: AccountState,
        positions: Dict[str, Position],
        mark_prices: Dict[str, Decimal]
    ) -> List[Mandate]:
        """Check all invariants and emit mandates (Section 11).
        
        Args:
            account: Account state
            positions: All positions
            mark_prices: Mark prices per symbol
            
        Returns:
            List of mandates to emit
        """
        mandates = []
        timestamp = time.time()
        
        #  Check I-L1: Total leverage constraint
        total_leverage = self.calculator.calculate_total_leverage(
            positions, account, mark_prices
        )
        
        if total_leverage > self.config.L_max:
            # Hard limit violated - BLOCK all new entries
            mandates.append(
                Mandate(
                    symbol="*",  # Global block
                    type=MandateType.BLOCK,
                    authority=10.0,  # Highest priority
                    timestamp=timestamp
                )
            )
        
        # Check I-LA1: Per-symbol liquidation distance
        portfolio_risk = self.calculator.calculate_portfolio_risk(
            positions, account, mark_prices
        )
        
        for symbol, position in positions.items():
            # print(f"DEBUG: Processing {symbol} state={position.state}")
            if position.state in (PositionState.FLAT, PositionState.ENTERING):
                continue
            
            if symbol not in mark_prices:
                continue
            
            # Calculate position risk
            pos_risk = self.calculator.calculate_position_risk(
                position,
                mark_prices[symbol],
                total_leverage if total_leverage > 0 else 1.0
            )
            
            # Check critical threshold (Section 6.2: Full Exit)
            if pos_risk.liquidation_distance < self.config.D_critical:
                mandates.append(
                    Mandate(
                        symbol=symbol,
                        type=MandateType.EXIT,
                        authority=10.0,  # Immediate exit
                        timestamp=timestamp
                    )
                )
            
            # Check minimum safe distance (Section 6.3: Partial Exit)
            elif pos_risk.liquidation_distance < self.config.D_min_safe:
                mandates.append(
                    Mandate(
                        symbol=symbol,
                        type=MandateType.REDUCE,
                        authority=8.0,  # High priority
                        timestamp=timestamp
                    )
                )
            
            # Check I-L2: Per-symbol leverage
            symbol_exposure = pos_risk.exposure
            max_symbol_exposure = account.equity * Decimal(str(self.config.L_symbol_max))
            
            if symbol_exposure > max_symbol_exposure:
                # Per-symbol limit violated
                mandates.append(
                    Mandate(
                        symbol=symbol,
                        type=MandateType.REDUCE,
                        authority=7.0,
                        timestamp=timestamp
                    )
                )
        
        # Check I-LA2: Portfolio-wide liquidation buffer
        if portfolio_risk.min_liquidation_distance < self.config.R_liq_min:
            # Portfolio-level risk - reduce worst position
            if portfolio_risk.worst_symbol:
                mandates.append(
                    Mandate(
                        symbol=portfolio_risk.worst_symbol,
                        type=MandateType.REDUCE,
                        authority=9.0,
                        timestamp=timestamp
                    )
                )
        
        return mandates
    
    def validate_entry(
        self,
        symbol: str,
        size: Decimal,
        direction: str,
        entry_price: Decimal,
        account: AccountState,
        positions: Dict[str, Position],
        mark_prices: Dict[str, Decimal]
    ) -> tuple[bool, str]:
        """Validate ENTRY mandate before execution (Section 11.1).
        
        Checks:
        - I-L1: Total leverage after entry
        - I-L2: Per-symbol leverage
        - I-M1: Sufficient margin
        - I-LA1: Post-entry liquidation safety
        
        Args:
            symbol: Symbol to enter
            size: Position size
            direction: LONG or SHORT
            entry_price: Entry price
            account: Account state
            positions: Current positions
            mark_prices: Mark prices
            
        Returns:
            (valid, error_message)
        """
        # Calculate projected exposure
        new_exposure = size * entry_price
        
        # Check I-L1: Total leverage constraint
        current_leverage = self.calculator.calculate_total_leverage(
            positions, account, mark_prices
        )
        
        total_exposure_current = Decimal(str(current_leverage)) * account.equity
        total_exposure_projected = total_exposure_current + new_exposure
        projected_leverage = float(total_exposure_projected / account.equity)
        
        if projected_leverage > self.config.L_max:
            return False, f"Leverage limit violated: {projected_leverage:.2f}x > {self.config.L_max}x (I-L1)"
        
        # Check I-L2: Per-symbol leverage
        max_symbol_exposure = account.equity * Decimal(str(self.config.L_symbol_max))
        if new_exposure > max_symbol_exposure:
            return False, f"Per-symbol leverage limit violated: {new_exposure} > {max_symbol_exposure} (I-L2)"
        
        # Check I-M1: Margin available
        required_margin = new_exposure / Decimal(str(self.config.L_max))
        if required_margin > account.margin_available:
            return False, f"Insufficient margin: need {required_margin}, have {account.margin_available} (I-M1)"
        
        # Check I-LA1: Post-entry liquidation safety (estimated)
        # This is a simplified check - exact check requires simulating the position
        if projected_leverage <= 0:
             return True, "" # Zero leverage is safe
             
        estimated_D_liq = float(1/projected_leverage - self.config.MMR_default)
        if estimated_D_liq < self.config.D_min_safe:
            return False, f"Insufficient liquidation buffer: {estimated_D_liq:.2%} < {self.config.D_min_safe:.2%} (I-LA1)"
        
        return True, ""
