"""
M4 Order Book Primitives - Tier B Phase B-2.1

Order book state primitives for validation.

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Optional


# ==============================================================================
# B2.1.1: Resting Size At Price
# ==============================================================================

@dataclass(frozen=True)
class RestingSizeAtPrice:
    """
    Observed resting order book size at bid and ask levels.

    Records fact of size presence. Cannot imply: liquidity quality, depth, support.
    """
    bid_size: float  # Total size on bid side
    ask_size: float  # Total size on ask side
    best_bid_price: Optional[float]  # Best bid price level
    best_ask_price: Optional[float]  # Best ask price level
    timestamp: float  # When observed


# ==============================================================================
# B2.1.2: Order Consumption
# ==============================================================================

@dataclass(frozen=True)
class OrderConsumption:
    """
    Observed decrease in resting size.

    Records fact of size removal. Cannot imply: aggression, intent, pressure.
    """
    consumed_size: float  # Amount of size removed
    side: str  # Which side consumed ("bid" or "ask")
    price_level: float  # Price where consumption occurred
    timestamp: float  # When observed


# ==============================================================================
# B2.1.3: Absorption Event
# ==============================================================================

@dataclass(frozen=True)
class AbsorptionEvent:
    """
    Order consumption coinciding with limited price movement.

    Records coincidence of events. Cannot imply: strength, defense, quality.
    """
    consumed_size: float  # Size consumed
    price_movement_pct: float  # Observed price change magnitude
    side: str  # Which side absorbed
    timestamp: float  # When observed


# ==============================================================================
# B2.1.4: Refill Event
# ==============================================================================

@dataclass(frozen=True)
class RefillEvent:
    """
    Observed increase in resting size after prior decrease.

    Records fact of size addition. Cannot imply: replacement intent, renewal.
    """
    added_size: float  # Amount of size added
    side: str  # Which side refilled
    price_level: float  # Price where refill occurred
    timestamp: float  # When observed


# ==============================================================================
# Computation Functions
# ==============================================================================

def compute_resting_size(
    *,
    bid_size: float,
    ask_size: float,
    best_bid_price: Optional[float],
    best_ask_price: Optional[float],
    timestamp: float
) -> RestingSizeAtPrice:
    """
    Record current resting order book size.

    Args:
        bid_size: Total size on bid side
        ask_size: Total size on ask side
        best_bid_price: Best bid price level (None if no bids)
        best_ask_price: Best ask price level (None if no asks)
        timestamp: Observation timestamp

    Returns:
        RestingSizeAtPrice with current state

    Raises:
        ValueError: If sizes are negative
    """
    if bid_size < 0 or ask_size < 0:
        raise ValueError(f"Sizes must be non-negative: bid={bid_size}, ask={ask_size}")

    return RestingSizeAtPrice(
        bid_size=bid_size,
        ask_size=ask_size,
        best_bid_price=best_bid_price,
        best_ask_price=best_ask_price,
        timestamp=timestamp
    )


def detect_order_consumption(
    *,
    previous_size: float,
    current_size: float,
    side: str,
    price_level: float,
    timestamp: float,
    min_consumption_threshold: float = 0.0
) -> Optional[OrderConsumption]:
    """
    Detect decrease in resting size.

    Args:
        previous_size: Size at previous observation
        current_size: Size at current observation
        side: Which side ("bid" or "ask")
        price_level: Price level observed
        timestamp: Current timestamp
        min_consumption_threshold: Minimum decrease to record (default: 0.0)

    Returns:
        OrderConsumption if size decreased, None otherwise

    Raises:
        ValueError: If sizes negative or side invalid
    """
    if previous_size < 0 or current_size < 0:
        raise ValueError(f"Sizes must be non-negative: prev={previous_size}, curr={current_size}")
    if side not in ("bid", "ask"):
        raise ValueError(f"Side must be 'bid' or 'ask', got: {side}")

    consumed = previous_size - current_size

    if consumed > min_consumption_threshold:
        return OrderConsumption(
            consumed_size=consumed,
            side=side,
            price_level=price_level,
            timestamp=timestamp
        )

    return None


def detect_absorption_event(
    *,
    consumed_size: float,
    price_before: float,
    price_after: float,
    side: str,
    timestamp: float,
    max_price_movement_pct: float = 1.0
) -> Optional[AbsorptionEvent]:
    """
    Detect consumption event with limited price movement.

    Args:
        consumed_size: Amount consumed
        price_before: Price before consumption
        price_after: Price after consumption
        side: Which side consumed
        timestamp: Event timestamp
        max_price_movement_pct: Maximum movement to qualify as absorption

    Returns:
        AbsorptionEvent if consumption occurred with limited movement, None otherwise

    Raises:
        ValueError: If inputs invalid
    """
    if consumed_size <= 0:
        return None
    if price_before <= 0 or price_after <= 0:
        raise ValueError(f"Prices must be positive: before={price_before}, after={price_after}")
    if side not in ("bid", "ask"):
        raise ValueError(f"Side must be 'bid' or 'ask', got: {side}")

    price_movement_pct = abs((price_after - price_before) / price_before) * 100

    if price_movement_pct <= max_price_movement_pct:
        return AbsorptionEvent(
            consumed_size=consumed_size,
            price_movement_pct=price_movement_pct,
            side=side,
            timestamp=timestamp
        )

    return None


def detect_refill_event(
    *,
    previous_size: float,
    current_size: float,
    side: str,
    price_level: float,
    timestamp: float,
    min_refill_threshold: float = 0.0
) -> Optional[RefillEvent]:
    """
    Detect increase in resting size.

    Args:
        previous_size: Size at previous observation
        current_size: Size at current observation
        side: Which side ("bid" or "ask")
        price_level: Price level observed
        timestamp: Current timestamp
        min_refill_threshold: Minimum increase to record

    Returns:
        RefillEvent if size increased, None otherwise

    Raises:
        ValueError: If sizes negative or side invalid
    """
    if previous_size < 0 or current_size < 0:
        raise ValueError(f"Sizes must be non-negative: prev={previous_size}, curr={current_size}")
    if side not in ("bid", "ask"):
        raise ValueError(f"Side must be 'bid' or 'ask', got: {side}")

    added = current_size - previous_size

    if added > min_refill_threshold:
        return RefillEvent(
            added_size=added,
            side=side,
            price_level=price_level,
            timestamp=timestamp
        )

    return None
