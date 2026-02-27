"""Tests for ROLLING_FADE fixes.

Verifies:
1. Exhaustion gate in RollingVolumeTracker:
   - Tiny burst rejection (first_half < 3)
   - Cascade still active rejection (second_half > first_half * 0.5)
   - Signal passes when declining (second_half <= first_half * 0.5 AND first_half >= 3)

2. ATR corruption guard in ATRCalculator:
   - TR clamped when it exceeds 5% of price
   - ATR clamped at 10% of price
   - Normal operation unaffected by clamps
"""

import time
import pytest

from runtime.liquidations.rolling_volume_tracker import RollingVolumeTracker
from runtime.indicators.atr import ATRCalculator


# ─── Helpers ───

def _seed_baseline(tracker: RollingVolumeTracker, symbol: str, base_ts: float, count: int = 40):
    """Seed enough baseline events so MIN_BASELINE_EVENTS is met.

    Events are spread evenly across the baseline window (3600s) BEFORE
    the burst window starts.  This ensures burst events stand out
    against the background rate.
    """
    baseline_start = base_ts - tracker.BASELINE_WINDOW
    burst_start = base_ts - tracker.BURST_WINDOW
    # Place baseline events from baseline_start to just before burst window
    spread = burst_start - baseline_start - 1  # -1 so they stay outside burst
    for i in range(count):
        ts = baseline_start + (spread * i / count)
        tracker.add_event(symbol, "LONG", 100.0, 1.0, ts)


def _add_burst_events(
    tracker: RollingVolumeTracker,
    symbol: str,
    base_ts: float,
    first_half_count: int,
    second_half_count: int,
):
    """Add burst events split across the two halves of the 30s burst window.

    First half: [base_ts - 30, base_ts - 15)
    Second half: [base_ts - 15, base_ts)
    Events within each half are evenly spread with a small clustering in the
    first half to pass the concentration gate.
    """
    burst_start = base_ts - tracker.BURST_WINDOW
    half = tracker.BURST_WINDOW / 2

    # First half events clustered in a 10s sub-window to pass concentration gate
    for i in range(first_half_count):
        # Cluster within 8s of burst_start
        ts = burst_start + (8.0 * i / max(first_half_count, 1))
        tracker.add_event(symbol, "LONG", 100.0, 1.0, ts)

    # Second half events spread from half_cutoff onward
    half_cutoff = base_ts - half
    for i in range(second_half_count):
        ts = half_cutoff + (half * 0.9 * i / max(second_half_count, 1))
        tracker.add_event(symbol, "LONG", 100.0, 1.0, ts)


# ─── 1. Exhaustion Gate Tests ───

class TestExhaustionGateTinyBurst:
    """first_half < 3 should reject (too few events to be a real burst)."""

    def test_first_half_2_returns_none(self):
        tracker = RollingVolumeTracker()
        symbol = "BTCUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        # first_half=2, second_half=0 — total 2 events in burst < MIN_BURST_EVENTS(5)
        # We need >=5 total burst events to even reach the exhaustion gate.
        # Put 2 in first half and 4 in second half (total 6 >= 5).
        # first_half(2) < 3 → rejected at exhaustion gate.
        _add_burst_events(tracker, symbol, now, first_half_count=2, second_half_count=4)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is None

    def test_first_half_0_returns_none(self):
        tracker = RollingVolumeTracker()
        symbol = "ETHUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        # All events in second half: first_half=0, second_half=6
        _add_burst_events(tracker, symbol, now, first_half_count=0, second_half_count=6)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is None


class TestExhaustionGateCascadeStillActive:
    """second_half > first_half * 0.5 should reject (cascade not declining enough)."""

    def test_equal_halves_returns_none(self):
        """5 in each half: second(5) > first(5) * 0.5 = 2.5 → reject."""
        tracker = RollingVolumeTracker()
        symbol = "SOLUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        _add_burst_events(tracker, symbol, now, first_half_count=5, second_half_count=5)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is None

    def test_barely_above_half_returns_none(self):
        """first=6, second=4: 4 > 6*0.5=3.0 → reject (cascade still active)."""
        tracker = RollingVolumeTracker()
        symbol = "DOGEUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        _add_burst_events(tracker, symbol, now, first_half_count=6, second_half_count=4)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is None


class TestExhaustionGatePasses:
    """Signal should pass when first_half >= 3 AND second_half <= first_half * 0.5."""

    def test_strong_decline_emits_signal(self):
        """first=8, second=2: 2 <= 8*0.5=4.0 → passes exhaustion gate."""
        tracker = RollingVolumeTracker()
        symbol = "BTCUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        _add_burst_events(tracker, symbol, now, first_half_count=8, second_half_count=2)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is not None
        assert signal.symbol == symbol
        assert signal.fade_direction in ("LONG", "SHORT")

    def test_exact_half_boundary_emits_signal(self):
        """first=6, second=3: 3 <= 6*0.5=3.0 → passes (boundary case, <= not <)."""
        tracker = RollingVolumeTracker()
        symbol = "ETHUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        _add_burst_events(tracker, symbol, now, first_half_count=6, second_half_count=3)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is not None

    def test_zero_second_half_emits_signal(self):
        """first=8, second=0: cascade completely stopped → passes."""
        tracker = RollingVolumeTracker()
        symbol = "XRPUSDT"
        now = time.time()

        _seed_baseline(tracker, symbol, now, count=50)
        _add_burst_events(tracker, symbol, now, first_half_count=8, second_half_count=0)

        signal = tracker.check_for_signal(symbol, now)
        assert signal is not None


# ─── 2. ATR Corruption Guard Tests ───

class TestATRTrClamp:
    """TR should be clamped when it exceeds 5% of price (or 3x current ATR)."""

    def test_extreme_tr_clamped_to_5pct(self):
        """A single massive TR (e.g., 20% of price) should be clamped to 5%."""
        calc = ATRCalculator(period=1)  # period=1 so ATR returns after 1 sample

        # First update: normal candle at price ~100
        calc.update(high=101.0, low=99.0, close=100.0)
        atr_after_normal = calc.get()
        assert atr_after_normal is not None
        # TR = 101-99 = 2.0 on a $100 asset (2%) — below 5% cap, no clamping
        assert atr_after_normal == pytest.approx(2.0, abs=0.01)

        # Second update: extreme spike — high=125, low=100 (25% range!)
        # mid_price = 112.5, TR = 25.0, tr_cap = max(112.5*0.05, 2.0*3) = max(5.625, 6.0) = 6.0
        calc.update(high=125.0, low=100.0, close=110.0)
        atr_after_spike = calc.get()
        assert atr_after_spike is not None
        # TR 25.0 should have been clamped to 6.0 (3x prior ATR)
        # ATR = EMA(6.0) given alpha = 2/(1+1) = 1.0 for period=1 → ATR = 6.0
        # But then 10% clamp: mid=112.5, 10%=11.25 → 6.0 < 11.25, no second clamp
        assert atr_after_spike < 7.0  # Clamped — without guard would be ~25.0

    def test_tr_clamp_on_first_sample_uses_5pct(self):
        """When _atr is None (first sample), tr_cap = mid_price * 0.05."""
        calc = ATRCalculator(period=1)

        # First (and only) candle: massive range on $1000 asset
        # TR = 1200 - 800 = 400, mid = 1000, cap = 1000 * 0.05 = 50
        calc.update(high=1200.0, low=800.0, close=1000.0)
        atr = calc.get()
        assert atr is not None
        # Should be clamped to 50.0 (5% of $1000), not 400.0
        assert atr == pytest.approx(50.0, abs=0.1)


class TestATRPriceClamp:
    """ATR should be clamped at 10% of price."""

    def test_atr_capped_at_10pct(self):
        """If ATR accumulates above 10% of price, clamp it down."""
        calc = ATRCalculator(period=1)

        # Feed many high-TR candles to push ATR up.
        # Each candle: 5% TR (at the TR cap), so ATR accumulates near 5%.
        # Then feed one candle where mid_price drops drastically,
        # making 10% of mid_price < current ATR.
        for _ in range(5):
            calc.update(high=105.0, low=100.0, close=102.0)

        # Now a candle where price is much lower — ATR from $100 range applied to $20 asset
        # mid_price = 20, 10% = 2.0. If ATR > 2.0, it gets clamped to 2.0
        calc.update(high=21.0, low=19.0, close=20.0)
        atr = calc.get()
        assert atr is not None
        assert atr <= 20.0 * 0.10 + 0.01  # ATR <= 10% of mid_price ($2.00)


class TestATRNormalOperation:
    """Normal candles (small TR relative to price) should not be affected by clamps."""

    def test_small_tr_not_clamped(self):
        """0.5% candle range on a $50000 asset — well below 5% TR cap."""
        calc = ATRCalculator(period=3)

        # BTC-like: price ~50000, candle range ~250 (0.5%)
        values = [
            (50125, 49875, 50000),
            (50200, 49900, 50100),
            (50150, 49850, 50050),
        ]
        for h, l, c in values:
            result = calc.update(high=h, low=l, close=c)

        atr = calc.get()
        assert atr is not None
        # ATR should be close to the actual true ranges (~250-300), not clamped
        assert 200.0 < atr < 350.0

    def test_normal_progression_stable(self):
        """ATR from consistent candles converges to the true range."""
        calc = ATRCalculator(period=5)

        # 10 consistent candles with TR = 2.0 on a $100 asset (2% — below 5% cap)
        for _ in range(10):
            calc.update(high=101.0, low=99.0, close=100.0)

        atr = calc.get()
        assert atr is not None
        # Should converge near 2.0 (the constant true range)
        assert atr == pytest.approx(2.0, abs=0.3)
