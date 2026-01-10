"""
M6-M5 Integration Tests

End-to-end verification of M6 scaffolding against live M5 governance layer.

Per M6-M5 Integration Test Plan v1.0.

CRITICAL: These tests verify boundary integrity, not strategy effectiveness.
"""

import pytest
from memory.m6_scaffolding import (
    MandateType,
    PredicateOperation,
    PredicateCondition,
    PolicyPredicate,
    MandateDefinition,
    M5DescriptiveSnapshot,
    MandateLoader,
    EvaluationEngine,
    OutputEnforcer,
    InvariantAsserter,
    InvariantViolationError,
    PredicateStructureError
)
from memory.m5_access import MemoryAccess, AccessDeniedError, SchemaValidationError
from memory.m5_selection_guards import EpistemicSafetyError, DeterminismError
from memory.m2_continuity_store import ContinuityMemoryStore


# ==============================================================================
# TEST FIXTURES
# ==============================================================================

@pytest.fixture
def live_store():
    """Create a live M2 store with deterministic fixtures."""
    store = ContinuityMemoryStore()
    
    # Add deterministic test nodes
    store.add_or_update_node(
        node_id="node_integration_1",
        price_center=100.0,
        price_band=2.0,  # Band width (not tuple)
        side="BID",
        timestamp=1000.0,
        creation_reason="TEST_FIXTURE"
    )
    
    store.add_or_update_node(
        node_id="node_integration_2",
        price_center=200.0,
        price_band=2.0,  # Band width (not tuple)
        side="ASK",
        timestamp=1000.0,
        creation_reason="TEST_FIXTURE"
    )
    
    return store


@pytest.fixture
def m5_firewall(live_store):
    """Create live M5 governance layer."""
    return MemoryAccess(live_store)


@pytest.fixture
def example_mandate_v1():
    """Example Mandate v1 definition."""
    return {
        "mandate_id": "M6-INTEGRATION-001",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "INTEGRATION_TEST",
        "policy_predicate": {
            "requires": [
                {"operation": "EXISTS", "fact_key": "node_id"},
                {"operation": "EXISTS", "fact_key": "state"}
            ],
            "forbids": []
        }
    }


# ==============================================================================
# TEST 1 — Happy Path Evaluation
# ==============================================================================

def test_integration_happy_path_evaluation(m5_firewall, example_mandate_v1):
    """
    TEST 1: Verify valid M5 → M6 evaluation.
    
    Proves:
    - M5 query accepted
    - M6 evaluation returns deterministic boolean
    - Output grammar valid
    """
    # Step 1: Query M5 with allowed descriptive query
    m5_result = m5_firewall.execute_query("IDENTITY", {
        "node_id": "node_integration_1"
    })
    
    # Verify M5 query accepted (no exception)
    assert m5_result is not None
    assert "node_id" in m5_result
    assert "state" in m5_result
    
    # Step 2: Convert M5 result to M6 snapshot
    snapshot = M5DescriptiveSnapshot(
        query_id="INTEGRATION_Q1",
        timestamp=1000.0,
        descriptive_facts=m5_result
    )
    
    # Step 3: Load mandate and evaluate
    mandate = MandateLoader.load_mandate(example_mandate_v1)
    result = EvaluationEngine.evaluate(mandate, snapshot)
    
    # Assertions
    assert isinstance(result, bool)  # Deterministic boolean
    assert result is True  # Both required facts exist
    
    # Step 4: Generate certified output
    output = OutputEnforcer.enforce_permission_output(
        mandate_id=mandate.mandate_id,
        action_id="TEST_ACTION_1",
        result=result,
        reason_code="PREDICATE_SATISFIED"
    )
    
    # Verify output grammar
    assert output.mandate_id == "M6-INTEGRATION-001"
    assert output.result == "ALLOWED"


# ==============================================================================
# TEST 2 — M5 Forbidden Query Propagation
# ==============================================================================

def test_integration_forbidden_query_propagation(m5_firewall):
    """
    TEST 2: Ensure governance rejection propagates.
    
    Proves:
    - M5 rejects forbidden parameters
    - Exception type preserved
    - M6 never invoked
    """
    # Attempt M5 query with forbidden parameter
    with pytest.raises(EpistemicSafetyError) as exc_info:
        m5_firewall.execute_query("SPATIAL_GROUP", {
            "min_price": 100.0,
            "max_price": 200.0,
            "current_ts": 1000.0,
            "min_strength": 0.8  # FORBIDDEN PARAMETER
        })
    
    # Verify exception type preserved
    assert "min_strength" in str(exc_info.value) or "judgment" in str(exc_info.value)
    
    # M6 is never invoked (test completes without M6 evaluation)
    # This is verified by the test not reaching M6 code paths


# ==============================================================================
# TEST 3 — Determinism Across Layers
# ==============================================================================

def test_integration_determinism_across_layers(m5_firewall, example_mandate_v1):
    """
    TEST 3: Prove end-to-end determinism.
    
    Proves:
    - Identical M5 queries → identical snapshots
    - Identical snapshots → identical M6 outputs
    """
    mandate = MandateLoader.load_mandate(example_mandate_v1)
    
    # Execute identical M5 query twice
    m5_result_1 = m5_firewall.execute_query("IDENTITY", {
        "node_id": "node_integration_1"
    })
    
    m5_result_2 = m5_firewall.execute_query("IDENTITY", {
        "node_id": "node_integration_1"
    })
    
    # Verify M5 snapshots identical
    assert m5_result_1 == m5_result_2
    
    # Create identical snapshots
    snapshot_1 = M5DescriptiveSnapshot(
        query_id="DET_Q1",
        timestamp=1000.0,
        descriptive_facts=m5_result_1
    )
    
    snapshot_2 = M5DescriptiveSnapshot(
        query_id="DET_Q1",
        timestamp=1000.0,
        descriptive_facts=m5_result_2
    )
    
    # Evaluate with M6
    result_1 = EvaluationEngine.evaluate(mandate, snapshot_1)
    result_2 = EvaluationEngine.evaluate(mandate, snapshot_2)
    
    # Verify M6 outputs identical
    assert result_1 == result_2
    
    # Generate outputs
    output_1 = OutputEnforcer.enforce_permission_output(
        mandate_id=mandate.mandate_id,
        action_id="DET_ACT",
        result=result_1,
        reason_code="DET_TEST"
    )
    
    output_2 = OutputEnforcer.enforce_permission_output(
        mandate_id=mandate.mandate_id,
        action_id="DET_ACT",
        result=result_2,
        reason_code="DET_TEST"
    )
    
    # Verify outputs identical
    assert output_1 == output_2


# ==============================================================================
# TEST 4 — Snapshot Shape Tampering
# ==============================================================================

def test_integration_snapshot_tampering_rejection():
    """
    TEST 4: Ensure M6 rejects non-M5 outputs.
    
    Proves:
    - Tampered snapshots raise errors
    - No partial evaluation occurs
    """
    mandate_def = {
        "mandate_id": "M6-TAMPER-TEST",
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "TEST",
        "policy_predicate": {
            "requires": [{"operation": "EXISTS", "fact_key": "valid_field"}],
            "forbids": []
        }
    }
    
    mandate = MandateLoader.load_mandate(mandate_def)
    
    # Create tampered snapshot (missing required timestamp)
    tampered_snapshot = M5DescriptiveSnapshot(
        query_id="TAMPER_Q",
        timestamp=None,  # TAMPERED: None instead of explicit value
        descriptive_facts={"valid_field": "value"}
    )
    
    # Attempt invariant check
    with pytest.raises(InvariantViolationError) as exc_info:
        InvariantAsserter.assert_determinism(tampered_snapshot)
    
    # Verify hard rejection
    assert "I-02" in str(exc_info.value) or "timestamp" in str(exc_info.value).lower()


# ==============================================================================
# TEST 5 — Semantic Injection Attempt
# ==============================================================================

def test_integration_semantic_injection_rejection():
    """
    TEST 5: Validate semantic firewall.
    
    Proves:
    - Forbidden identifiers rejected
    - Invariant violation raised
    - Error is explicit
    """
    # Attempt to create mandate with forbidden semantic term
    forbidden_mandate_def = {
        "mandate_id": "M6-BULLISH-SIGNAL",  # FORBIDDEN: market semantic
        "mandate_type": "CONSTRAINT_GATE",
        "mandate_scope": "TEST",
        "policy_predicate": {
            "requires": [],
            "forbids": []
        }
    }
    
    # Load mandate (passes, as mandate_id itself isn't validated for semantics)
    mandate = MandateLoader.load_mandate(forbidden_mandate_def)
    
    # But invariant check should reject it
    forbidden_identifiers = ["M6-BULLISH-SIGNAL"]
    
    with pytest.raises(InvariantViolationError) as exc_info:
        InvariantAsserter.assert_semantic_purity(forbidden_identifiers)
    
    # Verify explicit error
    assert "bullish" in str(exc_info.value).lower() or "I-04" in str(exc_info.value)


# ==============================================================================
# TEST 6 — Cross-Layer Type Safety
# ==============================================================================

def test_integration_type_safety_enforcement(m5_firewall):
    """
    BONUS TEST: Verify type safety across M5-M6 boundary.
    
    Proves:
    - M5 outputs match expected schema
    - M6 snapshots are type-safe
    """
    # Query M5
    m5_result = m5_firewall.execute_query("IDENTITY", {
        "node_id": "node_integration_1"
    })
    
    # Verify M5 output types
    assert isinstance(m5_result, dict)
    assert isinstance(m5_result["node_id"], str)
    assert isinstance(m5_result["state"], str)
    assert isinstance(m5_result["creation_ts"], (int, float))
    
    # Create M6 snapshot
    snapshot = M5DescriptiveSnapshot(
        query_id="TYPE_Q",
        timestamp=1000.0,
        descriptive_facts=m5_result
    )
    
    # Verify snapshot is frozen (immutable)
    with pytest.raises(Exception):  # FrozenInstanceError
        snapshot.timestamp = 2000.0


# ==============================================================================
# TEST 7 — M5 Schema Validation Propagation
# ==============================================================================

def test_integration_schema_violation_propagation(m5_firewall):
    """
    BONUS TEST: Verify M5 schema violations propagate correctly.
    
    Proves:
    - Invalid query types rejected
    - Exceptions propagate without alteration
    """
    # Attempt invalid query type
    with pytest.raises(AccessDeniedError):
        m5_firewall.execute_query("INVALID_QUERY_TYPE", {})
    
    # Attempt query with missing required field
    with pytest.raises(Exception):  # SchemaValidationError or similar
        m5_firewall.execute_query("IDENTITY", {})  # Missing node_id
