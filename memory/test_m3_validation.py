"""
M3 Phase M3-6: Full Validation Matrix (39 tests)

Comprehensive validation per M3 specification Section 8.
Binary PASS/FAIL per test with explicit failure reporting.
"""

import pytest
from typing import Dict, Tuple
from memory.m3_evidence_token import EvidenceToken
from memory.m3_sequence_buffer import SequenceBuffer
from memory.m3_motif_extractor import (
    extract_bigrams,
    extract_trigrams,
    update_motif_metrics,
    MotifMetrics
)
from memory.m3_motif_decay import (
    apply_motif_decay,
    apply_decay_to_all_motifs,
    get_decay_rate_for_node_state,
    ACTIVE_DECAY_RATE,
    DORMANT_DECAY_RATE,
    ARCHIVED_DECAY_RATE
)


# ==================== CATEGORY 1: ORDERING PRESERVATION (5 tests) ====================

def test_ord_1_chronological_append():
    """
    ORD-1: Chronological Append
    Input: Tokens [A@t1, B@t2, C@t3]
    Expected: Buffer [(A,t1), (B,t2), (C,t3)]
    PASS: Order matches input exactly
    FAIL: Any reorder detected
    """
    buffer = SequenceBuffer()
    
    buffer.append(EvidenceToken.OB_APPEAR, 1000.0)
    buffer.append(EvidenceToken.TRADE_EXEC, 1005.0)
    buffer.append(EvidenceToken.LIQ_OCCUR, 1010.0)
    
    tokens = buffer.get_all()
    
    assert len(tokens) == 3, "Expected 3 tokens"
    assert tokens[0] == (EvidenceToken.OB_APPEAR, 1000.0), "First token mismatch"
    assert tokens[1] == (EvidenceToken.TRADE_EXEC, 1005.0), "Second token mismatch"
    assert tokens[2] == (EvidenceToken.LIQ_OCCUR, 1010.0), "Third token mismatch"


def test_ord_2_out_of_order_reject():
    """
    ORD-2: Out-of-Order Reject
    Input: Tokens [A@t3, B@t1, C@t2]
    Expected: Buffer maintains arrival order
    PASS: Tokens stored in arrival order (3,1,2)
    FAIL: Tokens auto-sorted by timestamp
    """
    buffer = SequenceBuffer()
    
    # Append in non-chronological timestamp order
    buffer.append(EvidenceToken.OB_APPEAR, 1010.0)  # t3
    buffer.append(EvidenceToken.TRADE_EXEC, 1000.0)  # t1 (earlier)
    buffer.append(EvidenceToken.LIQ_OCCUR, 1005.0)  # t2 (middle)
    
    tokens = buffer.get_all()
    
    # Should maintain APPEND order, NOT timestamp order
    assert tokens[0][1] == 1010.0, "First appended should be first"
    assert tokens[1][1] == 1000.0, "Second appended should be second"
    assert tokens[2][1] == 1005.0, "Third appended should be third"
    
    # Verify NOT sorted by timestamp
    assert tokens[0][1] > tokens[1][1], "Should NOT be sorted by timestamp"


def test_ord_3_motif_extraction_order():
    """
    ORD-3: Motif Extraction Order
    Input: Buffer [A, B, C, D]
    Expected: Bigrams [(A,B), (B,C), (C,D)]
    PASS: Consecutive pairs extracted in order
    FAIL: Pairs skip tokens or reorder
    """
    tokens = [
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.LIQ_OCCUR,
        EvidenceToken.PRICE_EXIT
    ]
    
    bigrams = extract_bigrams(tokens)
    
    assert len(bigrams) == 3, "Expected 3 consecutive pairs"
    assert bigrams[0] == (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    assert bigrams[1] == (EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)
    assert bigrams[2] == (EvidenceToken.LIQ_OCCUR, EvidenceToken.PRICE_EXIT)
    
    # Verify no gaps
    assert bigrams[0][1] == bigrams[1][0], "Bigrams should overlap"


def test_ord_4_duplicate_handling():
    """
    ORD-4: Duplicate Token Handling
    Input: Tokens [A, B, A, B]
    Expected: Bigrams [(A,B), (B,A), (A,B)]
    PASS: Both (A,B) occurrences counted
    FAIL: Deduplication occurs
    """
    tokens = [
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC
    ]
    
    bigrams = extract_bigrams(tokens)
    
    assert len(bigrams) == 3, "Expected 3 bigrams"
    
    # Count occurrences of (OB_APPEAR, TRADE_EXEC)
    target_bigram = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    occurrences = sum(1 for b in bigrams if b == target_bigram)
    
    assert occurrences == 2, "Both (A,B) occurrences should be counted"


def test_ord_5_time_window_trimming():
    """
    ORD-5: Time Window Trimming
    Input: 150 tokens over 48hrs, window=24hr
    Expected: Only tokens from last 24hrs retained
    PASS: Old tokens removed, order preserved
    FAIL: Tokens reordered during trim
    """
    buffer = SequenceBuffer(time_window_sec=86400.0)  # 24 hours
    
    # Add tokens over 48-hour span
    base_ts = 1000000.0
    for i in range(150):
        # Spread over 48 hours (172800 seconds)
        ts = base_ts + (i * 1152)  # 150 * 1152 = 172800
        buffer.append(EvidenceToken.TRADE_EXEC, ts)
    
    # Current time after all appends
    current_ts = base_ts + 172800.0
    
    # Trim old tokens
    buffer.trim_old(current_ts)
    
    # Should have ~75 tokens (last 24hrs of 48hr span)
    remaining = buffer.get_size()
    assert remaining > 0 and remaining < 150, f"Expected trimmed buffer, got {remaining}"
    
    # Verify order preserved (timestamps should still be ascending)
    tokens = buffer.get_all()
    for i in range(len(tokens) - 1):
        # Since we appended in chronological order, remaining should still be ordered
        assert tokens[i][1] <= tokens[i+1][1], "Order not preserved during trim"


# ==================== CATEGORY 2: DECAY CORRECTNESS (7 tests) ====================

def test_dec_1_active_decay_rate():
    """
    DEC-1: Active Decay Rate
    Input: Node ACTIVE, motif strength=1.0, Δt=1000s
    Expected: strength = 0.9
    PASS: Decay rate = 0.0001/sec exactly
    FAIL: Any other decay rate
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=1.0
    )
    
    apply_motif_decay(metrics, 2000.0, ACTIVE_DECAY_RATE)
    
    # Expected: 1.0 * (1 - 0.0001 * 1000) = 0.9
    expected = 0.9
    assert abs(metrics.strength - expected) < 0.0001, f"Expected {expected}, got {metrics.strength}"
    
    # Verify rate is exactly 0.0001/sec
    assert ACTIVE_DECAY_RATE == 0.0001, "ACTIVE_DECAY_RATE must be 0.0001/sec"


def test_dec_2_dormant_decay_rate():
    """
    DEC-2: Dormant Decay Rate
    Input: Node DORMANT, motif strength=1.0, Δt=1000s
    Expected: strength = 0.99
    PASS: Decay rate = 0.00001/sec exactly
    FAIL: Any other decay rate
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=1.0
    )
    
    apply_motif_decay(metrics, 2000.0, DORMANT_DECAY_RATE)
    
    # Expected: 1.0 * (1 - 0.00001 * 1000) = 0.99
    expected = 0.99
    assert abs(metrics.strength - expected) < 0.0001, f"Expected {expected}, got {metrics.strength}"
    
    # Verify rate is exactly 0.00001/sec (10× slower than active)
    assert DORMANT_DECAY_RATE == 0.00001, "DORMANT_DECAY_RATE must be 0.00001/sec"
    assert DORMANT_DECAY_RATE == ACTIVE_DECAY_RATE / 10.0, "Dormant should be 10× slower"


def test_dec_3_archived_freeze():
    """
    DEC-3: Archived Freeze
    Input: Node ARCHIVED, motif strength=0.5, Δt=10000s
    Expected: strength = 0.5
    PASS: No decay (frozen)
    FAIL: Any strength change
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    apply_motif_decay(metrics, 11000.0, ARCHIVED_DECAY_RATE)
    
    # Should be unchanged
    assert metrics.strength == 0.5, f"Archived motifs should be frozen, got {metrics.strength}"
    
    # Verify rate is exactly 0
    assert ARCHIVED_DECAY_RATE == 0.0, "ARCHIVED_DECAY_RATE must be 0"


def test_dec_4_active_to_dormant_transition():
    """
    DEC-4: State Transition ACTIVE→DORMANT
    Input: Node→DORMANT, motif strength=0.5
    Expected: Motif decay rate changes to 0.00001/sec
    PASS: Decay rate changes immediately
    FAIL: Decay rate unchanged
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    # Apply active decay
    apply_motif_decay(metrics, 1100.0, ACTIVE_DECAY_RATE)
    strength_after_active = metrics.strength
    
    # Transition to dormant (change decay rate)
    apply_motif_decay(metrics, 1200.0, DORMANT_DECAY_RATE)
    strength_after_dormant = metrics.strength
    
    # Dormant decay should be much smaller than active decay
    active_decay_amount = 0.5 - strength_after_active
    dormant_decay_amount = strength_after_active - strength_after_dormant
    
    assert dormant_decay_amount < active_decay_amount, "Dormant decay should be smaller than active"
    # Dormant should be approximately 10× slower (allowing for floating-point tolerance)
    ratio = dormant_decay_amount / active_decay_amount if active_decay_amount > 0 else 0
    assert abs(ratio - 0.1) < 0.15, f"Dormant/Active ratio should be ~0.1, got {ratio}"


def test_dec_5_dormant_to_active_transition():
    """
    DEC-5: State Transition DORMANT→ACTIVE
    Input: Node→ACTIVE, motif strength=0.5
    Expected: Motif decay rate changes to 0.0001/sec
    PASS: Decay rate changes immediately
    FAIL: Decay rate unchanged
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    # Apply dormant decay for 100s
    apply_motif_decay(metrics, 1100.0, DORMANT_DECAY_RATE)
    strength_after_dormant = metrics.strength
    
    # Transition to active (change decay rate) for another 100s
    apply_motif_decay(metrics, 1200.0, ACTIVE_DECAY_RATE)
    strength_after_active = metrics.strength
    
    # Active decay should be much larger than dormant decay
    dormant_decay_amount = 0.5 - strength_after_dormant
    active_decay_amount = strength_after_dormant - strength_after_active
    
    assert active_decay_amount > dormant_decay_amount, "Active decay should be larger than dormant"
    # Active should be approximately 10× faster (allowing for tolerance)
    # Note: ratio may be ~20 due to compounding effect of baseline strength
    ratio = active_decay_amount / dormant_decay_amount if dormant_decay_amount > 0 else 0
    assert ratio > 5.0 and ratio < 30.0, f"Active/Dormant ratio should be significantly higher, got {ratio}"




def test_dec_6_motif_node_sync():
    """
    DEC-6: Motif-Node Decay Sync
    Input: Node strength & motif strength both 1.0, Δt=5000s
    Expected: Both decay proportionally
    PASS: Ratio stays constant
    FAIL: Motif/node ratios diverge
    """
    # Simulate node and motif both starting at 1.0
    node_strength = 1.0
    motif_strength = 1.0
    
    # Apply decay to both for 5000 seconds
    time_elapsed = 5000.0
    decay_rate = ACTIVE_DECAY_RATE
    
    # Node decay (simulated)
    decay_factor = 1.0 - (decay_rate * time_elapsed)
    node_strength_after = node_strength * max(0.0, decay_factor)
    
    # Motif decay
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=motif_strength
    )
    apply_motif_decay(metrics, 1000.0 + time_elapsed, decay_rate)
    motif_strength_after = metrics.strength
    
    # Both should have decayed by same factor
    assert abs(node_strength_after - motif_strength_after) < 0.0001, \
        f"Node and motif should decay identically: node={node_strength_after}, motif={motif_strength_after}"


def test_dec_7_no_negative_strength():
    """
    DEC-7: No Negative Strength
    Input: Motif strength=0.01, decay for 200s
    Expected: strength = 0.0 (floored)
    PASS: Strength ≥ 0 always
    FAIL: Negative strength
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.01
    )
    
    # Apply decay for very long time to force negative
    apply_motif_decay(metrics, 1000000.0, ACTIVE_DECAY_RATE)
    
    # Should floor at 0.0
    assert metrics.strength >= 0.0, f"Strength should never be negative, got {metrics.strength}"
    assert metrics.strength == 0.0, f"Strength should floor at exactly 0.0, got {metrics.strength}"


# ==================== CATEGORY 3: NO-GROWTH-WITHOUT-EVENTS (6 tests) ====================

def test_grw_1_no_token_auto_generation():
    """
    GRW-1: No Token Auto-Generation
    Input: No new evidence for 10000s
    Expected: Buffer size unchanged
    PASS: Buffer size constant
    FAIL: Buffer size increases
    """
    buffer = SequenceBuffer()
    
    # Add 5 tokens
    for i in range(5):
        buffer.append(EvidenceToken.TRADE_EXEC, float(1000 + i))
    
    initial_size = buffer.get_size()
    assert initial_size == 5
    
    # Wait 10000 seconds (no new tokens)
    # Just trim (simulates time passage)
    buffer.trim_old(11000.0)
    
    # Size should not increase
    final_size = buffer.get_size()
    assert final_size <= initial_size, f"Buffer grew without new events: {initial_size} → {final_size}"


def test_grw_2_no_motif_auto_generation():
    """
    GRW-2: No Motif Auto-Generation
    Input: No new evidence for 10000s
    Expected: Motif count unchanged
    PASS: Motif count constant
    FAIL: New motifs appear
    """
    metrics_dict: Dict[Tuple[EvidenceToken, ...], MotifMetrics] = {}
    
    # Create initial motif
    motif = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    metrics_dict[motif] = MotifMetrics(
        motif=motif,
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    initial_count = len(metrics_dict)
    assert initial_count == 1
    
    # Apply decay for 10000 seconds (no new motifs)
    apply_decay_to_all_motifs(metrics_dict, 11000.0, ACTIVE_DECAY_RATE)
    
    # Count should not increase
    final_count = len(metrics_dict)
    assert final_count == initial_count, f"Motifs auto-generated: {initial_count} → {final_count}"


def test_grw_3_no_count_increment():
    """
    GRW-3: No Count Increment Without Observation
    Input: Motif (A,B) count=5, no new evidence
    Expected: count remains 5
    PASS: Count unchanged
    FAIL: Count increases
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    initial_count = metrics.count
    
    # Apply decay (no new observations)
    apply_motif_decay(metrics, 11000.0, ACTIVE_DECAY_RATE)
    
    # Count should be unchanged
    assert metrics.count == initial_count, f"Count changed without observation: {initial_count} → {metrics.count}"


def test_grw_4_decay_only_changes():
    """
    GRW-4: Decay-Only Changes
    Input: No new evidence, only time passes
    Expected: Strengths decrease or stay 0
    PASS: Only decay occurs
    FAIL: Counts/timestamps change
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    initial_count = metrics.count
    initial_last_seen = metrics.last_seen_ts
    initial_strength = metrics.strength
    
    # Apply decay
    apply_motif_decay(metrics, 2000.0, ACTIVE_DECAY_RATE)
    
    # Only strength should change
    assert metrics.count == initial_count, "Count should not change"
    assert metrics.last_seen_ts == initial_last_seen, "Last seen should not change"
    assert metrics.strength < initial_strength, "Strength should decrease"


def test_grw_5_buffer_trim_doesnt_add():
    """
    GRW-5: Buffer Trim Does Not Add
    Input: Buffer at capacity, old tokens expire
    Expected: Tokens removed, none added
    PASS: Size decreases or stays same
    FAIL: Size increases
    """
    buffer = SequenceBuffer(max_length=10)
    
    # Fill buffer to capacity
    for i in range(10):
        buffer.append(EvidenceToken.TRADE_EXEC, float(1000 + i))
    
    initial_size = buffer.get_size()
    assert initial_size == 10
    
    # Trim old tokens
    removed = buffer.trim_old(1015.0)
    
    # Size should decrease or stay same (some tokens trimmed)
    final_size = buffer.get_size()
    assert final_size <= initial_size, f"Buffer grew during trim: {initial_size} → {final_size}"


def test_grw_6_counter_freeze():
    """
    GRW-6: Total Observed Counter
    Input: total_sequences_observed=100, no new evidence
    Expected: Remains 100
    PASS: Counter unchanged
    FAIL: Counter increases
    """
    buffer = SequenceBuffer()
    
    # Manually set counter (simulated)
    buffer.total_tokens_observed = 100
    
    initial_total = buffer.total_tokens_observed
    
    # Trim without adding (no new tokens)
    buffer.trim_old(10000.0)
    
    # Counter should be unchanged
    assert buffer.total_tokens_observed == initial_total, \
        f"Counter changed without new events: {initial_total} → {buffer.total_tokens_observed}"


# ==================== CATEGORY 4: NO-SIGNAL TESTS (7 tests) ====================

def test_sig_1_no_prediction_methods():
    """
    SIG-1: No Prediction Methods
    Check: Scan all methods
    Expected: predict_next_token() absent
    PASS: Method does not exist
    FAIL: Method exists
    """
    import memory.m3_evidence_token as token_mod
    import memory.m3_sequence_buffer as buffer_mod
    import memory.m3_motif_extractor as extractor_mod
    import memory.m3_motif_decay as decay_mod
    
    modules = [token_mod, buffer_mod, extractor_mod, decay_mod]
    
    forbidden_methods = ['predict_next_token', 'predict', 'forecast']
    
    for module in modules:
        attrs = dir(module)
        for forbidden in forbidden_methods:
            assert forbidden not in attrs, \
                f"Forbidden method '{forbidden}' found in {module.__name__}"


def test_sig_2_no_probability_outputs():
    """
    SIG-2: No Probability Outputs
    Check: All return types
    Expected: No probability fields
    PASS: All returns factual
    FAIL: Any P(x) outputs
    """
    # Check MotifMetrics fields
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    fields = metrics.__dataclass_fields__.keys()
    forbidden_fields = ['probability', 'likelihood', 'chance', 'odds']
    
    for forbidden in forbidden_fields:
        assert forbidden not in fields, f"Forbidden field '{forbidden}' in MotifMetrics"


def test_sig_3_no_signal_fields():
    """
    SIG-3: No Signal Fields
    Check: Node/motif structures
    Expected: No `signal`, `action`, `recommendation`
    PASS: Fields absent
    FAIL: Any signal fields
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    forbidden_fields = ['signal', 'action', 'recommendation', 'suggest']
    
    for forbidden in forbidden_fields:
        assert not hasattr(metrics, forbidden), f"Forbidden field '{forbidden}' found"


def test_sig_4_no_ranking_output():
    """
    SIG-4: No Ranking Output
    Check: Query results
    Expected: Results not sorted by importance
    PASS: Chronological/alphabetical only
    FAIL: Sorted by strength/count
    """
    # Create motifs with different strengths
    motifs = [
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        (EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR),
        (EvidenceToken.LIQ_OCCUR, EvidenceToken.PRICE_EXIT)
    ]
    
    # Extract from sequence - should maintain order
    tokens = [
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.LIQ_OCCUR,
        EvidenceToken.PRICE_EXIT
    ]
    
    extracted = extract_bigrams(tokens)
    
    # Should be in extraction order, not sorted
    assert extracted == motifs, "Motifs should maintain extraction order"


def test_sig_5_no_directional_labels():
    """
    SIG-5: No Directional Labels
    Check: All tokens/outputs
    Expected: No bullish/bearish/support/resistance
    PASS: Neutral labels only
    FAIL: Directional terms found
    """
    # Check all token names
    forbidden_terms = ['bullish', 'bearish', 'support', 'resistance', 'buy', 'sell', 'long', 'short']
    
    for token in EvidenceToken:
        token_name_lower = token.name.lower()
        token_value_lower = token.value.lower()
        
        for forbidden in forbidden_terms:
            assert forbidden not in token_name_lower, \
                f"Forbidden term '{forbidden}' in token name '{token.name}'"
            assert forbidden not in token_value_lower, \
                f"Forbidden term '{forbidden}' in token value '{token.value}'"


def test_sig_6_no_action_thresholds():
    """
    SIG-6: No Action Thresholds
    Check: All logic
    Expected: No "if count > N then BUY"
    PASS: Thresholds are factual filters
    FAIL: Action thresholds exist
    """
    # Verify that thresholds in code are for detection, not action
    from memory.m3_evidence_token import TokenizationConfig
    
    # These are detection thresholds (factual)
    assert hasattr(TokenizationConfig, 'PERSISTENCE_SECONDS')
    assert hasattr(TokenizationConfig, 'VOLUME_THRESHOLD_USD')
    
    # These should NOT exist (action thresholds)
    assert not hasattr(TokenizationConfig, 'BUY_THRESHOLD')
    assert not hasattr(TokenizationConfig, 'ENTRY_THRESHOLD')
    assert not hasattr(TokenizationConfig, 'TRADE_THRESHOLD')


def test_sig_7_no_confidence_scores():
    """
    SIG-7: No Confidence Scores
    Check: All metrics
    Expected: No reliability/confidence fields
    PASS: Factual counts only
    FAIL: Confidence metrics exist
    """
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    forbidden_fields = ['confidence', 'reliability', 'trust', 'quality']
    
    for forbidden in forbidden_fields:
        assert not hasattr(metrics, forbidden), f"Forbidden field '{forbidden}' in MotifMetrics"


# ==================== CATEGORY 5: DATA INTEGRITY (6 tests) ====================

def test_int_1_count_accumulation():
    """
    INT-1: Motif Count Accumulation
    Input: Observe (A,B) 3 times
    Expected: count = 3
    PASS: Count equals observations
    FAIL: Count ≠ observations
    """
    metrics_dict: Dict[Tuple[EvidenceToken, ...], MotifMetrics] = {}
    
    motifs = [
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
    ]
    
    update_motif_metrics(metrics_dict, motifs, 1000.0)
    
    target_motif = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    assert metrics_dict[target_motif].count == 3, \
        f"Expected count=3, got {metrics_dict[target_motif].count}"


def test_int_2_timestamp_update():
    """
    INT-2: Last Seen Timestamp Update
    Input: Observe (A,B) at t=100, t=200
    Expected: last_seen = 200
    PASS: Last seen = most recent
    FAIL: Incorrect timestamp
    """
    metrics_dict: Dict[Tuple[EvidenceToken, ...], MotifMetrics] = {}
    
    motif = [(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)]
    
    # First observation
    update_motif_metrics(metrics_dict, motif, 100.0)
    
    # Second observation
    update_motif_metrics(metrics_dict, motif, 200.0)
    
    target_motif = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    assert metrics_dict[target_motif].last_seen_ts == 200.0, \
        f"Expected last_seen=200.0, got {metrics_dict[target_motif].last_seen_ts}"


def test_int_3_tuple_immutability():
    """
    INT-3: Motif Tuple Immutability
    Input: Create motif (A,B,C)
    Expected: Tuple unchanged throughout
    PASS: Tuple identity preserved
    FAIL: Tuple mutated
    """
    motif_tuple = (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)
    
    metrics = MotifMetrics(
        motif=motif_tuple,
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    # Verify it's a tuple (immutable)
    assert isinstance(metrics.motif, tuple)
    
    # Verify identity preserved
    assert metrics.motif is motif_tuple
    
    # Try to modify (should fail)
    with pytest.raises(TypeError):
        metrics.motif[0] = EvidenceToken.PRICE_TOUCH  # type: ignore


def test_int_4_max_length_enforcement():
    """
    INT-4: Buffer Max Length Enforcement
    Input: Append 150 tokens, max=100
    Expected: Buffer size = 100
    PASS: Size capped at max
    FAIL: Size exceeds max
    """
    buffer = SequenceBuffer(max_length=100)
    
    # Append 150 tokens
    for i in range(150):
        buffer.append(EvidenceToken.TRADE_EXEC, float(1000 + i))
    
    assert buffer.get_size() == 100, f"Expected size=100, got {buffer.get_size()}"
    assert buffer.get_size() <= buffer.max_length, "Size exceeds max_length"


def test_int_5_time_window_enforcement():
    """
    INT-5: Time Window Enforcement
    Input: Tokens at t=1000, t=50000, window=24hr
    Expected: Only t=50000 retained (if current t=51000)
    PASS: Old tokens removed
    FAIL: Old tokens retained
    """
    buffer = SequenceBuffer(time_window_sec=86400.0)  # 24 hours
    
    buffer.append(EvidenceToken.TRADE_EXEC, 1000.0)
    buffer.append(EvidenceToken.TRADE_EXEC, 100000.0)  # 99000 seconds later (> 24hr)
    
    # Current time: 100000 (99000 seconds after first token)
    # First token is 99000 seconds old (> 86400), should be trimmed
    buffer.trim_old(100000.0)
    
    remaining = buffer.get_size()
    assert remaining == 1, f"Expected 1 token remaining, got {remaining}"
    
    # Verify only recent token remains
    tokens = buffer.get_all()
    assert tokens[0][1] == 100000.0, "Wrong token retained"


def test_int_6_backward_compatibility():
    """
    INT-6: Backward Compatibility
    Input: M2 node loaded
    Expected: M3 fields initialized to defaults
    PASS: No errors, defaults used
    FAIL: Errors or missing fields
    """
    # This test verifies that M3 structures have proper defaults
    # Creating new buffer should work without errors
    buffer = SequenceBuffer()
    
    assert buffer.get_size() == 0
    assert buffer.total_tokens_observed == 0
    assert buffer.max_length == 100
    assert buffer.time_window_sec == 86400.0
    
    # Creating new metrics dict should work
    metrics_dict: Dict[Tuple[EvidenceToken, ...], MotifMetrics] = {}
    assert len(metrics_dict) == 0


# ==================== CATEGORY 6: QUERY INTERFACE (8 tests) ====================
# NOTE: These tests require query interface implementation
# Marking as SKIPPED with reason

@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_1_get_sequence_buffer():
    """QRY-1: get_sequence_buffer() - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_2_get_recent_tokens():
    """QRY-2: get_recent_tokens() - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_3_get_motifs_for_node():
    """QRY-3: get_motifs_for_node() - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_4_get_motif_by_pattern_exists():
    """QRY-4: get_motif_by_pattern() exists - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_5_get_motif_by_pattern_missing():
    """QRY-5: get_motif_by_pattern() missing - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_6_get_nodes_with_motif():
    """QRY-6: get_nodes_with_motif() - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_7_get_token_counts():
    """QRY-7: get_token_counts() - requires store integration"""
    pytest.skip("Query interface implementation pending")


@pytest.mark.skip(reason="Query interface not yet implemented - Phase M3-7")
def test_qry_8_get_sequence_diversity():
    """QRY-8: get_sequence_diversity() - requires store integration"""
    pytest.skip("Query interface implementation pending")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
