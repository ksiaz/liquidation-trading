"""
Unit tests for ROLLING_FADE entry quality gates.

Tests the three quality gates restored to prevent bad entries:
1. Warmup: MIN_BASELINE_EVENTS=30 — need baseline history before signaling
2. Burst concentration: events must be clustered in 10s sub-window, not spread
3. Exhaustion gate: always required (no fast path bypass)
4. Min liq count gate at entry path level
"""

import time

import pytest

from runtime.liquidations.rolling_volume_tracker import RollingVolumeTracker


def _add_baseline(tracker: RollingVolumeTracker, symbol: str, n: int, ts: float):
    """Add n events spread evenly over 60 minutes before ts."""
    interval = 3600.0 / n
    for i in range(n):
        event_ts = ts - 3600 + i * interval
        tracker.add_event(symbol, "LONG", 100.0, 1.0, event_ts)


def _add_burst(tracker: RollingVolumeTracker, symbol: str, n: int, ts: float,
               spread: float = 2.0, side: str = "LONG"):
    """Add n events in burst window. spread controls total span in seconds."""
    interval = spread / max(n - 1, 1)
    for i in range(n):
        event_ts = ts - spread + i * interval
        tracker.add_event(symbol, side, 100.0, 10.0, event_ts)


class TestWarmupGate:
    """MIN_BASELINE_EVENTS prevents signals with insufficient history."""

    def test_no_baseline_blocks(self):
        """5 burst events with 0 baseline → no signal."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_burst(t, "BTCUSDT", 5, now)
        assert t.check_for_signal("BTCUSDT", now) is None

    def test_insufficient_baseline_blocks(self):
        """5 burst events with 20 baseline events (< 30 required) → no signal."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 20, now - 30)  # 20 baseline events outside burst
        _add_burst(t, "BTCUSDT", 7, now, spread=3.0)
        assert t.check_for_signal("BTCUSDT", now) is None

    def test_sufficient_baseline_allows(self):
        """7 burst events with 40 baseline events → signal (if other gates pass)."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)  # 40 baseline = enough
        # Concentrated burst: 7 events in 3 seconds, first 15s of window
        # so exhaustion gate passes (first_half > second_half)
        burst_start = now - 25  # Well within first half of 30s window
        for i in range(7):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, burst_start + i * 0.5)
        sig = t.check_for_signal("BTCUSDT", now)
        assert sig is not None

    def test_is_warmed_up_reflects_threshold(self):
        """is_warmed_up() uses MIN_BASELINE_EVENTS."""
        t = RollingVolumeTracker()
        now = time.time()
        assert not t.is_warmed_up("BTCUSDT")
        for i in range(29):
            t.add_event("BTCUSDT", "LONG", 100.0, 1.0, now - 3600 + i * 120)
        assert not t.is_warmed_up("BTCUSDT")
        t.add_event("BTCUSDT", "LONG", 100.0, 1.0, now - 60)
        assert t.is_warmed_up("BTCUSDT")


class TestBurstConcentration:
    """Events must be clustered in a dense sub-window, not evenly spread."""

    def test_spread_events_blocked(self):
        """5 events spread evenly over 30s (one every 6s) → blocked."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)
        # Add 5 events spread evenly over 25 seconds (one every ~6s)
        for i in range(5):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 25 + i * 6)
        assert t.check_for_signal("BTCUSDT", now) is None

    def test_clustered_events_pass(self):
        """7 events clustered in 3s (all in first half for exhaustion gate) → signal."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)
        # All events in first half (25s ago) and within 3 seconds
        burst_start = now - 25
        for i in range(7):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, burst_start + i * 0.4)
        sig = t.check_for_signal("BTCUSDT", now)
        assert sig is not None

    def test_concentration_min_3(self):
        """min_concentrated is at least 3, even for 5 events (5 * 0.6 = 3)."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)
        # 5 events spread 6s apart — no 10s sub-window has >= 3 events
        # best sub-window: 2 events → blocked (need 3)
        t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 28)
        t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 22)
        t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 16)
        t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 10)
        t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 4)
        assert t.check_for_signal("BTCUSDT", now) is None


class TestExhaustionGateAlwaysApplied:
    """Exhaustion gate (declining cascade) must always apply — no fast path bypass."""

    def test_accelerating_cascade_blocked(self):
        """More events in second half than first → blocked, even at high ratio."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)
        # All events in second half (recent 15s) — accelerating
        burst_start = now - 10
        for i in range(8):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, burst_start + i * 0.5)
        assert t.check_for_signal("BTCUSDT", now) is None

    def test_declining_cascade_passes(self):
        """More events in first half → signal."""
        t = RollingVolumeTracker()
        now = time.time()
        _add_baseline(t, "BTCUSDT", 40, now - 30)
        # 5 events in first half, 2 events in second half
        for i in range(5):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 25 + i * 0.5)
        for i in range(2):
            t.add_event("BTCUSDT", "LONG", 100.0, 10.0, now - 5 + i * 0.5)
        sig = t.check_for_signal("BTCUSDT", now)
        assert sig is not None

    def test_no_fast_path_attribute(self):
        """FAST_PATH_RATIO should not exist on the class."""
        assert not hasattr(RollingVolumeTracker, 'FAST_PATH_RATIO')


class TestMinLiqCountGate:
    """Min liq count gate at entry path level (cascade_sniper.py)."""

    def test_low_liq_count_blocked(self):
        """Signal with 2 liq events should be blocked by entry path."""
        from unittest.mock import patch
        from external_policy.ep2_strategy_cascade_sniper import (
            EntryMode, PermissionOutput, StrategyContext,
            generate_cascade_sniper_proposal,
        )
        from runtime.liquidations.rolling_volume_tracker import RollingFadeSignal

        ts = time.time()
        signal = RollingFadeSignal(
            symbol="WLDUSDT", spike_volume=1000, z_score=15.0,
            short_liq_volume=800, long_liq_volume=200,
            liq_count=2,  # Below default min of 3
            spike_ts=ts, confirmation_ts=ts, fade_direction="SHORT",
        )
        with patch(
            "external_policy.ep2_strategy_cascade_sniper._check_warmup_gate",
            return_value=(True, "test"),
        ):
            result = generate_cascade_sniper_proposal(
                permission=PermissionOutput(
                    result="ALLOWED", mandate_id="t", action_id="t",
                    reason_code="t", timestamp=ts,
                ),
                proximity=None, liquidations=None,
                context=StrategyContext(context_id="t", timestamp=ts),
                entry_mode=EntryMode.ROLLING_FADE,
                rolling_fade_signal=signal,
                price_returns={"ret_1m": -0.002},
            )
        assert result is None

    def test_adequate_liq_count_passes(self):
        """Signal with 5 liq events should pass."""
        from unittest.mock import patch
        from external_policy.ep2_strategy_cascade_sniper import (
            EntryMode, PermissionOutput, StrategyContext,
            generate_cascade_sniper_proposal,
        )
        from runtime.liquidations.rolling_volume_tracker import RollingFadeSignal

        ts = time.time()
        signal = RollingFadeSignal(
            symbol="WLDUSDT", spike_volume=1000, z_score=15.0,
            short_liq_volume=800, long_liq_volume=200,
            liq_count=5,  # Above default min of 3
            spike_ts=ts, confirmation_ts=ts, fade_direction="SHORT",
        )
        with patch(
            "external_policy.ep2_strategy_cascade_sniper._check_warmup_gate",
            return_value=(True, "test"),
        ):
            result = generate_cascade_sniper_proposal(
                permission=PermissionOutput(
                    result="ALLOWED", mandate_id="t", action_id="t",
                    reason_code="t", timestamp=ts,
                ),
                proximity=None, liquidations=None,
                context=StrategyContext(context_id="t", timestamp=ts),
                entry_mode=EntryMode.ROLLING_FADE,
                rolling_fade_signal=signal,
                price_returns={"ret_1m": -0.002},
            )
        assert result is not None
        assert result.confidence == "ROLLING_FADE"


class TestOPExcluded:
    """OP should be in EXHAUSTION_FADE_EXCLUDED_COINS (0W/3L cascade)."""

    def test_op_excluded(self):
        from external_policy.ep2_strategy_cascade_sniper import EXHAUSTION_FADE_EXCLUDED_COINS
        assert "OP" in EXHAUSTION_FADE_EXCLUDED_COINS
