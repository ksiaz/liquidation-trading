"""
Tests for M5 Selection Guards.
Verifies that the 'Police' correctly rejects forbidden inputs and sanitizes queries.
"""

import pytest
from memory.m5_selection_guards import (
    validate_keys,
    validate_values,
    enforce_determinism,
    inject_neutral_defaults,
    run_guards,
    EpistemicSafetyError,
    DeterminismError
)

# ==============================================================================
# TEST 1: FORBIDDEN KEYS
# ==============================================================================

def test_validate_keys_rejects_forbidden_params():
    """Verify that forbidden keys trigger EpistemicSafetyError."""
    # Test a few representative forbidden keys
    bad_inputs = [
        {"min_strength": 0.5},
        {"importance": "high"},
        {"rank": 1},
        {"alpha": 0.01},
        {"bullish": True},
        {"top_n": 10}
    ]
    
    for params in bad_inputs:
        with pytest.raises(EpistemicSafetyError) as exc:
            validate_keys(params)
        assert "implies judgment" in str(exc.value)

def test_validate_keys_accepts_allowed_params():
    """Verify that neutral keys are accepted."""
    good_params = {
        "node_id": "123",
        "current_ts": 1000.0,
        "limit": 10,  # "limit" itself is not forbidden, "top_n" is
        "sort_by": "time"
    }
    validate_keys(good_params)  # Should not raise

# ==============================================================================
# TEST 2: FORBIDDEN VALUES
# ==============================================================================

def test_validate_values_rejects_forbidden_patterns():
    """Verify that forbidden value patterns trigger EpistemicSafetyError."""
    bad_values = [
        {"tag": "STRONG_BUY"},
        {"sentiment": "VERY_BULLISH"},
        {"action": "GOOD_ENTRY"},
        {"direction": "POSITIVE_TREND"}
    ]
    
    for params in bad_values:
        with pytest.raises(EpistemicSafetyError) as exc:
            validate_values(params)
        assert "forbidden semantic pattern" in str(exc.value)

def test_validate_values_accepts_neutral_strings():
    """Verify that neutral strings are accepted."""
    good_values = {
        "id": "node_123_part_b",
        "type": "TRADE_EXECUTION", # Contains "EXECUTION", safe
        "reason": "OB_APPEARED"
    }
    validate_values(good_values) # Should not raise

# ==============================================================================
# TEST 3: DETERMINISM ENFORCEMENT
# ==============================================================================

def test_enforce_determinism_rejects_implicit_time():
    """Verify rejection of implicit time strings."""
    bad_times = [
        {"current_ts": "now"},
        {"current_ts": "latest"},
        {"query_ts": "realtime"}
    ]
    
    for params in bad_times:
        with pytest.raises(DeterminismError):
            enforce_determinism(params)

def test_enforce_determinism_accepts_floats():
    """Verify explicit float times are accepted."""
    enforce_determinism({"current_ts": 123456.789})

# ==============================================================================
# TEST 4: NEUTRAL DEFAULTS
# ==============================================================================

def test_inject_neutral_defaults_adds_missing_keys():
    """Verify missing keys are populated with neutral defaults."""
    inp = {"node_id": "123"}
    out = inject_neutral_defaults(inp)
    
    # Should have added defaults
    assert "limit" in out
    assert out["limit"] is None  # Neutral default
    assert "sort_by" in out
    assert out["sort_by"] == "time"

def test_inject_neutral_defaults_preserves_existing_keys():
    """Verify that user-provided values override defaults (if keys match)."""
    inp = {
        "node_id": "123",
        "limit": 50,         # User provided limit
        "sort_by": "price"   # User provided sort
    }
    out = inject_neutral_defaults(inp)
    
    assert out["limit"] == 50
    assert out["sort_by"] == "price"

# ==============================================================================
# TEST 5: MASTER GUARD
# ==============================================================================

def test_run_guards_integration():
    """Verify run_guards calls all checks."""
    # Case 1: Bad Key
    with pytest.raises(EpistemicSafetyError):
        run_guards({"min_score": 5})
        
    # Case 2: Bad Value
    with pytest.raises(EpistemicSafetyError):
        run_guards({"reason": "STRONG_SIGNAL"})
        
    # Case 3: Bad Time
    with pytest.raises(DeterminismError):
        run_guards({"time": "now"})
        
    # Case 4: Good Input
    run_guards({"node_id": "ok", "time": 123.0})
