"""
M4 Primitive: Open Interest Directional Bias

Tier 2 computation from confirmed Hyperliquid position facts.
Net direction of open positions - factual aggregation.

Constitutional compliance:
- Factual sum of long vs short
- No "bullish" or "bearish" labels
- Pure arithmetic aggregation
"""

from dataclasses import dataclass
from typing import Optional, List, Dict


@dataclass(frozen=True)
class OpenInterestDirectionalBias:
    """
    Net direction of open positions.

    Factual aggregation - no interpretation as "bullish" or "bearish".
    """
    symbol: str

    # Net position sizes (USD value)
    net_long_value: float           # Total long position value
    net_short_value: float          # Total short position value
    net_imbalance: float            # long - short (positive = net long)

    # Ratio (for structural comparison)
    long_short_ratio: float         # long / short (> 1 = more long, < 1 = more short)

    # Participant counts
    long_participant_count: int
    short_participant_count: int
    total_participant_count: int

    # Total open interest
    total_open_interest: float      # long + short absolute values

    # Average sizes
    avg_long_position_value: float
    avg_short_position_value: float

    timestamp: float


def compute_open_interest_bias(
    symbol: str,
    positions: List[Dict],
    timestamp: float = 0.0
) -> Optional[OpenInterestDirectionalBias]:
    """
    Compute open interest directional bias from confirmed position facts.

    Args:
        symbol: Trading symbol
        positions: List of position dicts with keys:
            - position_size: Signed size (positive=long, negative=short)
            - position_value: USD value (always positive)
        timestamp: Observation timestamp

    Returns:
        OpenInterestDirectionalBias or None if no positions
    """
    if not positions:
        return None

    long_value = 0.0
    short_value = 0.0
    long_count = 0
    short_count = 0

    for pos in positions:
        size = pos.get('position_size', 0.0)
        value = abs(pos.get('position_value', 0.0))

        if value <= 0:
            continue

        if size > 0:  # Long
            long_value += value
            long_count += 1
        elif size < 0:  # Short
            short_value += value
            short_count += 1

    if long_count == 0 and short_count == 0:
        return None

    total_oi = long_value + short_value
    total_participants = long_count + short_count

    # Compute ratio (avoid division by zero)
    if short_value > 0:
        ls_ratio = long_value / short_value
    elif long_value > 0:
        ls_ratio = float('inf')
    else:
        ls_ratio = 1.0

    return OpenInterestDirectionalBias(
        symbol=symbol,
        net_long_value=long_value,
        net_short_value=short_value,
        net_imbalance=long_value - short_value,
        long_short_ratio=ls_ratio,
        long_participant_count=long_count,
        short_participant_count=short_count,
        total_participant_count=total_participants,
        total_open_interest=total_oi,
        avg_long_position_value=long_value / long_count if long_count > 0 else 0.0,
        avg_short_position_value=short_value / short_count if short_count > 0 else 0.0,
        timestamp=timestamp
    )
