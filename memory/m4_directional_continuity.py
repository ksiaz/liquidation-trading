"""
M4 Primitive: Directional Continuity

Constitutional Authority: RAW-DATA PRIMITIVES.md Section 4.3

Definition: Count of consecutive price updates with identical sign of Δprice.

Fields:
- count: Number of consecutive moves
- direction: +1 (up) or -1 (down)

Constitutional: Factual count, no interpretation of momentum or trend.
"""

from dataclasses import dataclass
from typing import Optional, Literal


@dataclass(frozen=True)
class DirectionalContinuity:
    """4.3: Count of consecutive same-direction price movements.

    Constitutional: Factual count, NOT momentum/trend interpretation.

    Fields:
        count: Number of consecutive moves in same direction
        direction: +1 for upward, -1 for downward
    """
    count: int
    direction: Literal[1, -1]


def compute_directional_continuity(
    ordered_prices: list[float]
) -> Optional[DirectionalContinuity]:
    """Compute directional continuity from ordered price sequence.

    Constitutional: Counts consecutive same-sign deltas, no interpretation.

    Args:
        ordered_prices: Chronologically ordered prices

    Returns:
        DirectionalContinuity if at least 2 prices exist, None otherwise
    """
    if len(ordered_prices) < 2:
        return None

    # Compute deltas
    deltas = [ordered_prices[i] - ordered_prices[i-1] for i in range(1, len(ordered_prices))]

    # Find most recent direction
    last_direction = None
    for delta in reversed(deltas):
        if delta > 0:
            last_direction = 1
            break
        elif delta < 0:
            last_direction = -1
            break

    if last_direction is None:
        # All deltas are zero (no movement)
        return None

    # Count consecutive moves in same direction from end
    count = 0
    for delta in reversed(deltas):
        if last_direction == 1 and delta > 0:
            count += 1
        elif last_direction == -1 and delta < 0:
            count += 1
        elif delta == 0:
            # Zero delta continues the streak
            continue
        else:
            # Direction changed
            break

    if count == 0:
        return None

    return DirectionalContinuity(
        count=count,
        direction=last_direction
    )
