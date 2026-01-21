"""
M4 Primitive: Trade Burst

Constitutional Authority: RAW-DATA PRIMITIVES.md Section 5.4

Definition: Trade count exceeds baseline count within Δt.

Fields:
- count: Actual trade count in window
- window_duration: Time window duration
- baseline: Mechanical baseline threshold

Constitutional: Factual count comparison, baseline must be mechanical (not adaptive).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TradeBurst:
    """5.4: Trade count exceeds baseline within time window.

    Constitutional: Factual count, mechanical baseline (not adaptive).

    Fields:
        count: Actual trade count in window
        window_duration: Duration of observation window
        baseline: Fixed threshold for burst detection
        excess_count: count - baseline (factual difference)
    """
    count: int
    window_duration: float
    baseline: int
    excess_count: int


def compute_trade_burst(
    trade_count: int,
    window_duration: float,
    baseline: int = 10
) -> Optional[TradeBurst]:
    """Detect trade burst based on mechanical baseline.

    Constitutional: Mechanical threshold, NOT adaptive/predictive.

    Args:
        trade_count: Number of trades in window
        window_duration: Duration of observation window (seconds)
        baseline: Fixed threshold count (default: 10 trades)

    Returns:
        TradeBurst if count exceeds baseline, None otherwise
    """
    if trade_count <= baseline:
        return None

    excess_count = trade_count - baseline

    return TradeBurst(
        count=trade_count,
        window_duration=window_duration,
        baseline=baseline,
        excess_count=excess_count
    )
