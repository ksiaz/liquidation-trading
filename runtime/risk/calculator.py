"""Risk Calculator.

Core risk and exposure calculations per RISK_EXPOSURE_MATHEMATICS.md.

Implements:
- Section 2: Liquidation mechanics
- Section 3: Leverage bounds
- Section 4: Liquidation avoidance
- Section 5: Exposure aggregation
- Section 7: Position sizing
"""

from decimal import Decimal
from typing import Dict, Tuple, Optional

from runtime.position.types import Position, PositionState, Direction
from .types import RiskConfig, AccountState, PositionRisk, PortfolioRisk


class RiskCalculator:
    """Calculates risk metrics from raw position data.
    
    All calculations are deterministic pure functions.
    No interpretation, prediction, or learning.
    """
    
    def __init__(self, config: RiskConfig):
        """Initialize with risk configuration."""
        config.validate()
        self.config = config
    
    # ========== Section 2.2: Liquidation Mechanics ==========
    
    def calculate_liquidation_price(
        self,
        direction: Direction,
        entry_price: Decimal,
        leverage: float,
        mmr: float
    ) -> Decimal:
        """Calculate liquidation price (Section 2.2).
        
        For LONG: P_liq = P_entry × (1 - 1/L + MMR)
        For SHORT: P_liq = P_entry × (1 + 1/L - MMR)
        
        Args:
            direction: Position direction
            entry_price: Entry price
            leverage: Leverage ratio
            mmr: Maintenance margin rate
            
        Returns:
            Liquidation price
        """
        if leverage <= 0:
            raise ValueError(f"Leverage must be positive: {leverage}")
        
        if direction == Direction.LONG:
            factor = Decimal(str(1 - 1/leverage + mmr))
            return entry_price * factor
        elif direction == Direction.SHORT:
            factor = Decimal(str(1 + 1/leverage - mmr))
            return entry_price * factor
        else:
            raise ValueError(f"Cannot calculate liq price for FLAT position")
    
    def calculate_liquidation_distance(
        self,
        mark_price: Decimal,
        liq_price: Decimal
    ) -> float:
        """Calculate distance to liquidation (Section 2.2).
        
        D_liq = |P_mark - P_liq| / P_mark (percentage)
        
        Args:
            mark_price: Current mark price
            liq_price: Liquidation price
            
        Returns:
            Distance as decimal (0.08 = 8%)
        """
        if mark_price <= 0:
            raise ValueError(f"Mark price must be positive: {mark_price}")
        
        distance = abs(mark_price - liq_price) / mark_price
        return float(distance)
    
    # ========== Section 3.1: Leverage Calculation ==========
    
    def calculate_total_leverage(
        self,
        positions: Dict[str, Position],
        account: AccountState,
        mark_prices: Dict[str, Decimal]
    ) -> float:
        """Calculate total leverage (Section 3.1).
        
        L_actual = Σ_s Exposure_s / E
        
        Args:
            positions: All positions
            account: Account state
            mark_prices: Mark prices per symbol
            
        Returns:
            Total leverage ratio
        """
        if account.equity <= 0:
            return 0.0
        
        total_exposure = Decimal("0")
        for symbol, position in positions.items():
            if position.state == PositionState.FLAT:
                continue
            
            if symbol not in mark_prices:
                raise ValueError(f"Missing mark price for {symbol}")
            
            exposure = abs(position.quantity * mark_prices[symbol])
            total_exposure += exposure
        
        return float(total_exposure / account.equity)
    
    # ========== Section 5: Exposure Aggregation ==========
    
    def calculate_position_risk(
        self,
        position: Position,
        mark_price: Decimal,
        leverage: float
    ) -> PositionRisk:
        """Calculate risk metrics for a position (Section 2.1, 5.1).
        
        Args:
            position: Position to analyze
            mark_price: Current mark price
            leverage: Current account leverage
            
        Returns:
            PositionRisk with all metrics
        """
        if position.state == PositionState.FLAT:
            raise ValueError("Cannot calculate risk for FLAT position")
        
        if position.entry_price is None:
            raise ValueError(f"Position {position.symbol} missing entry price")
        
        # Calculate exposure
        notional = position.quantity * mark_price
        exposure = abs(notional)
        
        # Calculate PnL
        unrealized_pnl = position.quantity * (mark_price - position.entry_price)
        
        # Calculate liquidation metrics
        liq_price = self.calculate_liquidation_price(
            position.direction,
            position.entry_price,
            leverage,
            self.config.MMR_default
        )
        
        # Check if already liquidated (crossed price)
        # If crossed, distance is effectively 0 (critical)
        is_liquidated = False
        if position.direction == Direction.LONG:
            if mark_price <= liq_price:
                is_liquidated = True
        elif position.direction == Direction.SHORT:
            if mark_price >= liq_price:
                is_liquidated = True
                
        if is_liquidated:
            liq_distance = 0.0
        else:
            liq_distance = self.calculate_liquidation_distance(mark_price, liq_price)
        
        return PositionRisk(
            symbol=position.symbol,
            direction=position.direction,
            quantity=position.quantity,
            entry_price=position.entry_price,
            mark_price=mark_price,
            exposure=exposure,
            notional=notional,
            unrealized_pnl=unrealized_pnl,
            liquidation_price=liq_price,
            liquidation_distance=liq_distance
        )
    
    def calculate_portfolio_risk(
        self,
        positions: Dict[str, Position],
        account: AccountState,
        mark_prices: Dict[str, Decimal]
    ) -> PortfolioRisk:
        """Calculate aggregate portfolio risk (Section 5).
        
        Args:
            positions: All positions
            account: Account state
            mark_prices: Mark prices per symbol
            
        Returns:
            PortfolioRisk with aggregated metrics
        """
        # Calculate leverage
        total_leverage = self.calculate_total_leverage(positions, account, mark_prices)
        
        # Initialize aggregates
        total_exposure = Decimal("0")
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        
        min_liq_distance = float('inf')
        worst_symbol = None
        
        # Aggregate over positions
        for symbol, position in positions.items():
            if position.state in (PositionState.FLAT, PositionState.ENTERING):
                continue
            
            if symbol not in mark_prices:
                continue
            
            # Calculate position risk
            pos_risk = self.calculate_position_risk(
                position,
                mark_prices[symbol],
                total_leverage if total_leverage > 0 else 1.0
            )
            
            # Aggregate
            total_exposure += pos_risk.exposure
            total_unrealized_pnl += pos_risk.unrealized_pnl
            
            if position.direction == Direction.LONG:
                long_exposure += pos_risk.exposure
            elif position.direction == Direction.SHORT:
                short_exposure += pos_risk.exposure
            
            # Track worst liquidation distance
            if pos_risk.liquidation_distance < min_liq_distance:
                min_liq_distance = pos_risk.liquidation_distance
                worst_symbol = symbol
        
        # Handle no positions case
        if min_liq_distance == float('inf'):
            min_liq_distance = 1.0  # No positions = infinite safety
        
        net_exposure = long_exposure - short_exposure
        
        return PortfolioRisk(
            total_leverage=total_leverage,
            total_exposure=total_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            net_exposure=net_exposure,
            min_liquidation_distance=min_liq_distance,
            worst_symbol=worst_symbol,
            total_unrealized_pnl=total_unrealized_pnl
        )
    
    # ========== Section 7: Position Sizing ==========
    
    def calculate_max_position_size(
        self,
        symbol: str,
        entry_price: Decimal,
        direction: Direction,
        account: AccountState,
        current_leverage: float
    ) -> Decimal:
        """Calculate maximum safe position size (Section 7.1).
        
        Q_max = (E_available × L_target) / P_entry
        
        With liquidation safety:
        Q_safe = Q_max × (1 - safety_margin)
        
        Args:
            symbol: Symbol to size
            entry_price: Proposed entry price
            direction: Position direction
            account: Account state
            current_leverage: Current leverage
            
        Returns:
            Maximum safe quantity
        """
        # Calculate available equity for new position
        E_available = account.margin_available
        
        # Use target leverage, not max
        target_leverage = Decimal(str(self.config.L_target))
        
        # Base position size
        Q_max = (E_available * target_leverage) / entry_price
        
        # Apply safety margin for liquidation buffer
        safety_margin = Decimal(str(1 - (self.config.D_min_safe * self.config.L_target)))
        Q_safe = Q_max * safety_margin
        
        return Q_safe
    
    def calculate_reduce_quantity(
        self,
        position: Position,
        reduction_pct: Optional[float] = None
    ) -> Decimal:
        """Calculate quantity to reduce (Section 7.2).
        
        Q_reduce = Q_s × reduction_pct
        
        Args:
            position: Position to reduce
            reduction_pct: Reduction percentage (default from config)
            
        Returns:
            Quantity to close
        """
        if reduction_pct is None:
            reduction_pct = self.config.reduction_pct_default
        
        if not (0 < reduction_pct <= 1.0):
            raise ValueError(f"Reduction pct must be in (0, 1]: {reduction_pct}")
        
        Q_reduce = abs(position.quantity) * Decimal(str(reduction_pct))
        return Q_reduce
