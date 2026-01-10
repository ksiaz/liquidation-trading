"""
M4 Traversal Kinematics - Phase 1 Tier A Primitives

Implements:
- A3: price_traversal_velocity
- A4: traversal_compactness

Per M4 Structural Primitive Canon v1.0

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Sequence


# ==============================================================================
# A3: price_traversal_velocity
# ==============================================================================

@dataclass(frozen=True)
class PriceTraversalVelocity:
    """
    Deterministic price change per unit time.
    
    Cannot imply: strength, momentum, direction quality
    """
    traversal_id: str
    price_delta: float
    time_delta: float
    velocity: float  # price_delta / time_delta


def compute_price_traversal_velocity(
    *,
    traversal_id: str,
    price_start: float,
    price_end: float,
    ts_start: float,
    ts_end: float
) -> PriceTraversalVelocity:
    """
    Deterministically compute price change per unit time.
    
    Args:
        traversal_id: Unique traversal identifier
        price_start: Starting price
        price_end: Ending price
        ts_start: Start timestamp
        ts_end: End timestamp
    
    Returns:
        PriceTraversalVelocity with computed metrics
    
    Raises:
        ValueError: If ts_end <= ts_start
    """
    if ts_end <= ts_start:
        raise ValueError(f"ts_end ({ts_end}) must be > ts_start ({ts_start})")
    
    price_delta = price_end - price_start
    time_delta = ts_end - ts_start
    velocity = price_delta / time_delta
    
    return PriceTraversalVelocity(
        traversal_id=traversal_id,
        price_delta=price_delta,
        time_delta=time_delta,
        velocity=velocity
    )


# ==============================================================================
# A4: traversal_compactness
# ==============================================================================

@dataclass(frozen=True)
class TraversalCompactness:
    """
    Ratio of net displacement to total path length.
    
    Cannot imply: quality, efficiency
    """
    traversal_id: str
    net_displacement: float
    total_path_length: float
    compactness_ratio: float


def compute_traversal_compactness(
    *,
    traversal_id: str,
    ordered_prices: Sequence[float]
) -> TraversalCompactness:
    """
    Ratio of net displacement to total path length.
    
    Args:
        traversal_id: Unique traversal identifier
        ordered_prices: Chronologically ordered price sequence
    
    Returns:
        TraversalCompactness with computed metrics
    
    Raises:
        ValueError: If ordered_prices contains < 2 values
    """
    if len(ordered_prices) < 2:
        raise ValueError(f"ordered_prices must contain >= 2 values, got {len(ordered_prices)}")
    
    # Net displacement (start to end)
    net_displacement = abs(ordered_prices[-1] - ordered_prices[0])
    
    # Total path length (sum of all movements)
    total_path_length = sum(
        abs(ordered_prices[i] - ordered_prices[i-1])
        for i in range(1, len(ordered_prices))
    )
    
    # Compactness ratio (avoid division by zero)
    if total_path_length == 0:
        compactness_ratio = 1.0  # No movement, perfectly compact
    else:
        compactness_ratio = net_displacement / total_path_length
    
    return TraversalCompactness(
        traversal_id=traversal_id,
        net_displacement=net_displacement,
        total_path_length=total_path_length,
        compactness_ratio=compactness_ratio
    )
