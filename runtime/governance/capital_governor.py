"""
Pillar 4: Sovereign Capital Governor.

Controls capital allocation, scaling, and drawdown response.
Prevents overconfidence, risk creep, and scaling into liquidity collapse.

Doctrine: SURVIVAL > CAPITAL PRESERVATION > EDGE PRESERVATION > GROWTH > TRADE COUNT

Scaling State Machine:
- GROW: May increase allocation (confidence > 0.75)
- HOLD: Maintain current (confidence 0.30 - 0.75)
- SHRINK: Reduce allocation (confidence < 0.30)
- FREEZE: Locked after ATH/streaks/spikes
- QUARANTINE: Risk spike - lock capital

Anti-Euphoria Engine:
- New ATH → FREEZE for 24 hours
- Win streak >= 5 → FREEZE for 12 hours
- Daily profit > 5% → FREEZE for 12 hours

Hard Limits:
- Max growth per week: +10%
- Max shrink per day: -40%
- Absolute exposure cap: 100%
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
from enum import Enum

from .confidence_engine import ConfidenceEngine, ConfidenceSubScores
from .quarantine_controller import QuarantineController, QuarantineInputs, QuarantineState


class ScalingState(Enum):
    """Capital scaling state."""
    GROW = "GROW"           # May increase allocation
    HOLD = "HOLD"           # Maintain current
    SHRINK = "SHRINK"       # Reduce allocation
    FREEZE = "FREEZE"       # Locked after ATH/spikes
    QUARANTINE = "QUARANTINE"  # Risk spike - lock capital


class FreezeReason(Enum):
    """Reasons for FREEZE state."""
    NONE = "NONE"
    NEW_ATH = "NEW_ATH"                    # New all-time high
    WIN_STREAK = "WIN_STREAK"              # Consecutive wins
    DAILY_PROFIT_SPIKE = "DAILY_PROFIT_SPIKE"  # Large daily profit
    MANUAL = "MANUAL"                      # Manual freeze


@dataclass(frozen=True)
class CapitalGovernorDecision:
    """Output contract for capital governor."""
    ts_ns: int
    allowed_capital_fraction: float  # 0.0 to 1.0
    allowed_size_multiplier: float   # 0.0 to 1.0
    scaling_state: ScalingState
    confidence_score: float          # 0.0 to 1.0
    sub_scores: Optional[ConfidenceSubScores]
    reason: str

    # Freeze details (if applicable)
    freeze_until_ns: Optional[int] = None
    freeze_reason: FreezeReason = FreezeReason.NONE

    # Quarantine details (if applicable)
    quarantine_state: Optional[QuarantineState] = None


@dataclass(frozen=True)
class EuphoriaEvent:
    """Detected euphoria condition."""
    ts_ns: int
    event_type: FreezeReason
    value: float  # ATH value, streak count, or profit %
    freeze_duration_ns: int


@dataclass
class CapitalGovernorThresholds:
    """Configurable thresholds for capital governor."""
    # Confidence thresholds for state transitions
    grow_confidence_threshold: float = 0.75    # Above this = GROW
    hold_confidence_threshold: float = 0.30    # Above this = HOLD, below = SHRINK

    # Hard limits
    max_growth_per_week_pct: float = 0.10     # +10% max per week
    max_shrink_per_day_pct: float = 0.40      # -40% max per day
    absolute_exposure_cap: float = 1.0         # Never exceed 100%

    # Anti-euphoria: freeze durations (nanoseconds)
    ath_freeze_duration_ns: int = 24 * 60 * 60 * 1_000_000_000       # 24 hours
    win_streak_freeze_duration_ns: int = 12 * 60 * 60 * 1_000_000_000  # 12 hours
    profit_spike_freeze_duration_ns: int = 12 * 60 * 60 * 1_000_000_000  # 12 hours

    # Anti-euphoria: thresholds
    win_streak_threshold: int = 5             # 5 consecutive wins
    daily_profit_spike_pct: float = 5.0       # 5% daily profit

    # Size multipliers by state
    grow_size_multiplier: float = 1.0
    hold_size_multiplier: float = 1.0
    shrink_size_multiplier: float = 0.5
    freeze_size_multiplier: float = 0.75
    quarantine_size_multiplier: float = 0.25


@dataclass
class CapitalGovernorInputs:
    """Inputs for capital governor evaluation."""
    # Current equity metrics
    current_equity: float = 0.0
    peak_equity: float = 0.0             # Historical ATH
    daily_pnl_pct: float = 0.0           # Today's P&L %

    # Win/loss streak
    consecutive_wins: int = 0

    # Drawdown metrics
    current_drawdown_pct: float = 0.0
    drawdown_velocity_pct_per_hour: float = 0.0

    # Market conditions
    volatility_ratio: float = 1.0        # Current vs baseline

    # Current allocation
    current_capital_fraction: float = 1.0


class AntiEuphoriaEngine:
    """
    Detects euphoria conditions and recommends FREEZE.

    Euphoria indicators:
    - New all-time high reached
    - Win streak exceeds threshold
    - Daily profit exceeds threshold
    """

    def __init__(self, thresholds: Optional[CapitalGovernorThresholds] = None):
        self._thresholds = thresholds or CapitalGovernorThresholds()

        # State tracking
        self._last_peak_equity: float = 0.0
        self._freeze_until_ns: Optional[int] = None
        self._freeze_reason: FreezeReason = FreezeReason.NONE

    def check_euphoria(
        self,
        inputs: CapitalGovernorInputs,
        now_ns: Optional[int] = None,
    ) -> Optional[EuphoriaEvent]:
        """
        Check for euphoria conditions.

        Returns:
            EuphoriaEvent if condition detected, None otherwise
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        t = self._thresholds

        # Check new ATH
        if inputs.current_equity > self._last_peak_equity and self._last_peak_equity > 0:
            self._last_peak_equity = inputs.current_equity
            return EuphoriaEvent(
                ts_ns=now_ns,
                event_type=FreezeReason.NEW_ATH,
                value=inputs.current_equity,
                freeze_duration_ns=t.ath_freeze_duration_ns,
            )

        # Update peak tracking
        if inputs.peak_equity > self._last_peak_equity:
            self._last_peak_equity = inputs.peak_equity

        # Check win streak
        if inputs.consecutive_wins >= t.win_streak_threshold:
            return EuphoriaEvent(
                ts_ns=now_ns,
                event_type=FreezeReason.WIN_STREAK,
                value=float(inputs.consecutive_wins),
                freeze_duration_ns=t.win_streak_freeze_duration_ns,
            )

        # Check daily profit spike
        if inputs.daily_pnl_pct >= t.daily_profit_spike_pct:
            return EuphoriaEvent(
                ts_ns=now_ns,
                event_type=FreezeReason.DAILY_PROFIT_SPIKE,
                value=inputs.daily_pnl_pct,
                freeze_duration_ns=t.profit_spike_freeze_duration_ns,
            )

        return None

    def set_freeze(
        self,
        reason: FreezeReason,
        duration_ns: int,
        now_ns: Optional[int] = None,
    ) -> None:
        """Set freeze state."""
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        self._freeze_until_ns = now_ns + duration_ns
        self._freeze_reason = reason

    def is_frozen(self, now_ns: Optional[int] = None) -> Tuple[bool, Optional[int], FreezeReason]:
        """
        Check if currently frozen.

        Returns:
            Tuple of (is_frozen, freeze_until_ns, freeze_reason)
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        if self._freeze_until_ns is None:
            return False, None, FreezeReason.NONE

        if now_ns >= self._freeze_until_ns:
            # Freeze expired
            self._freeze_until_ns = None
            self._freeze_reason = FreezeReason.NONE
            return False, None, FreezeReason.NONE

        return True, self._freeze_until_ns, self._freeze_reason

    def restore_state(
        self,
        last_peak_equity: float,
        freeze_until_ns: Optional[int],
        freeze_reason: str,
    ) -> None:
        """Restore state from persistence."""
        self._last_peak_equity = last_peak_equity
        self._freeze_until_ns = freeze_until_ns
        self._freeze_reason = FreezeReason(freeze_reason) if freeze_reason else FreezeReason.NONE


class SovereignCapitalGovernor:
    """
    Supreme authority over capital allocation.

    Override hierarchy (from supreme):
    1. Meta-Governor (can override this)
    2. Capital Governor (this) - controls scaling
    3. Alpha Decay Governor - controls strategy participation
    4. Latency Gate - controls execution viability
    5. Execution Engine - submits orders

    State machine:
    - GROW: Confidence > 0.75, may increase allocation
    - HOLD: Confidence 0.30-0.75, maintain current
    - SHRINK: Confidence < 0.30, reduce allocation
    - FREEZE: After euphoria events, temporary lock
    - QUARANTINE: Risk spike, lock portion of capital
    """

    def __init__(
        self,
        confidence_engine: ConfidenceEngine,
        quarantine_controller: QuarantineController,
        thresholds: Optional[CapitalGovernorThresholds] = None,
    ):
        self._confidence = confidence_engine
        self._quarantine = quarantine_controller
        self._thresholds = thresholds or CapitalGovernorThresholds()
        self._anti_euphoria = AntiEuphoriaEngine(self._thresholds)

        # Current state
        self._scaling_state: ScalingState = ScalingState.HOLD
        self._allowed_capital_fraction: float = 1.0
        self._consecutive_wins: int = 0

    def evaluate(
        self,
        inputs: CapitalGovernorInputs,
        sub_scores: Optional[ConfidenceSubScores] = None,
        now_ns: Optional[int] = None,
    ) -> CapitalGovernorDecision:
        """
        Evaluate current conditions and return capital decision.

        Args:
            inputs: Current capital and market conditions
            sub_scores: Pre-computed confidence sub-scores (optional)
            now_ns: Current timestamp

        Returns:
            Capital governor decision
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)
        t = self._thresholds

        # Track consecutive wins
        self._consecutive_wins = inputs.consecutive_wins

        # Step 1: Check quarantine conditions
        quarantine_inputs = QuarantineInputs(
            drawdown_velocity_pct_per_hour=inputs.drawdown_velocity_pct_per_hour,
            volatility_ratio=inputs.volatility_ratio,
            current_drawdown_pct=inputs.current_drawdown_pct,
        )
        quarantine_state = self._quarantine.evaluate(quarantine_inputs, now_ns)

        if quarantine_state.is_active:
            return self._build_quarantine_decision(
                quarantine_state,
                sub_scores,
                now_ns,
            )

        # Step 2: Check freeze conditions
        is_frozen, freeze_until_ns, freeze_reason = self._anti_euphoria.is_frozen(now_ns)

        if not is_frozen:
            # Check for new euphoria events
            euphoria_event = self._anti_euphoria.check_euphoria(inputs, now_ns)
            if euphoria_event:
                self._anti_euphoria.set_freeze(
                    euphoria_event.event_type,
                    euphoria_event.freeze_duration_ns,
                    now_ns,
                )
                is_frozen = True
                freeze_until_ns = now_ns + euphoria_event.freeze_duration_ns
                freeze_reason = euphoria_event.event_type

        if is_frozen:
            return self._build_freeze_decision(
                freeze_until_ns,
                freeze_reason,
                sub_scores,
                now_ns,
            )

        # Step 3: Compute confidence score
        if sub_scores:
            confidence_score = sub_scores.composite_score
        else:
            # Use neutral scores if not provided
            confidence_score = 0.5
            sub_scores = None

        # Step 4: Determine scaling state
        if confidence_score >= t.grow_confidence_threshold:
            new_state = ScalingState.GROW
        elif confidence_score >= t.hold_confidence_threshold:
            new_state = ScalingState.HOLD
        else:
            new_state = ScalingState.SHRINK

        # Step 5: Compute allowed capital fraction
        allowed_fraction = self._compute_allowed_fraction(
            new_state,
            confidence_score,
            inputs.current_capital_fraction,
        )

        # Step 6: Get size multiplier
        size_multiplier = self._get_size_multiplier(new_state)

        self._scaling_state = new_state

        return CapitalGovernorDecision(
            ts_ns=now_ns,
            allowed_capital_fraction=allowed_fraction,
            allowed_size_multiplier=size_multiplier,
            scaling_state=new_state,
            confidence_score=confidence_score,
            sub_scores=sub_scores,
            reason=f"scaling_state={new_state.value}_confidence={confidence_score:.2f}",
        )

    def _build_quarantine_decision(
        self,
        quarantine_state: QuarantineState,
        sub_scores: Optional[ConfidenceSubScores],
        now_ns: int,
    ) -> CapitalGovernorDecision:
        """Build decision for quarantine state."""
        t = self._thresholds

        return CapitalGovernorDecision(
            ts_ns=now_ns,
            allowed_capital_fraction=quarantine_state.available_capital_pct,
            allowed_size_multiplier=t.quarantine_size_multiplier,
            scaling_state=ScalingState.QUARANTINE,
            confidence_score=0.0,  # Confidence irrelevant during quarantine
            sub_scores=sub_scores,
            reason=f"quarantine_trigger={quarantine_state.trigger.value}",
            quarantine_state=quarantine_state,
        )

    def _build_freeze_decision(
        self,
        freeze_until_ns: int,
        freeze_reason: FreezeReason,
        sub_scores: Optional[ConfidenceSubScores],
        now_ns: int,
    ) -> CapitalGovernorDecision:
        """Build decision for freeze state."""
        t = self._thresholds

        return CapitalGovernorDecision(
            ts_ns=now_ns,
            allowed_capital_fraction=self._allowed_capital_fraction,  # Maintain current
            allowed_size_multiplier=t.freeze_size_multiplier,
            scaling_state=ScalingState.FREEZE,
            confidence_score=0.0,  # Confidence irrelevant during freeze
            sub_scores=sub_scores,
            reason=f"freeze_reason={freeze_reason.value}",
            freeze_until_ns=freeze_until_ns,
            freeze_reason=freeze_reason,
        )

    def _compute_allowed_fraction(
        self,
        state: ScalingState,
        confidence: float,
        current_fraction: float,
    ) -> float:
        """Compute allowed capital fraction based on state and confidence."""
        t = self._thresholds

        if state == ScalingState.GROW:
            # May increase, but respect weekly limit
            target = min(t.absolute_exposure_cap, current_fraction * 1.05)  # +5% per evaluation
            new_fraction = min(target, current_fraction + t.max_growth_per_week_pct)

        elif state == ScalingState.HOLD:
            # Maintain current
            new_fraction = current_fraction

        elif state == ScalingState.SHRINK:
            # Reduce based on how far below threshold
            shrink_factor = confidence / t.hold_confidence_threshold  # 0 to 1
            target_shrink = (1 - shrink_factor) * t.max_shrink_per_day_pct
            new_fraction = max(0.1, current_fraction * (1 - target_shrink))  # Never below 10%

        else:
            new_fraction = current_fraction

        self._allowed_capital_fraction = new_fraction
        return new_fraction

    def _get_size_multiplier(self, state: ScalingState) -> float:
        """Get size multiplier for state."""
        t = self._thresholds

        multipliers = {
            ScalingState.GROW: t.grow_size_multiplier,
            ScalingState.HOLD: t.hold_size_multiplier,
            ScalingState.SHRINK: t.shrink_size_multiplier,
            ScalingState.FREEZE: t.freeze_size_multiplier,
            ScalingState.QUARANTINE: t.quarantine_size_multiplier,
        }

        return multipliers.get(state, 1.0)

    def force_freeze(
        self,
        duration_ns: int,
        now_ns: Optional[int] = None,
    ) -> CapitalGovernorDecision:
        """
        Manually trigger freeze.

        Args:
            duration_ns: Freeze duration in nanoseconds
            now_ns: Current timestamp

        Returns:
            Updated decision
        """
        now_ns = now_ns or int(time.time() * 1_000_000_000)

        self._anti_euphoria.set_freeze(FreezeReason.MANUAL, duration_ns, now_ns)

        return self._build_freeze_decision(
            now_ns + duration_ns,
            FreezeReason.MANUAL,
            None,
            now_ns,
        )

    def restore_state(
        self,
        scaling_state: str,
        allowed_capital_fraction: float,
        freeze_until_ns: Optional[int],
        freeze_reason: str,
        quarantine_active: bool,
        quarantine_pct: float,
        last_ath: float,
        consecutive_wins: int,
    ) -> None:
        """
        Restore governor state from persistence.

        Args:
            scaling_state: Scaling state string
            allowed_capital_fraction: Current allowed fraction
            freeze_until_ns: Freeze end timestamp
            freeze_reason: Freeze reason string
            quarantine_active: Whether quarantine is active
            quarantine_pct: Quarantine percentage
            last_ath: Last ATH value
            consecutive_wins: Current win streak
        """
        self._scaling_state = ScalingState(scaling_state)
        self._allowed_capital_fraction = allowed_capital_fraction
        self._consecutive_wins = consecutive_wins

        # Restore anti-euphoria state
        self._anti_euphoria.restore_state(
            last_peak_equity=last_ath,
            freeze_until_ns=freeze_until_ns,
            freeze_reason=freeze_reason,
        )

        # Restore quarantine state
        if quarantine_active:
            self._quarantine.restore_state(
                is_active=True,
                quarantine_pct=quarantine_pct,
                trigger="MANUAL",
                trigger_value=0.0,
                activated_at_ns=None,
            )

    @property
    def scaling_state(self) -> ScalingState:
        """Get current scaling state."""
        return self._scaling_state

    @property
    def allowed_capital_fraction(self) -> float:
        """Get current allowed capital fraction."""
        return self._allowed_capital_fraction

    def allows_scaling_up(self) -> bool:
        """Check if scaling up is currently allowed."""
        return self._scaling_state == ScalingState.GROW
