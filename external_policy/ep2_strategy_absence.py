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
    persistence
) -> bool:
    """
    Check if entry conditions are met (structural existence).

    Returns:
        True if absence and persistence primitives show structural presence
    """
    # Required primitives missing -> conditions not met
    if absence is None:
        return False
    if persistence is None:
        return False

    # Check structural existence conditions
    # Required Condition 1: Absence exists
    if not (absence.absence_duration > 0):
        return False

    # Required Condition 2: Persistence exists
    if not (persistence.total_persistence_duration > 0):
        return False

    # Required Condition 3: Absence is not total
    if not (absence.absence_ratio < 1.0):
        return False

    return True


def generate_absence_proposal(
    *,
    permission: PermissionOutput,
    absence,  # StructuralAbsenceDuration | None (B1.1)
    persistence,  # StructuralPersistenceDuration | None (B2.1)
    geometry,  # ZonePenetrationDepth | None (A6, optional)
    context: StrategyContext,
    position_state: Optional[PositionState] = None
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural absence proposal.

    Proposes ENTRY if ALL required conditions are true:
    1. Absence exists (absence_duration > 0)
    2. Persistence exists (total_persistence_duration > 0)
    3. Absence is not total (absence_ratio < 1.0)

    Proposes EXIT if position exists and conditions no longer met.

    Optional enrichment:
    - Geometry present (penetration_depth > 0)

    These are structural existence checks only.
    No thresholds, no comparisons, no interpretation.

    Args:
        permission: M6 permission result
        absence: B1.1 primitive output or None
        persistence: B2.1 primitive output or None
        geometry: A6 primitive output or None (optional)
        context: Strategy execution context
        position_state: Current position state (from executor)

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
        if not _entry_conditions_met(absence, persistence):
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
        # Check if entry conditions met
        if _entry_conditions_met(absence, persistence):
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
