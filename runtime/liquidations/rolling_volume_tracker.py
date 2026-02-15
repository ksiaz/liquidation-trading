"""
Rolling Liquidation Volume Tracker

Tracks per-coin liquidation volume in a 30-minute rolling window and detects
volume spikes via z-score. Used by ROLLING_FADE entry mode in Cascade Sniper.

Design:
- 30m rolling window accumulates per-coin liquidation USD volume
- Z-score spike detection: z >= 1.5 triggers spike
- Spike peak = when z drops back below threshold (spike ended)
- 30s confirmation delay after spike peak before entry
- Fade direction: opposite to cascade (short liqs → fade SHORT, long liqs → fade LONG)

Thread safety:
- add_event() called from gRPC daemon thread
- check_for_signal() called from asyncio event loop
- Use list() snapshots on deques per established pattern
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Deque, List
import math


@dataclass
class RollingFadeSignal:
    """Signal for ROLLING_FADE entry."""
    symbol: str
    spike_volume: float        # USD volume at spike peak
    z_score: float             # Z-score at peak
    short_liq_volume: float    # Short liq volume in window at peak
    long_liq_volume: float     # Long liq volume in window at peak
    liq_count: int             # Number of liquidation events in window at peak
    spike_ts: float            # When spike peaked
    confirmation_ts: float     # When confirmation period ends (spike_ts + 30s)
    fade_direction: str        # "LONG" or "SHORT"


@dataclass
class _LiqEvent:
    """Internal liquidation event record."""
    timestamp: float
    side: str       # "LONG" or "SHORT" (position side that was liquidated)
    usd_value: float


@dataclass
class _PendingSpike:
    """A spike that has peaked but awaits confirmation delay."""
    signal: RollingFadeSignal
    emitted: bool = False


class RollingVolumeTracker:
    """Rolling liquidation volume tracker with spike detection.

    Accumulates per-coin liquidation USD volume over a 30m rolling window.
    Detects z-score spikes and emits RollingFadeSignal after confirmation delay.
    """

    WINDOW = 1800              # 30m rolling window (seconds)
    Z_THRESHOLD = 1.5          # Min z-score to trigger spike detection
    CONFIRMATION_DELAY = 30.0  # Seconds after spike peak before entry
    MIN_HISTORY = 100          # Min data points before z-score meaningful
    SPIKE_COOLDOWN = 900       # 15m between spikes per coin
    MAX_CLUSTER_COINS = 5      # Max coins in concurrent spike cluster

    def __init__(self):
        # Per-coin event deques (rolling window)
        self._events: Dict[str, Deque[_LiqEvent]] = {}
        # Per-coin volume history for z-score (all-time, sampled)
        self._volume_history: Dict[str, Deque[float]] = {}
        # Per-coin: was z above threshold last check? (for spike-start detection)
        self._was_above: Dict[str, bool] = {}
        # Per-coin: pending spike awaiting confirmation
        self._pending: Dict[str, _PendingSpike] = {}
        # Per-coin: last signal emission time (cooldown)
        self._last_signal_ts: Dict[str, float] = {}
        # Per-coin: last volume sample timestamp (for history sampling)
        self._last_sample_ts: Dict[str, float] = {}

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
            self._events[symbol] = deque(maxlen=10000)
        self._events[symbol].append(event)

        # Sample volume every 10s for history (avoids huge history arrays)
        last_sample = self._last_sample_ts.get(symbol, 0)
        if timestamp - last_sample >= 10.0:
            window_vol = self._get_window_volume(symbol, timestamp)
            if symbol not in self._volume_history:
                self._volume_history[symbol] = deque(maxlen=10000)
            self._volume_history[symbol].append(window_vol)
            self._last_sample_ts[symbol] = timestamp

    def check_for_signal(
        self,
        symbol: str,
        timestamp: float
    ) -> Optional[RollingFadeSignal]:
        """Check for a rolling fade signal for a symbol.

        Called from asyncio event loop. Returns signal only after confirmation delay.

        Spike detection: when z first crosses above threshold, record spike immediately
        and start 30s confirmation timer. Signal emitted after confirmation delay.
        (We don't wait for z to drop — with a 30m window, that takes too long.)

        Returns:
            RollingFadeSignal if confirmed spike detected, None otherwise.
        """
        # Check pending signal first (already detected spike, waiting for confirmation)
        pending = self._pending.get(symbol)
        if pending is not None:
            if pending.emitted:
                # Already emitted — don't emit again
                return None
            if timestamp >= pending.signal.confirmation_ts:
                # Confirmation delay passed — emit signal
                pending.emitted = True
                self._last_signal_ts[symbol] = timestamp
                return pending.signal
            # Still waiting for confirmation
            return None

        # Cooldown check
        last_signal = self._last_signal_ts.get(symbol, 0)
        if timestamp - last_signal < self.SPIKE_COOLDOWN:
            return None

        # Compute current z-score
        window_vol = self._get_window_volume(symbol, timestamp)
        z = self._compute_zscore(symbol, window_vol)

        if z >= self.Z_THRESHOLD:
            was_above = self._was_above.get(symbol, False)
            self._was_above[symbol] = True

            if not was_above:
                # Spike just started (z first crossed above threshold)

                # Check cluster filter: how many coins are spiking concurrently?
                concurrent_spikes = sum(1 for s, above in self._was_above.items() if above)
                if concurrent_spikes > self.MAX_CLUSTER_COINS:
                    # Too many coins spiking — broad market event, skip
                    return None

                # Build signal immediately at spike start, then wait for confirmation
                signal = self._build_signal(symbol, timestamp, z, window_vol)
                if signal is not None:
                    self._pending[symbol] = _PendingSpike(signal=signal)
                    print(f"[ROLL FADE] {symbol}: spike detected z={z:.2f} "
                          f"vol=${window_vol:,.0f} — waiting {self.CONFIRMATION_DELAY}s")
                    # Don't emit yet — wait for confirmation delay
                    return None
        else:
            # Z below threshold — reset spike tracking
            self._was_above[symbol] = False

        return None

    def _get_window_volume(self, symbol: str, timestamp: float) -> float:
        """Get total USD volume in the rolling window. Thread-safe via list() snapshot."""
        events_deque = self._events.get(symbol)
        if not events_deque:
            return 0.0
        # Snapshot for thread safety
        events = list(events_deque)
        cutoff = timestamp - self.WINDOW
        return sum(e.usd_value for e in events if e.timestamp >= cutoff)

    def _compute_zscore(self, symbol: str, current_volume: float) -> float:
        """Compute z-score of current window volume vs historical."""
        history_deque = self._volume_history.get(symbol)
        if not history_deque:
            return 0.0
        history = list(history_deque)
        if len(history) < self.MIN_HISTORY:
            return 0.0

        mean = sum(history) / len(history)
        variance = sum((v - mean) ** 2 for v in history) / len(history)
        stddev = math.sqrt(variance) if variance > 0 else 0.0

        if stddev == 0:
            return 0.0

        return (current_volume - mean) / stddev

    def _build_signal(
        self,
        symbol: str,
        spike_ts: float,
        peak_z: float,
        window_vol: float
    ) -> Optional[RollingFadeSignal]:
        """Build a RollingFadeSignal from spike data."""
        events_deque = self._events.get(symbol)
        if not events_deque:
            return None

        # Snapshot for thread safety
        events = list(events_deque)
        cutoff = spike_ts - self.WINDOW

        # Compute per-side volumes in window
        long_vol = 0.0
        short_vol = 0.0
        count = 0
        for e in events:
            if e.timestamp >= cutoff:
                count += 1
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
            spike_volume=window_vol,
            z_score=peak_z,
            short_liq_volume=short_vol,
            long_liq_volume=long_vol,
            liq_count=count,
            spike_ts=spike_ts,
            confirmation_ts=spike_ts + self.CONFIRMATION_DELAY,
            fade_direction=fade_direction,
        )

    def trim_windows(self, timestamp: float):
        """Trim old events from rolling windows. Call periodically."""
        cutoff = timestamp - self.WINDOW
        for symbol, events in self._events.items():
            while events and events[0].timestamp < cutoff:
                events.popleft()
        # Clean up emitted pending signals
        for symbol in list(self._pending.keys()):
            p = self._pending[symbol]
            if p.emitted and timestamp - p.signal.spike_ts > self.SPIKE_COOLDOWN:
                del self._pending[symbol]
