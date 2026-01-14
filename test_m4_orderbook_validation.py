"""
M4 Order Book Primitive Validation Tests

Tests that order book primitives compute correctly from raw parameters.
Constitutional: Tests facts, not quality assessments.
"""

import pytest
import time
from memory.m4_orderbook_primitives import (
    compute_resting_size,
    detect_order_consumption,
    detect_absorption_event,
    detect_refill_event,
    RestingSizeAtPrice,
    OrderConsumption,
    AbsorptionEvent,
    RefillEvent
)


# ============================================================================
# TEST SUITE 1: RestingSizeAtPrice
# ============================================================================

def test_resting_size_computed_when_orderbook_data_available():
    """Verify resting size computed when order book data exists."""
    ts = time.time()

    result = compute_resting_size(
        bid_size=100.0,
        ask_size=80.0,
        best_bid_price=50000.0,
        best_ask_price=50010.0,
        timestamp=ts
    )

    assert result is not None
    assert isinstance(result, RestingSizeAtPrice)
    assert result.bid_size == 100.0
    assert result.ask_size == 80.0
    assert result.best_bid_price == 50000.0
    assert result.best_ask_price == 50010.0
    assert result.timestamp == ts


def test_resting_size_allows_zero_sizes():
    """Resting size allows zero bid or ask."""
    ts = time.time()

    result = compute_resting_size(
        bid_size=0.0,
        ask_size=0.0,
        best_bid_price=None,
        best_ask_price=None,
        timestamp=ts
    )

    assert result is not None
    assert result.bid_size == 0.0
    assert result.ask_size == 0.0
    assert result.best_bid_price is None
    assert result.best_ask_price is None


def test_resting_size_rejects_negative_sizes():
    """Resting size rejects negative sizes."""
    ts = time.time()

    with pytest.raises(ValueError, match="non-negative"):
        compute_resting_size(
            bid_size=-10.0,
            ask_size=80.0,
            best_bid_price=50000.0,
            best_ask_price=50010.0,
            timestamp=ts
        )


# ============================================================================
# TEST SUITE 2: OrderConsumption Detection
# ============================================================================

def test_order_consumption_detected_on_size_decrease():
    """Verify consumption detected when current_size < previous_size."""
    ts = time.time()

    consumption = detect_order_consumption(
        previous_size=100.0,
        current_size=80.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert consumption is not None
    assert isinstance(consumption, OrderConsumption)
    assert consumption.consumed_size == 20.0
    assert consumption.side == "bid"
    assert consumption.price_level == 50000.0
    assert consumption.timestamp == ts


def test_no_consumption_when_size_unchanged():
    """No consumption if size stayed same."""
    ts = time.time()

    result = detect_order_consumption(
        previous_size=100.0,
        current_size=100.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert result is None


def test_no_consumption_when_size_increased():
    """No consumption if size increased (that's a refill)."""
    ts = time.time()

    result = detect_order_consumption(
        previous_size=100.0,
        current_size=120.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert result is None


def test_no_consumption_when_previous_size_zero():
    """No consumption if previous size was zero."""
    ts = time.time()

    result = detect_order_consumption(
        previous_size=0.0,
        current_size=0.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert result is None


def test_consumption_full_depletion():
    """Consumption detected when size goes to zero."""
    ts = time.time()

    consumption = detect_order_consumption(
        previous_size=100.0,
        current_size=0.0,
        side="ask",
        price_level=50010.0,
        timestamp=ts
    )

    assert consumption is not None
    assert consumption.consumed_size == 100.0
    assert consumption.side == "ask"


def test_consumption_with_threshold():
    """Consumption respects minimum threshold."""
    ts = time.time()

    # Small change below threshold
    result = detect_order_consumption(
        previous_size=100.0,
        current_size=99.9,
        side="bid",
        price_level=50000.0,
        timestamp=ts,
        min_consumption_threshold=0.5
    )

    assert result is None  # 0.1 < 0.5 threshold

    # Larger change above threshold
    consumption = detect_order_consumption(
        previous_size=100.0,
        current_size=99.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts,
        min_consumption_threshold=0.5
    )

    assert consumption is not None
    assert consumption.consumed_size == 1.0


def test_consumption_validates_side():
    """Consumption validates side parameter."""
    ts = time.time()

    with pytest.raises(ValueError, match="Side must be"):
        detect_order_consumption(
            previous_size=100.0,
            current_size=80.0,
            side="invalid",
            price_level=50000.0,
            timestamp=ts
        )


def test_consumption_validates_sizes():
    """Consumption validates non-negative sizes."""
    ts = time.time()

    with pytest.raises(ValueError, match="non-negative"):
        detect_order_consumption(
            previous_size=-10.0,
            current_size=80.0,
            side="bid",
            price_level=50000.0,
            timestamp=ts
        )


# ============================================================================
# TEST SUITE 3: AbsorptionEvent Detection
# ============================================================================

def test_absorption_detected_with_stable_price():
    """Absorption detected when consumption + price stability."""
    ts = time.time()

    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50049.0,  # 0.098% movement (< 1%)
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption is not None
    assert isinstance(absorption, AbsorptionEvent)
    assert absorption.consumed_size == 20.0
    assert absorption.price_movement_pct < 1.0
    assert absorption.side == "bid"
    assert absorption.timestamp == ts


def test_no_absorption_when_price_moves_beyond_tolerance():
    """No absorption if price moved > tolerance."""
    ts = time.time()

    # 1.2% movement (> 1% tolerance)
    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50600.0,
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption is None


def test_no_absorption_without_consumption():
    """No absorption if no size was consumed."""
    ts = time.time()

    absorption = detect_absorption_event(
        consumed_size=0.0,  # No consumption
        price_before=50000.0,
        price_after=50025.0,  # Stable price
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption is None


def test_absorption_exact_tolerance_boundary():
    """Absorption at exactly 1.0% movement is allowed (boundary inclusive)."""
    ts = time.time()

    # Exactly 1.0% movement (at boundary, should pass)
    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50500.0,  # 1.0% movement
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    # Boundary is inclusive (movement <= tolerance passes)
    assert absorption is not None

    # Just beyond boundary should fail
    absorption_beyond = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50505.0,  # 1.01% movement
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption_beyond is None


def test_absorption_with_custom_tolerance():
    """Absorption detection with custom price tolerance."""
    ts = time.time()

    # 1.5% movement, but tolerance set to 2%
    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50750.0,  # 1.5% movement
        side="ask",
        timestamp=ts,
        max_price_movement_pct=2.0  # 2% tolerance
    )

    assert absorption is not None
    assert absorption.consumed_size == 20.0


def test_absorption_price_decrease():
    """Absorption works for both price increases and decreases."""
    ts = time.time()

    # Price decreased 0.8%
    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=49600.0,  # 0.8% down
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption is not None


def test_absorption_validates_side():
    """Absorption validates side parameter."""
    ts = time.time()

    with pytest.raises(ValueError, match="Side must be"):
        detect_absorption_event(
            consumed_size=20.0,
            price_before=50000.0,
            price_after=50025.0,
            side="invalid",
            timestamp=ts
        )


def test_absorption_validates_prices():
    """Absorption validates positive prices."""
    ts = time.time()

    with pytest.raises(ValueError, match="must be positive"):
        detect_absorption_event(
            consumed_size=20.0,
            price_before=-50000.0,
            price_after=50025.0,
            side="bid",
            timestamp=ts
        )


# ============================================================================
# TEST SUITE 4: RefillEvent Detection
# ============================================================================

def test_refill_detected_on_size_increase():
    """Refill detected when current_size > previous_size."""
    ts = time.time()

    refill = detect_refill_event(
        previous_size=80.0,
        current_size=100.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert refill is not None
    assert isinstance(refill, RefillEvent)
    assert refill.added_size == 20.0
    assert refill.side == "bid"
    assert refill.price_level == 50000.0
    assert refill.timestamp == ts


def test_no_refill_when_size_decreased():
    """No refill if size decreased (that's consumption)."""
    ts = time.time()

    result = detect_refill_event(
        previous_size=100.0,
        current_size=80.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert result is None


def test_no_refill_when_size_unchanged():
    """No refill if size stayed same."""
    ts = time.time()

    result = detect_refill_event(
        previous_size=100.0,
        current_size=100.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert result is None


def test_refill_from_zero():
    """Refill detected when size increases from zero."""
    ts = time.time()

    refill = detect_refill_event(
        previous_size=0.0,
        current_size=100.0,
        side="ask",
        price_level=50010.0,
        timestamp=ts
    )

    assert refill is not None
    assert refill.added_size == 100.0


def test_refill_large_increase():
    """Refill detected for large size increases."""
    ts = time.time()

    refill = detect_refill_event(
        previous_size=50.0,
        current_size=500.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert refill is not None
    assert refill.added_size == 450.0


def test_refill_with_threshold():
    """Refill respects minimum threshold."""
    ts = time.time()

    # Small change below threshold
    result = detect_refill_event(
        previous_size=100.0,
        current_size=100.1,
        side="bid",
        price_level=50000.0,
        timestamp=ts,
        min_refill_threshold=0.5
    )

    assert result is None  # 0.1 < 0.5 threshold

    # Larger change above threshold
    refill = detect_refill_event(
        previous_size=100.0,
        current_size=101.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts,
        min_refill_threshold=0.5
    )

    assert refill is not None
    assert refill.added_size == 1.0


def test_refill_validates_side():
    """Refill validates side parameter."""
    ts = time.time()

    with pytest.raises(ValueError, match="Side must be"):
        detect_refill_event(
            previous_size=80.0,
            current_size=100.0,
            side="invalid",
            price_level=50000.0,
            timestamp=ts
        )


def test_refill_validates_sizes():
    """Refill validates non-negative sizes."""
    ts = time.time()

    with pytest.raises(ValueError, match="non-negative"):
        detect_refill_event(
            previous_size=-10.0,
            current_size=100.0,
            side="bid",
            price_level=50000.0,
            timestamp=ts
        )


# ============================================================================
# TEST SUITE 5: Edge Cases
# ============================================================================

def test_consumption_and_refill_mutually_exclusive():
    """Same delta cannot be both consumption and refill."""
    ts = time.time()

    # Size decreased: should be consumption, not refill
    consumption = detect_order_consumption(
        previous_size=100.0,
        current_size=80.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )
    refill = detect_refill_event(
        previous_size=100.0,
        current_size=80.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert consumption is not None
    assert refill is None

    # Size increased: should be refill, not consumption
    consumption2 = detect_order_consumption(
        previous_size=80.0,
        current_size=100.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )
    refill2 = detect_refill_event(
        previous_size=80.0,
        current_size=100.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    assert consumption2 is None
    assert refill2 is not None


def test_very_small_price_movement():
    """Absorption detects very small price movements correctly."""
    ts = time.time()

    # 0.001% movement (well within tolerance)
    absorption = detect_absorption_event(
        consumed_size=20.0,
        price_before=50000.0,
        price_after=50000.5,  # 0.001% movement
        side="bid",
        timestamp=ts,
        max_price_movement_pct=1.0
    )

    assert absorption is not None


def test_negative_consumed_size_returns_none():
    """Negative consumed size returns None (not an absorption)."""
    ts = time.time()

    result = detect_absorption_event(
        consumed_size=-10.0,
        price_before=50000.0,
        price_after=50025.0,
        side="bid",
        timestamp=ts
    )

    assert result is None


def test_bid_and_ask_sides_distinct():
    """Bid and ask sides are treated distinctly."""
    ts = time.time()

    consumption_bid = detect_order_consumption(
        previous_size=100.0,
        current_size=80.0,
        side="bid",
        price_level=50000.0,
        timestamp=ts
    )

    consumption_ask = detect_order_consumption(
        previous_size=100.0,
        current_size=80.0,
        side="ask",
        price_level=50010.0,
        timestamp=ts
    )

    assert consumption_bid.side == "bid"
    assert consumption_ask.side == "ask"
    assert consumption_bid.price_level != consumption_ask.price_level


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
