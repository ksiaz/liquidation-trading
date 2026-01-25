"""
HLP17: Capital Manager.

Integrates all capital management and risk control components:
- Position sizing
- Risk limits
- Drawdown tracking
- Trade decision validation
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum, auto

from .position_sizer import PositionSizer, SizingConfig, SizingResult, Regime
from .risk_limits import RiskLimitsChecker, RiskLimitsConfig, Position, LimitCheckResult
from .drawdown_tracker import DrawdownTracker, DrawdownConfig, DrawdownState


class TradeDecision(Enum):
    """Trade decision result."""
    APPROVED = auto()
    REJECTED_RISK_LIMIT = auto()
    REJECTED_DRAWDOWN = auto()
    REJECTED_SIZE_ZERO = auto()
    REJECTED_INVALID_PARAMS = auto()


@dataclass
class CapitalManagerConfig:
    """Configuration for capital manager."""
    sizing: SizingConfig = field(default_factory=SizingConfig)
    limits: RiskLimitsConfig = field(default_factory=RiskLimitsConfig)
    drawdown: DrawdownConfig = field(default_factory=DrawdownConfig)


@dataclass
class TradeRequest:
    """Request to validate a potential trade."""
    symbol: str
    entry_price: float
    stop_price: float
    side: str = 'long'
    event_type: str = 'default'
    current_volatility: Optional[float] = None


@dataclass
class TradeApproval:
    """Result of trade validation."""
    decision: TradeDecision
    approved_size: float
    position_value: float
    risk_amount: float
    risk_pct: float
    rejection_reasons: List[str] = field(default_factory=list)
    details: Dict = field(default_factory=dict)


class CapitalManager:
    """
    Central capital management coordinator.

    Integrates:
    - Position sizing (how much to trade)
    - Risk limits (hard caps on exposure)
    - Drawdown tracking (dynamic risk adjustment)

    All trades must be validated through this manager.
    """

    def __init__(
        self,
        initial_capital: float,
        config: CapitalManagerConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or CapitalManagerConfig()
        self._logger = logger or logging.getLogger(__name__)

        self._capital = initial_capital

        # Initialize components
        self._sizer = PositionSizer(
            config=self._config.sizing,
            logger=self._logger
        )

        self._limits = RiskLimitsChecker(
            config=self._config.limits,
            logger=self._logger
        )

        self._drawdown = DrawdownTracker(
            initial_capital=initial_capital,
            config=self._config.drawdown,
            logger=self._logger
        )

        # Current regime
        self._regime = Regime.SIDEWAYS

    @property
    def capital(self) -> float:
        """Get current capital."""
        return self._capital

    @property
    def regime(self) -> Regime:
        """Get current regime."""
        return self._regime

    def set_regime(self, regime: Regime):
        """Set current market regime."""
        self._regime = regime
        self._logger.info(f"Regime set to {regime.name}")

    def update_capital(self, new_capital: float):
        """Update current capital value."""
        self._capital = new_capital
        self._drawdown.update_capital(new_capital)

    def validate_trade(self, request: TradeRequest) -> TradeApproval:
        """
        Validate a potential trade against all risk controls.

        This is the main entry point for trade validation.
        """
        rejection_reasons = []
        details = {}

        # Check if trading is allowed
        if not self._drawdown.is_trading_allowed():
            return TradeApproval(
                decision=TradeDecision.REJECTED_DRAWDOWN,
                approved_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                rejection_reasons=['Trading halted due to drawdown'],
                details={'drawdown_state': self._drawdown.state.name}
            )

        # Check regime
        if self._regime == Regime.DISABLED:
            return TradeApproval(
                decision=TradeDecision.REJECTED_RISK_LIMIT,
                approved_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                rejection_reasons=['Regime is DISABLED'],
                details={'regime': self._regime.name}
            )

        # Validate parameters
        if request.entry_price <= 0 or request.stop_price <= 0:
            return TradeApproval(
                decision=TradeDecision.REJECTED_INVALID_PARAMS,
                approved_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                rejection_reasons=['Invalid price parameters']
            )

        # Calculate position size
        sizing_result = self._sizer.calculate_size(
            capital=self._capital,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            current_volatility=request.current_volatility,
            regime=self._regime,
            event_type=request.event_type,
            symbol=request.symbol
        )

        # Apply drawdown multiplier
        dd_multiplier = self._drawdown.get_size_multiplier()
        adjusted_size = sizing_result.position_size * dd_multiplier
        adjusted_value = adjusted_size * request.entry_price

        details['base_size'] = sizing_result.position_size
        details['dd_multiplier'] = dd_multiplier
        details['sizing_adjustments'] = sizing_result.adjustments

        if adjusted_size <= 0:
            return TradeApproval(
                decision=TradeDecision.REJECTED_SIZE_ZERO,
                approved_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                rejection_reasons=['Calculated size is zero'],
                details=details
            )

        # Check against risk limits
        limit_check = self._limits.check_new_position(
            symbol=request.symbol,
            size=adjusted_size,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            capital=self._capital,
            side=request.side
        )

        if not limit_check.allowed:
            # Try with adjusted size
            if limit_check.adjusted_size and limit_check.adjusted_size > 0:
                adjusted_size = limit_check.adjusted_size
                adjusted_value = adjusted_size * request.entry_price
                details['size_adjusted_for_limits'] = True
                rejection_reasons.append(f"Size reduced to meet limits")
            else:
                return TradeApproval(
                    decision=TradeDecision.REJECTED_RISK_LIMIT,
                    approved_size=0,
                    position_value=0,
                    risk_amount=0,
                    risk_pct=0,
                    rejection_reasons=[v.name for v in limit_check.violations],
                    details={**details, 'limit_details': limit_check.details}
                )

        # Calculate final risk
        stop_distance = abs(request.entry_price - request.stop_price)
        risk_amount = adjusted_size * stop_distance
        risk_pct = risk_amount / self._capital if self._capital > 0 else 0

        return TradeApproval(
            decision=TradeDecision.APPROVED,
            approved_size=adjusted_size,
            position_value=adjusted_value,
            risk_amount=risk_amount,
            risk_pct=risk_pct,
            rejection_reasons=rejection_reasons,
            details=details
        )

    def record_trade_result(self, pnl: float, symbol: str = None):
        """
        Record a trade result.

        Updates all tracking components.
        """
        # Update capital
        self._capital += pnl
        self._drawdown.record_trade(pnl)

        # Update position sizer streaks
        self._sizer.record_trade_result(pnl > 0)

        # Remove position from limits tracker
        if symbol:
            self._limits.remove_position(symbol)

        self._logger.info(
            f"Trade recorded: PnL={pnl:.2f}, Capital={self._capital:.2f}"
        )

    def add_position(self, position: Position):
        """Add a position to tracking."""
        self._limits.add_position(position)

    def remove_position(self, symbol: str):
        """Remove a position from tracking."""
        self._limits.remove_position(symbol)

    def update_position_price(self, symbol: str, price: float):
        """Update current price for a tracked position."""
        self._limits.update_price(symbol, price)

    def set_correlation(self, symbol1: str, symbol2: str, correlation: float):
        """Set correlation between two symbols."""
        self._limits.set_correlation(symbol1, symbol2, correlation)

    def set_baseline_volatility(self, symbol: str, volatility: float):
        """Set baseline volatility for a symbol."""
        self._sizer.set_baseline_volatility(symbol, volatility)

    def reset_daily(self):
        """Reset daily tracking (call at start of new trading day)."""
        self._drawdown.reset_daily()

    def reset_weekly(self):
        """Reset weekly tracking (call at start of new trading week)."""
        self._drawdown.reset_weekly()

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all risk controls."""
        return {
            'capital': self._capital,
            'regime': self._regime.name,
            'drawdown': self._drawdown.get_summary(),
            'exposure': self._limits.get_exposure_summary(self._capital),
            'sizing': self._sizer.get_streak_info(),
            'trading_allowed': self.is_trading_allowed()
        }

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        if self._regime == Regime.DISABLED:
            return False
        return self._drawdown.is_trading_allowed()

    def get_available_exposure(self) -> float:
        """Get remaining available exposure capacity."""
        return self._limits.get_available_exposure(self._capital)

    def get_size_multiplier(self) -> float:
        """Get current size multiplier from all factors."""
        dd_mult = self._drawdown.get_size_multiplier()
        regime_mult = self._config.sizing.regime_scalars.get(
            self._regime.name, 1.0
        )
        return dd_mult * regime_mult
