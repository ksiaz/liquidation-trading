"""
M4 Primitive: Liquidation Cascade Proximity

Tier 2 computation from confirmed Hyperliquid position facts.
Observes structural distance to liquidation - not a prediction.

Constitutional compliance:
- Factual observation only
- No predictive language
- No semantic labels ("whale", "danger")
"""

from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass(frozen=True)
class LiquidationCascadeProximity:
    """
    Structural fact: N positions within X% of liquidation price.

    This observes distance to liquidation - not a prediction.
    Computed from confirmed Hyperliquid position data.
    """
    symbol: str
    price_level: float                  # Current market price
    threshold_pct: float                # Proximity threshold used (e.g., 0.02 = 2%)

    # Aggregate counts
    positions_at_risk_count: int        # Total positions within threshold
    aggregate_position_value: float     # Total USD value at risk

    # Long positions (positive size)
    long_positions_count: int
    long_positions_value: float         # USD value
    long_closest_price: Optional[float] # Nearest long liquidation price
    long_avg_distance_pct: float        # Average distance to liquidation

    # Short positions (negative size)
    short_positions_count: int
    short_positions_value: float        # USD value
    short_closest_price: Optional[float]  # Nearest short liquidation price
    short_avg_distance_pct: float       # Average distance to liquidation

    timestamp: float


def compute_liquidation_cascade_proximity(
    symbol: str,
    current_price: float,
    positions: List[Dict],
    threshold_pct: float = 0.02,
    timestamp: float = 0.0
) -> Optional[LiquidationCascadeProximity]:
    """
    Compute cascade proximity from confirmed position facts.

    Args:
        symbol: Trading symbol (e.g., "BTC")
        current_price: Current market price
        positions: List of position dicts with keys:
            - position_size: Signed size (positive=long, negative=short)
            - position_value: USD value
            - liquidation_price: Price at which liquidation triggers
        threshold_pct: Proximity threshold (0.02 = 2%)
        timestamp: Observation timestamp

    Returns:
        LiquidationCascadeProximity or None if no positions at risk
    """
    if not positions or current_price <= 0:
        return None

    long_positions = []
    short_positions = []

    for pos in positions:
        liq_price = pos.get('liquidation_price', 0)
        if liq_price <= 0:
            continue

        # Calculate distance to liquidation
        distance_pct = abs(current_price - liq_price) / current_price

        if distance_pct > threshold_pct:
            continue  # Not at risk

        pos_size = pos.get('position_size', 0)
        pos_value = pos.get('position_value', 0)

        if pos_size > 0:  # Long
            long_positions.append({
                'value': pos_value,
                'liq_price': liq_price,
                'distance_pct': distance_pct
            })
        elif pos_size < 0:  # Short
            short_positions.append({
                'value': pos_value,
                'liq_price': liq_price,
                'distance_pct': distance_pct
            })

    total_count = len(long_positions) + len(short_positions)

    if total_count == 0:
        return None  # No positions at risk

    # Compute long statistics
    long_count = len(long_positions)
    long_value = sum(p['value'] for p in long_positions)
    long_closest = min((p['liq_price'] for p in long_positions), default=None)
    long_avg_dist = (
        sum(p['distance_pct'] for p in long_positions) / long_count
        if long_count > 0 else 0.0
    )

    # Compute short statistics
    short_count = len(short_positions)
    short_value = sum(p['value'] for p in short_positions)
    short_closest = min((p['liq_price'] for p in short_positions), default=None)
    short_avg_dist = (
        sum(p['distance_pct'] for p in short_positions) / short_count
        if short_count > 0 else 0.0
    )

    return LiquidationCascadeProximity(
        symbol=symbol,
        price_level=current_price,
        threshold_pct=threshold_pct,
        positions_at_risk_count=total_count,
        aggregate_position_value=long_value + short_value,
        long_positions_count=long_count,
        long_positions_value=long_value,
        long_closest_price=long_closest,
        long_avg_distance_pct=long_avg_dist,
        short_positions_count=short_count,
        short_positions_value=short_value,
        short_closest_price=short_closest,
        short_avg_distance_pct=short_avg_dist,
        timestamp=timestamp
    )
