"""
Unit tests for ROLLING_FADE fuel gate.

The fuel gate lives in service.py and uses liq event count in a 60s window
(via rolling_volume_tracker.get_event_count_in_window) to decide whether
to defer entry. These tests verify the underlying tracker methods and
the pending signal lifecycle that the fuel gate depends on.
"""

import time

import pytest

from runtime.liquidations.rolling_volume_tracker import (
    RollingVolumeTracker,
    RollingFadeSignal,
)


# -- Fuel gate metric: get_event_count_in_window --

class TestGetEventCountInWindow:
    """Test the liq event count metric used by the fuel gate."""

    def test_empty_returns_zero(self):
        t = RollingVolumeTracker()
        assert t.get_event_count_in_window("BTCUSDT", time.time()) == 0

    def test_counts_events_in_window(self):
        t = RollingVolumeTracker()
        now = time.time()
        for i in range(5):
            t.add_event("BTCUSDT", "LONG", 60000, 0.1, now - 30 + i)
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=60.0) == 5

    def test_excludes_events_outside_window(self):
        t = RollingVolumeTracker()
        now = time.time()
        # 3 events inside 60s, 2 outside
        for i in range(3):
            t.add_event("BTCUSDT", "LONG", 60000, 0.1, now - 30 + i)
        for i in range(2):
            t.add_event("BTCUSDT", "LONG", 60000, 0.1, now - 120 + i)
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=60.0) == 3

    def test_custom_window_size(self):
        t = RollingVolumeTracker()
        now = time.time()
        # Events at -10s, -20s, -40s, -80s
        for offset in [10, 20, 40, 80]:
            t.add_event("BTCUSDT", "LONG", 60000, 0.1, now - offset)
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=30.0) == 2
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=50.0) == 3
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=90.0) == 4

    def test_per_symbol_isolation(self):
        t = RollingVolumeTracker()
        now = time.time()
        for i in range(5):
            t.add_event("BTCUSDT", "LONG", 60000, 0.1, now - 10 + i)
        for i in range(2):
            t.add_event("ETHUSDT", "SHORT", 2000, 1.0, now - 10 + i)
        assert t.get_event_count_in_window("BTCUSDT", now, window_sec=60.0) == 5
        assert t.get_event_count_in_window("ETHUSDT", now, window_sec=60.0) == 2

    def test_fuel_gate_threshold(self):
        """Simulate fuel gate logic: >3 liqs in 60s = defer."""
        FUEL_GATE_MAX_LIQS_60S = 3
        t = RollingVolumeTracker()
        now = time.time()

        # 2 liqs — should pass
        for i in range(2):
            t.add_event("SOLUSDT", "LONG", 85, 10, now - 20 + i)
        recent = t.get_event_count_in_window("SOLUSDT", now, window_sec=60.0)
        assert recent <= FUEL_GATE_MAX_LIQS_60S  # pass — cascade over

        # 5 liqs — should defer
        for i in range(3):
            t.add_event("SOLUSDT", "LONG", 85, 10, now - 10 + i)
        recent = t.get_event_count_in_window("SOLUSDT", now, window_sec=60.0)
        assert recent > FUEL_GATE_MAX_LIQS_60S  # defer — cascade still active


# -- Pending signal lifecycle --

class TestPendingSignalLifecycle:
    """Test that unconfirmed pending signals don't block new detection."""

    def _seed_baseline(self, tracker, symbol, now, count=30):
        """Seed enough baseline events for warmup gate."""
        for i in range(count):
            tracker.add_event(symbol, "LONG", 60000, 0.1, now - 3600 + i * 100)

    def _create_burst(self, tracker, symbol, ts, count=8, side="LONG"):
        """Create a concentrated burst in the first half of the 30s window."""
        for i in range(count):
            tracker.add_event(symbol, side, 60000, 0.5, ts - 25 + i)

    def test_first_detection_returns_signal(self):
        t = RollingVolumeTracker()
        now = time.time()
        self._seed_baseline(t, "BTCUSDT", now)
        self._create_burst(t, "BTCUSDT", now)
        signal = t.check_for_signal("BTCUSDT", now)
        assert signal is not None
        assert isinstance(signal, RollingFadeSignal)

    def test_unconfirmed_pending_returns_signal_on_no_new_burst(self):
        """When no new burst qualifies, the old unconfirmed pending is returned."""
        t = RollingVolumeTracker()
        now = time.time()
        self._seed_baseline(t, "BTCUSDT", now)
        self._create_burst(t, "BTCUSDT", now)

        # First detection
        sig1 = t.check_for_signal("BTCUSDT", now)
        assert sig1 is not None

        # 60s later — burst fell out of 30s window, no new burst
        sig2 = t.check_for_signal("BTCUSDT", now + 60)
        # Should still return the pending signal for fuel gate retry
        assert sig2 is not None
        assert sig2.spike_ts == sig1.spike_ts

    def test_confirmed_pending_enforces_cooldown(self):
        t = RollingVolumeTracker()
        now = time.time()
        self._seed_baseline(t, "BTCUSDT", now)
        self._create_burst(t, "BTCUSDT", now)

        sig = t.check_for_signal("BTCUSDT", now)
        assert sig is not None

        # Confirm the signal (starts 15m cooldown)
        t.confirm_signal("BTCUSDT", now)

        # Next check during cooldown should return None
        assert t.check_for_signal("BTCUSDT", now + 60) is None
        assert t.check_for_signal("BTCUSDT", now + 300) is None

        # After 15m cooldown expires
        self._create_burst(t, "BTCUSDT", now + 901)
        sig2 = t.check_for_signal("BTCUSDT", now + 901)
        assert sig2 is not None

    def test_new_burst_replaces_stale_pending(self):
        """A new qualifying burst replaces an old unconfirmed pending."""
        t = RollingVolumeTracker()
        now = time.time()
        self._seed_baseline(t, "BTCUSDT", now)
        self._create_burst(t, "BTCUSDT", now)

        sig1 = t.check_for_signal("BTCUSDT", now)
        assert sig1 is not None

        # 120s later — new burst (old one fell out of 30s window)
        self._create_burst(t, "BTCUSDT", now + 120)
        sig2 = t.check_for_signal("BTCUSDT", now + 120)
        assert sig2 is not None
        # New signal has updated spike_ts
        assert sig2.spike_ts > sig1.spike_ts

    def test_confirm_signal_idempotent(self):
        """Confirming an already-confirmed signal is a no-op."""
        t = RollingVolumeTracker()
        now = time.time()
        self._seed_baseline(t, "BTCUSDT", now)
        self._create_burst(t, "BTCUSDT", now)

        t.check_for_signal("BTCUSDT", now)
        t.confirm_signal("BTCUSDT", now)
        t.confirm_signal("BTCUSDT", now + 1)  # no-op, already confirmed

        # Still in cooldown
        assert t.check_for_signal("BTCUSDT", now + 60) is None

    def test_confirm_without_pending_is_noop(self):
        """Confirming a symbol with no pending signal does nothing."""
        t = RollingVolumeTracker()
        t.confirm_signal("BTCUSDT", time.time())  # should not raise


# -- Fuel gate phase 2: price momentum logic --

class TestFuelGateMomentum:
    """Test the price momentum deferral logic (phase 2 of fuel gate).

    The actual check lives inline in service.py, but we test the
    direction logic here to prevent regressions.
    """

    _FUEL_MOMENTUM_BPS = 2
    _FUEL_MOMENTUM_WINDOW = 5

    @staticmethod
    def _should_defer(fade_direction: str, prices: list[tuple[float, float]],
                      timestamp: float, window: float = 5, threshold_bps: float = 2) -> bool:
        """Reproduce the fuel gate momentum check from service.py.

        CRITICAL: insufficient data → DEFER (True), not pass.
        Can't confirm momentum dissipated without price data.
        """
        cutoff = timestamp - window
        recent = [(t, p) for t, p in prices if t >= cutoff]
        if len(recent) < 2:
            return True  # No data = defer (safe default)
        p_first = recent[0][1]
        p_last = recent[-1][1]
        move_bps = (p_last - p_first) / p_first * 10000
        return (
            (fade_direction == "SHORT" and move_bps > threshold_bps) or
            (fade_direction == "LONG" and move_bps < -threshold_bps)
        )

    def test_short_fade_defers_on_rising_price(self):
        """SHORT fade (short liq cascade pushed price up) defers while rising."""
        now = time.time()
        # Price rose ~5bp in 5s (30 at 60000 = 5bp)
        prices = [(now - 4, 60000), (now - 2, 60015), (now, 60030)]
        assert self._should_defer("SHORT", prices, now)

    def test_short_fade_passes_on_flat_price(self):
        """SHORT fade passes when price stopped rising."""
        now = time.time()
        prices = [(now - 4, 60000), (now - 2, 60001), (now, 60001)]
        assert not self._should_defer("SHORT", prices, now)

    def test_short_fade_passes_on_falling_price(self):
        """SHORT fade passes when price reversing (our desired direction)."""
        now = time.time()
        prices = [(now - 4, 60000), (now - 2, 59998), (now, 59995)]
        assert not self._should_defer("SHORT", prices, now)

    def test_long_fade_defers_on_falling_price(self):
        """LONG fade (long liq cascade pushed price down) defers while falling."""
        now = time.time()
        # Price fell ~5bp in 5s
        prices = [(now - 4, 60000), (now - 2, 59985), (now, 59970)]
        assert self._should_defer("LONG", prices, now)

    def test_long_fade_passes_on_flat_price(self):
        """LONG fade passes when price stopped falling."""
        now = time.time()
        prices = [(now - 4, 60000), (now - 2, 59999), (now, 59999)]
        assert not self._should_defer("LONG", prices, now)

    def test_long_fade_passes_on_rising_price(self):
        """LONG fade passes when price reversing (our desired direction)."""
        now = time.time()
        prices = [(now - 4, 60000), (now - 2, 60015), (now, 60030)]
        assert not self._should_defer("LONG", prices, now)

    def test_insufficient_data_defers(self):
        """With <2 price points in window, DEFER — can't confirm momentum gone."""
        now = time.time()
        prices = [(now - 3, 60000)]
        assert self._should_defer("SHORT", prices, now)

    def test_empty_price_history_defers(self):
        """No price data at all → defer."""
        now = time.time()
        assert self._should_defer("SHORT", [], now)

    def test_stale_prices_only_defers(self):
        """All prices older than 5s window → defer (same as no data)."""
        now = time.time()
        prices = [(now - 20, 60000), (now - 10, 60030)]
        assert self._should_defer("LONG", prices, now)

    def test_old_prices_excluded(self):
        """Prices outside the 5s window are ignored."""
        now = time.time()
        # Big move happened 10s ago, recent price flat
        prices = [(now - 10, 59000), (now - 3, 60000), (now, 60001)]
        assert not self._should_defer("SHORT", prices, now)

    def test_exactly_at_threshold(self):
        """Move of exactly 2bp should NOT defer (> not >=)."""
        now = time.time()
        # Exactly 2bp rise: 60000 * 2/10000 = 12
        prices = [(now - 3, 60000), (now, 60012)]
        assert not self._should_defer("SHORT", prices, now)
