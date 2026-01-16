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
# Threshold Configuration
# ==============================================================================

@dataclass(frozen=True)
class GeometryThresholds:
    """Calibrated thresholds for meaningful entry conditions.

    These filter noise from signal - constitutional thresholds on observable facts.
    NOT predictions, NOT confidence scores - just minimum values for structural presence.
    """
    # Zone penetration: minimum depth as fraction of price (e.g., 0.005 = 0.5%)
    min_penetration_depth: float = 0.005

    # Traversal compactness: minimum ratio (0-1 scale, e.g., 0.3 = 30% compactness)
    min_compactness_ratio: float = 0.3

    # Central tendency deviation: minimum absolute deviation as fraction of price
    min_deviation_value: float = 0.002


# Default thresholds - can be overridden per-instance
DEFAULT_GEOMETRY_THRESHOLDS = GeometryThresholds()


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
    central_tendency_deviation,
    thresholds: GeometryThresholds = DEFAULT_GEOMETRY_THRESHOLDS
) -> bool:
    """
    Check if entry conditions are met (meaningful structural presence).

    Uses calibrated thresholds to filter noise from signal.
    Thresholds are factual comparisons, NOT predictions or confidence scores.

    Returns:
        True if all three geometry primitives exceed meaningful thresholds
    """
    # Any input missing -> conditions not met
    if zone_penetration is None:
        return False
    if traversal_compactness is None:
        return False
    if central_tendency_deviation is None:
        return False

    # Check structural conditions against meaningful thresholds
    # Condition 1: Zone penetration exceeds minimum (filters micro-penetrations)
    if not (zone_penetration.penetration_depth >= thresholds.min_penetration_depth):
        return False

    # Condition 2: Traversal compactness exceeds minimum (filters degenerate traversals)
    if not (traversal_compactness.compactness_ratio >= thresholds.min_compactness_ratio):
        return False

    # Condition 3: Deviation exceeds minimum (filters noise)
    if not (abs(central_tendency_deviation.deviation_value) >= thresholds.min_deviation_value):
        return False

    return True


def generate_geometry_proposal(
    *,
    zone_penetration,  # ZonePenetrationDepth | None
    traversal_compactness,  # TraversalCompactness  | None
    central_tendency_deviation,  # CentralTendencyDeviation | None
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    thresholds: GeometryThresholds = DEFAULT_GEOMETRY_THRESHOLDS
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural geometry proposal.

    Proposes ENTRY if ALL three conditions exceed meaningful thresholds:
    1. Zone penetration >= min_penetration_depth (default 0.5%)
    2. Traversal compactness >= min_compactness_ratio (default 0.3)
    3. Deviation absolute value >= min_deviation_value (default 0.2%)

    Proposes EXIT if position exists and conditions no longer met.

    Thresholds are calibrated filters on observable facts - NOT predictions.
    They distinguish meaningful structural presence from noise.

    Args:
        zone_penetration: A6 primitive output or None
        traversal_compactness: A4 primitive output or None
        central_tendency_deviation: A8 primitive output or None
        context: Strategy execution context
        permission: M6 permission result
        position_state: Current position state (from executor)
        thresholds: Calibrated threshold values (default: GeometryThresholds())

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
        if not _entry_conditions_met(zone_penetration, traversal_compactness, central_tendency_deviation, thresholds):
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
        # Check if entry conditions met (using calibrated thresholds)
        if _entry_conditions_met(zone_penetration, traversal_compactness, central_tendency_deviation, thresholds):
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
