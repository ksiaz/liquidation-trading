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
- Two-phase signal: detect burst exhaustion, then wait 60s for price momentum
  to dissipate before emitting entry signal (liq events stop before price bottoms)

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
    confirmation_ts: float     # When exhaustion confirmed (cascade rate declining)
    fade_direction: str        # "LONG" or "SHORT"


@dataclass
class _LiqEvent:
    """Internal liquidation event record."""
    timestamp: float
    side: str       # "LONG" or "SHORT" (position side that was liquidated)
    usd_value: float


@dataclass
class _PendingSpike:
    """A spike that was detected — kept for deferral and cooldown.

    confirmed=False: signal detected but not yet acted on by strategy.
                     Returned on each check_for_signal() call for re-evaluation
                     (e.g., fuel gate may pass once positions deplete).
    confirmed=True:  strategy accepted or hard-gate consumed the signal.
                     Full SPIKE_COOLDOWN enforced before next signal.
    """
    signal: RollingFadeSignal
    confirmed: bool = False
    first_detected_ts: float = 0.0  # Original creation time (survives stale_replace)


class RollingVolumeTracker:
    """Burst-rate liquidation detector with per-coin calibration.

    Compares event rate in a short burst window against a longer baseline.
    Naturally adapts to each coin's activity level without fixed thresholds.
    Emits immediately on exhaustion — wide trailing stop handles price overshoot.
    """

    BURST_WINDOW = 30          # 30s burst detection window
    BASELINE_WINDOW = 3600     # 60m baseline rate window
    RATIO_THRESHOLD = 10.0     # Burst rate must be 10x baseline rate
    MIN_BURST_EVENTS = 5       # Minimum events in burst window to trigger
    SPIKE_COOLDOWN = 0         # No cooldown — burst quality gates handle signal filtering
    MAX_CLUSTER_COINS = 5      # Max coins in concurrent spike cluster
    MAX_PENDING_AGE = 60       # Pending signal expires after 60s — prevents stale
                               # signals from being consumed after cascade pauses briefly

    # Warmup: need enough baseline data for rate comparison to be meaningful.
    # Without this, 5 events vs near-zero baseline → infinite ratio → triggers.
    # Old z-score system had MIN_HISTORY=50 (~8 min). 30 events at 1/min = ~30 min.
    MIN_BASELINE_EVENTS = 30

    # Burst concentration: events must be clustered, not spread evenly over 30s.
    # Old system had MIN_Z_JUMP=1.0 which required sudden z-score jump.
    # New equivalent: >=60% of burst events must fall within any 10s sub-window.
    CONCENTRATION_WINDOW = 10  # Sub-window size for concentration check
    CONCENTRATION_RATIO = 0.6  # Fraction of events that must be in densest sub-window

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

        Emits immediately when burst exhaustion detected (liq events declining).
        No artificial delay — wide trailing stop handles price momentum overshoot.

        When an unconfirmed pending signal exists (fuel gate deferring), the full
        detection logic still runs. If a new qualifying burst is found, the pending
        is replaced with the fresh signal. Otherwise the old pending is returned
        for continued fuel gate retry.

        Returns:
            RollingFadeSignal if burst detected/pending, None if cooldown or no data.
        """
        # Check confirmed signal — enforce cooldown
        pending = self._pending.get(symbol)
        if pending is not None and pending.confirmed:
            if timestamp - pending.signal.spike_ts >= self.SPIKE_COOLDOWN:
                del self._pending[symbol]
                pending = None  # Clear local ref — expired, don't re-emit
            else:
                return None  # Still in cooldown

        last_signal = self._last_signal_ts.get(symbol, 0)
        if timestamp - last_signal < self.SPIKE_COOLDOWN:
            return None

        # Expire stale pending signals. Uses first_detected_ts (original creation
        # time) NOT spike_ts (which gets refreshed by stale_replace). This prevents
        # sustained cascades from keeping the signal alive indefinitely via z-decay
        # refreshes. A cascade that's been active for >60s is too dangerous to fade.
        if pending is not None and not pending.confirmed:
            _origin_ts = pending.first_detected_ts or pending.signal.spike_ts
            age = timestamp - _origin_ts
            if age >= self.MAX_PENDING_AGE:
                print(f"[ROLL FADE] {symbol}: expiring stale pending signal "
                      f"(age={age:.0f}s >= {self.MAX_PENDING_AGE}s)")
                del self._pending[symbol]
                pending = None

        # Get events snapshot (thread-safe)
        events_deque = self._events.get(symbol)
        if not events_deque:
            return pending.signal if pending else None
        events = list(events_deque)

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

        if burst_count < self.MIN_BURST_EVENTS:
            return pending.signal if pending else None

        # Compute rates (before baseline gate — ratio determines adaptive minimum)
        baseline_minutes = self.BASELINE_WINDOW / 60.0
        burst_minutes = self.BURST_WINDOW / 60.0
        baseline_rate = baseline_count / baseline_minutes
        burst_rate = burst_count / burst_minutes

        if baseline_rate > 0:
            ratio = burst_rate / baseline_rate
        else:
            ratio = float('inf')

        if ratio < self.RATIO_THRESHOLD:
            return pending.signal if pending else None

        # Warmup: adaptive baseline minimum (strong signals need less context)
        baseline_only = baseline_count - burst_count
        min_baseline = self._min_baseline_for_ratio(ratio)

        # Cold-start bypass: no pre-burst history but overwhelming burst evidence.
        # 0 events → 15+ in 30s is definitionally extreme regardless of context.
        # Higher burst threshold (3× normal) compensates for missing baseline.
        _cold_start_bypass = (
            baseline_only == 0
            and burst_count >= self.MIN_BURST_EVENTS * 3
        )

        if baseline_only < min_baseline and not _cold_start_bypass:
            return pending.signal if pending else None

        # ── Burst concentration gate ──
        burst_events_ts = [e.timestamp for e in events if e.timestamp >= burst_cutoff]
        min_concentrated = max(3, int(burst_count * self.CONCENTRATION_RATIO + 0.5))
        best_in_subwindow = 0
        for i, t in enumerate(burst_events_ts):
            sub_end = t + self.CONCENTRATION_WINDOW
            count_in_sub = sum(1 for t2 in burst_events_ts[i:] if t2 <= sub_end)
            if count_in_sub > best_in_subwindow:
                best_in_subwindow = count_in_sub
        if best_in_subwindow < min_concentrated:
            return pending.signal if pending else None

        # ── Cascade exhaustion gate ──
        half_cutoff = timestamp - self.BURST_WINDOW / 2
        first_half = 0
        second_half = 0
        for e in events:
            if e.timestamp >= burst_cutoff:
                if e.timestamp < half_cutoff:
                    first_half += 1
                else:
                    second_half += 1

        if first_half < 3:
            return pending.signal if pending else None

        if second_half > first_half * 0.5:
            return pending.signal if pending else None

        # Check cluster filter
        concurrent_spikes = sum(
            1 for p in self._pending.values()
            if timestamp - p.signal.spike_ts < 60
        )
        if concurrent_spikes >= self.MAX_CLUSTER_COINS:
            return pending.signal if pending else None

        # New qualifying burst found — create/replace pending signal.
        # If an unconfirmed pending existed, the new burst provides a fresher
        # entry point (updated spike_ts, current burst metrics).
        signal = self._build_signal(symbol, timestamp, ratio, events, burst_cutoff)
        if signal is not None:
            # Only log on first detection or when replacing a genuinely stale
            # pending (>30s old). The same burst re-qualifying every 200ms cycle
            # while fuel gate defers is expected — don't spam the log.
            _is_new = pending is None
            _is_stale_replace = (pending is not None and
                                 timestamp - pending.signal.spike_ts > 30)
            # Preserve first_detected_ts on replacement — stale_replace updates
            # the signal metrics but the age clock keeps ticking from original detection.
            _origin = timestamp if _is_new else (pending.first_detected_ts or pending.signal.spike_ts)
            self._pending[symbol] = _PendingSpike(
                signal=signal, confirmed=False, first_detected_ts=_origin
            )
            # NOTE: _last_signal_ts NOT set here — only on confirm_signal()
            if _is_new or _is_stale_replace:
                ratio_str = f"{min(ratio, 999):.1f}"
                _replaced = " (REPLACED stale)" if pending else ""
                print(f"[ROLL FADE] {symbol}: burst {burst_count}evts in {self.BURST_WINDOW}s "
                      f"ratio={ratio_str}x base={baseline_rate:.2f}/min "
                      f"concentrated={best_in_subwindow}/{burst_count} "
                      f"(declining: {first_half}→{second_half}) "
                      f"L=${signal.long_liq_volume:,.0f} S=${signal.short_liq_volume:,.0f} "
                      f"→ fade {signal.fade_direction} — ENTRY SIGNAL{_replaced}")
            return signal

        return pending.signal if pending else None

    def confirm_signal(self, symbol: str, timestamp: float):
        """Mark a signal as consumed — starts the full cooldown timer.

        Called by service.py when:
        - Strategy accepted the signal (generated a mandate)
        - A hard gate consumed the signal (regime unavailable, stop cooldown)

        NOT called when fuel gate defers — signal stays unconfirmed for retry.
        """
        pending = self._pending.get(symbol)
        if pending is not None and not pending.confirmed:
            pending.confirmed = True
            self._last_signal_ts[symbol] = timestamp

    def _min_baseline_for_ratio(self, ratio: float) -> int:
        """Adaptive baseline minimum — strong signals need less context.

        BTC/ETH/SOL have bursty liq patterns (long gaps then floods).
        A 50x burst ratio is overwhelming evidence even with sparse baseline.
        """
        if ratio >= 50:
            return 5
        if ratio >= 20:
            return 10
        return 20

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

    def get_burst_dominant_side(self, symbol: str, timestamp: float) -> Optional[str]:
        """Dominant liquidation side in burst window (30s).

        Returns "LONG" or "SHORT" based on which side has more USD volume.
        None if no events in burst window.

        Thread-safe: list() snapshot of deque before iterating.
        """
        events_deque = self._events.get(symbol)
        if not events_deque:
            return None
        events = list(events_deque)
        cutoff = timestamp - self.BURST_WINDOW

        long_vol = 0.0
        short_vol = 0.0
        for e in events:
            if e.timestamp >= cutoff:
                if e.side == "LONG":
                    long_vol += e.usd_value
                else:
                    short_vol += e.usd_value

        if long_vol == 0 and short_vol == 0:
            return None
        return "LONG" if long_vol >= short_vol else "SHORT"

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
        """Whether enough baseline history exists for meaningful comparisons."""
        return len(self._events.get(symbol, [])) >= self.MIN_BASELINE_EVENTS

    def get_event_count_in_window(self, symbol: str, timestamp: float,
                                   window_sec: float = 60.0) -> int:
        """Count liq events in a custom time window. Used by DCA gate.

        Thread-safe: list() snapshot of deque before iterating.
        """
        events_deque = self._events.get(symbol)
        if not events_deque:
            return 0
        events = list(events_deque)
        cutoff = timestamp - window_sec
        return sum(1 for e in events if e.timestamp >= cutoff)

    def trim_windows(self, timestamp: float):
        """Trim old events from rolling windows. Call periodically."""
        cutoff = timestamp - self.BASELINE_WINDOW
        for symbol, events in self._events.items():
            while events and events[0].timestamp < cutoff:
                events.popleft()
        # Clean up confirmed pending signals past cooldown.
        # Unconfirmed signals stay alive — fuel gate decides timing.
        for symbol in list(self._pending.keys()):
            p = self._pending[symbol]
            if p.confirmed and timestamp - p.signal.spike_ts > self.SPIKE_COOLDOWN:
                del self._pending[symbol]
