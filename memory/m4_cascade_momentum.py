"""
M4 Primitive: Cascade Momentum Tracking

Tracks velocity and acceleration of liquidation cascades to detect exhaustion.
Records observable rates, not predictions.

Constitutional compliance:
- Observable metrics only (rate, acceleration, elapsed time)
- No predictive language
- Exhaustion based on confirmed rate decline
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
from collections import deque
import time


class MomentumPhase(Enum):
    """
    Observable momentum states based on rate changes.

    States describe what IS happening, not what WILL happen.
    """
    IDLE = auto()           # No significant OI changes
    ACCELERATING = auto()   # Rate increasing (cascade building)
    STEADY = auto()         # Rate stable (cascade ongoing)
    DECELERATING = auto()   # Rate decreasing (cascade slowing)
    EXHAUSTED = auto()      # Rate near zero after activity (cascade ended)


@dataclass(frozen=True)
class CascadeMomentumObservation:
    """
    Factual observation of cascade momentum.

    All metrics are derived from observable OI changes.
    """
    coin: str
    phase: MomentumPhase

    # Rate metrics (observable facts)
    oi_change_rate_1s: float      # OI change per second (1s window)
    oi_change_rate_5s: float      # OI change per second (5s window)
    oi_change_rate_30s: float     # OI change per second (30s window)

    # Acceleration (rate of rate change)
    acceleration: float            # Positive = speeding up, Negative = slowing down

    # Cumulative cascade metrics
    total_oi_dropped: float        # Total OI dropped in current cascade
    cascade_duration_sec: float    # Seconds since cascade started
    peak_rate: float               # Highest rate observed in cascade

    # Signal counts
    liquidation_signals_5s: int    # Count of >0.1% OI drops in 5s
    liquidation_signals_30s: int   # Count of >0.1% OI drops in 30s

    timestamp: float


class CascadeMomentumTracker:
    """
    Tracks cascade momentum from OI change events.

    Maintains rolling windows to compute:
    - Instantaneous rate (1s)
    - Short-term rate (5s)
    - Medium-term rate (30s)
    - Acceleration (rate change over 5s)
    """

    # Thresholds for phase detection
    IDLE_THRESHOLD = 0.01          # <0.01% OI change/sec = idle
    ACCELERATION_THRESHOLD = 0.005  # Rate change > 0.5%/sec^2 = accelerating
    EXHAUSTION_WINDOW = 10.0        # Seconds of low rate after cascade = exhausted

    def __init__(self):
        # Per-coin event buffers: deque of (timestamp, oi_change_pct)
        self._events: Dict[str, deque] = {}

        # Per-coin cascade state
        self._cascade_start: Dict[str, Optional[float]] = {}
        self._peak_rate: Dict[str, float] = {}
        self._total_oi_dropped: Dict[str, float] = {}
        self._last_active: Dict[str, float] = {}

        # Rate history for acceleration calculation
        self._rate_history: Dict[str, deque] = {}  # (timestamp, rate)

        # Max buffer size (60 seconds at ~10 events/sec)
        self._max_events = 600

    def record_event(
        self,
        coin: str,
        oi_change_pct: float,
        is_liquidation_signal: bool,
        timestamp: Optional[float] = None
    ) -> CascadeMomentumObservation:
        """
        Record an OI change event and compute momentum.

        Args:
            coin: Asset symbol (e.g., "BTC")
            oi_change_pct: Percentage change in OI (negative = liquidations)
            is_liquidation_signal: True if OI drop > 0.1%
            timestamp: Event time (defaults to now)

        Returns:
            CascadeMomentumObservation with computed metrics
        """
        ts = timestamp or time.time()

        # Initialize buffers for new coins
        if coin not in self._events:
            self._events[coin] = deque(maxlen=self._max_events)
            self._rate_history[coin] = deque(maxlen=60)
            self._cascade_start[coin] = None
            self._peak_rate[coin] = 0.0
            self._total_oi_dropped[coin] = 0.0
            self._last_active[coin] = 0.0

        # Record event
        self._events[coin].append((ts, oi_change_pct, is_liquidation_signal))

        # Track cascade state for OI drops
        if oi_change_pct < 0:
            if self._cascade_start[coin] is None:
                self._cascade_start[coin] = ts
            self._total_oi_dropped[coin] += abs(oi_change_pct)
            self._last_active[coin] = ts

        # Compute rates for different windows
        rate_1s = self._compute_rate(coin, ts, 1.0)
        rate_5s = self._compute_rate(coin, ts, 5.0)
        rate_30s = self._compute_rate(coin, ts, 30.0)

        # Track peak rate
        if abs(rate_5s) > self._peak_rate[coin]:
            self._peak_rate[coin] = abs(rate_5s)

        # Record rate for acceleration calculation
        self._rate_history[coin].append((ts, rate_5s))

        # Compute acceleration (rate change over last 5 seconds)
        acceleration = self._compute_acceleration(coin, ts)

        # Count liquidation signals
        signals_5s = self._count_signals(coin, ts, 5.0)
        signals_30s = self._count_signals(coin, ts, 30.0)

        # Determine cascade duration
        cascade_duration = 0.0
        if self._cascade_start[coin] is not None:
            cascade_duration = ts - self._cascade_start[coin]

        # Determine momentum phase
        phase = self._determine_phase(
            rate_5s, acceleration, ts, coin
        )

        # Capture values before potential reset
        total_oi = self._total_oi_dropped.get(coin, 0.0)
        peak_rate = self._peak_rate.get(coin, 0.0)

        # Create observation with current values
        observation = CascadeMomentumObservation(
            coin=coin,
            phase=phase,
            oi_change_rate_1s=rate_1s,
            oi_change_rate_5s=rate_5s,
            oi_change_rate_30s=rate_30s,
            acceleration=acceleration,
            total_oi_dropped=total_oi,
            cascade_duration_sec=cascade_duration,
            peak_rate=peak_rate,
            liquidation_signals_5s=signals_5s,
            liquidation_signals_30s=signals_30s,
            timestamp=ts
        )

        # Reset cascade tracking AFTER creating observation
        if phase == MomentumPhase.EXHAUSTED:
            self._cascade_start[coin] = None
            self._peak_rate[coin] = 0.0
            self._total_oi_dropped[coin] = 0.0

        return observation

    def _compute_rate(self, coin: str, current_time: float, window_sec: float) -> float:
        """Compute OI change rate (% per second) over window."""
        events = self._events.get(coin, [])
        if not events:
            return 0.0

        cutoff = current_time - window_sec
        window_events = [(ts, change, _) for ts, change, _ in events if ts > cutoff]

        if not window_events:
            return 0.0

        # Sum all OI changes in window
        total_change = sum(change for _, change, _ in window_events)

        # Rate = total change / window duration
        return total_change / window_sec

    def _compute_acceleration(self, coin: str, current_time: float) -> float:
        """Compute rate acceleration (rate change per second)."""
        history = self._rate_history.get(coin, [])
        if len(history) < 2:
            return 0.0

        # Get rates from 5 seconds ago and now
        cutoff = current_time - 5.0
        old_rates = [(ts, rate) for ts, rate in history if ts <= cutoff]
        new_rates = [(ts, rate) for ts, rate in history if ts > cutoff]

        if not old_rates or not new_rates:
            return 0.0

        # Average rates in each period
        old_rate = sum(r for _, r in old_rates) / len(old_rates)
        new_rate = sum(r for _, r in new_rates) / len(new_rates)

        # Acceleration = (new_rate - old_rate) / time
        return (new_rate - old_rate) / 5.0

    def _count_signals(self, coin: str, current_time: float, window_sec: float) -> int:
        """Count liquidation signals (>0.1% drops) in window."""
        events = self._events.get(coin, [])
        cutoff = current_time - window_sec
        return sum(1 for ts, _, is_signal in events if ts > cutoff and is_signal)

    def _determine_phase(
        self,
        rate_5s: float,
        acceleration: float,
        current_time: float,
        coin: str
    ) -> MomentumPhase:
        """Determine momentum phase from observable metrics."""

        # Check if we're in an active cascade (had recent activity)
        last_active = self._last_active.get(coin, 0.0)
        time_since_active = current_time - last_active
        had_cascade = self._cascade_start.get(coin) is not None

        # EXHAUSTED: Had cascade, now inactive for EXHAUSTION_WINDOW
        if had_cascade and time_since_active > self.EXHAUSTION_WINDOW:
            if abs(rate_5s) < self.IDLE_THRESHOLD:
                return MomentumPhase.EXHAUSTED

        # IDLE: No significant rate
        if abs(rate_5s) < self.IDLE_THRESHOLD:
            return MomentumPhase.IDLE

        # ACCELERATING: Rate increasing (more negative for drops)
        if acceleration < -self.ACCELERATION_THRESHOLD:
            return MomentumPhase.ACCELERATING

        # DECELERATING: Rate decreasing (becoming less negative)
        if acceleration > self.ACCELERATION_THRESHOLD:
            return MomentumPhase.DECELERATING

        # STEADY: Rate stable, cascade ongoing
        return MomentumPhase.STEADY

    def get_all_observations(self) -> Dict[str, CascadeMomentumObservation]:
        """Get current momentum observations for all tracked coins."""
        ts = time.time()
        observations = {}

        for coin in self._events.keys():
            # Recompute with current time
            rate_1s = self._compute_rate(coin, ts, 1.0)
            rate_5s = self._compute_rate(coin, ts, 5.0)
            rate_30s = self._compute_rate(coin, ts, 30.0)
            acceleration = self._compute_acceleration(coin, ts)
            signals_5s = self._count_signals(coin, ts, 5.0)
            signals_30s = self._count_signals(coin, ts, 30.0)

            cascade_duration = 0.0
            if self._cascade_start[coin] is not None:
                cascade_duration = ts - self._cascade_start[coin]

            phase = self._determine_phase(rate_5s, acceleration, ts, coin)

            observations[coin] = CascadeMomentumObservation(
                coin=coin,
                phase=phase,
                oi_change_rate_1s=rate_1s,
                oi_change_rate_5s=rate_5s,
                oi_change_rate_30s=rate_30s,
                acceleration=acceleration,
                total_oi_dropped=self._total_oi_dropped.get(coin, 0.0),
                cascade_duration_sec=cascade_duration,
                peak_rate=self._peak_rate.get(coin, 0.0),
                liquidation_signals_5s=signals_5s,
                liquidation_signals_30s=signals_30s,
                timestamp=ts
            )

        return observations


def phase_to_string(phase: MomentumPhase) -> str:
    """Convert phase to display string."""
    return {
        MomentumPhase.IDLE: "IDLE",
        MomentumPhase.ACCELERATING: "ACCELERATING",
        MomentumPhase.STEADY: "STEADY",
        MomentumPhase.DECELERATING: "DECELERATING",
        MomentumPhase.EXHAUSTED: "EXHAUSTED"
    }.get(phase, "UNKNOWN")
