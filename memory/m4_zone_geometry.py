"""
M4 Zone Geometry - Phase 1 Tier A Primitives

Implements:
- A6: zone_penetration_depth
- A7: displacement_origin_anchor

Per M4 Structural Primitive Canon v1.0

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Sequence, Optional


# ==============================================================================
# A6: zone_penetration_depth
# ==============================================================================

@dataclass(frozen=True)
class ZonePenetrationDepth:
    """
    Maximum penetration into a zone.
    
    Cannot imply: validity, failure, strength
    """
    zone_id: str
    penetration_depth: float


def compute_zone_penetration_depth(
    *,
    zone_id: str,
    zone_low: float,
    zone_high: float,
    traversal_prices: Sequence[float]
) -> Optional[ZonePenetrationDepth]:
    """
    Compute maximum penetration into a zone.
    
    Returns None if no penetration occurred.
    
    Args:
        zone_id: Unique zone identifier
        zone_low: Lower boundary of zone
        zone_high: Upper boundary of zone
        traversal_prices: Price sequence to analyze
    
    Returns:
        ZonePenetrationDepth if penetration detected, None otherwise
    
    Raises:
        ValueError: If zone_low >= zone_high
    """
    if zone_low >= zone_high:
        raise ValueError(f"zone_low ({zone_low}) must be < zone_high ({zone_high})")
    
    if len(traversal_prices) == 0:
        return None
    
    # Find maximum penetration depth
    max_penetration = 0.0
    penetrated = False
    
    for price in traversal_prices:
        # Check if price is within zone
        if zone_low <= price <= zone_high:
            penetrated = True
            # Calculate penetration depth from nearest boundary
            depth_from_low = price - zone_low
            depth_from_high = zone_high - price
            penetration = min(depth_from_low, depth_from_high)
            max_penetration = max(max_penetration, penetration)
    
    if not penetrated:
        return None
    
    return ZonePenetrationDepth(
        zone_id=zone_id,
        penetration_depth=max_penetration
    )


# ==============================================================================
# A7: displacement_origin_anchor
# ==============================================================================

@dataclass(frozen=True)
class DisplacementOriginAnchor:
    """
    Price region immediately preceding a large traversal.
    
    Cannot imply: institutional activity, future reaction
    """
    traversal_id: str
    anchor_low: float
    anchor_high: float
    anchor_dwell_time: float


def identify_displacement_origin_anchor(
    *,
    traversal_id: str,
    pre_traversal_prices: Sequence[float],
    pre_traversal_timestamps: Sequence[float]
) -> DisplacementOriginAnchor:
    """
    Identify price region immediately preceding a large traversal.
    
    Args:
        traversal_id: Unique traversal identifier
        pre_traversal_prices: Prices before traversal
        pre_traversal_timestamps: Corresponding timestamps
    
    Returns:
        DisplacementOriginAnchor with anchor region metrics
    
    Raises:
        ValueError: If sequences empty or lengths don't match
    """
    if len(pre_traversal_prices) == 0:
        raise ValueError("pre_traversal_prices must be non-empty")
    
    if len(pre_traversal_prices) != len(pre_traversal_timestamps):
        raise ValueError(
            f"Sequence lengths must match: prices={len(pre_traversal_prices)}, "
            f"timestamps={len(pre_traversal_timestamps)}"
        )
    
    # Anchor region is defined by price range
    anchor_low = min(pre_traversal_prices)
    anchor_high = max(pre_traversal_prices)
    
    # Dwell time is total time in pre-traversal period
    if len(pre_traversal_timestamps) > 1:
        anchor_dwell_time = pre_traversal_timestamps[-1] - pre_traversal_timestamps[0]
    else:
        anchor_dwell_time = 0.0
    
    return DisplacementOriginAnchor(
        traversal_id=traversal_id,
        anchor_low=anchor_low,
        anchor_high=anchor_high,
        anchor_dwell_time=anchor_dwell_time
    )
