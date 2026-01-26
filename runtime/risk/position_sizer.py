"""
HLP17: Position Sizing Calculator.

Calculates position sizes based on:
1. Fixed fractional method
2. Volatility adjustment
3. Event multipliers
4. Dynamic streak adjustments

Hardenings:
- H2-A: Size floor (prevents under-sizing from stacked adjustments)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum, auto


class SizingMethod(Enum):
    """Position sizing method."""
    FIXED_FRACTIONAL = auto()
    VOLATILITY_ADJUSTED = auto()
    KELLY = auto()


class Regime(Enum):
    """Market regime."""
    SIDEWAYS = auto()
    EXPANSION = auto()
    DISABLED = auto()


@dataclass
class SizingConfig:
    """Configuration for position sizing."""
    # Base risk settings
    risk_per_trade_default: float = 0.01  # 1%
    risk_per_trade_max: float = 0.02  # 2%
    risk_per_trade_min: float = 0.005  # 0.5%

    # H2-A: Size floor (prevents under-sizing)
    min_risk_pct_floor: float = 0.003  # 0.3% absolute minimum after all adjustments

    # Volatility adjustment
    max_volatility_scalar: float = 2.0
    min_volatility_scalar: float = 0.5

    # Regime scalars
    regime_scalars: Dict[str, float] = field(default_factory=lambda: {
        'SIDEWAYS': 1.0,
        'EXPANSION': 0.75,
        'DISABLED': 0.0
    })

    # Event type multipliers (1.0 until validated)
    event_multipliers: Dict[str, float] = field(default_factory=lambda: {
        'liquidation_cascade': 1.0,
        'failed_hunt': 1.0,
        'funding_snapback': 1.0,
        'inventory_distribution': 0.75,
        'default': 1.0
    })

    # Dynamic adjustment thresholds
    wins_for_increase: int = 3
    losses_for_decrease: int = 2

    # Kelly settings
    kelly_fraction: float = 0.1  # Tenth Kelly


@dataclass
class SizingResult:
    """Result of position size calculation."""
    position_size: float  # In base currency (e.g., BTC)
    position_value: float  # In quote currency (e.g., USD)
    risk_amount: float  # Dollar risk
    risk_pct: float  # Percent of capital risked
    method: SizingMethod
    adjustments: Dict = field(default_factory=dict)


class PositionSizer:
    """
    Calculates position sizes following HLP17 rules.

    Size = (capital × risk_per_trade) / stop_distance
    With adjustments for volatility, regime, and streaks.
    """

    def __init__(
        self,
        config: SizingConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or SizingConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Track win/loss streak
        self._consecutive_wins = 0
        self._consecutive_losses = 0

        # Track current risk level
        self._current_risk_pct = self._config.risk_per_trade_default

        # Volatility baselines by symbol
        self._baseline_volatility: Dict[str, float] = {}

    def calculate_size(
        self,
        capital: float,
        entry_price: float,
        stop_price: float,
        current_volatility: float = None,
        regime: Regime = Regime.SIDEWAYS,
        event_type: str = 'default',
        symbol: str = None
    ) -> SizingResult:
        """
        Calculate position size.

        Args:
            capital: Current account value in USD
            entry_price: Entry price
            stop_price: Stop loss price
            current_volatility: Current 24h ATR (optional)
            regime: Market regime
            event_type: Type of event triggering trade
            symbol: Trading symbol (for volatility baseline)

        Returns:
            SizingResult with calculated size and details
        """
        if capital <= 0:
            return SizingResult(
                position_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                method=SizingMethod.FIXED_FRACTIONAL,
                adjustments={'error': 'Invalid capital'}
            )

        # Calculate stop distance
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return SizingResult(
                position_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                method=SizingMethod.FIXED_FRACTIONAL,
                adjustments={'error': 'Invalid stop distance'}
            )

        adjustments = {}

        # Get base risk percentage
        risk_pct = self._current_risk_pct
        adjustments['base_risk_pct'] = risk_pct

        # Apply regime scalar
        regime_scalar = self._config.regime_scalars.get(regime.name, 1.0)
        risk_pct *= regime_scalar
        adjustments['regime_scalar'] = regime_scalar

        # Apply event multiplier
        event_multiplier = self._config.event_multipliers.get(
            event_type,
            self._config.event_multipliers['default']
        )
        adjustments['event_multiplier'] = event_multiplier

        # Calculate base size (fixed fractional)
        risk_amount = capital * risk_pct
        base_size = risk_amount / stop_distance

        # Apply volatility adjustment if available
        volatility_scalar = 1.0
        if current_volatility is not None and symbol is not None:
            volatility_scalar = self._calculate_volatility_scalar(
                symbol, current_volatility
            )
            adjustments['volatility_scalar'] = volatility_scalar

        # Final position size
        position_size = base_size * event_multiplier * volatility_scalar

        # Calculate position value
        position_value = position_size * entry_price

        # Calculate actual risk
        actual_risk = position_size * stop_distance
        actual_risk_pct = actual_risk / capital if capital > 0 else 0

        # H2-A: Apply size floor to prevent under-sizing
        if actual_risk_pct < self._config.min_risk_pct_floor and actual_risk_pct > 0:
            # Scale up to meet minimum floor
            floor_multiplier = self._config.min_risk_pct_floor / actual_risk_pct
            position_size *= floor_multiplier
            position_value = position_size * entry_price
            actual_risk = position_size * stop_distance
            actual_risk_pct = self._config.min_risk_pct_floor
            adjustments['floor_applied'] = True
            adjustments['floor_multiplier'] = floor_multiplier

        # AUDIT-P0-5: Re-validate against max risk limit after floor application
        # This prevents floor from bypassing maximum risk constraints
        if actual_risk_pct > self._config.risk_per_trade_max:
            # Cap at maximum risk
            cap_scalar = self._config.risk_per_trade_max / actual_risk_pct
            position_size *= cap_scalar
            position_value = position_size * entry_price
            actual_risk = position_size * stop_distance
            actual_risk_pct = self._config.risk_per_trade_max
            adjustments['max_cap_applied'] = True
            adjustments['max_cap_scalar'] = cap_scalar

        return SizingResult(
            position_size=position_size,
            position_value=position_value,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=SizingMethod.VOLATILITY_ADJUSTED if current_volatility else SizingMethod.FIXED_FRACTIONAL,
            adjustments=adjustments
        )

    def _calculate_volatility_scalar(
        self,
        symbol: str,
        current_volatility: float
    ) -> float:
        """Calculate volatility-based size adjustment."""
        if symbol not in self._baseline_volatility:
            # First reading becomes baseline
            self._baseline_volatility[symbol] = current_volatility
            return 1.0

        baseline = self._baseline_volatility[symbol]
        if baseline <= 0 or current_volatility <= 0:
            return 1.0

        # Scalar = baseline / current
        # Higher volatility = smaller size
        scalar = baseline / current_volatility

        # Clamp to limits
        scalar = max(
            self._config.min_volatility_scalar,
            min(scalar, self._config.max_volatility_scalar)
        )

        return scalar

    def set_baseline_volatility(self, symbol: str, volatility: float):
        """Set baseline volatility for a symbol."""
        self._baseline_volatility[symbol] = volatility

    def record_trade_result(self, is_win: bool):
        """Record trade result for dynamic sizing adjustment."""
        if is_win:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
            self._adjust_risk_after_win()
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0
            self._adjust_risk_after_loss()

    def _adjust_risk_after_win(self):
        """Adjust risk percentage after a win."""
        if self._consecutive_wins >= 5:
            self._current_risk_pct = min(
                0.015,  # 1.5%
                self._config.risk_per_trade_max
            )
        elif self._consecutive_wins >= 3:
            self._current_risk_pct = min(
                0.0125,  # 1.25%
                self._config.risk_per_trade_max
            )

        self._logger.debug(
            f"After {self._consecutive_wins} wins, risk = {self._current_risk_pct*100:.2f}%"
        )

    def _adjust_risk_after_loss(self):
        """Adjust risk percentage after a loss."""
        if self._consecutive_losses >= 4:
            self._current_risk_pct = self._config.risk_per_trade_min  # 0.5%
        elif self._consecutive_losses >= 2:
            self._current_risk_pct = 0.0075  # 0.75%
        else:
            # Single loss resets to default
            self._current_risk_pct = self._config.risk_per_trade_default

        self._logger.debug(
            f"After {self._consecutive_losses} losses, risk = {self._current_risk_pct*100:.2f}%"
        )

    def reset_streak(self):
        """Reset win/loss streak tracking."""
        self._consecutive_wins = 0
        self._consecutive_losses = 0
        self._current_risk_pct = self._config.risk_per_trade_default

    def calculate_kelly_size(
        self,
        capital: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        entry_price: float
    ) -> SizingResult:
        """
        Calculate position size using Kelly criterion.

        Uses fractional Kelly (tenth by default) for safety.
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return SizingResult(
                position_size=0,
                position_value=0,
                risk_amount=0,
                risk_pct=0,
                method=SizingMethod.KELLY,
                adjustments={'error': 'Invalid Kelly parameters'}
            )

        # Kelly formula: f = (p*b - q) / b
        p = win_rate
        q = 1 - win_rate
        b = avg_win / avg_loss

        kelly_fraction = (p * b - q) / b

        # Apply fractional Kelly
        safe_fraction = kelly_fraction * self._config.kelly_fraction

        # Clamp to max risk
        safe_fraction = max(0, min(safe_fraction, self._config.risk_per_trade_max))

        # Calculate size
        risk_amount = capital * safe_fraction
        position_value = risk_amount  # Simplified for Kelly
        position_size = position_value / entry_price if entry_price > 0 else 0

        return SizingResult(
            position_size=position_size,
            position_value=position_value,
            risk_amount=risk_amount,
            risk_pct=safe_fraction,
            method=SizingMethod.KELLY,
            adjustments={
                'raw_kelly': kelly_fraction,
                'fractional_kelly': safe_fraction,
                'win_rate': win_rate,
                'win_loss_ratio': b
            }
        )

    def get_current_risk_pct(self) -> float:
        """Get current risk percentage."""
        return self._current_risk_pct

    def get_streak_info(self) -> Dict:
        """Get current streak information."""
        return {
            'consecutive_wins': self._consecutive_wins,
            'consecutive_losses': self._consecutive_losses,
            'current_risk_pct': self._current_risk_pct
        }
