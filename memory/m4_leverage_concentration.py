"""
M4 Primitive: Leverage Concentration Ratio

Tier 2 computation from confirmed Hyperliquid position facts.
Statistical distribution of leverage - pure facts, no interpretation.

Constitutional compliance:
- Statistical distribution only
- No "over-leveraged" or "risky" labels
- Factual percentiles and counts
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import statistics


@dataclass(frozen=True)
class LeverageConcentrationRatio:
    """
    Statistical distribution of leverage across positions.

    Pure statistics - no interpretation of "good" or "bad" leverage.
    """
    symbol: str

    # Distribution statistics
    median_leverage: float
    mean_leverage: float
    leverage_25th_pct: float
    leverage_75th_pct: float
    leverage_90th_pct: float
    leverage_max: float

    # Counts by leverage band (factual categorization)
    low_leverage_count: int      # < 5x
    medium_leverage_count: int   # 5x - 10x
    high_leverage_count: int     # 10x - 20x
    extreme_leverage_count: int  # > 20x

    # Weighted statistics
    weighted_avg_leverage: float  # Position-value weighted

    # Totals
    total_positions_observed: int
    total_position_value: float

    timestamp: float


def compute_leverage_concentration(
    symbol: str,
    positions: List[Dict],
    timestamp: float = 0.0
) -> Optional[LeverageConcentrationRatio]:
    """
    Compute leverage distribution from confirmed position facts.

    Args:
        symbol: Trading symbol
        positions: List of position dicts with keys:
            - leverage: Leverage multiplier
            - position_value: USD value
        timestamp: Observation timestamp

    Returns:
        LeverageConcentrationRatio or None if no positions
    """
    if not positions:
        return None

    # Extract leverage values and weights
    leverages = []
    weighted_sum = 0.0
    total_value = 0.0

    low_count = 0
    medium_count = 0
    high_count = 0
    extreme_count = 0

    for pos in positions:
        lev = pos.get('leverage', 1.0)
        val = pos.get('position_value', 0.0)

        if lev <= 0 or val <= 0:
            continue

        leverages.append(lev)
        weighted_sum += lev * val
        total_value += val

        # Categorize by leverage band
        if lev < 5:
            low_count += 1
        elif lev < 10:
            medium_count += 1
        elif lev < 20:
            high_count += 1
        else:
            extreme_count += 1

    if not leverages:
        return None

    # Sort for percentile computation
    sorted_lev = sorted(leverages)
    n = len(sorted_lev)

    def percentile(p: float) -> float:
        """Compute p-th percentile (0-100)."""
        k = (n - 1) * (p / 100.0)
        f = int(k)
        c = f + 1 if f + 1 < n else f
        d = k - f
        return sorted_lev[f] + d * (sorted_lev[c] - sorted_lev[f])

    return LeverageConcentrationRatio(
        symbol=symbol,
        median_leverage=statistics.median(leverages),
        mean_leverage=statistics.mean(leverages),
        leverage_25th_pct=percentile(25),
        leverage_75th_pct=percentile(75),
        leverage_90th_pct=percentile(90),
        leverage_max=max(leverages),
        low_leverage_count=low_count,
        medium_leverage_count=medium_count,
        high_leverage_count=high_count,
        extreme_leverage_count=extreme_count,
        weighted_avg_leverage=weighted_sum / total_value if total_value > 0 else 0.0,
        total_positions_observed=len(leverages),
        total_position_value=total_value,
        timestamp=timestamp
    )
