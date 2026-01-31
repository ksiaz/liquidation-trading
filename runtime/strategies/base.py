"""
HLP10: Base Strategy State Machine.

Provides the foundation for all strategy state machines.

Key principles:
- Deterministic state transitions
- No state skipping (must follow valid transitions)
- Every transition logged
- Timeout handling for stuck states
- Cooldown enforcement

State Flow:
    DISABLED -> SCANNING: Regime becomes compatible
    SCANNING -> ARMED: Setup conditions met
    ARMED -> ENTERED: Trigger condition fires
    ARMED -> SCANNING: Timeout or invalidation
    ENTERED -> EXITED: Target, stop, or invalidation
    EXITED -> COOLDOWN: Always after exit
    COOLDOWN -> SCANNING: Cooldown period complete
    * -> DISABLED: Regime becomes incompatible
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Any, Tuple


class StrategyState(Enum):
    """Standard strategy states."""
    DISABLED = "disabled"       # Strategy inactive (wrong regime)
    SCANNING = "scanning"       # Looking for setup conditions
    PRE_ARMED = "pre_armed"    # Optional: Early warning state
    ARMED = "armed"            # Setup complete, waiting for trigger
    ENTERED = "entered"        # Position active
    EXITED = "exited"          # Position closed
    COOLDOWN = "cooldown"      # Waiting before next trade


class MandateType(Enum):
    """Types of trading mandates."""
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"
    ADJUST_STOP = "adjust_stop"
    CANCEL = "cancel"


@dataclass
class Mandate:
    """
    Trading mandate from strategy.

    Mandates are requests to the execution layer.
    They specify what action to take and why.
    """
    mandate_type: MandateType
    symbol: str
    strategy_name: str
    size: Optional[float] = None
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    reason: str = ""
    urgency: float = 1.0  # 0-1, higher = more urgent
    max_slippage: float = 0.001  # 0.1% default
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        return self.mandate_type in (MandateType.ENTER_LONG, MandateType.ENTER_SHORT)

    @property
    def is_long(self) -> bool:
        return self.mandate_type == MandateType.ENTER_LONG

    @property
    def is_short(self) -> bool:
        return self.mandate_type == MandateType.ENTER_SHORT


@dataclass
class StrategyConfig:
    """Base configuration for strategies."""
    # Timing
    armed_timeout_sec: int = 120       # Max time in ARMED state
    entry_window_sec: int = 30         # Max time to execute entry
    min_hold_sec: int = 10             # Minimum position hold time
    max_hold_sec: int = 300            # Maximum position hold time
    cooldown_sec: int = 300            # Time between trades
    entry_grace_sec: int = 10          # No exit checks after entry

    # Position sizing
    base_risk_pct: float = 0.01        # 1% base risk per trade
    max_risk_pct: float = 0.02         # 2% max risk

    # Compatible regimes
    allowed_regimes: Set[str] = field(default_factory=lambda: {'sideways'})


@dataclass
class StrategySetup:
    """
    Base class for strategy setup conditions.

    Subclass for each strategy with specific conditions.
    """
    symbol: str
    detected_at: datetime
    conditions_met: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if all conditions are met."""
        return all(self.conditions_met.values())

    @property
    def age_sec(self) -> float:
        """Time since setup was detected."""
        return (datetime.now() - self.detected_at).total_seconds()


@dataclass
class StateTransition:
    """Record of a state transition."""
    from_state: StrategyState
    to_state: StrategyState
    timestamp: datetime
    reason: str
    metrics: Dict[str, float] = field(default_factory=dict)


class StrategyStateMachine(ABC):
    """
    Base class for strategy state machines.

    Provides:
    - State management and transitions
    - Transition validation
    - Timeout handling
    - Logging and audit trail
    - Cooldown tracking

    Subclasses must implement:
    - _check_arm_conditions: When to transition SCANNING -> ARMED
    - _check_trigger_conditions: When to transition ARMED -> ENTERED
    - _check_exit_conditions: When to transition ENTERED -> EXITED
    - _calculate_mandate: Generate trading mandate for entry
    """

    # Valid state transitions
    VALID_TRANSITIONS: Dict[StrategyState, Set[StrategyState]] = {
        StrategyState.DISABLED: {StrategyState.SCANNING},
        StrategyState.SCANNING: {StrategyState.ARMED, StrategyState.PRE_ARMED, StrategyState.DISABLED},
        StrategyState.PRE_ARMED: {StrategyState.ARMED, StrategyState.SCANNING, StrategyState.DISABLED},
        StrategyState.ARMED: {StrategyState.ENTERED, StrategyState.SCANNING, StrategyState.DISABLED},
        StrategyState.ENTERED: {StrategyState.EXITED, StrategyState.DISABLED},
        StrategyState.EXITED: {StrategyState.COOLDOWN, StrategyState.DISABLED},
        StrategyState.COOLDOWN: {StrategyState.SCANNING, StrategyState.DISABLED},
    }

    def __init__(
        self,
        name: str,
        symbol: str,
        config: StrategyConfig = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize state machine.

        Args:
            name: Strategy name (e.g., 'geometry', 'cascade')
            symbol: Trading symbol
            config: Strategy configuration
            logger: Logger instance
        """
        self._name = name
        self._symbol = symbol
        self._config = config or StrategyConfig()
        self._logger = logger or logging.getLogger(f"strategy.{name}.{symbol}")

        # State
        self._state = StrategyState.DISABLED
        self._state_entered_at = datetime.now()
        self._setup: Optional[StrategySetup] = None

        # Position tracking
        self._entry_price: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        self._position_size: Optional[float] = None
        self._stop_price: Optional[float] = None

        # History
        self._transitions: List[StateTransition] = []
        self._last_exit_time: Optional[datetime] = None
        self._trade_count: int = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def state(self) -> StrategyState:
        return self._state

    @property
    def is_active(self) -> bool:
        """Check if strategy is actively looking for trades."""
        return self._state not in (StrategyState.DISABLED, StrategyState.COOLDOWN)

    @property
    def has_position(self) -> bool:
        """Check if strategy has an open position."""
        return self._state == StrategyState.ENTERED

    @property
    def time_in_state(self) -> float:
        """Seconds since entering current state."""
        return (datetime.now() - self._state_entered_at).total_seconds()

    @property
    def cooldown_remaining(self) -> float:
        """Seconds remaining in cooldown, or 0 if not in cooldown."""
        if self._state != StrategyState.COOLDOWN:
            return 0.0
        if self._last_exit_time is None:
            return 0.0
        elapsed = (datetime.now() - self._last_exit_time).total_seconds()
        return max(0.0, self._config.cooldown_sec - elapsed)

    def transition_to(self, new_state: StrategyState, reason: str = "", metrics: Dict[str, float] = None) -> bool:
        """
        Attempt to transition to a new state.

        Args:
            new_state: Target state
            reason: Why this transition is happening
            metrics: Optional metrics at transition time

        Returns:
            True if transition succeeded, False if invalid
        """
        if new_state not in self.VALID_TRANSITIONS.get(self._state, set()):
            self._logger.warning(
                f"Invalid transition: {self._state.value} -> {new_state.value}"
            )
            return False

        old_state = self._state
        self._state = new_state
        self._state_entered_at = datetime.now()

        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now(),
            reason=reason,
            metrics=metrics or {},
        )
        self._transitions.append(transition)

        self._logger.info(
            f"Transition: {old_state.value} -> {new_state.value} ({reason})"
        )

        # Handle special transitions
        if new_state == StrategyState.EXITED:
            self._last_exit_time = datetime.now()
            self._trade_count += 1
            self._clear_position()

        elif new_state == StrategyState.SCANNING:
            self._setup = None

        return True

    def _clear_position(self):
        """Clear position tracking after exit."""
        self._entry_price = None
        self._entry_time = None
        self._position_size = None
        self._stop_price = None

    def enable(self, regime: str) -> bool:
        """
        Enable strategy if regime is compatible.

        Args:
            regime: Current market regime

        Returns:
            True if strategy is now enabled
        """
        if regime.lower() in self._config.allowed_regimes:
            if self._state == StrategyState.DISABLED:
                return self.transition_to(
                    StrategyState.SCANNING,
                    reason=f"Regime '{regime}' is compatible"
                )
            return True
        else:
            if self._state != StrategyState.DISABLED:
                return self.transition_to(
                    StrategyState.DISABLED,
                    reason=f"Regime '{regime}' not compatible"
                )
            return False

    def evaluate(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """
        Evaluate current market state and return mandate if action needed.

        This is the main entry point called on each update.

        Args:
            market_state: Current market data and indicators

        Returns:
            Mandate if action should be taken, None otherwise
        """
        # Handle timeouts
        self._check_timeouts()

        # State-specific evaluation
        if self._state == StrategyState.DISABLED:
            return None

        elif self._state == StrategyState.SCANNING:
            return self._evaluate_scanning(market_state)

        elif self._state == StrategyState.PRE_ARMED:
            return self._evaluate_pre_armed(market_state)

        elif self._state == StrategyState.ARMED:
            return self._evaluate_armed(market_state)

        elif self._state == StrategyState.ENTERED:
            return self._evaluate_entered(market_state)

        elif self._state == StrategyState.EXITED:
            # Always transition to cooldown
            self.transition_to(StrategyState.COOLDOWN, "Position closed")
            return None

        elif self._state == StrategyState.COOLDOWN:
            return self._evaluate_cooldown(market_state)

        return None

    def _check_timeouts(self):
        """Check for state timeouts and handle appropriately."""
        if self._state == StrategyState.ARMED:
            if self.time_in_state > self._config.armed_timeout_sec:
                self.transition_to(
                    StrategyState.SCANNING,
                    reason=f"Armed timeout ({self._config.armed_timeout_sec}s)"
                )

        elif self._state == StrategyState.ENTERED:
            if self.time_in_state > self._config.max_hold_sec:
                # This should trigger an exit
                self._logger.warning(
                    f"Position held beyond max time ({self._config.max_hold_sec}s)"
                )

    def _evaluate_scanning(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """Evaluate market while scanning for setup."""
        setup = self._check_arm_conditions(market_state)

        if setup and setup.is_valid:
            self._setup = setup

            # Check if we use PRE_ARMED state
            if self._use_pre_armed():
                self.transition_to(
                    StrategyState.PRE_ARMED,
                    reason="Pre-arm conditions met",
                    metrics=setup.metrics,
                )
            else:
                self.transition_to(
                    StrategyState.ARMED,
                    reason="Arm conditions met",
                    metrics=setup.metrics,
                )

        return None

    def _evaluate_pre_armed(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """Evaluate during pre-armed state."""
        # Check if we should advance to ARMED
        if self._check_pre_arm_to_arm(market_state):
            self.transition_to(
                StrategyState.ARMED,
                reason="Pre-arm to arm conditions met",
            )
        # Check if we should fall back to SCANNING
        elif self._check_pre_arm_invalidation(market_state):
            self.transition_to(
                StrategyState.SCANNING,
                reason="Pre-arm conditions invalidated",
            )

        return None

    def _evaluate_armed(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """Evaluate while armed, looking for trigger."""
        # Check for trigger
        trigger_result = self._check_trigger_conditions(market_state)

        if trigger_result:
            # Generate entry mandate
            mandate = self._calculate_mandate(market_state, trigger_result)

            if mandate:
                self.transition_to(
                    StrategyState.ENTERED,
                    reason=trigger_result.get('reason', 'Trigger conditions met'),
                    metrics=trigger_result.get('metrics', {}),
                )
                return mandate

        # Check for invalidation
        if self._check_arm_invalidation(market_state):
            self.transition_to(
                StrategyState.SCANNING,
                reason="Armed conditions invalidated",
            )

        return None

    def _evaluate_entered(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """Evaluate while in position."""
        # Check grace period
        if self._entry_time:
            time_since_entry = (datetime.now() - self._entry_time).total_seconds()
            if time_since_entry < self._config.entry_grace_sec:
                return None  # No exit checks during grace period

        # Check exit conditions
        exit_result = self._check_exit_conditions(market_state)

        if exit_result:
            mandate = Mandate(
                mandate_type=MandateType.EXIT,
                symbol=self._symbol,
                strategy_name=self._name,
                size=self._position_size,
                reason=exit_result.get('reason', 'Exit conditions met'),
                metadata=exit_result,
            )
            self.transition_to(
                StrategyState.EXITED,
                reason=exit_result.get('reason', 'Exit conditions met'),
                metrics=exit_result.get('metrics', {}),
            )
            return mandate

        return None

    def _evaluate_cooldown(self, market_state: Dict[str, Any]) -> Optional[Mandate]:
        """Evaluate during cooldown period."""
        if self.cooldown_remaining <= 0:
            self.transition_to(
                StrategyState.SCANNING,
                reason="Cooldown complete",
            )

        return None

    def _use_pre_armed(self) -> bool:
        """Override to enable PRE_ARMED state for this strategy."""
        return False

    def _check_pre_arm_to_arm(self, market_state: Dict[str, Any]) -> bool:
        """Override: Check if should advance from PRE_ARMED to ARMED."""
        return True  # Default: immediately advance

    def _check_pre_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Override: Check if PRE_ARMED conditions are invalidated."""
        return False

    def _check_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Override: Check if ARMED conditions are invalidated."""
        return False

    @abstractmethod
    def _check_arm_conditions(self, market_state: Dict[str, Any]) -> Optional[StrategySetup]:
        """
        Check if conditions for arming are met.

        Returns setup object if conditions met, None otherwise.
        """
        pass

    @abstractmethod
    def _check_trigger_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if trigger conditions are met.

        Returns dict with trigger info if triggered, None otherwise.
        """
        pass

    @abstractmethod
    def _check_exit_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if exit conditions are met.

        Returns dict with exit info if should exit, None otherwise.
        """
        pass

    @abstractmethod
    def _calculate_mandate(
        self,
        market_state: Dict[str, Any],
        trigger_result: Dict[str, Any],
    ) -> Optional[Mandate]:
        """
        Calculate entry mandate based on market state and trigger.

        Returns mandate if valid entry, None otherwise.
        """
        pass

    def record_fill(self, price: float, size: float, is_entry: bool = True):
        """Record a fill from the execution layer."""
        if is_entry:
            self._entry_price = price
            self._entry_time = datetime.now()
            self._position_size = size
            self._logger.info(f"Entry fill recorded: {size} @ {price}")
        else:
            self._logger.info(f"Exit fill recorded: {size} @ {price}")

    def set_stop(self, stop_price: float):
        """Set stop price for current position."""
        self._stop_price = stop_price
        self._logger.info(f"Stop set: {stop_price}")

    def get_summary(self) -> Dict[str, Any]:
        """Get strategy state summary."""
        return {
            'name': self._name,
            'symbol': self._symbol,
            'state': self._state.value,
            'time_in_state': self.time_in_state,
            'has_position': self.has_position,
            'trade_count': self._trade_count,
            'entry_price': self._entry_price,
            'stop_price': self._stop_price,
            'cooldown_remaining': self.cooldown_remaining,
            'last_transition': self._transitions[-1].to_state.value if self._transitions else None,
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent transition history."""
        return [
            {
                'from': t.from_state.value,
                'to': t.to_state.value,
                'timestamp': t.timestamp.isoformat(),
                'reason': t.reason,
                'metrics': t.metrics,
            }
            for t in self._transitions[-limit:]
        ]
