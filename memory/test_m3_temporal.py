"""
M3 Temporal Evidence Ordering - Unit Tests

Tests for evidence tokenization, sequence buffering, motif extraction, and decay logic.
Validates prohibition compliance (no prediction, no signals).
"""

import pytest
import time
from collections import deque
from memory.m3_evidence_token import (
    EvidenceToken,
    tokenize_orderbook_event,
    tokenize_trade_event,
    tokenize_liquidation_event,
    tokenize_price_event
)
from memory.m3_sequence_buffer import SequenceBuffer, create_sequence_buffer
from memory.m3_motif_extractor import (
    extract_bigrams,
    extract_trigrams,
    extract_all_motifs,
    count_motifs,
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


# ==================== EVIDENCE TOKEN TESTS ====================

def test_evidence_token_enum_completeness():
    """Test that EvidenceToken enum has exactly 10 tokens."""
    assert len(EvidenceToken) == 10
    
    # Verify all expected tokens exist
    expected_tokens = {
        'OB_APPEAR', 'OB_PERSIST', 'OB_VANISH',
        'TRADE_EXEC', 'TRADE_VOLUME_HIGH',
        'LIQ_OCCUR', 'LIQ_CASCADE',
        'PRICE_TOUCH', 'PRICE_EXIT', 'PRICE_DWELL'
    }
    actual_tokens = {token.name for token in EvidenceToken}
    assert actual_tokens == expected_tokens


def test_orderbook_tokenization():
    """Test orderbook event tokenization."""
    # Level appears
    token = tokenize_orderbook_event("appear", True, False)
    assert token == EvidenceToken.OB_APPEAR
    
    # Level vanishes
    token = tokenize_orderbook_event("vanish", False, True)
    assert token == EvidenceToken.OB_VANISH
    
    # Level persists
    token = tokenize_orderbook_event("persist", True, True, persistence_duration=35.0)
    assert token == EvidenceToken.OB_PERSIST
    
    # Level persists but not long enough
    token = tokenize_orderbook_event("persist", True, True, persistence_duration=10.0)
    assert token is None


def test_trade_tokenization():
    """Test trade event tokenization."""
    # Regular trade
    token = tokenize_trade_event(10000.0, True)
    assert token == EvidenceToken.TRADE_EXEC
    
    # High volume trade
    token = tokenize_trade_event(60000.0, True)
    assert token == EvidenceToken.TRADE_VOLUME_HIGH
    
    # Trade outside node band
    token = tokenize_trade_event(60000.0, False)
    assert token is None


def test_liquidation_tokenization():
    """Test liquidation event tokenization."""
    # Single liquidation
    token = tokenize_liquidation_event(5.0, 1, 10.0)
    assert token == EvidenceToken.LIQ_OCCUR
    
    # Liquidation cascade
    token = tokenize_liquidation_event(5.0, 5, 3.0)
    assert token == EvidenceToken.LIQ_CASCADE
    
    # Liquidation too far from node
    token = tokenize_liquidation_event(15.0, 1, 10.0)
    assert token is None


def test_price_tokenization():
    """Test price event tokenization."""
    # Price touch
    token = tokenize_price_event(True, False)
    assert token == EvidenceToken.PRICE_TOUCH
    
    # Price exit
    token = tokenize_price_event(False, True)
    assert token == EvidenceToken.PRICE_EXIT
    
    # Price dwell
    token = tokenize_price_event(True, True, dwell_duration=70.0)
    assert token == EvidenceToken.PRICE_DWELL
    
    # Price dwell but not long enough
    token = tokenize_price_event(True, True, dwell_duration=30.0)
    assert token is None


# ==================== SEQUENCE BUFFER TESTS ====================

def test_sequence_buffer_append():
    """Test appending tokens to buffer."""
    buffer = SequenceBuffer()
    
    buffer.append(EvidenceToken.OB_APPEAR, 1000.0)
    buffer.append(EvidenceToken.TRADE_EXEC, 1005.0)
    
    assert buffer.get_size() == 2
    assert buffer.total_tokens_observed == 2
    
    tokens = buffer.get_all()
    assert len(tokens) == 2
    assert tokens[0] == (EvidenceToken.OB_APPEAR, 1000.0)
    assert tokens[1] == (EvidenceToken.TRADE_EXEC, 1005.0)


def test_sequence_buffer_max_length():
    """Test that buffer enforces max length."""
    buffer = SequenceBuffer(max_length=5)
    
    # Append 10 tokens
    for i in range(10):
        buffer.append(EvidenceToken.TRADE_EXEC, float(i))
    
    # Should only have 5 most recent
    assert buffer.get_size() == 5
    assert buffer.total_tokens_observed == 10
    
    # Oldest should be token 5
    oldest_ts = buffer.get_oldest_timestamp()
    assert oldest_ts == 5.0


def test_sequence_buffer_time_window():
    """Test that buffer trims by time window."""
    buffer = SequenceBuffer(time_window_sec=100.0)
    
    buffer.append(EvidenceToken.TRADE_EXEC, 1000.0)
    buffer.append(EvidenceToken.TRADE_EXEC, 1050.0)
    buffer.append(EvidenceToken.TRADE_EXEC, 1120.0)
    
    # Trim with cutoff at 1120 - older than 100s should be removed
    buffer.trim_old(1120.0)
    
    # Only tokens at 1050 and 1120 should remain
    assert buffer.get_size() == 2
    oldest_ts = buffer.get_oldest_timestamp()
    assert oldest_ts >= 1020.0


def test_sequence_buffer_get_recent():
    """Test getting N most recent tokens."""
    buffer = SequenceBuffer()
    
    for i in range(10):
        buffer.append(EvidenceToken.TRADE_EXEC, float(i))
    
    recent = buffer.get_recent(3)
    assert len(recent) == 3
    assert recent[0][1] == 7.0
    assert recent[1][1] == 8.0
    assert recent[2][1] == 9.0


# ==================== MOTIF EXTRACTION TESTS ====================

def test_extract_bigrams():
    """Test bigram extraction from token sequence."""
    tokens = [
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.LIQ_OCCUR
    ]
    
    bigrams = extract_bigrams(tokens)
    
    assert len(bigrams) == 3
    assert bigrams[0] == (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)
    assert bigrams[1] == (EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_EXEC)
    assert bigrams[2] == (EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)


def test_extract_trigrams():
    """Test trigram extraction from token sequence."""
    tokens = [
        EvidenceToken.OB_APPEAR,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.TRADE_EXEC,
        EvidenceToken.LIQ_OCCUR
    ]
    
    trigrams = extract_trigrams(tokens)
    
    assert len(trigrams) == 2
    assert trigrams[0] == (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_EXEC)
    assert trigrams[1] == (EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)


def test_motif_extraction_overlap():
    """Test that motif extraction captures overlapping windows."""
    tokens = [EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_EXEC]
    
    bigrams = extract_bigrams(tokens)
    
    # Should have 2 bigrams, both (TRADE_EXEC, TRADE_EXEC)
    assert len(bigrams) == 2
    assert bigrams[0] == bigrams[1]


def test_count_motifs():
    """Test motif counting with duplicates."""
    motifs = [
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        (EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR),
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),  # Duplicate
    ]
    
    counts = count_motifs(motifs)
    
    assert len(counts) == 2
    assert counts[(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)] == 2
    assert counts[(EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)] == 1


def test_update_motif_metrics_new():
    """Test creating new motif metrics."""
    metrics = {}
    new_motifs = [
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        (EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR),
    ]
    
    update_motif_metrics(metrics, new_motifs, 1000.0)
    
    assert len(metrics) == 2
    assert metrics[(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)].count == 1
    assert metrics[(EvidenceToken.TRADE_EXEC, EvidenceToken.LIQ_OCCUR)].count == 1


def test_update_motif_metrics_existing():
    """Test updating existing motif metrics."""
    # Create initial metrics
    metrics = {
        (EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC): MotifMetrics(
            motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
            count=5,
            last_seen_ts=1000.0,
            strength=0.5
        )
    }
    
    # Observe same motif again
    new_motifs = [(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)]
    
    update_motif_metrics(metrics, new_motifs, 1100.0)
    
    # Count should increment
    assert metrics[(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)].count == 6
    # Timestamp should update
    assert metrics[(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC)].last_seen_ts == 1100.0


# ==================== MOTIF DECAY TESTS ====================

def test_motif_decay_active_rate():
    """Test motif decay at ACTIVE rate."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=1.0
    )
    
    # Apply decay for 1000 seconds at active rate
    apply_motif_decay(metrics, 2000.0, ACTIVE_DECAY_RATE)
    
    # Expected: strength = 1.0 * (1 - 0.0001 * 1000) = 0.9
    assert abs(metrics.strength - 0.9) < 0.001


def test_motif_decay_dormant_rate():
    """Test motif decay at DORMANT rate (10× slower)."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=1.0
    )
    
    # Apply decay for 1000 seconds at dormant rate
    apply_motif_decay(metrics, 2000.0, DORMANT_DECAY_RATE)
    
    # Expected: strength = 1.0 * (1 - 0.00001 * 1000) = 0.99
    assert abs(metrics.strength - 0.99) < 0.001


def test_motif_decay_archived_freeze():
    """Test that archived motifs don't decay."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    # Apply "decay" for 10000 seconds at archived rate (0)
    apply_motif_decay(metrics, 11000.0, ARCHIVED_DECAY_RATE)
    
    # Strength should be unchanged
    assert metrics.strength == 0.5


def test_motif_decay_floor_at_zero():
    """Test that motif strength floors at 0.0."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=1,
        last_seen_ts=1000.0,
        strength=0.01
    )
    
    # Apply decay for long time to drive negative
    apply_motif_decay(metrics, 1000000.0, ACTIVE_DECAY_RATE)
    
    # Strength should floor at 0.0
    assert metrics.strength == 0.0


def test_get_decay_rate_for_node_state():
    """Test decay rate lookup by node state."""
    assert get_decay_rate_for_node_state("ACTIVE") == ACTIVE_DECAY_RATE
    assert get_decay_rate_for_node_state("DORMANT") == DORMANT_DECAY_RATE
    assert get_decay_rate_for_node_state("ARCHIVED") == ARCHIVED_DECAY_RATE


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_no_prediction_methods():
    """Test that no prediction methods exist."""
    # Import all M3 modules
    import memory.m3_evidence_token as token_module
    import memory.m3_sequence_buffer as buffer_module
    import memory.m3_motif_extractor as extractor_module
    import memory.m3_motif_decay as decay_module
    
    # Check that no forbidden method names exist
    forbidden_names = [
        'predict', 'forecast', 'recommend', 'suggest',
        'probability', 'likelihood', 'confidence',
        'rank', 'score', 'importance', 'reliability'
    ]
    
    modules = [token_module, buffer_module, extractor_module, decay_module]
    
    for module in modules:
        module_attrs = dir(module)
        for attr in module_attrs:
            attr_lower = attr.lower()
            for forbidden in forbidden_names:
                assert forbidden not in attr_lower, f"Forbidden method name '{attr}' found in {module.__name__}"


def test_sequence_buffer_no_auto_sorting():
    """Test that sequence buffer doesn't auto-sort by timestamp."""
    buffer = SequenceBuffer()
    
    # Append tokens out of timestamp order
    buffer.append(EvidenceToken.TRADE_EXEC, 1005.0)
    buffer.append(EvidenceToken.OB_APPEAR, 1000.0)  # Earlier timestamp
    buffer.append(EvidenceToken.LIQ_OCCUR, 1010.0)
    
    tokens = buffer.get_all()
    
    # Should maintain append order, NOT sorted by timestamp
    assert tokens[0][1] == 1005.0
    assert tokens[1][1] == 1000.0
    assert tokens[2][1] == 1010.0


def test_motif_metrics_factual_only():
    """Test that MotifMetrics contains only factual fields."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    # Check field types
    assert isinstance(metrics.motif, tuple)
    assert isinstance(metrics.count, int)
    assert isinstance(metrics.last_seen_ts, float)
    assert isinstance(metrics.strength, float)
    
    # Check that no forbidden fields exist
    forbidden_fields = ['probability', 'confidence', 'importance', 'reliability', 'rank', 'score']
    for field in forbidden_fields:
        assert not hasattr(metrics, field), f"Forbidden field '{field}' found in MotifMetrics"


# ==================== DATA INTEGRITY TESTS ====================

def test_token_immutability():
    """Test that evidence tokens are immutable."""
    token = EvidenceToken.TRADE_EXEC
    
    # Tokens should be enum members (immutable)
    assert isinstance(token, EvidenceToken)
    
    # Attempting to modify should fail
    with pytest.raises(AttributeError):
        token.value = "modified"  # type: ignore


def test_sequence_buffer_total_observed_never_decreases():
    """Test that total_tokens_observed is cumulative."""
    buffer = SequenceBuffer(max_length=3)
    
    for i in range(10):
        buffer.append(EvidenceToken.TRADE_EXEC, float(i))
    
    # Buffer size is 3, but total observed should be 10
    assert buffer.get_size() == 3
    assert buffer.total_tokens_observed == 10
    
    # Clear buffer
    buffer.clear()
    
    # Total observed should still be 10
    assert buffer.total_tokens_observed == 10


def test_motif_count_never_decreases():
    """Test that motif counts are cumulative."""
    metrics = MotifMetrics(
        motif=(EvidenceToken.OB_APPEAR, EvidenceToken.TRADE_EXEC),
        count=5,
        last_seen_ts=1000.0,
        strength=0.5
    )
    
    initial_count = metrics.count
    
    # Apply decay (should only affect strength, not count)
    apply_motif_decay(metrics, 2000.0, ACTIVE_DECAY_RATE)
    
    # Count should be unchanged
    assert metrics.count == initial_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
