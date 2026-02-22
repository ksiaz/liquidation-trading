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
    """A spike that was emitted — kept for cooldown enforcement."""
    signal: RollingFadeSignal


class RollingVolumeTracker:
    """Rolling liquidation volume tracker with spike detection.

    Accumulates per-coin liquidation USD volume over a 30m rolling window.
    Detects z-score spikes and emits RollingFadeSignal after confirmation delay.
    """

    WINDOW = 1800              # 30m rolling window (seconds)
    Z_THRESHOLD = 1.5          # Min z-score to trigger spike detection
    MIN_HISTORY = 50           # Min data points before z-score meaningful (~8 min at 10s sampling)
    SPIKE_COOLDOWN = 900       # 15m between spikes per coin
    MAX_CLUSTER_COINS = 5      # Max coins in concurrent spike cluster

    # Adaptive per-coin volume gate: max($1000, mean_volume * 3)
    # Replaces fixed $10K threshold that blocked 9/20 coins on HL's thinner books.
    # Z-score + z_jump gates handle signal quality; this gate prevents pure noise.
    MIN_VOLUME_FLOOR = 1000    # Absolute minimum — below this, not enough momentum to fade
    VOLUME_SPIKE_MULTIPLIER = 3  # Spike must be 3x the coin's mean 30m window volume

    MIN_Z_JUMP = 1.0           # Min z-score increase in one sample interval to trigger (prevents gradual accumulation)

    def __init__(self):
        # Per-coin event deques (rolling window)
        self._events: Dict[str, Deque[_LiqEvent]] = {}
        # Per-coin volume history for z-score (all-time, sampled)
        self._volume_history: Dict[str, Deque[float]] = {}
        # Per-coin: z-score at last 10s sample (for jump detection)
        # Updated only at sample boundaries — NOT every call.
        # check_for_signal() runs at 5Hz but z_jump needs to measure
        # the 10s delta, not the 200ms delta.
        self._sampled_z: Dict[str, float] = {}
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

        Also periodically samples volume history so baseline builds up even during
        quiet periods (zero-volume intervals create low mean/stddev baseline, making
        actual bursts produce high z-scores).

        Returns:
            RollingFadeSignal if confirmed spike detected, None otherwise.
        """
        # Periodic volume sampling — build baseline even when no events arrive.
        # This prevents the chicken-and-egg problem where z-scores require history
        # but history only builds when events arrive.
        just_sampled = False
        last_sample = self._last_sample_ts.get(symbol, 0)
        if timestamp - last_sample >= 10.0:
            window_vol_sample = self._get_window_volume(symbol, timestamp)
            if symbol not in self._volume_history:
                self._volume_history[symbol] = deque(maxlen=10000)
            self._volume_history[symbol].append(window_vol_sample)
            self._last_sample_ts[symbol] = timestamp
            just_sampled = True

        # Check pending signal — enforce cooldown then clean up
        pending = self._pending.get(symbol)
        if pending is not None:
            if timestamp - pending.signal.spike_ts >= self.SPIKE_COOLDOWN:
                del self._pending[symbol]
                # Fall through to normal spike detection below
            else:
                return None  # Still in cooldown

        # Cooldown check
        last_signal = self._last_signal_ts.get(symbol, 0)
        if timestamp - last_signal < self.SPIKE_COOLDOWN:
            return None

        # Compute current z-score
        window_vol = self._get_window_volume(symbol, timestamp)
        z = self._compute_zscore(symbol, window_vol)

        # Track z-score jump relative to last 10s SAMPLE, not last 200ms call.
        # check_for_signal() runs at 5Hz but MIN_Z_JUMP is calibrated for 10s
        # intervals. Updating prev_z every call made z_jump always < 1.0 because
        # events trickle in one-by-one between 200ms calls.
        sampled_z = self._sampled_z.get(symbol, 0.0)
        z_jump = z - sampled_z
        if just_sampled:
            self._sampled_z[symbol] = z

        min_vol = self._get_min_spike_volume(symbol)
        if (z >= self.Z_THRESHOLD
                and window_vol >= min_vol
                and z_jump >= self.MIN_Z_JUMP):
            # Spike detected: z above threshold with a sudden jump and real volume.
            # MIN_Z_JUMP prevents gradual accumulation from triggering — only
            # sudden bursts (z jumping by >= 1.0 in one sample interval) fire.

            # Check cluster filter: how many coins spiked in the last 60s?
            concurrent_spikes = sum(
                1 for p in self._pending.values()
                if timestamp - p.signal.spike_ts < 60
            )
            if concurrent_spikes >= self.MAX_CLUSTER_COINS:
                # Too many coins spiking — broad market event, skip
                return None

            # Build and emit signal immediately — every second of delay costs edge.
            signal = self._build_signal(symbol, timestamp, z, window_vol)
            if signal is not None:
                self._pending[symbol] = _PendingSpike(signal=signal)
                self._last_signal_ts[symbol] = timestamp
                print(f"[ROLL FADE] {symbol}: spike z={z:.2f} jump={z_jump:.2f} "
                      f"vol=${window_vol:,.0f} min=${min_vol:,.0f} — ENTRY SIGNAL")
                return signal

        return None

    def _get_min_spike_volume(self, symbol: str) -> float:
        """Adaptive per-coin minimum spike volume.

        Returns max(MIN_VOLUME_FLOOR, mean_volume * VOLUME_SPIKE_MULTIPLIER).
        Coins with near-zero baseline get the $500 floor.
        High-volume coins (BTC, ETH) naturally get higher thresholds.
        """
        history_deque = self._volume_history.get(symbol)
        if not history_deque or len(history_deque) < self.MIN_HISTORY:
            return self.MIN_VOLUME_FLOOR
        history = list(history_deque)
        mean = sum(history) / len(history)
        return max(self.MIN_VOLUME_FLOOR, mean * self.VOLUME_SPIKE_MULTIPLIER)

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
            confirmation_ts=spike_ts,  # Emit immediately (no delay)
            fade_direction=fade_direction,
        )

    def get_window_volume(self, symbol: str, timestamp: float) -> float:
        """Public accessor for current window volume."""
        return self._get_window_volume(symbol, timestamp)

    def get_current_z(self, symbol: str, timestamp: float) -> float:
        """Current z-score for a symbol."""
        vol = self._get_window_volume(symbol, timestamp)
        return self._compute_zscore(symbol, vol)

    def get_history_count(self, symbol: str) -> int:
        """Number of volume history samples for a symbol."""
        return len(self._volume_history.get(symbol, []))

    def is_warmed_up(self, symbol: str) -> bool:
        """Whether enough history has accumulated for meaningful z-scores."""
        return self.get_history_count(symbol) >= self.MIN_HISTORY

    def trim_windows(self, timestamp: float):
        """Trim old events from rolling windows. Call periodically."""
        cutoff = timestamp - self.WINDOW
        for symbol, events in self._events.items():
            while events and events[0].timestamp < cutoff:
                events.popleft()
        # Clean up expired pending signals
        for symbol in list(self._pending.keys()):
            p = self._pending[symbol]
            if timestamp - p.signal.spike_ts > self.SPIKE_COOLDOWN:
                del self._pending[symbol]
