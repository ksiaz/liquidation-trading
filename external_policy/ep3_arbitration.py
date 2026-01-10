"""
EP-3: External Arbitration & Risk Gate

Neutral arbitration choke point for external policy system.
Consumes M6 outputs and strategy proposals, emits authorization decisions.

CRITICAL: This is NOT a decision maker. It is a permission gate and collision absorber.
Default behavior: NO_ACTION on ambiguity.

Per: External Arbitration & Risk Gate Design v1.0
"""

from dataclasses import dataclass
from typing import List, Optional, Literal
from enum import Enum


# ==============================================================================
# DECISION CODES (Exhaustive)
# ==============================================================================

class DecisionCode(Enum):
    """Exhaustive set of arbitration decision codes."""
    NO_ACTION = "NO_ACTION"
    AUTHORIZED_ACTION = "AUTHORIZED_ACTION"
    REJECTED_ACTION = "REJECTED_ACTION"


class RejectionReason(Enum):
    """Exhaustive set of rejection/abstention reasons."""
    M6_PERMISSION_DENIED = "M6_PERMISSION_DENIED"
    ZERO_PROPOSALS = "ZERO_PROPOSALS"
    MULTIPLE_PROPOSALS = "MULTIPLE_PROPOSALS"
    INVALID_PROPOSAL_SCHEMA = "INVALID_PROPOSAL_SCHEMA"
    AUTHORIZED = "AUTHORIZED"


# ==============================================================================
# INPUT TYPES (From M6 and Strategy Modules)
# ==============================================================================

@dataclass(frozen=True)
class PermissionOutput:
    """M6 permission output (immutable)."""
    result: Literal["ALLOWED", "DENIED"]
    mandate_id: str
    action_id: str
    reason_code: str
    timestamp: float


@dataclass(frozen=True)
class StrategyProposal:
    """Strategy module proposal (immutable)."""
    strategy_id: str
    action_type: str  # Opaque
    confidence: str  # Opaque, NOT numeric
    justification_ref: str  # ID only
    timestamp: float


# ==============================================================================
# OUTPUT TYPE
# ==============================================================================

@dataclass(frozen=True)
class PolicyDecision:
    """EP-3 arbitration decision (immutable)."""
    decision_code: DecisionCode
    selected_proposal: Optional[StrategyProposal]
    reason: RejectionReason
    timestamp: float
    trace_id: str


# ==============================================================================
# PROPOSAL VALIDATOR
# ==============================================================================

class ProposalValidator:
    """Validates strategy proposal structural integrity."""
    
    @staticmethod
    def is_valid(proposal: StrategyProposal, timestamp: float) -> bool:
        """
        Validate proposal structural integrity.
        
        Rules:
        - All fields must be present
        - Timestamp must match context timestamp
        - No semantic validation (action_type is opaque)
        """
        # Check required fields non-empty
        if not proposal.strategy_id:
            return False
        if not proposal.action_type:
            return False
        if not proposal.confidence:
            return False
        if not proposal.justification_ref:
            return False
        
        # Check timestamp match
        if proposal.timestamp != timestamp:
            return False
        
        return True


# ==============================================================================
# ARBITRATION ENGINE
# ==============================================================================

class ArbitrationEngine:
    """
    Deterministic arbitration choke point.
    
    Enforces M6 supremacy and conservative conflict resolution.
    Default behavior: NO_ACTION on ambiguity.
    """
    
    @staticmethod
    def arbitrate(
        m6_permission: PermissionOutput,
        proposals: List[StrategyProposal],
        timestamp: float,
        trace_id: str
    ) -> PolicyDecision:
        """
        Execute arbitration pipeline in exact order.
        
        Pipeline:
        1. M6 Permission Gate (hard veto)
        2. Zero Proposal Rule
        3. Multiplicity Rule
        4. Structural Validity Rule
        5. Authorization Rule
        """
        # STEP 1: M6 Permission Gate (ABSOLUTE VETO)
        if m6_permission.result == "DENIED":
            return PolicyDecision(
                decision_code=DecisionCode.REJECTED_ACTION,
                selected_proposal=None,
                reason=RejectionReason.M6_PERMISSION_DENIED,
                timestamp=timestamp,
                trace_id=trace_id
            )
        
        # STEP 2: Zero Proposal Rule
        if len(proposals) == 0:
            return PolicyDecision(
                decision_code=DecisionCode.NO_ACTION,
                selected_proposal=None,
                reason=RejectionReason.ZERO_PROPOSALS,
                timestamp=timestamp,
                trace_id=trace_id
            )
        
        # STEP 3: Multiplicity Rule
        if len(proposals) > 1:
            return PolicyDecision(
                decision_code=DecisionCode.NO_ACTION,
                selected_proposal=None,
                reason=RejectionReason.MULTIPLE_PROPOSALS,
                timestamp=timestamp,
                trace_id=trace_id
            )
        
        # Single proposal - validate structure
        proposal = proposals[0]
        
        # STEP 4: Structural Validity Rule
        if not ProposalValidator.is_valid(proposal, timestamp):
            return PolicyDecision(
                decision_code=DecisionCode.NO_ACTION,
                selected_proposal=None,
                reason=RejectionReason.INVALID_PROPOSAL_SCHEMA,
                timestamp=timestamp,
                trace_id=trace_id
            )
        
        # STEP 5: Authorization Rule
        # Single valid proposal + M6 ALLOWED → AUTHORIZED
        return PolicyDecision(
            decision_code=DecisionCode.AUTHORIZED_ACTION,
            selected_proposal=proposal,
            reason=RejectionReason.AUTHORIZED,
            timestamp=timestamp,
            trace_id=trace_id
        )


# ==============================================================================
# DECISION EMITTER
# ==============================================================================

class DecisionEmitter:
    """
    Emits arbitration decisions in standard format.
    
    Provides logging and serialization support.
    """
    
    @staticmethod
    def emit(decision: PolicyDecision) -> dict:
        """
        Emit decision as structured output.
        
        Output suitable for logging or downstream consumption.
        """
        return {
            "decision_code": decision.decision_code.value,
            "selected_proposal": {
                "strategy_id": decision.selected_proposal.strategy_id,
                "action_type": decision.selected_proposal.action_type,
                "confidence": decision.selected_proposal.confidence,
                "justification_ref": decision.selected_proposal.justification_ref,
                "timestamp": decision.selected_proposal.timestamp
            } if decision.selected_proposal else None,
            "reason": decision.reason.value,
            "timestamp": decision.timestamp,
            "trace_id": decision.trace_id
        }
    
    @staticmethod
    def log_decision(decision: PolicyDecision) -> str:
        """
        Generate human-readable log entry.
        
        For audit and debugging purposes.
        """
        if decision.decision_code == DecisionCode.AUTHORIZED_ACTION:
            return (
                f"[{decision.trace_id}] AUTHORIZED: "
                f"strategy={decision.selected_proposal.strategy_id}, "
                f"action={decision.selected_proposal.action_type}, "
                f"ts={decision.timestamp}"
            )
        elif decision.decision_code == DecisionCode.REJECTED_ACTION:
            return (
                f"[{decision.trace_id}] REJECTED: "
                f"reason={decision.reason.value}, "
                f"ts={decision.timestamp}"
            )
        else:  # NO_ACTION
            return (
                f"[{decision.trace_id}] NO_ACTION: "
                f"reason={decision.reason.value}, "
                f"ts={decision.timestamp}"
            )
