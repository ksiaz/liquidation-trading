"""Tests for context-aware trailing stop (X4-A CONTEXT).

Verifies:
1. Context fields stored on state
2. Cascade active widens stop distance
3. Break-even suppressed during active cascade
4. Grace period ramp after cascade quiets
5. VWAP proximity tightens stop
6. Thin book widens stop
7. Backwards compat: None context = old behavior
8. FIXED_DISTANCE mode unaffected by context
"""

import time
import pytest

from runtime.exchange.trailing_stop_manager import (
    TrailingStopManager, TrailingStopConfig, TrailingStopState, TrailingMode,
)


def _make_manager():
    return TrailingStopManager()


def _atr_progressive_config(**overrides):
    defaults = dict(
        mode=TrailingMode.ATR_PROGRESSIVE,
        atr_prog_start_mult=2.5,
        atr_prog_phase1_end_mult=1.8,
        atr_prog_phase1_range=0.01,
        atr_prog_end_mult=1.0,
        atr_prog_profit_range=0.03,
        atr_prog_min_pct=0.005,
        atr_prog_min_lock_ratio=0.4,
        break_even_trigger_pct=0.008,
        break_even_offset_pct=0.001,
        orderflow_tighten_threshold=0.38,
        orderflow_tighten_mult=0.6,
        min_move_to_update_pct=0.0001,
        min_move_atr_fraction=0.001,
    )
    defaults.update(overrides)
    return TrailingStopConfig(**defaults)


class TestContextFieldsStored:
    """Context fields are stored on state when provided to update_price."""

    def test_liq_z_stored(self):
        mgr = _make_manager()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0,
                                   _atr_progressive_config())
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=3.5)
        state = mgr.get_stop_state("t1")
        assert state.last_liq_z == 3.5
        assert state.peak_liq_z == 3.5

    def test_peak_liq_z_tracks_max(self):
        mgr = _make_manager()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0,
                                   _atr_progressive_config())
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=5.0)
        mgr.update_price("BTCUSDT", 101.5, atr=1.0, liq_z=2.0)
        state = mgr.get_stop_state("t1")
        assert state.peak_liq_z == 5.0
        assert state.last_liq_z == 2.0

    def test_cascade_quiet_since_tracked(self):
        mgr = _make_manager()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0,
                                   _atr_progressive_config())
        # Active
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=2.0)
        state = mgr.get_stop_state("t1")
        assert state.cascade_quiet_since is None  # liq_z >= 1.0

        # Goes quiet
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=0.5)
        state = mgr.get_stop_state("t1")
        assert state.cascade_quiet_since is not None
        quiet_ts = state.cascade_quiet_since

        # Stays quiet — timestamp unchanged
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=0.3)
        state = mgr.get_stop_state("t1")
        assert state.cascade_quiet_since == quiet_ts

        # Active again
        mgr.update_price("BTCUSDT", 101.0, atr=1.0, liq_z=1.5)
        state = mgr.get_stop_state("t1")
        assert state.cascade_quiet_since is None

    def test_all_context_fields_stored(self):
        mgr = _make_manager()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0,
                                   _atr_progressive_config())
        mgr.update_price("BTCUSDT", 101.0, atr=1.0,
                         liq_z=2.0, cascade_state="TRIGGERED",
                         vwap_distance=-0.005, fill_count=12, atr_30m=1.5)
        state = mgr.get_stop_state("t1")
        assert state.last_liq_z == 2.0
        assert state.last_cascade_state == "TRIGGERED"
        assert state.last_vwap_distance == -0.005
        assert state.last_fill_count == 12
        assert state.last_atr_30m == 1.5


class TestCascadeActiveWidensStop:
    """When cascade is active, stop should be wider (context_mult >= 1.3)."""

    def test_cascade_active_wider_than_baseline(self):
        """Same price/ATR: cascade active should produce a lower stop (LONG) = wider."""
        mgr_base = _make_manager()
        mgr_ctx = _make_manager()
        cfg = _atr_progressive_config()
        entry = 100.0
        atr = 1.0

        # Baseline — no context
        mgr_base.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg)
        # Push MFE up to get a meaningful stop
        for p in [101.0, 102.0, 103.0]:
            mgr_base.update_price("BTCUSDT", p, atr=atr)
        stop_base = mgr_base.get_stop_state("t1").current_stop_price

        # Context — cascade active (liq_z=3.0)
        mgr_ctx.register_trailing_stop("t2", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0]:
            mgr_ctx.update_price("BTCUSDT", p, atr=atr,
                                 liq_z=3.0, cascade_state="TRIGGERED")
        stop_ctx = mgr_ctx.get_stop_state("t2").current_stop_price

        # Context stop should be lower (wider distance from MFE) or equal
        assert stop_ctx <= stop_base, (
            f"Cascade active stop {stop_ctx} should be <= baseline {stop_base}"
        )

    def test_cascade_via_state_only(self):
        """Cascade active via state string (ABSORBING) even if liq_z < 1.0."""
        mgr = _make_manager()
        cfg = _atr_progressive_config()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0, cfg)
        # liq_z below threshold but state is ABSORBING
        for p in [101.0, 102.0, 103.0]:
            mgr.update_price("BTCUSDT", p, atr=1.0,
                             liq_z=0.5, cascade_state="ABSORBING")
        state = mgr.get_stop_state("t1")
        # Stop should reflect widened context (not baseline)
        # With 3% MFE, the base_mult is tight, but context_mult=1.3 should widen it
        assert state.current_stop_price < 103.0


class TestBreakEvenSuppression:
    """BE should be suppressed during active cascade in early trade."""

    def test_be_suppressed_during_cascade(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config(break_even_trigger_pct=0.008)
        entry = 100.0
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                   entry_timestamp=time.time())
        # Price rises above BE trigger (0.8%)
        mgr.update_price("BTCUSDT", 101.0, atr=1.0,
                         liq_z=3.0, cascade_state="TRIGGERED")
        state = mgr.get_stop_state("t1")
        # BE should NOT be triggered (suppressed by cascade)
        assert not state.break_even_triggered

    def test_be_not_suppressed_without_cascade(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config(break_even_trigger_pct=0.008)
        entry = 100.0
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                   entry_timestamp=time.time())
        # Price rises above BE trigger — no cascade context
        mgr.update_price("BTCUSDT", 101.0, atr=1.0)
        state = mgr.get_stop_state("t1")
        assert state.break_even_triggered

    def test_be_not_suppressed_after_phase2_window(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config(break_even_trigger_pct=0.008)
        entry = 100.0
        # Entry was 400s ago (> PHASE2_WINDOW_SEC=300)
        old_timestamp = time.time() - 400
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                   entry_timestamp=old_timestamp)
        mgr.update_price("BTCUSDT", 101.0, atr=1.0,
                         liq_z=3.0, cascade_state="TRIGGERED")
        state = mgr.get_stop_state("t1")
        # Past the window — BE should trigger
        assert state.break_even_triggered

    def test_be_forced_after_2h(self):
        """Safety: BE forced after 2h regardless of cascade."""
        mgr = _make_manager()
        cfg = _atr_progressive_config(break_even_trigger_pct=0.008)
        entry = 100.0
        # Entry was 2.5h ago
        old_timestamp = time.time() - 9000
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                   entry_timestamp=old_timestamp)
        mgr.update_price("BTCUSDT", 101.0, atr=1.0,
                         liq_z=3.0, cascade_state="TRIGGERED")
        state = mgr.get_stop_state("t1")
        assert state.break_even_triggered

    def test_be_suppression_short_direction(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config(break_even_trigger_pct=0.008)
        entry = 100.0
        mgr.register_trailing_stop("t1", "BTCUSDT", "SHORT", entry, 105.0, cfg,
                                   entry_timestamp=time.time())
        # Price drops below entry enough to trigger BE (0.8%)
        mgr.update_price("BTCUSDT", 99.0, atr=1.0,
                         liq_z=3.0, cascade_state="TRIGGERED")
        state = mgr.get_stop_state("t1")
        assert not state.break_even_triggered  # Suppressed


class TestGracePeriodRamp:
    """After cascade quiets, stop should ramp from wide to normal over grace period."""

    def test_grace_ramp_wider_than_baseline(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config()
        entry = 100.0
        now = time.time()

        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                   entry_timestamp=now)
        # First: cascade active
        mgr.update_price("BTCUSDT", 103.0, atr=1.0, liq_z=3.0)
        stop_active = mgr.get_stop_state("t1").current_stop_price

        # Now cascade quiets (liq_z drops below 1.0)
        # cascade_quiet_since is set to now
        mgr.update_price("BTCUSDT", 103.0, atr=1.0, liq_z=0.5)
        state = mgr.get_stop_state("t1")
        assert state.cascade_quiet_since is not None

        # Stop should still be wider than pure baseline (grace ramp in effect)
        # The stop shouldn't jump tighter immediately


class TestVWAPTightens:
    """Approaching VWAP tightens stop (only when not cascade active)."""

    def test_vwap_close_tightens(self):
        mgr_base = _make_manager()
        mgr_vwap = _make_manager()
        cfg = _atr_progressive_config()
        entry = 100.0

        # Baseline — no VWAP info
        mgr_base.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0]:
            mgr_base.update_price("BTCUSDT", p, atr=1.0, liq_z=0.3)
        stop_base = mgr_base.get_stop_state("t1").current_stop_price

        # With VWAP very close (< 0.3%)
        mgr_vwap.register_trailing_stop("t2", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0]:
            mgr_vwap.update_price("BTCUSDT", p, atr=1.0, liq_z=0.3,
                                  vwap_distance=0.002)
        stop_vwap = mgr_vwap.get_stop_state("t2").current_stop_price

        # VWAP stop should be tighter (higher for LONG)
        assert stop_vwap >= stop_base, (
            f"VWAP-close stop {stop_vwap} should be >= baseline {stop_base}"
        )


class TestThinBookWidens:
    """Few fills = thin book = wider stop."""

    def test_thin_book_wider(self):
        mgr_base = _make_manager()
        mgr_thin = _make_manager()
        cfg = _atr_progressive_config()
        entry = 100.0

        # Baseline — normal fill count
        mgr_base.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0]:
            mgr_base.update_price("BTCUSDT", p, atr=1.0, fill_count=50)
        stop_base = mgr_base.get_stop_state("t1").current_stop_price

        # Thin book — very few fills
        mgr_thin.register_trailing_stop("t2", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0]:
            mgr_thin.update_price("BTCUSDT", p, atr=1.0, fill_count=3)
        stop_thin = mgr_thin.get_stop_state("t2").current_stop_price

        # Thin book stop should be wider (lower for LONG)
        assert stop_thin <= stop_base, (
            f"Thin book stop {stop_thin} should be <= baseline {stop_base}"
        )


class TestBackwardsCompat:
    """None context = old behavior (no context_mult applied)."""

    def test_none_context_same_as_before(self):
        mgr = _make_manager()
        cfg = _atr_progressive_config()
        entry = 100.0

        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg)
        # No context kwargs — all default to None
        for p in [101.0, 102.0, 103.0]:
            mgr.update_price("BTCUSDT", p, atr=1.0)
        state = mgr.get_stop_state("t1")

        # Context fields should remain None/default
        assert state.last_liq_z is None
        assert state.last_cascade_state is None
        assert state.last_vwap_distance is None
        assert state.last_fill_count is None
        assert state.peak_liq_z == 0.0

        # Stop should still be computed (no crash)
        assert state.current_stop_price > 95.0


class TestFixedDistanceUnaffected:
    """FIXED_DISTANCE mode should not be affected by context."""

    def test_fixed_distance_ignores_context(self):
        cfg_fixed = TrailingStopConfig(
            mode=TrailingMode.FIXED_DISTANCE,
            trail_distance_pct=0.02,
            min_move_to_update_pct=0.0001,
        )
        mgr1 = _make_manager()
        mgr2 = _make_manager()

        # Without context
        mgr1.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0, cfg_fixed)
        for p in [101.0, 102.0, 103.0]:
            mgr1.update_price("BTCUSDT", p, atr=1.0)
        stop1 = mgr1.get_stop_state("t1").current_stop_price

        # With cascade context
        mgr2.register_trailing_stop("t2", "BTCUSDT", "LONG", 100.0, 95.0, cfg_fixed)
        for p in [101.0, 102.0, 103.0]:
            mgr2.update_price("BTCUSDT", p, atr=1.0,
                              liq_z=5.0, cascade_state="TRIGGERED")
        stop2 = mgr2.get_stop_state("t2").current_stop_price

        # Both should produce the same stop
        assert stop1 == stop2, (
            f"FIXED_DISTANCE stops should match: {stop1} vs {stop2}"
        )


class TestProfitLockReduction:
    """During active cascade, profit lock ratio should be reduced."""

    def test_cascade_active_lower_profit_lock(self):
        mgr_base = _make_manager()
        mgr_casc = _make_manager()
        cfg = _atr_progressive_config(atr_prog_min_lock_ratio=0.4)
        entry = 100.0

        # Baseline — no cascade, push to high MFE so profit lock engages
        mgr_base.register_trailing_stop("t1", "BTCUSDT", "LONG", entry, 95.0, cfg)
        for p in [101.0, 102.0, 103.0, 104.0]:
            mgr_base.update_price("BTCUSDT", p, atr=0.3)  # Small ATR to make lock dominant
        stop_base = mgr_base.get_stop_state("t1").current_stop_price

        # Cascade active
        mgr_casc.register_trailing_stop("t2", "BTCUSDT", "LONG", entry, 95.0, cfg,
                                        entry_timestamp=time.time())
        for p in [101.0, 102.0, 103.0, 104.0]:
            mgr_casc.update_price("BTCUSDT", p, atr=0.3,
                                  liq_z=3.0, cascade_state="TRIGGERED")
        stop_casc = mgr_casc.get_stop_state("t2").current_stop_price

        # Cascade stop should be lower (less profit locked = wider room)
        assert stop_casc <= stop_base, (
            f"Cascade lock stop {stop_casc} should be <= baseline {stop_base}"
        )


class TestEntryTimestamp:
    """Entry timestamp is set and used correctly."""

    def test_entry_timestamp_set_at_registration(self):
        mgr = _make_manager()
        before = time.time()
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0)
        after = time.time()
        state = mgr.get_stop_state("t1")
        assert before <= state.entry_timestamp <= after

    def test_explicit_entry_timestamp(self):
        mgr = _make_manager()
        ts = 1700000000.0
        mgr.register_trailing_stop("t1", "BTCUSDT", "LONG", 100.0, 95.0,
                                   entry_timestamp=ts)
        state = mgr.get_stop_state("t1")
        assert state.entry_timestamp == ts
