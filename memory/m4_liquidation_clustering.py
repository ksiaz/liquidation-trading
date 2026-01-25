"""
M4 Liquidation Clustering - Tier B Phase B-3

B3.1: Liquidation Density

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Sequence


# ==============================================================================
# B3.1: Liquidation Density
# ==============================================================================

@dataclass(frozen=True)
class LiquidationDensity:
    """
    Measures spatial concentration of liquidation events.

    Cannot imply: cascade risk, market manipulation, forced selling
    """
    price_center: float
    price_window: float
    liquidation_count: int
    total_volume: float
    density_score: float  # liquidations per price unit


def compute_liquidation_density(
    *,
    liquidations: Sequence[dict],  # {'price': float, 'volume': float}
    price_center: float,
    price_window: float
) -> LiquidationDensity:
    """
    Measure spatial concentration of liquidations around price level.

    Args:
        liquidations: List of liquidation events with price and volume
        price_center: Center price for density measurement
        price_window: Price range around center (±window/2)

    Returns:
        LiquidationDensity with computed metrics

    Raises:
        ValueError: If price_window <= 0
    """
    if price_window <= 0:
        raise ValueError(f"price_window must be > 0, got {price_window}")

    # Define price range
    price_low = price_center - (price_window / 2.0)
    price_high = price_center + (price_window / 2.0)

    # Filter liquidations within window
    in_window = [
        liq for liq in liquidations
        if price_low <= liq['price'] <= price_high
    ]

    liquidation_count = len(in_window)
    total_volume = sum(liq['volume'] for liq in in_window)

    # Density: liquidations per price unit
    density_score = liquidation_count / price_window if price_window > 0 else 0.0

    return LiquidationDensity(
        price_center=price_center,
        price_window=price_window,
        liquidation_count=liquidation_count,
        total_volume=total_volume,
        density_score=density_score
    )
