"""
EP-2 Strategy #1: Geometry-Driven Structural Proposal

Pure proposal generator consuming Tier A structural primitives.

Authority:
- M4 Structural Primitive Canon v1.0 (Tier A)
- M5 Tier A Whitelist + Access Integration
- M6 Scaffolding v1.0
- EP-3 Arbitration & Risk Gate v1.0

Purpose:
Answers: "Is there a structurally non-trivial geometric interaction occurring?"
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
# EP-2 Strategy #1: Geometry-Driven Structural Proposal
# ==============================================================================

def _entry_conditions_met(
    zone_penetration,
    traversal_compactness,
    central_tendency_deviation
) -> bool:
    """
    Check if entry conditions are met (structural existence).

    Returns:
        True if all three geometry primitives show structural presence
    """
    # Any input missing -> conditions not met
    if zone_penetration is None:
        return False
    if traversal_compactness is None:
        return False
    if central_tendency_deviation is None:
        return False

    # Check structural existence conditions
    # Condition 1: Zone penetration exists
    if not (zone_penetration.penetration_depth > 0):
        return False

    # Condition 2: Traversal is non-degenerate
    if not (traversal_compactness.compactness_ratio > 0):
        return False

    # Condition 3: Deviation is non-zero
    if not (central_tendency_deviation.deviation_value != 0):
        return False

    return True


def generate_geometry_proposal(
    *,
    zone_penetration,  # ZonePenetrationDepth | None
    traversal_compactness,  # TraversalCompactness  | None
    central_tendency_deviation,  # CentralTendencyDeviation | None
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural geometry proposal.

    Proposes ENTRY if ALL three conditions are true:
    1. Zone penetration exists (depth > 0)
    2. Traversal is non-degenerate (compactness_ratio > 0)
    3. Deviation is non-zero (deviation_value != 0)

    Proposes EXIT if position exists and conditions no longer met.

    These are structural existence checks only.
    No thresholds, no comparisons, no interpretation.

    Args:
        zone_penetration: A6 primitive output or None
        traversal_compactness: A4 primitive output or None
        central_tendency_deviation: A8 primitive output or None
        context: Strategy execution context
        permission: M6 permission result
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
        if zone_penetration is None or traversal_compactness is None or central_tendency_deviation is None:
            # Insufficient data to evaluate -> HOLD (don't exit)
            return None

        # Primitives exist - check if original entry conditions are still met
        if not _entry_conditions_met(zone_penetration, traversal_compactness, central_tendency_deviation):
            # Raw event invalidating original entry condition (MANDATE EMISSION RULES.md Line 164)
            return StrategyProposal(
                strategy_id="EP2-GEOMETRY-V1",
                action_type="EXIT",
                confidence="INVALIDATED",
                justification_ref="A6|A4|A8_ABSENT",
                timestamp=context.timestamp
            )

        # Conditions still met -> HOLD (don't generate duplicate ENTRY)
        return None

    # Rule 3: Position FLAT -> check if should enter
    if position_state == PositionState.FLAT or position_state is None:
        # Check if entry conditions met
        if _entry_conditions_met(zone_penetration, traversal_compactness, central_tendency_deviation):
            # All conditions met -> emit ENTRY proposal
            return StrategyProposal(
                strategy_id="EP2-GEOMETRY-V1",
                action_type="ENTRY",
                confidence="STRUCTURAL_PRESENT",
                justification_ref="A6|A4|A8",
                timestamp=context.timestamp
            )

    # No action warranted
    return None
