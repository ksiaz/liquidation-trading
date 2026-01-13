"""
M4 Order Book Primitive Validation Tests

Tests that order book primitives compute correctly from node state.
Constitutional: Tests facts, not quality assessments.
"""

import pytest
import time
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m4_orderbook import (
    compute_resting_size,
    detect_order_consumption,
    detect_absorption_event,
    detect_refill_event,
    RestingSizeAtPrice,
    OrderConsumption,
    AbsorptionEvent,
    RefillEvent
)


def create_test_node(
    symbol: str = "BTCUSDT",
    price: float = 50000.0,
    resting_size_bid: float = 0.0,
    resting_size_ask: float = 0.0,
    previous_resting_size_bid: float = 0.0,
    previous_resting_size_ask: float = 0.0,
    last_orderbook_update_ts: float = None
) -> EnrichedLiquidityMemoryNode:
    """Create test node with order book state."""
    ts = last_orderbook_update_ts if last_orderbook_update_ts is not None else time.time()

    return EnrichedLiquidityMemoryNode(
        id=f"test_{symbol}_{price}",
        symbol=symbol,
        price_center=price,
        price_band=100.0,
        side="both",
        first_seen_ts=ts - 3600,
        last_interaction_ts=ts,
        strength=0.5,
        confidence=0.5,
        active=True,
        decay_rate=0.1,
        creation_reason="test",
        resting_size_bid=resting_size_bid,
        resting_size_ask=resting_size_ask,
        previous_resting_size_bid=previous_resting_size_bid,
        previous_resting_size_ask=previous_resting_size_ask,
        last_orderbook_update_ts=last_orderbook_update_ts
    )


# ============================================================================
# TEST SUITE 1: RestingSizeAtPrice
# ============================================================================

def test_resting_size_computed_when_orderbook_data_available():
    """Verify resting size computed when order book data exists."""
    node = create_test_node(
        resting_size_bid=100.0,
        resting_size_ask=80.0,
        last_orderbook_update_ts=time.time()
    )

    result = compute_resting_size(node)

    assert result is not None
    assert isinstance(result, RestingSizeAtPrice)
    assert result.price == 50000.0
    assert result.size_bid == 100.0
    assert result.size_ask == 80.0
    assert result.timestamp is not None


def test_resting_size_returns_none_without_orderbook_data():
    """No resting size if order book never updated."""
    node = create_test_node(
        resting_size_bid=100.0,
        resting_size_ask=80.0,
        last_orderbook_update_ts=None  # No OB data
    )

    result = compute_resting_size(node)

    assert result is None


# ============================================================================
# TEST SUITE 2: OrderConsumption Detection
# ============================================================================

def test_order_consumption_detected_on_size_decrease():
    """Verify consumption detected when current_size < previous_size."""
    node = create_test_node()

    consumption = detect_order_consumption(
        node,
        previous_size=100.0,
        current_size=80.0,
        duration=1.0
    )

    assert consumption is not None
    assert isinstance(consumption, OrderConsumption)
    assert consumption.consumed_size == 20.0
    assert consumption.initial_size == 100.0
    assert consumption.remaining_size == 80.0
    assert consumption.duration == 1.0


def test_no_consumption_when_size_unchanged():
    """No consumption if size stayed same."""
    node = create_test_node()

    result = detect_order_consumption(node, 100.0, 100.0, 1.0)

    assert result is None


def test_no_consumption_when_size_increased():
    """No consumption if size increased (that's a refill)."""
    node = create_test_node()

    result = detect_order_consumption(node, 100.0, 120.0, 1.0)

    assert result is None


def test_no_consumption_when_previous_size_zero():
    """No consumption if previous size was zero."""
    node = create_test_node()

    result = detect_order_consumption(node, 0.0, 0.0, 1.0)

    assert result is None


def test_consumption_full_depletion():
    """Consumption detected when size goes to zero."""
    node = create_test_node()

    consumption = detect_order_consumption(
        node,
        previous_size=100.0,
        current_size=0.0,
        duration=2.5
    )

    assert consumption is not None
    assert consumption.consumed_size == 100.0
    assert consumption.remaining_size == 0.0


# ============================================================================
# TEST SUITE 3: AbsorptionEvent Detection
# ============================================================================

def test_absorption_detected_with_stable_price():
    """Absorption detected when consumption + price stability."""
    node = create_test_node()

    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50049.0,  # 0.098% movement (< 1%)
        consumed_size=20.0,
        duration=1.0,
        trade_count=5
    )

    assert absorption is not None
    assert isinstance(absorption, AbsorptionEvent)
    assert absorption.consumed_size == 20.0
    assert absorption.duration == 1.0
    assert absorption.trade_count == 5


def test_no_absorption_when_price_moves_beyond_tolerance():
    """No absorption if price moved > tolerance."""
    node = create_test_node()

    # 1.2% movement (> 1% tolerance)
    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50600.0,
        consumed_size=20.0,
        duration=1.0,
        trade_count=5
    )

    assert absorption is None


def test_no_absorption_without_consumption():
    """No absorption if no size was consumed."""
    node = create_test_node()

    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50025.0,  # Stable price
        consumed_size=0.0,  # No consumption
        duration=1.0,
        trade_count=5
    )

    assert absorption is None


def test_absorption_exact_tolerance_boundary():
    """Absorption at exactly 1.0% movement is allowed (boundary inclusive)."""
    node = create_test_node()

    # Exactly 1.0% movement (at boundary, should pass)
    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50500.0,  # 1.0% movement
        consumed_size=20.0,
        duration=1.0,
        trade_count=5,
        price_tolerance=0.01
    )

    # Boundary is inclusive (movement <= tolerance passes)
    assert absorption is not None

    # Just beyond boundary should fail
    absorption_beyond = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50505.0,  # 1.01% movement
        consumed_size=20.0,
        duration=1.0,
        trade_count=5,
        price_tolerance=0.01
    )

    assert absorption_beyond is None


def test_absorption_with_custom_tolerance():
    """Absorption detection with custom price tolerance."""
    node = create_test_node()

    # 1.5% movement, but tolerance set to 2%
    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50750.0,  # 1.5% movement
        consumed_size=20.0,
        duration=1.0,
        trade_count=5,
        price_tolerance=0.02  # 2% tolerance
    )

    assert absorption is not None
    assert absorption.consumed_size == 20.0


def test_absorption_price_decrease():
    """Absorption works for both price increases and decreases."""
    node = create_test_node()

    # Price decreased 0.8%
    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=49600.0,  # 0.8% down
        consumed_size=20.0,
        duration=1.0,
        trade_count=5
    )

    assert absorption is not None


# ============================================================================
# TEST SUITE 4: RefillEvent Detection
# ============================================================================

def test_refill_detected_on_size_increase():
    """Refill detected when current_size > previous_size."""
    node = create_test_node()

    refill = detect_refill_event(
        node,
        previous_size=80.0,
        current_size=100.0,
        duration=1.0
    )

    assert refill is not None
    assert isinstance(refill, RefillEvent)
    assert refill.refill_size == 20.0
    assert refill.duration == 1.0


def test_no_refill_when_size_decreased():
    """No refill if size decreased (that's consumption)."""
    node = create_test_node()

    result = detect_refill_event(node, 100.0, 80.0, 1.0)

    assert result is None


def test_no_refill_when_size_unchanged():
    """No refill if size stayed same."""
    node = create_test_node()

    result = detect_refill_event(node, 100.0, 100.0, 1.0)

    assert result is None


def test_refill_from_zero():
    """Refill detected when size increases from zero."""
    node = create_test_node()

    refill = detect_refill_event(
        node,
        previous_size=0.0,
        current_size=100.0,
        duration=2.0
    )

    assert refill is not None
    assert refill.refill_size == 100.0


def test_refill_large_increase():
    """Refill detected for large size increases."""
    node = create_test_node()

    refill = detect_refill_event(
        node,
        previous_size=50.0,
        current_size=500.0,
        duration=3.5
    )

    assert refill is not None
    assert refill.refill_size == 450.0


# ============================================================================
# TEST SUITE 5: Edge Cases
# ============================================================================

def test_consumption_and_refill_mutually_exclusive():
    """Same delta cannot be both consumption and refill."""
    node = create_test_node()

    # Size decreased: should be consumption, not refill
    consumption = detect_order_consumption(node, 100.0, 80.0, 1.0)
    refill = detect_refill_event(node, 100.0, 80.0, 1.0)

    assert consumption is not None
    assert refill is None

    # Size increased: should be refill, not consumption
    consumption2 = detect_order_consumption(node, 80.0, 100.0, 1.0)
    refill2 = detect_refill_event(node, 80.0, 100.0, 1.0)

    assert consumption2 is None
    assert refill2 is not None


def test_zero_duration_allowed():
    """Zero duration is allowed (instantaneous detection)."""
    node = create_test_node()

    consumption = detect_order_consumption(node, 100.0, 80.0, 0.0)
    refill = detect_refill_event(node, 80.0, 100.0, 0.0)

    assert consumption is not None
    assert consumption.duration == 0.0
    assert refill is not None
    assert refill.duration == 0.0


def test_negative_consumed_size_impossible():
    """Consumed size is always positive (previous > current)."""
    node = create_test_node()

    consumption = detect_order_consumption(node, 80.0, 100.0, 1.0)

    # Should return None (size increased, not decreased)
    assert consumption is None


def test_very_small_price_movement():
    """Absorption detects very small price movements correctly."""
    node = create_test_node()

    # 0.001% movement (well within tolerance)
    absorption = detect_absorption_event(
        node,
        price_start=50000.0,
        price_end=50000.5,  # 0.001% movement
        consumed_size=20.0,
        duration=1.0,
        trade_count=5
    )

    assert absorption is not None


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
