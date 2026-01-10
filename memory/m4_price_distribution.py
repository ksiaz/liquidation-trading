"""
M4 Price Distribution - Phase 1 Tier A Primitives

Implements:
- A5: price_acceptance_ratio
- A8: central_tendency_deviation

Per M4 Structural Primitive Canon v1.0

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass


# ==============================================================================
# A5: price_acceptance_ratio
# ==============================================================================

@dataclass(frozen=True)
class PriceAcceptanceRatio:
    """
    Accepted vs rejected price range from OHLC.
    
    Cannot imply: acceptance quality, conviction
    """
    accepted_range: float
    rejected_range: float
    acceptance_ratio: float


def compute_price_acceptance_ratio(
    *,
    candle_open: float,
    candle_high: float,
    candle_low: float,
    candle_close: float
) -> PriceAcceptanceRatio:
    """
    Compute accepted vs rejected price range.
    
    Accepted range: body (distance between open and close)
    Rejected range: wicks (high-low minus body)
    
    Args:
        candle_open: Opening price
        candle_high: Highest price
        candle_low: Lowest price
        candle_close: Closing price
    
    Returns:
        PriceAcceptanceRatio with computed metrics
    
    Raises:
        ValueError: If OHLC validation fails
    """
    # Validate OHLC structure
    if candle_high < max(candle_open, candle_close):
        raise ValueError(
            f"candle_high ({candle_high}) must be >= max(open, close) "
            f"({max(candle_open, candle_close)})"
        )
    
    if candle_low > min(candle_open, candle_close):
        raise ValueError(
            f"candle_low ({candle_low}) must be <= min(open, close) "
            f"({min(candle_open, candle_close)})"
        )
    
    # Accepted range: body
    accepted_range = abs(candle_close - candle_open)
    
    # Total range
    total_range = candle_high - candle_low
    
    # Rejected range: wicks
    rejected_range = total_range - accepted_range
    
    # Acceptance ratio (avoid division by zero)
    if total_range == 0:
        acceptance_ratio = 1.0  # Doji case - no rejection
    else:
        acceptance_ratio = accepted_range / total_range
    
    return PriceAcceptanceRatio(
        accepted_range=accepted_range,
        rejected_range=rejected_range,
        acceptance_ratio=acceptance_ratio
    )


# ==============================================================================
# A8: central_tendency_deviation
# ==============================================================================

@dataclass(frozen=True)
class CentralTendencyDeviation:
    """
    Deviation from central price tendency.
    
    Cannot imply: overextension, reversion likelihood
    """
    deviation_value: float


def compute_central_tendency_deviation(
    *,
    price: float,
    central_tendency: float
) -> CentralTendencyDeviation:
    """
    Compute deviation from central price tendency.
    
    Args:
        price: Current price
        central_tendency: Central tendency value (e.g., mean, median)
    
    Returns:
        CentralTendencyDeviation with computed metric
    """
    deviation_value = price - central_tendency
    
    return CentralTendencyDeviation(
        deviation_value=deviation_value
    )
