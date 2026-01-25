"""
M4 Trade Flow - Tier B Phase B-4

B4.1: Directional Continuity
B4.2: Trade Burst

Per Tier B Canon v1.0 (Frozen)

CRITICAL: Pure functions only. No interpretation. No thresholds.
"""

from dataclasses import dataclass
from typing import Sequence


# ==============================================================================
# B4.1: Directional Continuity
# ==============================================================================

@dataclass(frozen=True)
class DirectionalContinuity:
    """
    Measures consistency of trade direction over sequence.

    Cannot imply: trend strength, momentum, market sentiment
    """
    total_trades: int
    buy_trades: int
    sell_trades: int
    continuity_value: float  # Ratio of dominant direction


def compute_directional_continuity(
    *,
    trade_sides: Sequence[str]  # Sequence of 'BUY' or 'SELL'
) -> DirectionalContinuity:
    """
    Measure directional consistency in trade sequence.

    Args:
        trade_sides: Sequence of trade sides ('BUY' or 'SELL')

    Returns:
        DirectionalContinuity with computed metrics

    Raises:
        ValueError: If trade_sides is empty
    """
    if len(trade_sides) == 0:
        raise ValueError("trade_sides must be non-empty")

    total_trades = len(trade_sides)
    buy_trades = sum(1 for side in trade_sides if side == 'BUY')
    sell_trades = total_trades - buy_trades

    # Continuity: ratio of dominant direction
    dominant_count = max(buy_trades, sell_trades)
    continuity_value = dominant_count / total_trades if total_trades > 0 else 0.0

    return DirectionalContinuity(
        total_trades=total_trades,
        buy_trades=buy_trades,
        sell_trades=sell_trades,
        continuity_value=continuity_value
    )


# ==============================================================================
# B4.2: Trade Burst
# ==============================================================================

@dataclass(frozen=True)
class TradeBurst:
    """
    Identifies rapid sequence of trades within short time window.

    Cannot imply: urgency, panic, market maker activity
    """
    burst_start_ts: float
    burst_end_ts: float
    burst_duration: float
    trade_count: int
    trades_per_second: float


def compute_trade_burst(
    *,
    trade_timestamps: Sequence[float],
    burst_window_sec: float = 1.0
) -> TradeBurst:
    """
    Identify rapid trade sequence within time window.

    Args:
        trade_timestamps: Sequence of trade timestamps (must be sorted)
        burst_window_sec: Maximum duration for burst identification

    Returns:
        TradeBurst with burst metrics

    Raises:
        ValueError: If timestamps empty or burst_window_sec <= 0
    """
    if len(trade_timestamps) == 0:
        raise ValueError("trade_timestamps must be non-empty")

    if burst_window_sec <= 0:
        raise ValueError(f"burst_window_sec must be > 0, got {burst_window_sec}")

    # Find maximum trade density window
    # Sliding window to find max trades within burst_window_sec
    max_count = 0
    max_start_idx = 0
    max_end_idx = 0

    for i in range(len(trade_timestamps)):
        window_start = trade_timestamps[i]
        window_end = window_start + burst_window_sec

        # Count trades within window
        count = 0
        end_idx = i
        for j in range(i, len(trade_timestamps)):
            if trade_timestamps[j] <= window_end:
                count += 1
                end_idx = j
            else:
                break

        if count > max_count:
            max_count = count
            max_start_idx = i
            max_end_idx = end_idx

    # Extract burst window
    burst_start_ts = trade_timestamps[max_start_idx]
    burst_end_ts = trade_timestamps[max_end_idx]
    burst_duration = burst_end_ts - burst_start_ts

    # Avoid division by zero
    if burst_duration > 0:
        trades_per_second = max_count / burst_duration
    else:
        # All trades at same timestamp
        trades_per_second = float(max_count)  # Instantaneous rate

    return TradeBurst(
        burst_start_ts=burst_start_ts,
        burst_end_ts=burst_end_ts,
        burst_duration=burst_duration,
        trade_count=max_count,
        trades_per_second=trades_per_second
    )
