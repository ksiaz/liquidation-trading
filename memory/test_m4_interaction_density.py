"""
M4 Interaction Density Views - Unit Tests

Tests for interaction density read model.
Validates determinism, prohibition compliance, and statistical correctness.
"""

import pytest
from dataclasses import dataclass
from typing import Optional
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


# Will be implemented in m4_interaction_density.py
@dataclass
class InteractionDensityView:
    """Read-only view of interaction density at a memory node."""
    node_id: str
    interactions_per_hour: float
    median_gap_sec: float
    min_gap_sec: float
    max_gap_sec: float
    gap_stddev_sec: float
    burstiness_coefficient: float
    longest_active_period_sec: float
    longest_idle_period_sec: float
    total_interaction_count: int
    observation_duration_sec: float


def create_test_node_with_interactions(
    node_id: str = "test_node",
    timestamps: list = None
) -> EnrichedLiquidityMemoryNode:
    """Create a test node with interaction timestamps."""
    if timestamps is None:
        # Default: 10 interactions over 1 hour
        timestamps = [1000.0 + i * 360.0 for i in range(10)]
    
    node = EnrichedLiquidityMemoryNode(
        id=node_id,
        price_center=100.0,
        price_band=0.1,
        side="both",
        first_seen_ts=timestamps[0] if timestamps else 1000.0,
        last_interaction_ts=timestamps[-1] if timestamps else 1000.0,
        strength=0.8,
        confidence=0.7,
        active=True,
        decay_rate=0.0001,
        creation_reason="test"
    )
    
    node.interaction_count = len(timestamps)
    
    # Populate interaction_timestamps deque
    from collections import deque
    node.interaction_timestamps = deque(timestamps, maxlen=50)
    
    return node


# ==================== DETERMINISM TESTS ====================

def test_det_1_identical_input_identical_output():
    """DET-1: Same input → identical output."""
    from memory.m4_interaction_density import get_interaction_density
    
    timestamps = [1000.0, 1100.0, 1250.0, 1400.0, 1700.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    current_ts = 2000.0
    
    result1 = get_interaction_density(node, current_ts)
    result2 = get_interaction_density(node, current_ts)
    
    assert result1 == result2
    assert result1.interactions_per_hour == result2.interactions_per_hour
    assert result1.median_gap_sec == result2.median_gap_sec


def test_det_3_timestamp_reference_consistency():
    """DET-3: Same current_ts produces identical results."""
    from memory.m4_interaction_density import get_interaction_density
    
    node = create_test_node_with_interactions()
    current_ts = 5000.0
    
    # Call multiple times with same current_ts
    results = [get_interaction_density(node, current_ts) for _ in range(5)]
    
    for i in range(1, len(results)):
        assert results[i] == results[0]


# ==================== NO-GROWTH-WITHOUT-CHANGE TESTS ====================

def test_ngc_2_memory_immutability():
    """NGC-2: Query does not modify M2 fields."""
    from memory.m4_interaction_density import get_interaction_density
    
    node = create_test_node_with_interactions()
    current_ts = 5000.0
    
    # Capture state
    timestamps_before = list(node.interaction_timestamps)
    interaction_count_before = node.interaction_count
    
    # Query
    get_interaction_density(node, current_ts)
    
    # Assert unchanged
    assert list(node.interaction_timestamps) == timestamps_before
    assert node.interaction_count == interaction_count_before


# ==================== PROHIBITION COMPLIANCE TESTS ====================

def test_pro_2_no_importance_fields():
    """PRO-2: No importance/ranking fields in output."""
    from memory.m4_interaction_density import get_interaction_density
    
    node = create_test_node_with_interactions()
    result = get_interaction_density(node, 5000.0)
    
    # Check no forbidden fields
    result_dict = result.__dict__
    forbidden = ['importance', 'priority', 'rank', 'score', 'quality',
                 'strength', 'density_score', 'activity_rating']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


def test_pro_6_no_action_recommendation():
    """PRO-6: No action recommendation fields."""
    from memory.m4_interaction_density import get_interaction_density
    
    node = create_test_node_with_interactions()
    result = get_interaction_density(node, 5000.0)
    
    # Check no action-oriented fields
    result_dict = result.__dict__
    forbidden = ['should_trade', 'entry_opportunity', 'activity_signal',
                 'hot_zone', 'optimal_timing']
    
    for field in forbidden:
        assert field not in result_dict, f"Forbidden field '{field}' found"


# ==================== EQUIVALENCE TESTS ====================

def test_eqv_3_statistical_accuracy_median():
    """EQV-3: Median calculation matches standard method."""
    from memory.m4_interaction_density import get_interaction_density
    import statistics
    
    timestamps = [1000.0, 1100.0, 1250.0, 1400.0, 1700.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 2000.0)
    
    # Calculate gaps manually
    gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
    expected_median = statistics.median(gaps)
    
    assert abs(result.median_gap_sec - expected_median) < 0.001


def test_eqv_3_statistical_accuracy_stddev():
    """EQV-3: Stddev calculation matches standard method."""
    from memory.m4_interaction_density import get_interaction_density
    import statistics
    
    timestamps = [1000.0, 1100.0, 1250.0, 1400.0, 1700.0, 1900.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 2000.0)
    
    # Calculate stddev manually
    gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
    expected_stddev = statistics.stdev(gaps)
    
    assert abs(result.gap_stddev_sec - expected_stddev) < 0.001


def test_eqv_interactions_per_hour_accuracy():
    """Interactions per hour calculated correctly."""
    from memory.m4_interaction_density import get_interaction_density
    
    # 10 interactions over 3600 seconds = 10 per hour
    timestamps = [1000.0 + i * 360.0 for i in range(10)]
    node = create_test_node_with_interactions(timestamps=timestamps)
    current_ts = timestamps[-1]
    
    result = get_interaction_density(node, current_ts)
    
    duration_hours = (timestamps[-1] - timestamps[0]) / 3600.0
    expected_rate = 10 / duration_hours if duration_hours > 0 else 0.0
    
    assert abs(result.interactions_per_hour - expected_rate) < 0.01


# ==================== EDGE CASE TESTS ====================

def test_edg_2_single_interaction():
    """EDG-2: Handle single interaction gracefully."""
    from memory.m4_interaction_density import get_interaction_density
    
    timestamps = [1000.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 2000.0)
    
    # Should handle single point gracefully
    assert result.median_gap_sec == 0.0 or result.median_gap_sec is None or result.median_gap_sec == result.median_gap_sec  # Not NaN
    assert result.total_interaction_count == 1


def test_edg_zero_duration():
    """Handle zero observation duration."""
    from memory.m4_interaction_density import get_interaction_density
    
    # All interactions at same timestamp
    timestamps = [1000.0, 1000.0, 1000.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 1000.0)
    
    # Should not crash, return valid (possibly zero/special) values
    assert result is not None
    assert result.observation_duration_sec >= 0.0


def test_edg_uniform_spacing():
    """Handle perfectly uniform spacing."""
    from memory.m4_interaction_density import get_interaction_density
    
    # Perfectly uniform: 100 second gaps
    timestamps = [1000.0 + i * 100.0 for i in range(10)]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 2000.0)
    
    # Uniform spacing should have stddev ≈ 0
    assert result.gap_stddev_sec < 0.001
    # All gaps should be 100
    assert abs(result.median_gap_sec - 100.0) < 0.001


# ==================== FUNCTIONAL CORRECTNESS TESTS ====================

def test_burstiness_coefficient_range():
    """Burstiness coefficient should be in valid range."""
    from memory.m4_interaction_density import get_interaction_density
    
    timestamps = [1000.0, 1010.0, 1020.0, 1500.0, 1510.0, 1520.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    result = get_interaction_density(node, 2000.0)
    
    # Burstiness coefficient typically in [-1, 1] range
    assert -1.5 <= result.burstiness_coefficient <= 1.5


def test_time_range_filtering():
    """Time range filtering works correctly."""
    from memory.m4_interaction_density import get_interaction_density_in_time_range
    
    timestamps = [1000.0, 1100.0, 1200.0, 1300.0, 1400.0]
    node = create_test_node_with_interactions(timestamps=timestamps)
    
    # Filter to middle 3 interactions
    result = get_interaction_density_in_time_range(node, 1050.0, 1350.0)
    
    # Should only include 1100, 1200, 1300
    # Gaps: 100, 100
    assert abs(result.median_gap_sec - 100.0) < 0.001


def test_complete_output_schema():
    """Verify all required fields present."""
    from memory.m4_interaction_density import get_interaction_density
    
    node = create_test_node_with_interactions()
    result = get_interaction_density(node, 5000.0)
    
    required_fields = [
        'node_id', 'interactions_per_hour', 'median_gap_sec',
        'min_gap_sec', 'max_gap_sec', 'gap_stddev_sec',
        'burstiness_coefficient', 'longest_active_period_sec',
        'longest_idle_period_sec', 'total_interaction_count',
        'observation_duration_sec'
    ]
    
    for field in required_fields:
        assert hasattr(result, field), f"Missing required field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
