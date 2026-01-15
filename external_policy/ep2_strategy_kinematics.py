"""
EP-2 Strategy #2: Kinematics-Driven Structural Proposal

Pure proposal generator consuming Tier A kinematic primitives.

Authority:
- M4 Structural Primitive Canon v1.0 (Tier A)
- M5 Tier A Whitelist + Access Integration
- M6 Scaffolding v1.0
- EP-3 Arbitration & Risk Gate v1.0

Purpose:
Answers: "Is there a structurally non-trivial kinematic traversal occurring?"
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
# EP-2 Strategy #2: Kinematics-Driven Structural Proposal
# ==============================================================================

def _entry_conditions_met(
    velocity,
    compactness,
    acceptance
) -> bool:
    """
    Check if entry conditions are met (structural existence).

    Returns:
        True if all three kinematic primitives show structural presence
    """
    # Any input missing -> conditions not met
    if velocity is None:
        return False
    if compactness is None:
        return False
    if acceptance is None:
        return False

    # Check structural existence conditions
    # Condition 1: Velocity is non-zero
    if not (velocity.velocity != 0):
        return False

    # Condition 2: Compactness is non-degenerate
    if not (compactness.compactness_ratio > 0):
        return False

    # Condition 3: Acceptance is non-zero
    if not (acceptance.acceptance_ratio > 0):
        return False

    return True


def generate_kinematics_proposal(
    *,
    velocity,  # PriceTraversalVelocity | None
    compactness,  # TraversalCompactness | None
    acceptance,  # PriceAcceptanceRatio | None
    permission: PermissionOutput,
    context: StrategyContext,
    position_state: Optional[PositionState] = None
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural kinematics proposal.

    Proposes ENTRY if ALL three conditions are true:
    1. Velocity is non-zero (velocity != 0)
    2. Compactness is non-degenerate (compactness_ratio > 0)
    3. Acceptance is non-zero (acceptance_ratio > 0)

    Proposes EXIT if position exists and conditions no longer met.

    These are structural existence checks only.
    No thresholds, no comparisons, no interpretation.

    Args:
        velocity: A3 primitive output or None
        compactness: A4 primitive output or None
        acceptance: A5 primitive output or None
        permission: M6 permission result
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
        if velocity is None or compactness is None or acceptance is None:
            # Insufficient data to evaluate -> HOLD (don't exit)
            return None

        # Primitives exist - check if original entry conditions are still met
        if not _entry_conditions_met(velocity, compactness, acceptance):
            # Raw event invalidating original entry condition
            return StrategyProposal(
                strategy_id="EP2-KINEMATICS-V1",
                action_type="EXIT",
                confidence="INVALIDATED",
                justification_ref="A3|A4|A5_ABSENT",
                timestamp=context.timestamp
            )

        # Conditions still met -> HOLD (don't generate duplicate ENTRY)
        return None

    # Rule 3: Position FLAT -> check if should enter
    if position_state == PositionState.FLAT or position_state is None:
        # Check if entry conditions met
        if _entry_conditions_met(velocity, compactness, acceptance):
            # All conditions met -> emit ENTRY proposal
            return StrategyProposal(
                strategy_id="EP2-KINEMATICS-V1",
                action_type="ENTRY",
                confidence="STRUCTURAL_PRESENT",
                justification_ref="A3|A4|A5",
                timestamp=context.timestamp
            )

    # No action warranted
    return None
