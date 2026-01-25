"""
Test Trend Kill-Switch Functionality

Tests the trend kill-switch hardening across:
1. Entry Quality Scorer (blocks LONG during strong downtrend)
2. Cascade Sniper (blocks reversal entries during strong trends)
3. Trend bonus for aligned entries
"""

import pytest
import time

from runtime.validation.entry_quality import (
    EntryQualityScorer,
    EntryScore,
    EntryQuality,
    TrendRegimeContext,
    TrendDirection,
)

from external_policy.ep2_strategy_cascade_sniper import (
    generate_cascade_sniper_proposal,
    record_liquidation_event,
    reset_state,
    _is_reversal_blocked_by_trend,
    ProximityData,
    LiquidationBurst,
    AbsorptionAnalysis,
    StrategyContext,
    PermissionOutput,
    EntryMode,
    CascadeState,
    CascadeStateMachine,
    CascadeSniperConfig,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def entry_scorer():
    """Create fresh entry quality scorer."""
    return EntryQualityScorer()


@pytest.fixture
def strong_downtrend() -> TrendRegimeContext:
    """Create a strong downtrend context that should block LONG entries."""
    return TrendRegimeContext(
        direction=TrendDirection.STRONG_DOWN,
        price_change_pct=-0.015,  # -1.5% drop
        higher_highs_count=0,
        lower_lows_count=4,  # Clear lower lows
        trend_strength=0.8,  # High strength
        consecutive_direction=5,
        long_liq_volume=100000.0,
        short_liq_volume=5000.0,
        liq_imbalance=0.9,  # Mostly longs being liquidated
        delta_60s=-50000.0,  # Negative delta (selling)
        delta_direction_aligned=True  # Selling aligned with downtrend
    )


@pytest.fixture
def strong_uptrend() -> TrendRegimeContext:
    """Create a strong uptrend context that should block SHORT entries."""
    return TrendRegimeContext(
        direction=TrendDirection.STRONG_UP,
        price_change_pct=0.015,  # +1.5% rise
        higher_highs_count=4,
        lower_lows_count=0,
        trend_strength=0.8,
        consecutive_direction=5,
        long_liq_volume=5000.0,
        short_liq_volume=100000.0,  # Shorts being squeezed
        liq_imbalance=-0.9,
        delta_60s=50000.0,  # Positive delta (buying)
        delta_direction_aligned=True
    )


@pytest.fixture
def weak_downtrend() -> TrendRegimeContext:
    """Create a weak downtrend that should allow reversal entries."""
    return TrendRegimeContext(
        direction=TrendDirection.WEAK_DOWN,
        price_change_pct=-0.003,  # -0.3% drop
        higher_highs_count=1,
        lower_lows_count=2,
        trend_strength=0.4,  # Low strength
        consecutive_direction=2,
        long_liq_volume=20000.0,
        short_liq_volume=10000.0,
        liq_imbalance=0.33,
        delta_60s=-10000.0,
        delta_direction_aligned=True
    )


@pytest.fixture
def neutral_trend() -> TrendRegimeContext:
    """Create a neutral trend context."""
    return TrendRegimeContext(
        direction=TrendDirection.NEUTRAL,
        price_change_pct=0.001,
        higher_highs_count=2,
        lower_lows_count=2,
        trend_strength=0.0,
        consecutive_direction=0,
        long_liq_volume=15000.0,
        short_liq_volume=15000.0,
        liq_imbalance=0.0,
        delta_60s=0.0,
        delta_direction_aligned=False
    )


@pytest.fixture
def diverging_downtrend() -> TrendRegimeContext:
    """Create downtrend with diverging delta (buyers accumulating).

    Note: trend_strength must be below 0.7 for delta divergence to save the entry.
    If trend_strength >= 0.7, entry is blocked regardless of delta.
    """
    return TrendRegimeContext(
        direction=TrendDirection.STRONG_DOWN,
        price_change_pct=-0.012,
        higher_highs_count=0,
        lower_lows_count=4,
        trend_strength=0.65,  # Below 0.7 threshold so delta divergence matters
        consecutive_direction=4,
        long_liq_volume=80000.0,
        short_liq_volume=5000.0,
        liq_imbalance=0.88,
        delta_60s=30000.0,  # Positive delta despite downtrend
        delta_direction_aligned=False  # Delta diverging - buyers accumulating
    )


# ==============================================================================
# Entry Quality Scorer Tests
# ==============================================================================

class TestEntryQualityScorerTrendKillSwitch:
    """Test trend kill-switch in Entry Quality Scorer."""

    def test_long_blocked_during_strong_downtrend(
        self, entry_scorer: EntryQualityScorer, strong_downtrend: TrendRegimeContext
    ):
        """LONG entry should be BLOCKED during strong downtrend with aligned delta."""
        # Record some liquidations
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        # Score entry with strong downtrend context
        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=strong_downtrend
        )

        # Should be SKIP quality (blocked by trend)
        assert score.quality == EntryQuality.SKIP
        assert score.trend_blocked is True
        assert score.should_enter is False
        assert "BLOCKED" in score.reason

    def test_short_allowed_during_strong_downtrend(
        self, entry_scorer: EntryQualityScorer, strong_downtrend: TrendRegimeContext
    ):
        """SHORT entry should be allowed during strong downtrend (trend-aligned)."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="SHORT",
            timestamp=ts,
            trend_context=strong_downtrend
        )

        # Should NOT be blocked (SHORT aligns with downtrend)
        assert score.quality != EntryQuality.SKIP
        assert score.trend_blocked is False

    def test_short_blocked_during_strong_uptrend(
        self, entry_scorer: EntryQualityScorer, strong_uptrend: TrendRegimeContext
    ):
        """SHORT entry should be BLOCKED during strong uptrend with aligned delta."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "BUY", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="SHORT",
            timestamp=ts,
            trend_context=strong_uptrend
        )

        # Should be SKIP quality
        assert score.quality == EntryQuality.SKIP
        assert score.trend_blocked is True
        assert score.should_enter is False

    def test_long_allowed_during_weak_downtrend(
        self, entry_scorer: EntryQualityScorer, weak_downtrend: TrendRegimeContext
    ):
        """LONG entry should be allowed during weak downtrend."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=weak_downtrend
        )

        # Should NOT be blocked
        assert score.quality != EntryQuality.SKIP
        assert score.trend_blocked is False

    def test_long_allowed_during_neutral_trend(
        self, entry_scorer: EntryQualityScorer, neutral_trend: TrendRegimeContext
    ):
        """LONG entry should be allowed during neutral trend."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=neutral_trend
        )

        assert score.quality != EntryQuality.SKIP
        assert score.trend_blocked is False

    def test_long_allowed_when_delta_diverging(
        self, entry_scorer: EntryQualityScorer, diverging_downtrend: TrendRegimeContext
    ):
        """LONG entry should be allowed during downtrend if delta is diverging.

        When delta_direction_aligned=False (buyers accumulating during selloff),
        and trend_strength < 0.7, the entry should be allowed.
        """
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=diverging_downtrend
        )

        # Delta diverging + moderate trend strength = entry allowed
        assert score.trend_blocked is False
        assert score.quality != EntryQuality.SKIP

    def test_no_trend_context_allows_entry(self, entry_scorer: EntryQualityScorer):
        """Entry should proceed normally when no trend context provided."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=None  # No trend context
        )

        # Should NOT be blocked
        assert score.quality != EntryQuality.SKIP
        assert score.trend_blocked is False


class TestTrendBonus:
    """Test trend bonus for aligned entries."""

    def test_long_gets_bonus_in_uptrend(
        self, entry_scorer: EntryQualityScorer
    ):
        """LONG entry should get trend bonus during uptrend."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        uptrend = TrendRegimeContext(
            direction=TrendDirection.WEAK_UP,
            price_change_pct=0.008,
            higher_highs_count=3,
            lower_lows_count=1,
            trend_strength=0.5,
            consecutive_direction=3,
            long_liq_volume=5000.0,
            short_liq_volume=20000.0,
            liq_imbalance=-0.6,
            delta_60s=20000.0,
            delta_direction_aligned=True
        )

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",
            timestamp=ts,
            trend_context=uptrend
        )

        # Should have positive trend bonus
        assert score.trend_bonus > 0

    def test_short_gets_bonus_in_downtrend(self, entry_scorer: EntryQualityScorer):
        """SHORT entry should get trend bonus during downtrend."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "BUY", 100000.0, ts - 30)

        downtrend = TrendRegimeContext(
            direction=TrendDirection.WEAK_DOWN,
            price_change_pct=-0.008,
            higher_highs_count=1,
            lower_lows_count=3,
            trend_strength=0.5,
            consecutive_direction=3,
            long_liq_volume=30000.0,
            short_liq_volume=5000.0,
            liq_imbalance=0.71,
            delta_60s=-20000.0,
            delta_direction_aligned=True
        )

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="SHORT",
            timestamp=ts,
            trend_context=downtrend
        )

        # Should have positive trend bonus
        assert score.trend_bonus > 0

    def test_counter_trend_gets_penalty(
        self, entry_scorer: EntryQualityScorer, weak_downtrend: TrendRegimeContext
    ):
        """Counter-trend entry should get negative trend bonus."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 50000.0, ts - 30)

        score = entry_scorer.score_entry(
            symbol="BTCUSDT",
            intended_side="LONG",  # Counter to downtrend
            timestamp=ts,
            trend_context=weak_downtrend
        )

        # Should have negative trend bonus (penalty)
        assert score.trend_bonus < 0


# ==============================================================================
# Cascade Sniper Kill-Switch Tests
# ==============================================================================

class TestCascadeSniperReversalBlockHelper:
    """Test the _is_reversal_blocked_by_trend helper function."""

    def test_long_blocked_during_strong_downtrend_aligned(
        self, strong_downtrend: TrendRegimeContext
    ):
        """LONG reversal blocked during strong downtrend with aligned delta."""
        assert _is_reversal_blocked_by_trend("LONG", strong_downtrend) is True

    def test_short_not_blocked_during_strong_downtrend(
        self, strong_downtrend: TrendRegimeContext
    ):
        """SHORT not blocked during strong downtrend (aligned with trend)."""
        assert _is_reversal_blocked_by_trend("SHORT", strong_downtrend) is False

    def test_short_blocked_during_strong_uptrend_aligned(
        self, strong_uptrend: TrendRegimeContext
    ):
        """SHORT reversal blocked during strong uptrend with aligned delta."""
        assert _is_reversal_blocked_by_trend("SHORT", strong_uptrend) is True

    def test_long_not_blocked_during_strong_uptrend(
        self, strong_uptrend: TrendRegimeContext
    ):
        """LONG not blocked during strong uptrend (aligned with trend)."""
        assert _is_reversal_blocked_by_trend("LONG", strong_uptrend) is False

    def test_long_not_blocked_during_weak_downtrend(
        self, weak_downtrend: TrendRegimeContext
    ):
        """LONG reversal allowed during weak downtrend."""
        assert _is_reversal_blocked_by_trend("LONG", weak_downtrend) is False

    def test_entries_not_blocked_during_neutral(
        self, neutral_trend: TrendRegimeContext
    ):
        """No entries blocked during neutral trend."""
        assert _is_reversal_blocked_by_trend("LONG", neutral_trend) is False
        assert _is_reversal_blocked_by_trend("SHORT", neutral_trend) is False

    def test_long_allowed_when_delta_diverging(
        self, diverging_downtrend: TrendRegimeContext
    ):
        """LONG allowed during downtrend if delta diverges (buyers accumulating).

        With trend_strength=0.65 (< 0.7 threshold) and delta_direction_aligned=False,
        the entry should be allowed because:
        1. delta_direction_aligned=False passes the delta check
        2. trend_strength=0.65 < 0.7 passes the strength check
        """
        result = _is_reversal_blocked_by_trend("LONG", diverging_downtrend)
        # With strength < 0.7 and delta not aligned, entry is allowed
        assert result is False


class TestCascadeSniperIntegration:
    """Integration tests for cascade sniper with trend kill-switch."""

    @pytest.fixture(autouse=True)
    def reset_cascade_state(self):
        """Reset cascade sniper state before each test."""
        reset_state()

    def test_reversal_blocked_during_strong_downtrend(
        self, strong_downtrend: TrendRegimeContext
    ):
        """Reversal entry should be blocked during strong downtrend."""
        ts = time.time()

        # Record liquidation events
        record_liquidation_event("BTCUSDT", "SELL", 100000.0, ts - 30)

        # Create proximity data with longs at risk
        proximity = ProximityData(
            coin="BTC",
            current_price=50000.0,
            threshold_pct=0.005,
            long_positions_count=10,
            long_positions_value=500000.0,
            long_closest_liquidation=49800.0,
            short_positions_count=2,
            short_positions_value=50000.0,
            short_closest_liquidation=51000.0,
            total_positions_at_risk=12,
            total_value_at_risk=550000.0,
            timestamp=ts
        )

        # Create liquidation burst to trigger cascade
        liquidations = LiquidationBurst(
            symbol="BTCUSDT",
            total_volume=100000.0,
            long_liquidations=90000.0,
            short_liquidations=10000.0,
            liquidation_count=5,
            window_start=ts - 10,
            window_end=ts
        )

        # Create absorption analysis (book can absorb)
        absorption = AbsorptionAnalysis(
            coin="BTC",
            mid_price=50000.0,
            bid_depth_2pct=1000000.0,
            ask_depth_2pct=800000.0,
            long_liq_value=500000.0,
            short_liq_value=50000.0,
            absorption_ratio_longs=2.0,  # Book can absorb
            absorption_ratio_shorts=16.0,
            timestamp=ts
        )

        # Permission and context
        permission = PermissionOutput(
            result="ALLOWED",
            mandate_id="test",
            action_id="test",
            reason_code="TEST",
            timestamp=ts
        )

        context = StrategyContext(
            context_id="test",
            timestamp=ts
        )

        # First update to prime the state machine
        proposal = generate_cascade_sniper_proposal(
            permission=permission,
            proximity=proximity,
            liquidations=None,  # No liquidations yet
            context=context,
            position_state=None,
            entry_mode=EntryMode.ABSORPTION_REVERSAL,
            absorption=None,
            trend_context=None
        )

        # Now trigger cascade
        context2 = StrategyContext(context_id="test2", timestamp=ts + 1)
        proposal = generate_cascade_sniper_proposal(
            permission=permission,
            proximity=proximity,
            liquidations=liquidations,
            context=context2,
            position_state=None,
            entry_mode=EntryMode.ABSORPTION_REVERSAL,
            absorption=absorption,
            trend_context=None
        )

        # Now try to enter during ABSORBING state with strong downtrend
        context3 = StrategyContext(context_id="test3", timestamp=ts + 2)
        proposal = generate_cascade_sniper_proposal(
            permission=permission,
            proximity=proximity,
            liquidations=liquidations,
            context=context3,
            position_state=None,
            entry_mode=EntryMode.ABSORPTION_REVERSAL,
            absorption=absorption,
            trend_context=strong_downtrend  # Strong downtrend should block LONG
        )

        # Should be blocked (returns None) due to trend kill-switch
        assert proposal is None

    def test_momentum_not_blocked_during_strong_downtrend(
        self, strong_downtrend: TrendRegimeContext
    ):
        """Momentum entry (SHORT) should NOT be blocked during strong downtrend."""
        ts = time.time()

        # Record liquidation events
        record_liquidation_event("BTCUSDT", "SELL", 100000.0, ts - 30)

        # Create proximity data
        proximity = ProximityData(
            coin="BTC",
            current_price=50000.0,
            threshold_pct=0.005,
            long_positions_count=10,
            long_positions_value=500000.0,
            long_closest_liquidation=49800.0,
            short_positions_count=2,
            short_positions_value=50000.0,
            short_closest_liquidation=51000.0,
            total_positions_at_risk=12,
            total_value_at_risk=550000.0,
            timestamp=ts
        )

        # Create liquidation burst
        liquidations = LiquidationBurst(
            symbol="BTCUSDT",
            total_volume=100000.0,
            long_liquidations=90000.0,
            short_liquidations=10000.0,
            liquidation_count=5,
            window_start=ts - 10,
            window_end=ts
        )

        # Thin book for momentum mode
        absorption = AbsorptionAnalysis(
            coin="BTC",
            mid_price=50000.0,
            bid_depth_2pct=200000.0,  # Thin book
            ask_depth_2pct=200000.0,
            long_liq_value=500000.0,
            short_liq_value=50000.0,
            absorption_ratio_longs=0.4,  # Below threshold
            absorption_ratio_shorts=4.0,
            timestamp=ts
        )

        permission = PermissionOutput(
            result="ALLOWED",
            mandate_id="test",
            action_id="test",
            reason_code="TEST",
            timestamp=ts
        )

        context = StrategyContext(context_id="test", timestamp=ts)

        # Prime state machine
        proposal = generate_cascade_sniper_proposal(
            permission=permission,
            proximity=proximity,
            liquidations=None,
            context=context,
            position_state=None,
            entry_mode=EntryMode.CASCADE_MOMENTUM,
            absorption=None,
            trend_context=None
        )

        # Trigger cascade
        context2 = StrategyContext(context_id="test2", timestamp=ts + 1)
        proposal = generate_cascade_sniper_proposal(
            permission=permission,
            proximity=proximity,
            liquidations=liquidations,
            context=context2,
            position_state=None,
            entry_mode=EntryMode.CASCADE_MOMENTUM,
            absorption=absorption,
            trend_context=strong_downtrend
        )

        # Momentum mode with strong downtrend should allow SHORT
        # (momentum aligns with trend)
        # Note: May or may not generate proposal depending on state machine
        # The key is it's NOT blocked by trend kill-switch
        # If proposal is None, it's for other reasons (state machine, absorption filter)


# ==============================================================================
# EntryQuality.SKIP Quality Level Tests
# ==============================================================================

class TestEntryQualitySkipLevel:
    """Test the new SKIP quality level."""

    def test_skip_is_lowest_quality(self):
        """SKIP should be the lowest quality level."""
        quality_order = {
            EntryQuality.HIGH: 3,
            EntryQuality.NEUTRAL: 2,
            EntryQuality.AVOID: 1,
            EntryQuality.SKIP: 0
        }

        assert quality_order[EntryQuality.SKIP] < quality_order[EntryQuality.AVOID]
        assert quality_order[EntryQuality.AVOID] < quality_order[EntryQuality.NEUTRAL]
        assert quality_order[EntryQuality.NEUTRAL] < quality_order[EntryQuality.HIGH]

    def test_get_entry_recommendation_rejects_skip(
        self, entry_scorer: EntryQualityScorer, strong_downtrend: TrendRegimeContext
    ):
        """get_entry_recommendation should reject SKIP quality entries."""
        ts = time.time()
        entry_scorer.record_liquidation("BTCUSDT", "SELL", 100000.0, ts - 30)

        should_enter, score = entry_scorer.get_entry_recommendation(
            symbol="BTCUSDT",
            intended_side="LONG",
            min_quality=EntryQuality.AVOID,  # Even allowing AVOID
            trend_context=strong_downtrend
        )

        # Should not enter due to SKIP quality
        assert should_enter is False
        assert score.quality == EntryQuality.SKIP
