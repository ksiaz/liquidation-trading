"""
M4 Primitive: Cascade State Observation

Tier 2 computation tracking cascade lifecycle from confirmed facts.
Records what we SEE happening, not what we predict.

Constitutional compliance:
- Observable states only (NONE, PROXIMITY, LIQUIDATING, CASCADING, EXHAUSTED)
- No predictive language
- State transitions based on confirmed events
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple


class CascadePhase(Enum):
    """
    Observable cascade lifecycle states (facts, not predictions).

    State machine based on confirmed observations:
    NONE → PROXIMITY → LIQUIDATING → CASCADING → EXHAUSTED → NONE
    """
    NONE = auto()           # No positions near liquidation
    PROXIMITY = auto()      # Positions approaching liquidation (observed)
    LIQUIDATING = auto()    # Liquidation(s) occurring now (observed)
    CASCADING = auto()      # Sequential liquidations happening (observed)
    EXHAUSTED = auto()      # No more nearby positions (observed)


@dataclass(frozen=True)
class CascadeStateObservation:
    """
    Factual observation of cascade lifecycle.

    Records what we SEE happening, not what we predict.

    KEY DISTINCTION:
    - Confirmed liquidations (has_confirmed_liquidation=True) are FACTS
    - Proximity observations (positions near liquidation) are STRUCTURAL CONDITIONS
    - Confirmed facts carry more weight than proximity alone
    """
    symbol: str
    phase: CascadePhase

    # CONFIRMED FACTS: Actual liquidation events
    has_confirmed_liquidation: bool    # At least one liquidation confirmed in window
    liquidations_5s: int               # Count in last 5 seconds (CONFIRMED)
    liquidations_30s: int              # Count in last 30 seconds (CONFIRMED)
    liquidations_60s: int              # Count in last 60 seconds (CONFIRMED)
    confirmed_liquidation_value: float # USD value of confirmed liquidations

    # STRUCTURAL CONDITIONS: Proximity observations
    positions_remaining_at_risk: int   # Still within proximity threshold

    # Cascade metrics (populated when confirmed liquidations occur)
    cascade_value_liquidated: float    # Total USD liquidated in this cascade (CONFIRMED)
    cascade_duration_sec: float        # Seconds since first confirmed liquidation
    cascade_start_ts: Optional[float]  # When first liquidation confirmed (if any)

    # Confidence indicator (higher when confirmed liquidations exist)
    # This is NOT a prediction - it's a factual measure of observation quality
    observation_confidence: str        # "CONFIRMED" (has liquidations) or "PROXIMITY_ONLY"

    timestamp: float


def compute_cascade_state(
    symbol: str,
    positions_at_risk: int,
    liquidation_timestamps: List[float],
    liquidation_values: List[float],
    current_time: float
) -> CascadeStateObservation:
    """
    Compute cascade state from confirmed facts.

    KEY DISTINCTION:
    - CONFIRMED LIQUIDATION: Actual event happened (strongest signal)
    - PROXIMITY: Positions near liquidation (structural condition only)

    State transitions based on observable evidence:
    - NONE: No positions within threshold, no liquidations
    - PROXIMITY: Positions approaching (positions_at_risk > 0, no recent liquidations)
    - LIQUIDATING: Liquidation(s) CONFIRMED in last 5 sec (FACT!)
    - CASCADING: Multiple CONFIRMED liquidations in sequence (3+ in 30 sec)
    - EXHAUSTED: Cascade ended (no liquidations for 60 sec, positions cleared)

    Args:
        symbol: Trading symbol
        positions_at_risk: Count of positions within proximity threshold
        liquidation_timestamps: List of CONFIRMED liquidation timestamps
        liquidation_values: List of liquidation values (USD) matching timestamps
        current_time: Current observation time

    Returns:
        CascadeStateObservation with computed phase
    """
    # Count CONFIRMED liquidations in time windows
    liquidations_5s = sum(
        1 for ts in liquidation_timestamps
        if current_time - ts <= 5.0
    )
    liquidations_30s = sum(
        1 for ts in liquidation_timestamps
        if current_time - ts <= 30.0
    )
    liquidations_60s = sum(
        1 for ts in liquidation_timestamps
        if current_time - ts <= 60.0
    )

    # Track confirmed liquidation value in recent window
    confirmed_liq_value = sum(
        val for ts, val in zip(liquidation_timestamps, liquidation_values)
        if current_time - ts <= 60.0
    )

    # Has at least one confirmed liquidation?
    has_confirmed = liquidations_60s > 0

    # Compute cascade metrics from CONFIRMED events only
    cascade_value = 0.0
    cascade_start = None
    cascade_duration = 0.0

    if liquidation_timestamps:
        # Find cascade start (first CONFIRMED liquidation in active window)
        active_liqs = [
            (ts, val) for ts, val in zip(liquidation_timestamps, liquidation_values)
            if current_time - ts <= 60.0
        ]
        if active_liqs:
            cascade_start = min(ts for ts, _ in active_liqs)
            cascade_duration = current_time - cascade_start
            cascade_value = sum(val for _, val in active_liqs)

    # Determine phase based on observable facts
    # PRIORITY: Confirmed liquidations > Proximity observations
    if liquidations_30s >= 3:
        # Multiple CONFIRMED liquidations in sequence - cascade happening (FACT)
        phase = CascadePhase.CASCADING

    elif liquidations_5s >= 1:
        # Recent CONFIRMED liquidation(s) detected (FACT)
        phase = CascadePhase.LIQUIDATING

    elif liquidations_60s > 0 and positions_at_risk == 0:
        # Had CONFIRMED liquidations but no more positions at risk
        phase = CascadePhase.EXHAUSTED

    elif positions_at_risk > 0:
        # Positions approaching but NO CONFIRMED liquidations yet
        # This is PROXIMITY ONLY - weaker signal
        phase = CascadePhase.PROXIMITY

    elif positions_at_risk == 0 and liquidations_60s == 0:
        phase = CascadePhase.NONE

    else:
        phase = CascadePhase.NONE

    # Observation confidence: CONFIRMED facts vs. proximity speculation
    if has_confirmed:
        observation_confidence = "CONFIRMED"  # We SAW liquidations happen
    elif positions_at_risk > 0:
        observation_confidence = "PROXIMITY_ONLY"  # No liquidation yet, just structural
    else:
        observation_confidence = "NONE"

    return CascadeStateObservation(
        symbol=symbol,
        phase=phase,
        has_confirmed_liquidation=has_confirmed,
        liquidations_5s=liquidations_5s,
        liquidations_30s=liquidations_30s,
        liquidations_60s=liquidations_60s,
        confirmed_liquidation_value=confirmed_liq_value,
        positions_remaining_at_risk=positions_at_risk,
        cascade_value_liquidated=cascade_value,
        cascade_duration_sec=cascade_duration,
        cascade_start_ts=cascade_start,
        observation_confidence=observation_confidence,
        timestamp=current_time
    )


def phase_to_string(phase: CascadePhase) -> str:
    """Convert phase to human-readable string (for logging only)."""
    return {
        CascadePhase.NONE: "NONE",
        CascadePhase.PROXIMITY: "PROXIMITY",
        CascadePhase.LIQUIDATING: "LIQUIDATING",
        CascadePhase.CASCADING: "CASCADING",
        CascadePhase.EXHAUSTED: "EXHAUSTED"
    }.get(phase, "UNKNOWN")
