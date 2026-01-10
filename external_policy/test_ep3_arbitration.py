"""
EP-3 Arbitration & Risk Gate Tests

Comprehensive test suite verifying:
- M6 DENIED veto enforcement
- Zero/multiple proposal handling
- Structural validation
- Determinism
- Semantic purity
"""

import pytest
from external_policy.ep3_arbitration import (
    DecisionCode,
    RejectionReason,
    PermissionOutput,
    StrategyProposal,
    PolicyDecision,
    ProposalValidator,
    ArbitrationEngine,
    DecisionEmitter
)


# ==============================================================================
# TEST 1: M6 DENIED Veto (Absolute)
# ==============================================================================

def test_m6_denied_veto_overrides_all():
    """TEST 1: M6 DENIED must veto even with valid proposal."""
    m6_permission = PermissionOutput(
        result="DENIED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_VIOLATED",
        timestamp=1000.0
    )
    
    # Valid proposal exists
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-001"
    )
    
    # Must reject due to M6 veto
    assert decision.decision_code == DecisionCode.REJECTED_ACTION
    assert decision.reason == RejectionReason.M6_PERMISSION_DENIED
    assert decision.selected_proposal is None


# ==============================================================================
# TEST 2: Zero Proposals
# ==============================================================================

def test_zero_proposals_returns_no_action():
    """TEST 2: Zero proposals must return NO_ACTION."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[],  # No proposals
        timestamp=1000.0,
        trace_id="TRACE-002"
    )
    
    assert decision.decision_code == DecisionCode.NO_ACTION
    assert decision.reason == RejectionReason.ZERO_PROPOSALS
    assert decision.selected_proposal is None


# ==============================================================================
# TEST 3: Multiple Proposals (Conflict Abstention)
# ==============================================================================

def test_multiple_proposals_returns_no_action():
    """TEST 3: Multiple proposals must trigger abstention."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    proposals = [
        StrategyProposal(
            strategy_id="STRAT-001",
            action_type="ACTION_A",
            confidence="HIGH",
            justification_ref="REF-001",
            timestamp=1000.0
        ),
        StrategyProposal(
            strategy_id="STRAT-002",
            action_type="ACTION_B",
            confidence="MEDIUM",
            justification_ref="REF-002",
            timestamp=1000.0
        )
    ]
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=proposals,
        timestamp=1000.0,
        trace_id="TRACE-003"
    )
    
    assert decision.decision_code == DecisionCode.NO_ACTION
    assert decision.reason == RejectionReason.MULTIPLE_PROPOSALS


# ==============================================================================
# TEST 4: Single Valid Proposal Authorized
# ==============================================================================

def test_single_valid_proposal_authorized():
    """TEST 4: Single valid proposal with M6 ALLOWED → AUTHORIZED."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-004"
    )
    
    assert decision.decision_code == DecisionCode.AUTHORIZED_ACTION
    assert decision.reason == RejectionReason.AUTHORIZED
    assert decision.selected_proposal == proposal


# ==============================================================================
# TEST 5: Determinism
# ==============================================================================

def test_determinism_identical_inputs():
    """TEST 5: Identical inputs must produce identical outputs."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    # Execute twice
    decision1 = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-005"
    )
    
    decision2 = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-005"  # Same trace_id
    )
    
    # Must be identical
    assert decision1 == decision2


# ==============================================================================
# TEST 6: Invalid Proposal Schema (Timestamp Mismatch)
# ==============================================================================

def test_invalid_proposal_timestamp_mismatch():
    """TEST 6: Proposal with mismatched timestamp must be rejected."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=2000.0  # MISMATCH!
    )
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-006"
    )
    
    assert decision.decision_code == DecisionCode.NO_ACTION
    assert decision.reason == RejectionReason.INVALID_PROPOSAL_SCHEMA


# ==============================================================================
# TEST 7: Invalid Proposal Schema (Empty Fields)
# ==============================================================================

def test_invalid_proposal_empty_fields():
    """TEST 7: Proposal with empty required fields must be rejected."""
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="PREDICATE_SATISFIED",
        timestamp=1000.0
    )
    
    proposal = StrategyProposal(
        strategy_id="",  # EMPTY!
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    decision = ArbitrationEngine.arbitrate(
        m6_permission=m6_permission,
        proposals=[proposal],
        timestamp=1000.0,
        trace_id="TRACE-007"
    )
    
    assert decision.decision_code == DecisionCode.NO_ACTION
    assert decision.reason == RejectionReason.INVALID_PROPOSAL_SCHEMA


# ==============================================================================
# TEST 8: Semantic Purity (No Market Terms)
# ==============================================================================

def test_semantic_purity_no_market_terms():
    """TEST 8: Verify no forbidden market terms in code."""
    # This test scans the module source for forbidden terms
    import external_policy.ep3_arbitration as ep3_module
    import inspect
    
    source_code = inspect.getsource(ep3_module)
    
    forbidden_terms = [
        "bullish", "bearish", "momentum", "reversal",
        "strong", "weak",
        "buy", "sell", "signal", "trade",
        "profit", "loss", "alpha", "edge"
    ]
    
    for term in forbidden_terms:
        assert term.lower() not in source_code.lower(), \
            f"Forbidden term '{term}' found in EP-3 code"


# ==============================================================================
# TEST 9: Decision Emitter
# ==============================================================================

def test_decision_emitter_authorized():
    """TEST 9: DecisionEmitter must correctly serialize AUTHORIZED decisions."""
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    decision = PolicyDecision(
        decision_code=DecisionCode.AUTHORIZED_ACTION,
        selected_proposal=proposal,
        reason=RejectionReason.AUTHORIZED,
        timestamp=1000.0,
        trace_id="TRACE-009"
    )
    
    output = DecisionEmitter.emit(decision)
    
    assert output["decision_code"] == "AUTHORIZED_ACTION"
    assert output["selected_proposal"]["strategy_id"] == "STRAT-001"
    assert output["reason"] == "AUTHORIZED"


def test_decision_emitter_no_action():
    """TEST 9b: DecisionEmitter must correctly serialize NO_ACTION decisions."""
    decision = PolicyDecision(
        decision_code=DecisionCode.NO_ACTION,
        selected_proposal=None,
        reason=RejectionReason.ZERO_PROPOSALS,
        timestamp=1000.0,
        trace_id="TRACE-009b"
    )
    
    output = DecisionEmitter.emit(decision)
    
    assert output["decision_code"] == "NO_ACTION"
    assert output["selected_proposal"] is None
    assert output["reason"] == "ZERO_PROPOSALS"


# ==============================================================================
# TEST 10: Immutability
# ==============================================================================

def test_immutability_enforcement():
    """TEST 10: All dataclasses must be immutable (frozen)."""
    proposal = StrategyProposal(
        strategy_id="STRAT-001",
        action_type="ACTION_A",
        confidence="HIGH",
        justification_ref="REF-001",
        timestamp=1000.0
    )
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError
        proposal.strategy_id = "MODIFIED"
    
    m6_permission = PermissionOutput(
        result="ALLOWED",
        mandate_id="M6-001",
        action_id="ACT-001",
        reason_code="TEST",
        timestamp=1000.0
    )
    
    with pytest.raises(Exception):
        m6_permission.result = "DENIED"
