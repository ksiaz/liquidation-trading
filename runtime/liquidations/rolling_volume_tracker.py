"""
Burst-Rate Liquidation Detector

Detects per-coin liquidation bursts by comparing event rate in a short window
(30s) against a longer baseline (60m). Naturally calibrates per-coin: DOGE
getting 5 events in 30s at a 0.03/min baseline = 333x ratio (massive signal),
while BTC getting 5 events at 3/min baseline = 3.3x (no signal).

Used by ROLLING_FADE entry mode in Cascade Sniper.

Design:
- 30s burst window vs 60m baseline window
- burst_ratio = burst_rate / baseline_rate
- Trigger: ratio >= 10x AND burst_events >= 5
- Fade direction: opposite to cascade (short liqs → fade SHORT, long liqs → fade LONG)
- Backtest (13 days, 106K liq events): 71.7% WR, +9.5 bps avg, 60 trades

Thread safety:
- add_event() called from gRPC daemon thread
- check_for_signal() called from asyncio event loop
- Use list() snapshots on deques per established pattern
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Deque, List


@dataclass
class RollingFadeSignal:
    """Signal for ROLLING_FADE entry."""
    symbol: str
    spike_volume: float        # USD volume in burst window
    z_score: float             # Burst rate ratio (burst_rate / baseline_rate)
    short_liq_volume: float    # Short liq volume in burst window
    long_liq_volume: float     # Long liq volume in burst window
    liq_count: int             # Number of liquidation events in burst window
    spike_ts: float            # When burst detected
    confirmation_ts: float     # Same as spike_ts (immediate entry)
    fade_direction: str        # "LONG" or "SHORT"


@dataclass
class _LiqEvent:
    """Internal liquidation event record."""
    timestamp: float
    side: str       # "LONG" or "SHORT" (position side that was liquidated)
    usd_value: float


@dataclass
class _PendingSpike:
    """A spike that was emitted — kept for cooldown enforcement."""
    signal: RollingFadeSignal


class RollingVolumeTracker:
    """Burst-rate liquidation detector with per-coin calibration.

    Compares event rate in a short burst window against a longer baseline.
    Naturally adapts to each coin's activity level without fixed thresholds.
    """

    BURST_WINDOW = 30          # 30s burst detection window
    BASELINE_WINDOW = 3600     # 60m baseline rate window
    RATIO_THRESHOLD = 10.0     # Burst rate must be 10x baseline rate
    MIN_BURST_EVENTS = 5       # Minimum events in burst window to trigger
    SPIKE_COOLDOWN = 900       # 15m between signals per coin
    MAX_CLUSTER_COINS = 5      # Max coins in concurrent spike cluster

    def __init__(self):
        # Per-coin event deques (baseline window retention)
        self._events: Dict[str, Deque[_LiqEvent]] = {}
        # Per-coin: pending spike (for cooldown enforcement)
        self._pending: Dict[str, _PendingSpike] = {}
        # Per-coin: last signal emission time (cooldown)
        self._last_signal_ts: Dict[str, float] = {}

    def add_event(
        self,
        symbol: str,      # Normalized: "BTCUSDT"
        side: str,         # Position side: "LONG" or "SHORT"
        price: float,
        size: float,       # Base units
        timestamp: float
    ):
        """Add a liquidation event to the rolling window.

        Called from gRPC daemon thread — must be thread-safe.
        """
        usd_value = price * size
        event = _LiqEvent(timestamp=timestamp, side=side, usd_value=usd_value)

        if symbol not in self._events:
            self._events[symbol] = deque(maxlen=50000)
        self._events[symbol].append(event)

    def check_for_signal(
        self,
        symbol: str,
        timestamp: float
    ) -> Optional[RollingFadeSignal]:
        """Check for a burst-rate signal for a symbol.

        Called from asyncio event loop. Returns signal immediately when
        burst rate exceeds threshold.

        Returns:
            RollingFadeSignal if burst detected, None otherwise.
        """
        # Check pending signal — enforce cooldown then clean up
        pending = self._pending.get(symbol)
        if pending is not None:
            if timestamp - pending.signal.spike_ts >= self.SPIKE_COOLDOWN:
                del self._pending[symbol]
            else:
                return None  # Still in cooldown

        # Cooldown check
        last_signal = self._last_signal_ts.get(symbol, 0)
        if timestamp - last_signal < self.SPIKE_COOLDOWN:
            return None

        # Get events snapshot (thread-safe)
        events_deque = self._events.get(symbol)
        if not events_deque:
            return None
        events = list(events_deque)

        # Trim old events beyond baseline window
        baseline_cutoff = timestamp - self.BASELINE_WINDOW
        burst_cutoff = timestamp - self.BURST_WINDOW

        # Count events in each window
        baseline_count = 0
        burst_count = 0
        for e in events:
            if e.timestamp >= baseline_cutoff:
                baseline_count += 1
                if e.timestamp >= burst_cutoff:
                    burst_count += 1

        # Need minimum burst events
        if burst_count < self.MIN_BURST_EVENTS:
            return None

        # Compute rates (events per minute)
        baseline_minutes = self.BASELINE_WINDOW / 60.0
        burst_minutes = self.BURST_WINDOW / 60.0
        baseline_rate = baseline_count / baseline_minutes
        burst_rate = burst_count / burst_minutes

        # Compute ratio
        if baseline_rate > 0:
            ratio = burst_rate / baseline_rate
        else:
            # No baseline activity but burst has events → extreme spike
            ratio = float('inf')

        if ratio < self.RATIO_THRESHOLD:
            return None

        # Check cluster filter: how many coins spiked in the last 60s?
        concurrent_spikes = sum(
            1 for p in self._pending.values()
            if timestamp - p.signal.spike_ts < 60
        )
        if concurrent_spikes >= self.MAX_CLUSTER_COINS:
            return None

        # Build and emit signal immediately
        signal = self._build_signal(symbol, timestamp, ratio, events, burst_cutoff)
        if signal is not None:
            self._pending[symbol] = _PendingSpike(signal=signal)
            self._last_signal_ts[symbol] = timestamp
            # Cap ratio display at 999 for readability
            ratio_str = f"{min(ratio, 999):.1f}"
            print(f"[ROLL FADE] {symbol}: burst {burst_count}evts in {self.BURST_WINDOW}s "
                  f"ratio={ratio_str}x base={baseline_rate:.2f}/min — ENTRY SIGNAL")
            return signal

        return None

    def _build_signal(
        self,
        symbol: str,
        spike_ts: float,
        ratio: float,
        events: List[_LiqEvent],
        burst_cutoff: float
    ) -> Optional[RollingFadeSignal]:
        """Build a RollingFadeSignal from burst data."""
        # Compute per-side volumes in burst window
        long_vol = 0.0
        short_vol = 0.0
        burst_volume = 0.0
        count = 0
        for e in events:
            if e.timestamp >= burst_cutoff:
                count += 1
                burst_volume += e.usd_value
                if e.side == "LONG":
                    long_vol += e.usd_value
                else:
                    short_vol += e.usd_value

        if count == 0:
            return None

        # Determine fade direction from dominant liquidation side
        # Short liqs (forced buys, price pushed up) → fade SHORT (sell)
        # Long liqs (forced sells, price pushed down) → fade LONG (buy)
        if short_vol > long_vol:
            fade_direction = "SHORT"
        else:
            fade_direction = "LONG"

        return RollingFadeSignal(
            symbol=symbol,
            spike_volume=burst_volume,
            z_score=min(ratio, 999.0),  # Burst ratio (capped for storage)
            short_liq_volume=short_vol,
            long_liq_volume=long_vol,
            liq_count=count,
            spike_ts=spike_ts,
            confirmation_ts=spike_ts,  # Emit immediately (no delay)
            fade_direction=fade_direction,
        )

    def get_window_volume(self, symbol: str, timestamp: float) -> float:
        """Total USD volume in burst window (30s)."""
        events_deque = self._events.get(symbol)
        if not events_deque:
            return 0.0
        events = list(events_deque)
        cutoff = timestamp - self.BURST_WINDOW
        return sum(e.usd_value for e in events if e.timestamp >= cutoff)

    def get_current_z(self, symbol: str, timestamp: float) -> float:
        """Current burst rate ratio for a symbol."""
        events_deque = self._events.get(symbol)
        if not events_deque:
            return 0.0
        events = list(events_deque)

        baseline_cutoff = timestamp - self.BASELINE_WINDOW
        burst_cutoff = timestamp - self.BURST_WINDOW

        baseline_count = 0
        burst_count = 0
        for e in events:
            if e.timestamp >= baseline_cutoff:
                baseline_count += 1
                if e.timestamp >= burst_cutoff:
                    burst_count += 1

        if burst_count == 0:
            return 0.0

        baseline_rate = baseline_count / (self.BASELINE_WINDOW / 60.0)
        burst_rate = burst_count / (self.BURST_WINDOW / 60.0)

        if baseline_rate > 0:
            return burst_rate / baseline_rate
        return float('inf') if burst_count > 0 else 0.0

    def get_history_count(self, symbol: str) -> int:
        """Number of events in baseline window for a symbol."""
        return len(self._events.get(symbol, []))

    def is_warmed_up(self, symbol: str) -> bool:
        """Whether any events have been seen (no warmup blocker)."""
        return len(self._events.get(symbol, [])) >= 1

    def trim_windows(self, timestamp: float):
        """Trim old events from rolling windows. Call periodically."""
        cutoff = timestamp - self.BASELINE_WINDOW
        for symbol, events in self._events.items():
            while events and events[0].timestamp < cutoff:
                events.popleft()
        # Clean up expired pending signals
        for symbol in list(self._pending.keys()):
            p = self._pending[symbol]
            if timestamp - p.signal.spike_ts > self.SPIKE_COOLDOWN:
                del self._pending[symbol]
