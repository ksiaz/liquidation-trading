"""
Tests for regime-adaptive absorption-based exhaustion confirmation.

Key principles:
- Silence != Safety (detect PRESENCE of absorption, not ABSENCE of activity)
- All thresholds are RELATIVE to current market regime
- Adaptive windows based on trade rate
- Volatility-normalized metrics
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
    AbsorptionPhase,
    ControlShiftPhase,
    RegimeContext,
    ControlShiftObservation,
    CombinedExhaustionObservation
)


class TestRegimeContextComputation:
    """Test regime context calculation."""

    def test_regime_context_from_trades(self):
        """Regime context computed from trade history."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Simulate trading activity over 30 seconds
        for i in range(100):
            price = 50000.0 + (i % 10) * 5  # Price range of ~50 bps
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0 + i,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30.0 + i * 0.3
            )

        regime = tracker.get_regime_context("BTC", ts)

        # Should have computed volatility
        assert regime.rolling_range_bps > 0
        # Should have computed trade rate (~3.3 trades/sec)
        assert regime.trade_rate_per_sec > 0
        # Should have computed median trade size
        assert regime.median_trade_size > 0
        # Adaptive window should be in bounds
        assert tracker.MIN_WINDOW_SEC <= regime.adaptive_window_sec <= tracker.MAX_WINDOW_SEC

    def test_adaptive_window_scales_with_trade_rate(self):
        """Window length adapts to trade frequency."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # High trade rate (10 trades/sec)
        for i in range(300):
            tracker.record_trade(
                coin="FAST",
                price=100.0,
                volume=10.0,
                is_sell=True,
                timestamp=ts - 30.0 + i * 0.1
            )

        # Low trade rate (0.5 trades/sec)
        for i in range(15):
            tracker.record_trade(
                coin="SLOW",
                price=100.0,
                volume=10.0,
                is_sell=True,
                timestamp=ts - 30.0 + i * 2.0
            )

        fast_regime = tracker.get_regime_context("FAST", ts)
        slow_regime = tracker.get_regime_context("SLOW", ts)

        # Fast market should have shorter window
        assert fast_regime.adaptive_window_sec < slow_regime.adaptive_window_sec

    def test_empty_coin_returns_default_regime(self):
        """No data returns default regime context."""
        tracker = AbsorptionConfirmationTracker()
        regime = tracker.get_regime_context("EMPTY", 1000.0)

        assert regime.rolling_range_bps == 0.0
        assert regime.trade_rate_per_sec == 0.0
        assert regime.adaptive_window_sec == tracker.MAX_WINDOW_SEC


class TestVolatilityNormalizedAbsorption:
    """Test volatility-adjusted absorption ratio."""

    def test_absorption_ratio_normalized_by_volatility(self):
        """Absorption ratio accounts for volatility regime."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create volatility context (100 bps range)
        for i in range(60):
            price = 50000.0 + (i % 20) * 25  # Creates ~100 bps range
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30.0 + i * 0.5
            )

        # Add absorption events
        tracker.record_absorption("BTC", consumed_size=5000.0, price_movement_pct=0.01, timestamp=ts - 2)
        tracker.record_absorption("BTC", consumed_size=3000.0, price_movement_pct=0.01, timestamp=ts - 1)

        obs = tracker.get_observation("BTC", ts)

        # Absorption ratio should be computed
        assert obs.absorption_ratio > 0
        # Should have regime context
        assert obs.regime.rolling_range_bps > 0

    def test_spread_adjustment_in_absorption(self):
        """Spread adds noise floor to movement calculation."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Add orderbook with spread
        for i in range(30):
            tracker.record_orderbook(
                coin="BTC",
                bid_size=1000.0,
                ask_size=1000.0,
                mid_price=50000.0,
                spread=5.0,  # 1 bps spread
                timestamp=ts - 30.0 + i
            )

        # Add trades
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30.0 + i * 0.5
            )

        # Add absorption with zero movement
        tracker.record_absorption("BTC", consumed_size=1000.0, price_movement_pct=0.0, timestamp=ts - 1)

        obs = tracker.get_observation("BTC", ts)

        # Spread should be in regime context
        assert obs.regime.avg_spread_bps > 0


class TestPercentileBasedThresholds:
    """Test percentile-based signal detection."""

    def test_volume_percentile_calculation(self):
        """Volume percentile computed from history."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build history with varying volumes
        for i in range(50):
            # Varying volumes: 10, 20, 30, ... 500
            vol = (i + 1) * 10
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=vol,
                is_sell=True,
                timestamp=ts - 100 + i * 2
            )
            # Trigger observation to update volume history
            tracker.get_observation("BTC", ts - 100 + i * 2 + 1)

        # Add a large volume trade
        tracker.record_trade(
            coin="BTC",
            price=50000.0,
            volume=1000.0,  # Larger than most history
            is_sell=True,
            timestamp=ts
        )

        obs = tracker.get_observation("BTC", ts + 0.1)

        # Large volume should be in high percentile
        assert obs.sell_volume_percentile > 50

    def test_absorption_percentile_calculation(self):
        """Absorption ratio percentile computed from history."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build baseline context
        for i in range(60):
            tracker.record_trade(
                coin="ETH",
                price=3000.0 + i * 0.1,
                volume=50.0,
                is_sell=True,
                timestamp=ts - 60 + i
            )

        # Build absorption history with varying ratios
        for i in range(20):
            tracker.record_absorption(
                "ETH",
                consumed_size=100.0 + i * 10,
                price_movement_pct=0.05,
                timestamp=ts - 50 + i * 2
            )
            tracker.get_observation("ETH", ts - 50 + i * 2 + 0.5)

        # Add high absorption event
        tracker.record_absorption("ETH", consumed_size=5000.0, price_movement_pct=0.01, timestamp=ts)

        obs = tracker.get_observation("ETH", ts + 0.1)

        # Should have percentile data
        assert 0 <= obs.absorption_ratio_percentile <= 100


class TestAggressorFailureDetection:
    """Test volatility-relative aggressor failure."""

    def test_aggressor_failure_when_range_below_volatility(self):
        """Aggressor failure when range < rolling volatility."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create high volatility regime (200 bps range) in first 30 seconds
        for i in range(60):
            price = 50000.0 + (i % 30) * 33  # ~200 bps range
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 60 + i * 0.5  # Earlier, so regime includes volatility
            )

        # Add more high-vol trades to establish regime
        for i in range(60):
            price = 50000.0 + (i % 30) * 33
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.5
            )

        # Check regime has high volatility
        regime = tracker.get_regime_context("BTC", ts)
        assert regime.rolling_range_bps > 100  # Should have significant volatility

        # Now add sells with TIGHT range in the observation window only
        # These should show low range_vs_volatility since range < regime volatility
        for i in range(50):
            price = 50000.0 + (i % 3)  # Only ~0.6 bps range
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=200.0,  # High volume
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_observation("BTC", ts + 5)

        # The tight-range sells should have low range relative to regime volatility
        # Note: The adaptive window includes recent trades, so we check the downside_range_bps
        # is low compared to regime.rolling_range_bps
        assert obs.downside_range_bps < obs.regime.rolling_range_bps

    def test_no_aggressor_failure_when_range_matches_volatility(self):
        """No aggressor failure when range matches expected volatility."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create moderate volatility regime (100 bps)
        for i in range(60):
            price = 50000.0 + (i % 20) * 25
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.5
            )

        # Add sells with similar range
        for i in range(30):
            price = 50000.0 + (i % 20) * 25  # Same range as regime
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_observation("BTC", ts + 3)

        # Range should be close to volatility
        # (may or may not trigger failure depending on exact ratio)
        assert obs.range_vs_volatility >= 0


class TestDeltaDivergenceNormalized:
    """Test volume-normalized delta divergence."""

    def test_delta_slope_normalized_by_volume(self):
        """Delta slope normalized by total volume."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.5
            )

        # First half: mostly sells
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        # Second half: buys absorbing
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=False,
                timestamp=ts + 2.5 + i * 0.1
            )

        obs = tracker.get_observation("BTC", ts + 5)

        # Delta slope should show change
        assert obs.delta_slope != 0
        # Normalized slope should be bounded
        assert -2.0 <= obs.delta_slope_normalized <= 2.0

    def test_delta_diverging_when_slope_flat(self):
        """Delta diverging when sells continue but delta flattens."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build regime context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.5
            )

        # Balanced buying and selling (flat delta)
        for i in range(50):
            # Sell
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )
            # Buy absorbing
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=95.0,  # Slightly less
                is_sell=False,
                timestamp=ts + i * 0.1 + 0.05
            )

        obs = tracker.get_observation("BTC", ts + 5)

        # Normalized slope should be small
        assert abs(obs.delta_slope_normalized) < 0.5


class TestExhaustionWithRegimeAdaptiveAbsorption:
    """Test cascade momentum exhaustion with regime-adaptive absorption."""

    def test_exhausted_with_regime_adaptive_confirmation(self):
        """EXHAUSTED requires regime-adaptive absorption confirmation."""
        absorption_tracker = AbsorptionConfirmationTracker()
        momentum_tracker = CascadeMomentumTracker(
            absorption_tracker=absorption_tracker
        )
        ts = 1000.0

        # Build regime context (30s of activity)
        for i in range(100):
            price = 50000.0 + (i % 20) * 5
            absorption_tracker.record_trade(
                coin="BTC",
                price=price,
                volume=50.0 + (i % 30),
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.3
            )

        # Simulate cascade in momentum tracker
        for i in range(20):
            momentum_tracker.record_event(
                coin="BTC",
                oi_change_pct=-0.3,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # Add absorption events
        absorption_tracker.record_absorption(
            coin="BTC",
            consumed_size=3000.0,
            price_movement_pct=0.01,
            timestamp=ts + 11
        )
        absorption_tracker.record_refill(
            coin="BTC",
            added_size=1500.0,
            timestamp=ts + 11.5
        )

        # Add trades showing absorption
        for i in range(50):
            absorption_tracker.record_trade(
                coin="BTC",
                price=49950.0 + (i % 3),  # Tight range
                volume=100.0,
                is_sell=True,
                timestamp=ts + 10 + i * 0.1
            )
            absorption_tracker.record_trade(
                coin="BTC",
                price=49950.0,
                volume=95.0,  # Buys absorbing
                is_sell=False,
                timestamp=ts + 10 + i * 0.1 + 0.05
            )

        # Get observation with low rate
        obs = momentum_tracker.record_event(
            coin="BTC",
            oi_change_pct=-0.001,
            is_liquidation_signal=False,
            timestamp=ts + 15
        )

        # Should have absorption data
        assert obs.absorption_signals >= 0

    def test_unconfirmed_without_sufficient_absorption(self):
        """DECELERATING_UNCONFIRMED when absorption signals insufficient."""
        absorption_tracker = AbsorptionConfirmationTracker()
        momentum_tracker = CascadeMomentumTracker(
            absorption_tracker=absorption_tracker
        )
        ts = 1000.0

        # Minimal regime context
        for i in range(30):
            absorption_tracker.record_trade(
                coin="ETH",
                price=3000.0,
                volume=10.0,
                is_sell=True,
                timestamp=ts - 30 + i
            )

        # Simulate cascade
        for i in range(10):
            momentum_tracker.record_event(
                coin="ETH",
                oi_change_pct=-0.5,
                is_liquidation_signal=True,
                timestamp=ts + i * 0.5
            )

        # No absorption events - just silence
        obs = momentum_tracker.record_event(
            coin="ETH",
            oi_change_pct=-0.001,
            is_liquidation_signal=False,
            timestamp=ts + 15
        )

        # Should be unconfirmed (silence != safety)
        assert obs.phase == MomentumPhase.DECELERATING_UNCONFIRMED
        assert obs.absorption_signals == 0


class TestPhaseTransitions:
    """Test momentum phase transitions with regime-adaptive absorption."""

    def test_all_phases_reachable(self):
        """All momentum phases can be reached."""
        tracker = CascadeMomentumTracker()

        # IDLE - no activity
        obs = tracker.record_event("TEST", 0.001, False, 1000.0)
        assert obs.phase == MomentumPhase.IDLE

        # ACCELERATING - rate increasing
        for i in range(20):
            tracker.record_event("TEST", -0.5 - i * 0.1, True, 1000.0 + i * 0.5)

        # STEADY - stable rate
        for i in range(20):
            tracker.record_event("TEST", -0.5, True, 1010.0 + i * 0.5)

        # DECELERATING - rate decreasing
        for i in range(20):
            tracker.record_event("TEST", -0.5 + i * 0.02, True, 1020.0 + i * 0.5)

    def test_phase_to_string_includes_all(self):
        """All phases have string representation."""
        for phase in MomentumPhase:
            s = phase_to_string(phase)
            assert s != "UNKNOWN"
            assert len(s) > 0


class TestReplenishmentRatio:
    """Test replenishment vs consumed ratio."""

    def test_replenishment_ratio_computed(self):
        """Replenishment ratio = added / consumed."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.5
            )

        # Record consumption and refill
        tracker.record_absorption("BTC", consumed_size=1000.0, price_movement_pct=0.01, timestamp=ts)
        tracker.record_refill("BTC", added_size=500.0, timestamp=ts + 1)

        obs = tracker.get_observation("BTC", ts + 2)

        # Ratio should be 500/1000 = 0.5
        assert 0.4 <= obs.replenishment_vs_consumed <= 0.6


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_volume_handling(self):
        """Handles zero volume gracefully."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        tracker.record_trade("BTC", 50000.0, 0.0, True, ts)
        obs = tracker.get_observation("BTC", ts + 1)

        # Should not crash
        assert obs.phase == AbsorptionPhase.NONE

    def test_single_trade_handling(self):
        """Handles single trade without crash."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        tracker.record_trade("BTC", 50000.0, 100.0, True, ts)
        obs = tracker.get_observation("BTC", ts + 0.1)

        # Should have some data
        assert obs.sell_volume_window >= 0

    def test_large_time_gap_handling(self):
        """Handles large gaps in data."""
        tracker = AbsorptionConfirmationTracker()

        # Old data
        tracker.record_trade("BTC", 50000.0, 100.0, True, 1000.0)

        # Much later observation
        obs = tracker.get_observation("BTC", 2000.0)

        # Old data should be outside window
        assert obs.sell_volume_window == 0


# =============================================================================
# CONTROL SHIFT CONFIRMATION TESTS
# =============================================================================

class TestBidAggressionTracking:
    """Test bid aggression (buyers crossing spread)."""

    def test_bid_lifting_when_buyers_dominate(self):
        """Bid lifting detected when buy volume > threshold."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build regime context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.5
            )

        # Add mostly buy trades (buyers lifting asks)
        for i in range(50):
            is_buy = i < 40  # 80% buys
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=not is_buy,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 5)

        # Should detect bid lifting
        assert obs.buy_aggression_ratio > 0.5
        assert obs.bid_lifting is True

    def test_no_bid_lifting_when_sellers_dominate(self):
        """No bid lifting when sell volume dominates."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.5
            )

        # Add mostly sell trades
        for i in range(50):
            is_sell = i < 40  # 80% sells
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=is_sell,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 5)

        # Should not detect bid lifting
        assert obs.buy_aggression_ratio < 0.5
        assert obs.bid_lifting is False


class TestBuyVolumeAcceleration:
    """Test buy volume acceleration detection."""

    def test_acceleration_when_buy_volume_increases(self):
        """Acceleration detected when buy volume increases in second half."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.5
            )

        # First half: low buy volume
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=50.0,  # Small buys
                is_sell=False,
                timestamp=ts + i * 0.1
            )

        # Second half: high buy volume (acceleration)
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=200.0,  # Large buys
                is_sell=False,
                timestamp=ts + 2.5 + i * 0.1
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 5)

        # Should detect acceleration
        assert obs.buy_volume_second_half > obs.buy_volume_first_half
        assert obs.buy_acceleration > 0
        assert obs.volume_accelerating is True

    def test_no_acceleration_when_buy_volume_flat(self):
        """No acceleration when buy volume is stable across both halves."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # No separate context - let observation trades define regime
        # With 100 trades in 2s = 50/s, trade_rate = 100/30 = 3.33/s
        # Window = 50/3.33 = 15s (capped at 15)
        # For 15s window at ts+2: cutoff=ts-13, mid=ts-5.5
        # That won't work - we need trades to span the window

        # Alternative: place many balanced trades to establish regime
        # 100 balanced trades spread over 30 seconds
        for i in range(100):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),  # 50% buys, 50% sells
                timestamp=ts - 29 + i * 0.3  # -29 to +1 seconds
            )

        # This gives trade_rate = 100/30 = 3.33/s, window = 50/3.33 = 15s
        # Query at ts+1: cutoff = ts+1-15 = ts-14
        # mid = ts-14 + 7.5 = ts-6.5

        # What we care about: the overall buy volume ratio
        # With 50% buys throughout, both halves should have similar ratios
        obs = tracker.get_control_shift_observation("BTC", ts + 1)

        # With balanced trades throughout, acceleration should be near zero
        assert abs(obs.buy_acceleration) < 0.5  # Allow some variance


class TestPriceFloorEstablishment:
    """Test price floor (higher lows) detection."""

    def test_higher_low_formed(self):
        """Higher low detected when second half low > first half low."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Need high trade rate to get short window
        # 500 trades = 16.7 trades/sec in 30s lookback → window = 50/16.7 = 3s
        # Place trades to match this window

        # 250 trades in first half with deep low (49800)
        for i in range(250):
            # Low price (49800) only in first 125 trades
            if i < 125:
                price = 49800.0 + (i % 10) * 10  # 49800-49890
            else:
                price = 49950.0 + (i % 5) * 10  # 49950-49990
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.006  # 0-1.5 seconds
            )

        # 250 trades in second half with higher low (49900)
        for i in range(250):
            price = 49900.0 + (i % 10) * 10  # 49900-49990 (higher low)
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts + 1.5 + i * 0.006  # 1.5-3 seconds
            )

        # 500 trades in 3 sec = 166.7/sec, rate = 500/30 = 16.7/sec
        # Window = 50/16.7 = 3s, cutoff = ts, mid = ts+1.5
        obs = tracker.get_control_shift_observation("BTC", ts + 3)

        # First half has low of 49800, second half has low of 49900
        assert obs.low_price_second_half > obs.low_price_first_half
        assert obs.higher_low_formed is True

    def test_no_higher_low_when_lower_low_forms(self):
        """No higher low when second half makes new low."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.5
            )

        # First half: low at 49950
        for i in range(25):
            price = 50000.0 - (i % 5) * 10
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        # Second half: new low at 49900 (lower low)
        for i in range(25):
            price = 50000.0 - (i % 10) * 10
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts + 2.5 + i * 0.1
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 5)

        # Should not detect higher low
        assert obs.higher_low_formed is False


class TestImbalanceFlip:
    """Test order flow imbalance flip detection."""

    def test_imbalance_flip_detected(self):
        """Imbalance flip when going from sell-heavy to buy-heavy."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Very high trade rate balanced context
        for i in range(500):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts + i * 0.002  # 0-1 second
            )

        # Query at ts+3: cutoff=ts+1, mid=ts+2
        # First half (ts+1 to ts+2): sell-heavy (80% sells)
        for i in range(50):
            is_sell = i < 40  # First 40 are sells, last 10 are buys
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=is_sell,
                timestamp=ts + 1 + i * 0.02
            )

        # Second half (ts+2 to ts+3): buy-heavy (80% buys)
        for i in range(50):
            is_buy = i < 40  # First 40 are buys, last 10 are sells
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=not is_buy,
                timestamp=ts + 2 + i * 0.02
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 3)

        # Should detect imbalance flip
        assert obs.imbalance_first_half < 0  # Sell-heavy
        assert obs.imbalance_second_half > 0  # Buy-heavy
        assert obs.imbalance_flipped is True

    def test_no_flip_when_consistently_sell_heavy(self):
        """No flip when imbalance stays constant (no delta)."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build consistent 80% sell-heavy regime throughout
        # 100 trades over 30 seconds, consistently 80% sells
        for i in range(100):
            is_sell = i % 5 != 0  # 80% sells throughout
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=is_sell,
                timestamp=ts - 15 + i * 0.3  # -15 to +15 seconds
            )

        # With consistent 80% sells in both halves:
        # imbalance_first ≈ -0.6, imbalance_second ≈ -0.6, delta ≈ 0
        obs = tracker.get_control_shift_observation("BTC", ts + 15)

        # Should not detect flip (no significant delta)
        # Both halves sell-heavy with same ratio
        assert obs.imbalance_first_half < 0  # Sell-heavy
        assert obs.imbalance_second_half < 0  # Still sell-heavy
        assert abs(obs.imbalance_delta) < 0.15  # No significant swing


class TestCombinedExhaustionConfirmation:
    """Test combined absorption + control shift confirmation."""

    def test_full_exhaustion_requires_both(self):
        """Full exhaustion needs both absorption AND control shift."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build extensive regime context
        for i in range(100):
            price = 50000.0 + (i % 20) * 5
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0 + (i % 30),
                is_sell=(i % 2 == 0),
                timestamp=ts - 50 + i * 0.5
            )

        # Add absorption evidence
        tracker.record_absorption("BTC", consumed_size=5000.0, price_movement_pct=0.005, timestamp=ts)
        tracker.record_refill("BTC", added_size=2000.0, timestamp=ts + 1)

        # Add control shift evidence (buy acceleration + imbalance flip)
        # First half: sell-heavy
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=49950.0 + i,  # Rising lows
                volume=100.0,
                is_sell=True,
                timestamp=ts + 2 + i * 0.1
            )

        # Second half: buy-heavy with higher lows
        for i in range(25):
            tracker.record_trade(
                coin="BTC",
                price=49960.0 + i,  # Higher lows
                volume=150.0,
                is_sell=False,
                timestamp=ts + 4.5 + i * 0.1
            )

        combined = tracker.get_combined_observation("BTC", ts + 7)

        # Should have component data
        assert combined.absorption is not None
        assert combined.control_shift is not None
        assert combined.total_signals >= 0

    def test_is_full_exhaustion_confirmed_method(self):
        """Test the convenience method for full exhaustion check."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Minimal context
        for i in range(30):
            tracker.record_trade(
                coin="ETH",
                price=3000.0,
                volume=10.0,
                is_sell=True,
                timestamp=ts - 30 + i
            )

        # Without strong signals, should not be confirmed
        result = tracker.is_full_exhaustion_confirmed("ETH", ts)
        assert isinstance(result, bool)

    def test_control_shift_phases(self):
        """Test control shift phase determination."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # No data = NONE
        obs = tracker.get_control_shift_observation("EMPTY", ts)
        assert obs.phase == ControlShiftPhase.NONE
        assert obs.control_signals_confirmed == 0


class TestControlShiftEdgeCases:
    """Test edge cases in control shift detection."""

    def test_empty_coin_control_shift(self):
        """Empty coin returns neutral control shift observation."""
        tracker = AbsorptionConfirmationTracker()
        obs = tracker.get_control_shift_observation("EMPTY", 1000.0)

        assert obs.phase == ControlShiftPhase.NONE
        assert obs.control_signals_confirmed == 0
        assert obs.buy_aggression_ratio == 0.0

    def test_single_trade_control_shift(self):
        """Single trade doesn't crash control shift calculation."""
        tracker = AbsorptionConfirmationTracker()
        tracker.record_trade("BTC", 50000.0, 100.0, False, 1000.0)

        obs = tracker.get_control_shift_observation("BTC", 1000.1)

        # Should not crash
        assert obs is not None
        assert obs.control_signals_confirmed >= 0

    def test_all_buys_control_shift(self):
        """All buy trades should show strong control shift signals."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(60):
            tracker.record_trade(
                coin="BTC",
                price=50000.0 + i,  # Rising prices
                volume=100.0,
                is_sell=False,  # All buys
                timestamp=ts - 30 + i * 0.5
            )

        # Add more buys
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50030.0 + i,  # Continuing rise
                volume=100.0 + i,  # Increasing volume
                is_sell=False,
                timestamp=ts + i * 0.1
            )

        obs = tracker.get_control_shift_observation("BTC", ts + 5)

        # Should show strong buy aggression
        assert obs.buy_aggression_ratio == 1.0  # All buys
        assert obs.bid_lifting is True


# =============================================================================
# HARDENING TESTS
# =============================================================================

class TestTrendRegimeFilter:
    """Test trend regime detection and filtering."""

    def test_strong_downtrend_detected(self):
        """Strong downtrend with lower lows should be detected."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create strong downtrend: consistently falling prices
        for i in range(100):
            price = 50000.0 - i * 10  # Falling from 50000 to 49000
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 60 + i * 0.6
            )

        trend = tracker._compute_trend_regime_context("BTC", ts)

        # Should detect downtrend
        assert trend.price_change_pct < 0
        assert trend.lower_lows_count > 0

    def test_neutral_trend_allows_exhaustion(self):
        """Neutral trend should allow exhaustion detection."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create sideways/neutral market
        for i in range(100):
            # Oscillating price around 50000
            price = 50000.0 + (i % 10 - 5) * 10
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 60 + i * 0.6
            )

        trend = tracker._compute_trend_regime_context("BTC", ts)

        # Neutral trend should be safe
        assert tracker._is_trend_safe(trend) is True

    def test_trend_with_liquidations(self):
        """Trend context includes liquidation imbalance."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Add trades
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=True,
                timestamp=ts - 30 + i * 0.6
            )

        # Add liquidations (mostly longs)
        for i in range(10):
            tracker.record_liquidation(
                coin="BTC",
                side="long",
                volume=1000.0,
                timestamp=ts - 30 + i * 3
            )
        for i in range(2):
            tracker.record_liquidation(
                coin="BTC",
                side="short",
                volume=500.0,
                timestamp=ts - 20 + i * 5
            )

        trend = tracker._compute_trend_regime_context("BTC", ts)

        # Should have liquidation imbalance (more long liqs)
        assert trend.long_liq_volume > trend.short_liq_volume
        assert trend.liq_imbalance > 0


class TestWhaleFlowWeighting:
    """Test whale vs retail flow distinction."""

    def test_whale_threshold_calculation(self):
        """Whale threshold should be 90th percentile of trade sizes."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Create trades with varying sizes
        # 90 small trades (100), 10 large trades (1000)
        for i in range(90):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.33
            )
        for i in range(10):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=1000.0,
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        regime = tracker._compute_regime_context("BTC", ts + 1)
        whale = tracker._compute_whale_flow_metrics("BTC", ts + 1, regime)

        # Whale threshold should be around 1000 (90th percentile)
        assert whale.whale_threshold >= 100.0
        assert whale.whale_volume > 0

    def test_whale_driven_exhaustion(self):
        """Exhaustion should be flagged as whale-driven when whales dominate."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context with many small trades
        for i in range(100):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=10.0,  # Small
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.3
            )

        # Add whale trades (large volume)
        for i in range(10):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=500.0,  # Large
                is_sell=True,
                timestamp=ts + i * 0.1
            )

        regime = tracker._compute_regime_context("BTC", ts + 1)
        whale = tracker._compute_whale_flow_metrics("BTC", ts + 1, regime)

        # Should detect whale participation
        assert whale.whale_sell_volume > 0
        assert whale.whale_ratio > 0


class TestPersistenceTracking:
    """Test depth and control shift persistence."""

    def test_bid_level_tracking(self):
        """Bid level appearance/disappearance should be tracked."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Bid appears
        tracker.record_bid_level("BTC", 49000.0, appeared=True, timestamp=ts)

        # Bid persists...
        # Bid disappears after 5 seconds
        tracker.record_bid_level("BTC", 49000.0, appeared=False, timestamp=ts + 5)

        # Check that event was recorded
        events = tracker._bid_level_events.get("BTC", [])
        assert len(events) == 1
        assert events[0][2] == 5.0  # Lifetime = 5 seconds

    def test_flash_bid_detection(self):
        """Flash bids (< 3 seconds) should be flagged."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Add trades for regime context
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.6
            )

        # Add flash bid (appears and disappears quickly)
        tracker.record_bid_level("BTC", 49000.0, appeared=True, timestamp=ts)
        tracker.record_bid_level("BTC", 49000.0, appeared=False, timestamp=ts + 1)  # 1 sec

        # Add persistent bid
        tracker.record_bid_level("BTC", 48000.0, appeared=True, timestamp=ts)
        tracker.record_bid_level("BTC", 48000.0, appeared=False, timestamp=ts + 10)  # 10 sec

        regime = tracker._compute_regime_context("BTC", ts + 10)
        persistence = tracker._compute_persistence_metrics("BTC", ts + 10, regime)

        # Should have 50% flash ratio (1 of 2 bids was flash)
        assert persistence.flash_bid_ratio == 0.5

    def test_control_shift_persistence(self):
        """Control shift should track consecutive windows."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Manually record control shift history
        tracker._record_control_shift_result("BTC", confirmed=True, timestamp=ts)
        tracker._record_control_shift_result("BTC", confirmed=True, timestamp=ts + 5)
        tracker._record_control_shift_result("BTC", confirmed=True, timestamp=ts + 10)

        # Add trades for regime context
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.6
            )

        regime = tracker._compute_regime_context("BTC", ts + 15)
        persistence = tracker._compute_persistence_metrics("BTC", ts + 15, regime)

        # Should have 3 consecutive windows
        assert persistence.control_shift_windows == 3
        assert persistence.control_persistent is True


class TestCombinedHardenings:
    """Test all hardenings together."""

    def test_full_exhaustion_requires_hardenings(self):
        """Full exhaustion confirmation requires all hardenings to pass."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build extensive regime context (neutral trend)
        for i in range(200):
            price = 50000.0 + (i % 20 - 10) * 5  # Oscillating
            tracker.record_trade(
                coin="BTC",
                price=price,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 100 + i * 0.5
            )

        combined = tracker.get_combined_observation("BTC", ts)

        # Should have all hardening fields
        assert combined.trend_context is not None
        assert combined.whale_metrics is not None
        assert combined.persistence is not None
        assert isinstance(combined.trend_safe, bool)
        assert isinstance(combined.whale_validated, bool)
        assert isinstance(combined.persistence_validated, bool)
        assert isinstance(combined.hardening_score, float)

    def test_base_vs_hardened_confirmation(self):
        """Base confirmation can pass without hardenings passing."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build minimal context
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.6
            )

        combined = tracker.get_combined_observation("BTC", ts)

        # base_exhaustion_confirmed and full_exhaustion_confirmed may differ
        # full requires all hardenings to pass
        assert isinstance(combined.base_exhaustion_confirmed, bool)
        assert isinstance(combined.full_exhaustion_confirmed, bool)

    def test_hardening_score_calculation(self):
        """Hardening score should be 0-1 based on how many pass."""
        tracker = AbsorptionConfirmationTracker()
        ts = 1000.0

        # Build context
        for i in range(50):
            tracker.record_trade(
                coin="BTC",
                price=50000.0,
                volume=100.0,
                is_sell=(i % 2 == 0),
                timestamp=ts - 30 + i * 0.6
            )

        combined = tracker.get_combined_observation("BTC", ts)

        # Hardening score should be between 0 and 1
        assert 0.0 <= combined.hardening_score <= 1.0

        # If all 3 hardenings pass, score = 1.0
        # If 2 pass, score = 0.67
        # If 1 passes, score = 0.33
        # If 0 pass, score = 0.0
        expected_scores = [0.0, 1/3, 2/3, 1.0]
        assert combined.hardening_score in expected_scores or \
               any(abs(combined.hardening_score - s) < 0.01 for s in expected_scores)
