"""
M4 Primitive: Liquidation Density

Constitutional Authority: RAW-DATA PRIMITIVES.md Section 6.4

Definition: Liquidation volume per unit price movement.

Fields:
- volume_per_unit: Liquidation volume / price range
- total_volume: Total liquidation volume in window
- price_range: Price movement magnitude
- liquidation_count: Number of liquidations

Constitutional: Factual ratio, no interpretation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LiquidationDensity:
    """6.4: Liquidation volume per unit price movement.

    Constitutional: Derived metric, no semantic interpretation.

    Fields:
        volume_per_unit: Liquidation volume divided by price range
        total_volume: Sum of liquidation volumes
        price_range: Magnitude of price movement
        liquidation_count: Count of liquidations in window
    """
    volume_per_unit: float  # volume / price_range
    total_volume: float
    price_range: float
    liquidation_count: int


def compute_liquidation_density(
    liquidation_volumes: list[float],
    price_start: float,
    price_end: float
) -> Optional[LiquidationDensity]:
    """Compute liquidation density from volume and price movement.

    Constitutional: Factual computation, no threshold interpretation.

    Args:
        liquidation_volumes: List of liquidation volumes in window
        price_start: Starting price of window
        price_end: Ending price of window

    Returns:
        LiquidationDensity if price movement exists, None otherwise
    """
    if len(liquidation_volumes) == 0:
        return None

    total_volume = sum(liquidation_volumes)
    price_range = abs(price_end - price_start)

    # Avoid division by zero
    if price_range == 0:
        return None

    volume_per_unit = total_volume / price_range

    return LiquidationDensity(
        volume_per_unit=volume_per_unit,
        total_volume=total_volume,
        price_range=price_range,
        liquidation_count=len(liquidation_volumes)
    )
