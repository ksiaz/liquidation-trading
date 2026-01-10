"""
M6 Scaffolding Tests

Verifies conformance to M6 Implementation Invariants v1.0 and Mandate Template v1.0.

Tests Example Mandates v0 and v1 as specified in certification.
"""

import pytest
from memory.m6_scaffolding import (
    MandateType,
    PredicateOperation,
    PredicateCondition,
    PolicyPredicate,
    MandateDefinition,
    M5DescriptiveSnapshot,
    PermissionOutput,
    StateClassificationOutput,
    AlertOutput,
    MandateLoader,
    PredicateValidator,
    EvaluationEngine,
    OutputEnforcer,
    InvariantAsserter,
    InvariantViolationError,
    PredicateStructureError,
    OutputGrammarError
)


# ==============================================================================
# TEST: EXAMPLE MANDATE V0 (Empty Predicate)
# ==============================================================================

def test_example_mandate_v0_load():
    """Test loading Example Mandate v0 (empty predicate)."""
    mandate_def = {
        "mandate_id": "M6-EXAMPLE-000",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "EXTERNAL_ACTION_GENERIC",
        "policy_predicate": {
            "requires": [],
            "forbids": []
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    assert mandate.mandate_id == "M6-EXAMPLE-000"
    assert mandate.mandate_type == MandateType.CONSTRAINT_GATE
    assert len(mandate.policy_predicate.requires) == 0
    assert len(mandate.policy_predicate.forbids) == 0


def test_example_mandate_v0_evaluate():
    """Test evaluating Example Mandate v0 always returns True (empty predicate)."""
    mandate_def = {
        "mandate_id": "M6-EXAMPLE-000",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "EXTERNAL_ACTION_GENERIC",
        "policy_predicate": {"requires": [], "forbids": []}
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    # Empty snapshot
    snapshot = M5DescriptiveSnapshot(
        query_id="QUERY-000",
        timestamp=1000.0,
        descriptive_facts={}
    )
    
    result = EvaluationEngine.evaluate(mandate, snapshot)
    assert result is True  # Empty predicate always satisfies


def test_example_mandate_v0_output():
    """Test Example Mandate v0 produces valid permission output."""
    output = OutputEnforcer.enforce_permission_output(
        mandate_id="M6-EXAMPLE-000",
        action_id="ACTION-000",
        result=True,
        reason_code="NO_CONSTRAINT_DEFINED"
    )
    
    assert output.mandate_id == "M6-EXAMPLE-000"
    assert output.action_id == "ACTION-000"
    assert output.result == "ALLOWED"
    assert output.reason_code == "NO_CONSTRAINT_DEFINED"


# ==============================================================================
# TEST: EXAMPLE MANDATE V1 (Non-Empty Predicate)
# ==============================================================================

def test_example_mandate_v1_load():
    """Test loading Example Mandate v1 (non-empty predicate)."""
    mandate_def = {
        "mandate_id": "M6-EXAMPLE-001",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "EXTERNAL_ACTION_GENERIC",
        "policy_predicate": {
            "requires": [
                {
                    "operation": "EQUALS",
                    "fact_key": "fact_X",
                    "expected_value": True
                },
                {
                    "operation": "IN_CATEGORY",
                    "fact_key": "fact_Y",
                    "category_set": ["CATEGORY_A", "CATEGORY_B"]
                }
            ],
            "forbids": [
                {
                    "operation": "EXISTS",
                    "fact_key": "fact_Z"
                }
            ]
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    assert mandate.mandate_id == "M6-EXAMPLE-001"
    assert len(mandate.policy_predicate.requires) == 2
    assert len(mandate.policy_predicate.forbids) == 1


def test_example_mandate_v1_evaluate_satisfied():
    """Test Example Mandate v1 evaluation when predicate satisfied."""
    mandate_def = {
        "mandate_id": "M6-EXAMPLE-001",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "EXTERNAL_ACTION_GENERIC",
        "policy_predicate": {
            "requires": [
                {"operation": "EQUALS", "fact_key": "fact_X", "expected_value": True},
                {"operation": "IN_CATEGORY", "fact_key": "fact_Y", "category_set": ["CATEGORY_A", "CATEGORY_B"]}
            ],
            "forbids": [
                {"operation": "EXISTS", "fact_key": "fact_Z"}
            ]
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    # Satisfying snapshot
    snapshot = M5DescriptiveSnapshot(
        query_id="QUERY-001",
        timestamp=1000.0,
        descriptive_facts={
            "fact_X": True,
            "fact_Y": "CATEGORY_A"
            # fact_Z absent (forbidden)
        }
    )
    
    result = EvaluationEngine.evaluate(mandate, snapshot)
    assert result is True


def test_example_mandate_v1_evaluate_violated():
    """Test Example Mandate v1 evaluation when predicate violated."""
    mandate_def = {
        "mandate_id": "M6-EXAMPLE-001",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "EXTERNAL_ACTION_GENERIC",
        "policy_predicate": {
            "requires": [
                {"operation": "EQUALS", "fact_key": "fact_X", "expected_value": True}
            ],
            "forbids": [
                {"operation": "EXISTS", "fact_key": "fact_Z"}
            ]
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    # Violating snapshot (fact_Z present)
    snapshot = M5DescriptiveSnapshot(
        query_id="QUERY-001",
        timestamp=1000.0,
        descriptive_facts={
            "fact_X": True,
            "fact_Z": "some_value"  # Forbidden!
        }
    )
    
    result = EvaluationEngine.evaluate(mandate, snapshot)
    assert result is False


# ==============================================================================
# TEST: PREDICATE VALIDATION (Invariant I-03)
# ==============================================================================

def test_predicate_validation_rejects_arithmetic():
    """Test that arithmetic operations are rejected."""
    # Attempt to create predicate with forbidden "sum" pattern
    with pytest.raises(PredicateStructureError):
        condition = PredicateCondition(
            operation=PredicateOperation.EXISTS,
            fact_key="sum_of_values"  # Contains forbidden "sum"
        )
        PredicateValidator._validate_condition(condition)


def test_predicate_validation_rejects_comparison():
    """Test that comparison patterns are rejected."""
    with pytest.raises(PredicateStructureError):
        condition = PredicateCondition(
            operation=PredicateOperation.EXISTS,
            fact_key="greater_than_threshold"  # Contains forbidden pattern
        )
        PredicateValidator._validate_condition(condition)


def test_predicate_validation_accepts_valid():
    """Test that valid predicates pass."""
    condition = PredicateCondition(
        operation=PredicateOperation.EQUALS,
        fact_key="neutral_fact",
        expected_value="ALLOWED"
    )
    # Should not raise
    PredicateValidator._validate_condition(condition)


# ==============================================================================
# TEST: MANDATE LOADER (Template Conformance)
# ==============================================================================

def test_mandate_loader_rejects_missing_fields():
    """Test that mandates missing required fields are rejected."""
    incomplete_def = {
        "mandate_id": "TEST-001"
        # Missing mandate_type, mandate_scope, policy_predicate
    }
    
    with pytest.raises(InvariantViolationError):
        MandateLoader.load_mandate(incomplete_def)


def test_mandate_loader_rejects_invalid_type():
    """Test that invalid mandate types are rejected."""
    invalid_def = {
        "mandate_id": "TEST-001",
        "mandate_type": "INVALID_TYPE",  # Not in allowed types
        "mandate_scope": "TEST",
        "policy_predicate": {"requires": [], "forbids": []}
    }
    
    with pytest.raises(InvariantViolationError):
        MandateLoader.load_mandate(invalid_def)


# ==============================================================================
# TEST: OUTPUT GRAMMAR (Invariant I-05)
# ==============================================================================

def test_output_enforcer_permission_valid():
    """Test valid permission output creation."""
    output = OutputEnforcer.enforce_permission_output(
        mandate_id="TEST-001",
        action_id="ACT-001",
        result=True,
        reason_code="SATISFIED"
    )
    
    assert isinstance(output, PermissionOutput)
    assert output.result == "ALLOWED"


def test_output_enforcer_permission_denied():
    """Test denied permission output creation."""
    output = OutputEnforcer.enforce_permission_output(
        mandate_id="TEST-001",
        action_id="ACT-001",
        result=False,
        reason_code="VIOLATED"
    )
    
    assert isinstance(output, PermissionOutput)
    assert output.result == "DENIED"


def test_output_enforcer_state_classification():
    """Test state classification output creation."""
    output = OutputEnforcer.enforce_state_output(
        mandate_id="TEST-001",
        state_id="STATE_A",
        timestamp=1000.0
    )
    
    assert isinstance(output, StateClassificationOutput)
    assert output.state_id == "STATE_A"
    assert output.timestamp == 1000.0


def test_output_enforcer_alert():
    """Test alert output creation."""
    output = OutputEnforcer.enforce_alert_output(
        mandate_id="TEST-001",
        alert_code="ALERT_X",
        timestamp=1000.0
    )
    
    assert isinstance(output, AlertOutput)
    assert output.alert_code == "ALERT_X"


# ==============================================================================
# TEST: DETERMINISM (Invariant I-02)
# ==============================================================================

def test_determinism_identical_inputs():
    """Test that identical inputs produce identical outputs."""
    mandate_def = {
        "mandate_id": "DET-TEST",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "TEST",
        "policy_predicate": {
            "requires": [{"operation": "EQUALS", "fact_key": "x", "expected_value": 1}],
            "forbids": []
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    snapshot = M5DescriptiveSnapshot(
        query_id="Q1",
        timestamp=1000.0,
        descriptive_facts={"x": 1}
    )
    
    # Evaluate multiple times
    result1 = EvaluationEngine.evaluate(mandate, snapshot)
    result2 = EvaluationEngine.evaluate(mandate, snapshot)
    result3 = EvaluationEngine.evaluate(mandate, snapshot)
    
    assert result1 == result2 == result3


def test_determinism_explicit_timestamp_required():
    """Test that snapshots must have explicit timestamps."""
    snapshot = M5DescriptiveSnapshot(
        query_id="Q1",
        timestamp=None,  # Missing explicit timestamp
        descriptive_facts={}
    )
    
    with pytest.raises(InvariantViolationError):
        InvariantAsserter.assert_determinism(snapshot)


# ==============================================================================
# TEST: SEMANTIC PURITY (Invariant I-04)
# ==============================================================================

def test_semantic_purity_rejects_market_terms():
    """Test that market semantic terms are rejected in identifiers."""
    forbidden_identifiers = [
        "bullish_condition",
        "bearish_signal",
        "momentum_strength",
        "buy_trigger",
        "sell_alert"
    ]
    
    for identifier in forbidden_identifiers:
        with pytest.raises(InvariantViolationError):
            InvariantAsserter.assert_semantic_purity([identifier])


def test_semantic_purity_accepts_neutral_terms():
    """Test that neutral terms are accepted."""
    neutral_identifiers = [
        "condition_a",
        "state_classifier",
        "fact_exists",
        "category_member"
    ]
    
    # Should not raise
    InvariantAsserter.assert_semantic_purity(neutral_identifiers)


# ==============================================================================
# TEST: IMMUTABILITY
# ==============================================================================

def test_mandate_immutability():
    """Test that mandates are immutable after creation."""
    mandate_def = {
        "mandate_id": "IMMUT-TEST",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "TEST",
        "policy_predicate": {"requires": [], "forbids": []}
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    # Attempt mutation should fail
    with pytest.raises(Exception):  # FrozenInstanceError in dataclasses
        mandate.mandate_id = "MODIFIED"


def test_snapshot_immutability():
    """Test that snapshots are immutable."""
    snapshot = M5DescriptiveSnapshot(
        query_id="Q1",
        timestamp=1000.0,
        descriptive_facts={"x": 1}
    )
    
    # Attempt mutation should fail
    with pytest.raises(Exception):
        snapshot.timestamp = 2000.0
