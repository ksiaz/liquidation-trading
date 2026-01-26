"""
Pillar 4: Quarantine Controller.

Controls capital quarantine during risk spikes. Locks a portion of capital
when adverse conditions are detected, releases after stability is proven.

Triggers:
- Drawdown velocity exceeds threshold
- Volatility ratio exceeds threshold
- Combined risk score exceeds threshold

Behavior:
- Lock configurable percentage of capital (default 25%)
- Trade with reduced slice
- Release after stability period (default 2 hours)
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple
from enum import Enum


class QuarantineTrigger(Enum):
    """Reasons for quarantine activation."""
    NONE = "NONE"
    DRAWDOWN_VELOCITY = "DRAWDOWN_VELOCITY"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    COMBINED_RISK = "COMBINED_RISK"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class QuarantineState:
    """Current quarantine state."""
    ts_ns: int
    is_active: bool
    quarantine_pct: float          # Percentage of capital locked (0.0 to 1.0)
    available_capital_pct: float   # Percentage available for trading (1.0 - quarantine_pct)
    trigger: QuarantineTrigger
    trigger_value: float           # Value that triggered quarantine
    activated_at_ns: Optional[int]
    release_eligible_at_ns: Optional[int]
    stability_duration_ns: int     # How long stability must be proven


@dataclass(frozen=True)
class QuarantineInputs:
    """Inputs for quarantine evaluation."""
    # Drawdown velocity (pct per hour, positive = losing)
    drawdown_velocity_pct_per_hour: float = 0.0

    # Volatility ratio (current vs baseline)
    volatility_ratio: float = 1.0

    # Current drawdown level
    current_drawdown_pct: float = 0.0

    # Time since last adverse event
    time_since_adverse_ns: int = 0


@dataclass
class QuarantineThresholds:
    """Configurable thresholds for quarantine."""
    # Drawdown velocity threshold (pct per hour)
    drawdown_velocity_threshold: float = 2.0  # Losing 2% per hour

    # Volatility ratio threshold
    volatility_ratio_threshold: float = 2.0  # 2x baseline

    # Combined risk threshold
    combined_risk_threshold: float = 1.5  # Weighted sum

    # Quarantine parameters
    default_quarantine_pct: float = 0.25  # Lock 25% of capital
    escalated_quarantine_pct: float = 0.50  # Lock 50% for severe

    # Stability period (nanoseconds)
    stability_period_ns: int = 2 * 60 * 60 * 1_000_000_000  # 2 hours

    # Weights for combined risk
    drawdown_velocity_weight: float = 0.4
    volatility_ratio_weight: float = 0.4
    drawdown_level_weight: float = 0.2


class QuarantineController:
    """
    Controls capital quarantine based on risk conditions.

    State machine:
    - INACTIVE: Normal operation, no capital locked
    - ACTIVE: Capital is quarantined, trading with reduced slice
    - RELEASING: Stability period in progress, awaiting full release

    Transitions:
    - INACTIVE -> ACTIVE: Risk trigger exceeded
    - ACTIVE -> RELEASING: Risk trigger normalized
    - RELEASING -> INACTIVE: Stability period completed
    - RELEASING -> ACTIVE: Risk trigger exceeded again
    """

    def __init__(self, thresholds: Optional[QuarantineThresholds] = None):
        self._thresholds = thresholds or QuarantineThresholds()

        # Internal state
        self._is_active: bool = False
        self._quarantine_pct: float = 0.0
        self._trigger: QuarantineTrigger = QuarantineTrigger.NONE
        self._trigger_value: float = 0.0
        self._activated_at_ns: Optional[int] = None
        self._normalized_at_ns: Optional[int] = None  # When conditions normalized

    def evaluate(
        self,
        inputs: QuarantineInputs,
        now_ns: Optional[int] = None,
    ) -> QuarantineState:
        """
        Evaluate quarantine conditions and return current state.

        Args:
            inputs: Current risk metrics
            now_ns: Current timestamp

        Returns:
            Current quarantine state
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        t = self._thresholds

        # Check if any trigger is active
        trigger, trigger_value = self._check_triggers(inputs)

        if trigger != QuarantineTrigger.NONE:
            # Risk condition detected
            self._activate_quarantine(trigger, trigger_value, inputs, now_ns)
        elif self._is_active:
            # Check if we can release
            self._check_release(now_ns)

        # Compute release eligibility
        release_eligible_at_ns = None
        if self._is_active and self._normalized_at_ns:
            release_eligible_at_ns = self._normalized_at_ns + t.stability_period_ns

        return QuarantineState(
            ts_ns=now_ns,
            is_active=self._is_active,
            quarantine_pct=self._quarantine_pct,
            available_capital_pct=1.0 - self._quarantine_pct,
            trigger=self._trigger,
            trigger_value=self._trigger_value,
            activated_at_ns=self._activated_at_ns,
            release_eligible_at_ns=release_eligible_at_ns,
            stability_duration_ns=t.stability_period_ns,
        )

    def _check_triggers(
        self,
        inputs: QuarantineInputs,
    ) -> Tuple[QuarantineTrigger, float]:
        """Check which trigger is active (if any)."""
        t = self._thresholds

        # Check drawdown velocity
        if inputs.drawdown_velocity_pct_per_hour >= t.drawdown_velocity_threshold:
            return QuarantineTrigger.DRAWDOWN_VELOCITY, inputs.drawdown_velocity_pct_per_hour

        # Check volatility ratio
        if inputs.volatility_ratio >= t.volatility_ratio_threshold:
            return QuarantineTrigger.VOLATILITY_SPIKE, inputs.volatility_ratio

        # Check combined risk
        combined_risk = self._compute_combined_risk(inputs)
        if combined_risk >= t.combined_risk_threshold:
            return QuarantineTrigger.COMBINED_RISK, combined_risk

        return QuarantineTrigger.NONE, 0.0

    def _compute_combined_risk(self, inputs: QuarantineInputs) -> float:
        """Compute combined risk score."""
        t = self._thresholds

        # Normalize each component to 0-1 range based on thresholds
        dd_velocity_normalized = min(1.0, inputs.drawdown_velocity_pct_per_hour / t.drawdown_velocity_threshold)
        volatility_normalized = min(1.0, (inputs.volatility_ratio - 1.0) / (t.volatility_ratio_threshold - 1.0))
        dd_level_normalized = min(1.0, inputs.current_drawdown_pct / 10.0)  # 10% DD = 1.0

        return (
            t.drawdown_velocity_weight * dd_velocity_normalized +
            t.volatility_ratio_weight * volatility_normalized +
            t.drawdown_level_weight * dd_level_normalized
        )

    def _activate_quarantine(
        self,
        trigger: QuarantineTrigger,
        trigger_value: float,
        inputs: QuarantineInputs,
        now_ns: int,
    ) -> None:
        """Activate or escalate quarantine."""
        t = self._thresholds

        if not self._is_active:
            # New activation
            self._is_active = True
            self._activated_at_ns = now_ns
            self._quarantine_pct = t.default_quarantine_pct
        else:
            # Already active - check for escalation
            if trigger_value > self._trigger_value * 1.5:
                # Escalate
                self._quarantine_pct = min(t.escalated_quarantine_pct, self._quarantine_pct * 1.5)

        self._trigger = trigger
        self._trigger_value = trigger_value
        self._normalized_at_ns = None  # Reset normalization timestamp

    def _check_release(self, now_ns: int) -> None:
        """Check if quarantine can be released."""
        t = self._thresholds

        if self._normalized_at_ns is None:
            # Conditions just normalized, start stability timer
            self._normalized_at_ns = now_ns
            return

        # Check if stability period has passed
        time_stable_ns = now_ns - self._normalized_at_ns
        if time_stable_ns >= t.stability_period_ns:
            # Release quarantine
            self._release_quarantine()

    def _release_quarantine(self) -> None:
        """Release quarantine and reset state."""
        self._is_active = False
        self._quarantine_pct = 0.0
        self._trigger = QuarantineTrigger.NONE
        self._trigger_value = 0.0
        self._activated_at_ns = None
        self._normalized_at_ns = None

    def force_activate(
        self,
        quarantine_pct: float = 0.25,
        now_ns: Optional[int] = None,
    ) -> QuarantineState:
        """
        Manually activate quarantine.

        Args:
            quarantine_pct: Percentage of capital to lock
            now_ns: Current timestamp

        Returns:
            New quarantine state
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        self._is_active = True
        self._quarantine_pct = quarantine_pct
        self._trigger = QuarantineTrigger.MANUAL
        self._trigger_value = 0.0
        self._activated_at_ns = now_ns
        self._normalized_at_ns = None

        return QuarantineState(
            ts_ns=now_ns,
            is_active=True,
            quarantine_pct=quarantine_pct,
            available_capital_pct=1.0 - quarantine_pct,
            trigger=QuarantineTrigger.MANUAL,
            trigger_value=0.0,
            activated_at_ns=now_ns,
            release_eligible_at_ns=None,
            stability_duration_ns=self._thresholds.stability_period_ns,
        )

    def force_release(self, now_ns: Optional[int] = None) -> QuarantineState:
        """
        Manually release quarantine.

        Args:
            now_ns: Current timestamp

        Returns:
            New quarantine state
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        self._release_quarantine()

        return QuarantineState(
            ts_ns=now_ns,
            is_active=False,
            quarantine_pct=0.0,
            available_capital_pct=1.0,
            trigger=QuarantineTrigger.NONE,
            trigger_value=0.0,
            activated_at_ns=None,
            release_eligible_at_ns=None,
            stability_duration_ns=self._thresholds.stability_period_ns,
        )

    def restore_state(
        self,
        is_active: bool,
        quarantine_pct: float,
        trigger: str,
        trigger_value: float,
        activated_at_ns: Optional[int],
    ) -> None:
        """
        Restore quarantine state from persistence.

        Args:
            is_active: Whether quarantine is active
            quarantine_pct: Current quarantine percentage
            trigger: Trigger name string
            trigger_value: Trigger value
            activated_at_ns: Activation timestamp
        """
        self._is_active = is_active
        self._quarantine_pct = quarantine_pct
        self._trigger = QuarantineTrigger(trigger) if trigger else QuarantineTrigger.NONE
        self._trigger_value = trigger_value
        self._activated_at_ns = activated_at_ns
        self._normalized_at_ns = None

    @property
    def is_active(self) -> bool:
        """Check if quarantine is currently active."""
        return self._is_active

    @property
    def available_capital_fraction(self) -> float:
        """Get fraction of capital available for trading."""
        return 1.0 - self._quarantine_pct
