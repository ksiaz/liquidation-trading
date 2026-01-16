"""
EP-2 Strategy #3: Absence-Driven Structural Proposal

Pure proposal generator consuming Tier B-1 absence and Tier B-2 Phase 1 persistence primitives.

Authority:
- Tier A Structural Primitives (Certified)
- Tier B-1 Structural Absence (Certified)
- Tier B-2 Phase 1 Persistence (Certified)
- M5 Whitelist (Tier A + B-1 + B-2.1)
- M6 Predicate Framework (Frozen)
- EP-3 Arbitration & Risk Gate (Certified)

Purpose:
Answers: "Is there a structurally meaningful absence relative to observed persistence?"
Does NOT answer: What it means, whether it's good/bad, whether to act.

CRITICAL: This module makes no decisions. It only proposes.
"""

from dataclasses import dataclass
from typing import Optional
from runtime.position.types import PositionState


# ==============================================================================
# Threshold Configuration
# ==============================================================================

@dataclass(frozen=True)
class AbsenceThresholds:
    """Calibrated thresholds for meaningful absence entry conditions.

    These filter noise from signal - constitutional thresholds on observable facts.
    NOT predictions, NOT confidence scores - just minimum values for structural presence.
    """
    # Absence duration: minimum seconds of structural absence to be meaningful
    min_absence_duration: float = 60.0  # 1 minute

    # Persistence duration: minimum seconds of structural persistence
    min_persistence_duration: float = 300.0  # 5 minutes

    # Absence ratio: maximum ratio (require at least some presence)
    max_absence_ratio: float = 0.8  # Require at least 20% presence


# Default thresholds - can be overridden per-instance
DEFAULT_ABSENCE_THRESHOLDS = AbsenceThresholds()


# ==============================================================================
# Input/Output Types
# ==============================================================================

@dataclass(frozen=True)
class StrategyContext:
    """Immutable context for strategy execution."""
    context_id: str
    timestamp: float


@dataclass(frozen=True)
class PermissionOutput:
    """M6 permission result (from M6 scaffolding)."""
    result: str  # "ALLOWED" | "DENIED"
    mandate_id: str
    action_id: str
    reason_code: str
    timestamp: float


@dataclass(frozen=True)
class StrategyProposal:
    """Immutable strategy proposal for EP-3 arbitration."""
    strategy_id: str
    action_type: str  # Opaque string
    confidence: str  # Opaque label (NOT numeric)
    justification_ref: str  # Reference ID only
    timestamp: float


# ==============================================================================
# EP-2 Strategy #3: Absence-Driven Structural Proposal
# ==============================================================================

def _entry_conditions_met(
    absence,
    persistence,
    thresholds: AbsenceThresholds = DEFAULT_ABSENCE_THRESHOLDS
) -> bool:
    """
    Check if entry conditions are met (meaningful structural presence).

    Uses calibrated thresholds to filter noise from signal.
    Thresholds are factual comparisons, NOT predictions or confidence scores.

    Returns:
        True if absence and persistence primitives exceed meaningful thresholds
    """
    # Required primitives missing -> conditions not met
    if absence is None:
        return False
    if persistence is None:
        return False

    # Check structural conditions against meaningful thresholds
    # Required Condition 1: Absence exceeds minimum duration (filters brief gaps)
    if not (absence.absence_duration >= thresholds.min_absence_duration):
        return False

    # Required Condition 2: Persistence exceeds minimum duration (filters noise)
    if not (persistence.total_persistence_duration >= thresholds.min_persistence_duration):
        return False

    # Required Condition 3: Absence ratio below maximum (require some presence)
    if not (absence.absence_ratio <= thresholds.max_absence_ratio):
        return False

    return True


def generate_absence_proposal(
    *,
    permission: PermissionOutput,
    absence,  # StructuralAbsenceDuration | None (B1.1)
    persistence,  # StructuralPersistenceDuration | None (B2.1)
    geometry,  # ZonePenetrationDepth | None (A6, optional)
    context: StrategyContext,
    position_state: Optional[PositionState] = None,
    thresholds: AbsenceThresholds = DEFAULT_ABSENCE_THRESHOLDS
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural absence proposal.

    Proposes ENTRY if ALL required conditions exceed meaningful thresholds:
    1. Absence duration >= min_absence_duration (default 60 sec)
    2. Persistence duration >= min_persistence_duration (default 300 sec)
    3. Absence ratio <= max_absence_ratio (default 0.8, require 20% presence)

    Proposes EXIT if position exists and conditions no longer met.

    Optional enrichment:
    - Geometry present (penetration_depth > 0)

    Thresholds are calibrated filters on observable facts - NOT predictions.
    They distinguish meaningful structural absence from noise.

    Args:
        permission: M6 permission result
        absence: B1.1 primitive output or None
        persistence: B2.1 primitive output or None
        geometry: A6 primitive output or None (optional)
        context: Strategy execution context
        position_state: Current position state (from executor)
        thresholds: Calibrated threshold values (default: AbsenceThresholds())

    Returns:
        StrategyProposal if conditions warrant action, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None

    # Rule 2: If position exists (ENTERING, OPEN, REDUCING), check if should exit
    if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
        # If primitives are None, we have insufficient data -> HOLD
        if absence is None or persistence is None:
            # Insufficient data to evaluate -> HOLD (don't exit)
            return None

        # Primitives exist - check if original entry conditions are still met
        if not _entry_conditions_met(absence, persistence, thresholds):
            # Raw event invalidating original entry condition
            return StrategyProposal(
                strategy_id="EP2-ABSENCE-V1",
                action_type="EXIT",
                confidence="INVALIDATED",
                justification_ref="B1.1|B2.1_ABSENT",
                timestamp=context.timestamp
            )

        # Conditions still met -> HOLD (don't generate duplicate ENTRY)
        return None

    # Rule 3: Position FLAT -> check if should enter
    if position_state == PositionState.FLAT or position_state is None:
        # Check if entry conditions met (using calibrated thresholds)
        if _entry_conditions_met(absence, persistence, thresholds):
            # All required conditions met
            # Check optional geometry enrichment
            justification_ref = "B1.1|B2.1"

            if geometry is not None and geometry.penetration_depth > 0:
                # Optional geometry present - enrich justification
                justification_ref = "B1.1|B2.1|A6"

            # Emit ENTRY proposal
            return StrategyProposal(
                strategy_id="EP2-ABSENCE-V1",
                action_type="ENTRY",
                confidence="STRUCTURAL_PRESENT",
                justification_ref=justification_ref,
                timestamp=context.timestamp
            )

    # No action warranted
    return None
