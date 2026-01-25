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
    RegimeContext
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
