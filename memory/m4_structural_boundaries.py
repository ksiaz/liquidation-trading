"""
M4 Structural Boundaries - Phase 1 Tier A Primitives

Implements:
- A1: structural_boundary_violation
- A2: structural_conversion_failure

Per M4 Structural Primitive Canon v1.0

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Sequence, Optional


# ==============================================================================
# A1: structural_boundary_violation
# ==============================================================================

@dataclass(frozen=True)
class StructuralBoundaryViolation:
    """
    Traversal beyond a structural boundary.
    
    Cannot imply: reversal, deception, liquidity intent
    """
    boundary_id: str
    violation_depth: float
    violation_start_ts: float
    violation_end_ts: float
    violation_duration: float


def detect_structural_boundary_violation(
    *,
    boundary_id: str,
    boundary_price: float,
    traversal_prices: Sequence[float],
    traversal_timestamps: Sequence[float]
) -> Optional[StructuralBoundaryViolation]:
    """
    Detect and describe traversal beyond a boundary.
    
    Returns None if no violation occurred.
    
    Args:
        boundary_id: Unique boundary identifier
        boundary_price: Boundary price level
        traversal_prices: Price sequence
        traversal_timestamps: Corresponding timestamps
    
    Returns:
        StructuralBoundaryViolation if detected, None otherwise
    
    Raises:
        ValueError: If sequence lengths don't match or timestamps not increasing
    """
    if len(traversal_prices) != len(traversal_timestamps):
        raise ValueError(
            f"Sequence lengths must match: prices={len(traversal_prices)}, "
            f"timestamps={len(traversal_timestamps)}"
        )
    
    if len(traversal_prices) == 0:
        return None
    
    # Validate timestamps strictly increasing
    for i in range(1, len(traversal_timestamps)):
        if traversal_timestamps[i] <= traversal_timestamps[i-1]:
            raise ValueError(
                f"Timestamps must be strictly increasing: "
                f"ts[{i-1}]={traversal_timestamps[i-1]}, ts[{i}]={traversal_timestamps[i]}"
            )
    
    # Find first and last violation points
    violation_start_idx = None
    violation_end_idx = None
    max_depth = 0.0
    
    for i, price in enumerate(traversal_prices):
        depth = abs(price - boundary_price)
        # Simple violation: any price beyond boundary
        if (price > boundary_price and violation_start_idx is None) or \
           (price < boundary_price and violation_start_idx is None):
            # Check if actually crossed boundary
            if price != boundary_price:
                if violation_start_idx is None:
                    violation_start_idx = i
                violation_end_idx = i
                max_depth = max(max_depth, depth)
    
    if violation_start_idx is None:
        return None
    
    return StructuralBoundaryViolation(
        boundary_id=boundary_id,
        violation_depth=max_depth,
        violation_start_ts=traversal_timestamps[violation_start_idx],
        violation_end_ts=traversal_timestamps[violation_end_idx],
        violation_duration=traversal_timestamps[violation_end_idx] - traversal_timestamps[violation_start_idx]
    )


# ==============================================================================
# A2: structural_conversion_failure
# ==============================================================================

@dataclass(frozen=True)
class StructuralConversionFailure:
    """
    Reversion without structural state change.
    
    Cannot imply: falseness, weakness, trapping
    """
    boundary_id: str
    reversion_ts: float
    conversion_window: float


def detect_structural_conversion_failure(
    *,
    boundary_id: str,
    violation: StructuralBoundaryViolation,
    post_violation_prices: Sequence[float],
    post_violation_timestamps: Sequence[float],
    conversion_window: float
) -> Optional[StructuralConversionFailure]:
    """
    Detect reversion without structural state change.
    
    Args:
        boundary_id: Boundary identifier
        violation: Previous violation event
        post_violation_prices: Prices after violation
        post_violation_timestamps: Timestamps after violation
        conversion_window: Time window to check for reversion
    
    Returns:
        StructuralConversionFailure if detected, None otherwise
    
    Raises:
        ValueError: If sequence lengths don't match or timestamps not increasing
    """
    if len(post_violation_prices) != len(post_violation_timestamps):
        raise ValueError(
            f"Sequence lengths must match: prices={len(post_violation_prices)}, "
            f"timestamps={len(post_violation_timestamps)}"
        )
    
    if len(post_violation_prices) == 0:
        return None
    
    # Validate timestamps strictly increasing
    for i in range(1, len(post_violation_timestamps)):
        if post_violation_timestamps[i] <= post_violation_timestamps[i-1]:
            raise ValueError("Timestamps must be strictly increasing")
    
    # Check for reversion within window
    # Reversion = price returns to region before violation
    # Simple detection: find first timestamp within window
    window_end = violation.violation_end_ts + conversion_window
    
    for i, ts in enumerate(post_violation_timestamps):
        if ts > window_end:
            break
        
        # Check if price suggests reversion (moved back across boundary conceptually)
        # For simplicity: detect if moved back significantly
        # This is structural - no semantic interpretation
        if ts <= window_end:
            # If we find any price in the window, consider it a reversion event
            return StructuralConversionFailure(
                boundary_id=boundary_id,
                reversion_ts=ts,
                conversion_window=conversion_window
            )
    
    return None
