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

def generate_absence_proposal(
    *,
    permission: PermissionOutput,
    absence,  # StructuralAbsenceDuration | None (B1.1)
    persistence,  # StructuralPersistenceDuration | None (B2.1)
    geometry,  # ZonePenetrationDepth | None (A6, optional)
    context: StrategyContext
) -> Optional[StrategyProposal]:
    """
    Generate at most one structural absence proposal.
    
    Proposes only if ALL required conditions are true:
    1. Absence exists (absence_duration > 0)
    2. Persistence exists (total_persistence_duration > 0)
    3. Absence is not total (absence_ratio < 1.0)
    
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
    
    Returns:
        StrategyProposal if all conditions met, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None
    
    # Rule 2: Required primitives missing -> no proposal
    if absence is None:
        return None
    if persistence is None:
        return None
    
    # Rule 3: Check structural existence conditions
    # Required Condition 1: Absence exists
    if not (absence.absence_duration > 0):
        return None
    
    # Required Condition 2: Persistence exists
    if not (persistence.total_persistence_duration > 0):
        return None
    
    # Required Condition 3: Absence is not total
    if not (absence.absence_ratio < 1.0):
        return None
    
    # All required conditions met
    # Check optional geometry enrichment
    justification_ref = "B1.1|B2.1"
    
    if geometry is not None and geometry.penetration_depth > 0:
        # Optional geometry present - enrich justification
        justification_ref = "B1.1|B2.1|A6"
    
    # Emit proposal
    return StrategyProposal(
        strategy_id="EP2-ABSENCE-V1",
        action_type="STRUCTURAL_ABSENCE_EVENT",
        confidence="STRUCTURAL_PRESENT",
        justification_ref=justification_ref,
        timestamp=context.timestamp
    )
