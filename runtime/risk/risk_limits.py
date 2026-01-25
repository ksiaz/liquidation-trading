"""
HLP17: Risk Limits Checker.

Hard caps on position sizes and exposures:
1. Max position size per symbol (5%)
2. Max aggregate exposure (10%)
3. Max correlated exposure (7%)
4. Leverage limit (1x)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum, auto


class LimitViolation(Enum):
    """Types of risk limit violations."""
    POSITION_SIZE_EXCEEDED = auto()
    AGGREGATE_EXPOSURE_EXCEEDED = auto()
    CORRELATED_EXPOSURE_EXCEEDED = auto()
    LEVERAGE_EXCEEDED = auto()
    MAX_POSITIONS_EXCEEDED = auto()
    PORTFOLIO_HEAT_EXCEEDED = auto()


@dataclass
class RiskLimitsConfig:
    """Configuration for risk limits."""
    # Position limits
    max_position_size_pct: float = 0.05  # 5% per symbol
    max_aggregate_exposure_pct: float = 0.10  # 10% total
    max_correlated_exposure_pct: float = 0.07  # 7% correlated
    max_leverage: float = 1.0  # No leverage
    max_concurrent_positions: int = 1

    # Correlation threshold
    correlation_threshold: float = 0.7  # Above this = correlated

    # Portfolio heat
    max_portfolio_heat_pct: float = 0.10  # 10%


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    size: float  # In base currency
    entry_price: float
    current_price: float
    stop_price: float
    side: str  # 'long' or 'short'

    @property
    def value(self) -> float:
        """Position value in quote currency."""
        return abs(self.size * self.current_price)

    @property
    def stop_distance_pct(self) -> float:
        """Distance to stop as percentage."""
        if self.entry_price <= 0:
            return 0
        return abs(self.entry_price - self.stop_price) / self.entry_price

    @property
    def heat(self) -> float:
        """Position heat = value * stop_distance_pct."""
        return self.value * self.stop_distance_pct


@dataclass
class LimitCheckResult:
    """Result of a risk limit check."""
    allowed: bool
    violations: List[LimitViolation] = field(default_factory=list)
    details: Dict = field(default_factory=dict)
    adjusted_size: Optional[float] = None  # Size that would be allowed


class RiskLimitsChecker:
    """
    Checks positions against risk limits.

    Validates that new positions don't exceed:
    - Per-symbol limits
    - Aggregate exposure limits
    - Correlated exposure limits
    - Leverage limits
    """

    def __init__(
        self,
        config: RiskLimitsConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or RiskLimitsConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Current positions
        self._positions: Dict[str, Position] = {}

        # Correlation matrix
        self._correlations: Dict[Tuple[str, str], float] = {}

    def set_correlation(self, symbol1: str, symbol2: str, correlation: float):
        """Set correlation between two symbols."""
        # Store both directions
        self._correlations[(symbol1, symbol2)] = correlation
        self._correlations[(symbol2, symbol1)] = correlation

    def get_correlation(self, symbol1: str, symbol2: str) -> float:
        """Get correlation between two symbols."""
        if symbol1 == symbol2:
            return 1.0
        return self._correlations.get((symbol1, symbol2), 0.0)

    def add_position(self, position: Position):
        """Add or update a position."""
        self._positions[position.symbol] = position

    def remove_position(self, symbol: str):
        """Remove a position."""
        self._positions.pop(symbol, None)

    def update_price(self, symbol: str, price: float):
        """Update current price for a position."""
        if symbol in self._positions:
            self._positions[symbol].current_price = price

    def check_new_position(
        self,
        symbol: str,
        size: float,
        entry_price: float,
        stop_price: float,
        capital: float,
        side: str = 'long'
    ) -> LimitCheckResult:
        """
        Check if a new position would violate any limits.

        Args:
            symbol: Trading symbol
            size: Position size in base currency
            entry_price: Entry price
            stop_price: Stop loss price
            capital: Current account capital
            side: Position side ('long' or 'short')

        Returns:
            LimitCheckResult with allowed flag and violations
        """
        violations = []
        details = {}

        if capital <= 0:
            return LimitCheckResult(
                allowed=False,
                violations=[],
                details={'error': 'Invalid capital'}
            )

        # Create proposed position
        proposed = Position(
            symbol=symbol,
            size=size,
            entry_price=entry_price,
            current_price=entry_price,
            stop_price=stop_price,
            side=side
        )

        # Check 1: Position size limit
        position_value = proposed.value
        position_pct = position_value / capital

        if position_pct > self._config.max_position_size_pct:
            violations.append(LimitViolation.POSITION_SIZE_EXCEEDED)
            details['position_pct'] = position_pct
            details['max_position_pct'] = self._config.max_position_size_pct

        # Check 2: Max concurrent positions
        current_count = len(self._positions)
        if symbol not in self._positions:  # New position
            if current_count >= self._config.max_concurrent_positions:
                violations.append(LimitViolation.MAX_POSITIONS_EXCEEDED)
                details['current_positions'] = current_count
                details['max_positions'] = self._config.max_concurrent_positions

        # Check 3: Aggregate exposure
        current_exposure = sum(p.value for p in self._positions.values())
        new_total = current_exposure + position_value

        # Subtract existing position for same symbol (if updating)
        if symbol in self._positions:
            new_total -= self._positions[symbol].value

        aggregate_pct = new_total / capital

        if aggregate_pct > self._config.max_aggregate_exposure_pct:
            violations.append(LimitViolation.AGGREGATE_EXPOSURE_EXCEEDED)
            details['aggregate_pct'] = aggregate_pct
            details['max_aggregate_pct'] = self._config.max_aggregate_exposure_pct

        # Check 4: Correlated exposure
        correlated_exposure = self._calculate_correlated_exposure(
            symbol, position_value, capital
        )
        details['correlated_pct'] = correlated_exposure / capital if capital > 0 else 0

        if correlated_exposure / capital > self._config.max_correlated_exposure_pct:
            violations.append(LimitViolation.CORRELATED_EXPOSURE_EXCEEDED)
            details['max_correlated_pct'] = self._config.max_correlated_exposure_pct

        # Check 5: Portfolio heat
        current_heat = sum(p.heat for p in self._positions.values())
        new_heat = current_heat + proposed.heat

        if symbol in self._positions:
            new_heat -= self._positions[symbol].heat

        heat_pct = new_heat / capital if capital > 0 else 0

        if heat_pct > self._config.max_portfolio_heat_pct:
            violations.append(LimitViolation.PORTFOLIO_HEAT_EXCEEDED)
            details['portfolio_heat_pct'] = heat_pct
            details['max_heat_pct'] = self._config.max_portfolio_heat_pct

        # Calculate adjusted size that would be allowed
        adjusted_size = None
        if violations:
            adjusted_size = self._calculate_max_allowed_size(
                symbol, entry_price, stop_price, capital, side
            )

        return LimitCheckResult(
            allowed=len(violations) == 0,
            violations=violations,
            details=details,
            adjusted_size=adjusted_size
        )

    def _calculate_correlated_exposure(
        self,
        symbol: str,
        position_value: float,
        capital: float
    ) -> float:
        """Calculate correlated exposure for a symbol."""
        correlated_value = position_value  # Include the position itself

        for pos_symbol, position in self._positions.items():
            if pos_symbol == symbol:
                continue

            correlation = self.get_correlation(symbol, pos_symbol)
            if correlation >= self._config.correlation_threshold:
                correlated_value += position.value

        return correlated_value

    def _calculate_max_allowed_size(
        self,
        symbol: str,
        entry_price: float,
        stop_price: float,
        capital: float,
        side: str
    ) -> float:
        """Calculate the maximum position size that would be allowed."""
        if entry_price <= 0 or capital <= 0:
            return 0

        # Start with position size limit
        max_value_by_position = capital * self._config.max_position_size_pct

        # Check aggregate limit
        current_exposure = sum(
            p.value for s, p in self._positions.items() if s != symbol
        )
        max_value_by_aggregate = (
            capital * self._config.max_aggregate_exposure_pct - current_exposure
        )

        # Check correlated limit
        correlated_exposure = 0
        for pos_symbol, position in self._positions.items():
            if pos_symbol == symbol:
                continue
            correlation = self.get_correlation(symbol, pos_symbol)
            if correlation >= self._config.correlation_threshold:
                correlated_exposure += position.value

        max_value_by_correlated = (
            capital * self._config.max_correlated_exposure_pct - correlated_exposure
        )

        # Take the minimum
        max_value = max(
            0,
            min(max_value_by_position, max_value_by_aggregate, max_value_by_correlated)
        )

        # Convert to size
        return max_value / entry_price

    def get_exposure_summary(self, capital: float) -> Dict:
        """Get current exposure summary."""
        total_exposure = sum(p.value for p in self._positions.values())
        total_heat = sum(p.heat for p in self._positions.values())

        return {
            'position_count': len(self._positions),
            'max_positions': self._config.max_concurrent_positions,
            'total_exposure_usd': total_exposure,
            'exposure_pct': total_exposure / capital if capital > 0 else 0,
            'max_exposure_pct': self._config.max_aggregate_exposure_pct,
            'portfolio_heat_usd': total_heat,
            'heat_pct': total_heat / capital if capital > 0 else 0,
            'max_heat_pct': self._config.max_portfolio_heat_pct,
            'positions': {
                symbol: {
                    'value': p.value,
                    'heat': p.heat,
                    'stop_distance_pct': p.stop_distance_pct
                }
                for symbol, p in self._positions.items()
            }
        }

    def get_available_exposure(self, capital: float) -> float:
        """Get available exposure capacity."""
        current = sum(p.value for p in self._positions.values())
        max_allowed = capital * self._config.max_aggregate_exposure_pct
        return max(0, max_allowed - current)

    def clear_positions(self):
        """Clear all tracked positions."""
        self._positions.clear()
