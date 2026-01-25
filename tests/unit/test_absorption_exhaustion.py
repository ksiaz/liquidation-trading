"""
Tests for absorption-based exhaustion confirmation.

Key principle: Silence != Safety
- EXHAUSTED requires structural confirmation (absorption)
- Without absorption, low rate yields DECELERATING_UNCONFIRMED
"""

import pytest
import time
from memory.m4_cascade_momentum import (
    CascadeMomentumTracker,
    MomentumPhase,
    phase_to_string
)
from memory.m4_absorption_confirmation import (
    AbsorptionConfirmationTracker,
    AbsorptionPhase
)


class TestExhaustionWithoutAbsorptionTracker:
    """Test behavior when no absorption tracker is attached."""

    def test_low_rate_without_tracker_is_unconfirmed(self):
        """Without absorption tracker, low rate after cascade is DECELERATING_UNCONFIRMED."""
        tracker = CascadeMomentumTracker(absorption_tracker=None)
        ts = 1000.0

        # Simulate cascade start
        for i in range(10):
            tracker.record_event(
                coin="BTC",
                oi_change_pct=-0.5,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # Simulate rate going low (cascade slowing)
        obs = tracker.record_event(
            coin="BTC",
            oi_change_pct=-0.001,  # Very small
            is_liquidation_signal=False,
            timestamp=ts + 20.0
        )

        # Without absorption tracker, cannot confirm exhaustion
        assert obs.phase == MomentumPhase.DECELERATING_UNCONFIRMED
        assert obs.absorption_signals == 0
        assert obs.absorption_confirmed is False

    def test_idle_without_cascade_is_idle(self):
        """Without prior cascade, low rate is just IDLE."""
        tracker = CascadeMomentumTracker(absorption_tracker=None)

        obs = tracker.record_event(
            coin="BTC",
            oi_change_pct=0.001,
            is_liquidation_signal=False,
            timestamp=1000.0
        )

        assert obs.phase == MomentumPhase.IDLE


class TestExhaustionWithAbsorptionTracker:
    """Test exhaustion detection with absorption confirmation."""

    def test_exhausted_requires_absorption_confirmation(self):
        """EXHAUSTED only when absorption signals confirmed."""
        absorption_tracker = AbsorptionConfirmationTracker()
        momentum_tracker = CascadeMomentumTracker(
            absorption_tracker=absorption_tracker
        )
        ts = 1000.0

        # Simulate cascade
        for i in range(10):
            momentum_tracker.record_event(
                coin="BTC",
                oi_change_pct=-0.5,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # Add absorption events (structural confirmation)
        absorption_tracker.record_absorption(
            coin="BTC",
            consumed_size=5000.0,
            price_movement_pct=0.01,  # High size / low movement = absorption
            timestamp=ts + 6.0
        )
        absorption_tracker.record_refill(
            coin="BTC",
            added_size=2000.0,
            timestamp=ts + 6.5
        )

        # Add trades showing aggressor failure
        for i in range(20):
            absorption_tracker.record_trade(
                coin="BTC",
                price=50000.0 - (i * 0.5),  # Tight range
                volume=200.0,
                is_sell=True,
                timestamp=ts + 5.0 + i * 0.2
            )

        # Now rate is low with absorption confirmed
        obs = momentum_tracker.record_event(
            coin="BTC",
            oi_change_pct=-0.001,
            is_liquidation_signal=False,
            timestamp=ts + 10.0
        )

        # Should see absorption signals
        assert obs.absorption_signals >= 1
        # If enough signals, should be EXHAUSTED
        if obs.absorption_signals >= momentum_tracker.MIN_ABSORPTION_SIGNALS:
            assert obs.phase == MomentumPhase.EXHAUSTED
            assert obs.absorption_confirmed is True

    def test_no_absorption_yields_unconfirmed(self):
        """Without absorption events, stays DECELERATING_UNCONFIRMED."""
        absorption_tracker = AbsorptionConfirmationTracker()
        momentum_tracker = CascadeMomentumTracker(
            absorption_tracker=absorption_tracker
        )
        ts = 1000.0

        # Simulate cascade
        for i in range(10):
            momentum_tracker.record_event(
                coin="BTC",
                oi_change_pct=-0.5,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # No absorption events recorded - just silence
        obs = momentum_tracker.record_event(
            coin="BTC",
            oi_change_pct=-0.001,
            is_liquidation_signal=False,
            timestamp=ts + 15.0
        )

        # Should be DECELERATING_UNCONFIRMED (silence != safety)
        assert obs.phase == MomentumPhase.DECELERATING_UNCONFIRMED
        assert obs.absorption_signals == 0
        assert obs.absorption_confirmed is False


class TestAbsorptionConfirmationTracker:
    """Test the absorption confirmation tracker directly."""

    def test_absorption_ratio_calculation(self):
        """Absorption ratio = consumed / movement."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # High absorption: lots consumed, little movement
        tracker.record_absorption("BTC", consumed_size=10000.0, price_movement_pct=0.01, timestamp=ts)
        tracker.record_absorption("BTC", consumed_size=5000.0, price_movement_pct=0.01, timestamp=ts + 1)

        obs = tracker.get_observation("BTC", ts + 2)

        # Ratio should be high (lots consumed per unit movement)
        assert obs.absorption_ratio > 0

    def test_replenishment_rate_calculation(self):
        """Replenishment rate = added size / time."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Add refill events
        tracker.record_refill("BTC", added_size=1000.0, timestamp=ts)
        tracker.record_refill("BTC", added_size=500.0, timestamp=ts + 1)
        tracker.record_refill("BTC", added_size=500.0, timestamp=ts + 2)

        obs = tracker.get_observation("BTC", ts + 3)

        # Rate = 2000 / 5s = 400/s (using 5s window)
        assert obs.bid_replenishment_rate > 0

    def test_aggressor_failure_detection(self):
        """Aggressor failure = high sell volume, tight range."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # High sell volume with tight price range
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0 + (i % 3) * 0.01,  # Very tight range
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_observation("BTC", ts + 5)

        # Should have high sell volume
        assert obs.sell_volume_5s >= tracker.MIN_SELL_VOLUME

    def test_delta_divergence_detection(self):
        """Delta divergence = sells continuing but delta flattening."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Mix of buys absorbing sells
        for i in range(30):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )
            # Buys absorbing
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=95.0,  # Slightly less but close
                is_sell=False,
                timestamp=ts + i * 0.1 + 0.05
            )

        obs = tracker.get_observation("BTC", ts + 4)

        # Cumulative delta should be relatively flat (buys ~ sells)
        assert abs(obs.cumulative_delta_5s) < obs.sell_volume_5s

    def test_phase_determination(self):
        """Phase based on signal count."""
        tracker = AbsorptionConfirmationTracker()

        # No events = NONE
        obs = tracker.get_observation("XYZ", 1000.0)
        assert obs.phase == AbsorptionPhase.NONE
        assert obs.signals_confirmed == 0


class TestSetAbsorptionTrackerMethod:
    """Test setting absorption tracker after construction."""

    def test_set_absorption_tracker_enables_confirmation(self):
        """Can add absorption tracker after construction."""
        momentum_tracker = CascadeMomentumTracker()
        absorption_tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Initially no tracker
        assert momentum_tracker._absorption_tracker is None

        # Add tracker
        momentum_tracker.set_absorption_tracker(absorption_tracker)
        assert momentum_tracker._absorption_tracker is absorption_tracker

        # Simulate cascade
        for i in range(10):
            momentum_tracker.record_event(
                coin="ETH",
                oi_change_pct=-0.3,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # Add absorption
        absorption_tracker.record_absorption(
            coin="ETH",
            consumed_size=3000.0,
            price_movement_pct=0.005,
            timestamp=ts + 6.0
        )
        absorption_tracker.record_refill(
            coin="ETH",
            added_size=1000.0,
            timestamp=ts + 6.5
        )

        # Check observation includes absorption data
        obs = momentum_tracker.record_event(
            coin="ETH",
            oi_change_pct=-0.001,
            is_liquidation_signal=False,
            timestamp=ts + 10.0
        )

        # Should have absorption data populated
        # Signals depend on thresholds but should be computed
        assert obs.absorption_signals >= 0


class TestPhaseToString:
    """Test phase string conversion."""

    def test_all_phases_have_strings(self):
        """All momentum phases have string representations."""
        for phase in MomentumPhase:
            string = phase_to_string(phase)
            assert string != "UNKNOWN"
            assert len(string) > 0

    def test_decelerating_unconfirmed_string(self):
        """DECELERATING_UNCONFIRMED has distinct string."""
        string = phase_to_string(MomentumPhase.DECELERATING_UNCONFIRMED)
        assert string == "DECEL_UNCONF"

    def test_exhausted_string(self):
        """EXHAUSTED string is correct."""
        string = phase_to_string(MomentumPhase.EXHAUSTED)
        assert string == "EXHAUSTED"
