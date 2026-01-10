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

def generate_geometry_proposal(
    *,
    zone_penetration,  # ZonePenetrationDepth | None
    traversal_compactness,  # TraversalCompactness  | None
    central_tendency_deviation,  # CentralTendencyDeviation | None
    context: StrategyContext,
    permission: PermissionOutput
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural geometry proposal.
    
    Proposes only if ALL three conditions are true:
    1. Zone penetration exists (depth > 0)
    2. Traversal is non-degenerate (compactness_ratio > 0)
    3. Deviation is non-zero (deviation_value != 0)
    
    These are structural existence checks only.
    No thresholds, no comparisons, no interpretation.
    
    Args:
        zone_penetration: A6 primitive output or None
        traversal_compactness: A4 primitive output or None
        central_tendency_deviation: A8 primitive output or None
        context: Strategy execution context
        permission: M6 permission result
    
    Returns:
        StrategyProposal if all conditions met, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None
    
    # Rule 2: Any input missing -> no proposal
    if zone_penetration is None:
        return None
    if traversal_compactness is None:
        return None
    if central_tendency_deviation is None:
        return None
    
    # Rule 3: Check structural existence conditions
    # Condition 1: Zone penetration exists
    if not (zone_penetration.penetration_depth > 0):
        return None
    
    # Condition 2: Traversal is non-degenerate
    if not (traversal_compactness.compactness_ratio > 0):
        return None
    
    # Condition 3: Deviation is non-zero
    if not (central_tendency_deviation.deviation_value != 0):
        return None
    
    # All conditions met -> emit proposal
    return StrategyProposal(
        strategy_id="EP2-GEOMETRY-V1",
        action_type="STRUCTURAL_GEOMETRY_EVENT",
        confidence="STRUCTURAL_PRESENT",
        justification_ref="A6|A4|A8",
        timestamp=context.timestamp
    )
