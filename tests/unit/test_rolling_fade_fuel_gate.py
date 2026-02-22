"""
Unit tests for ROLLING_FADE cascade fuel gate.

Verifies that entries are blocked when many positions remain at risk
on the cascade side (fuel for further cascades).
"""

import time
from unittest.mock import patch

import pytest

from external_policy.ep2_strategy_cascade_sniper import (
    EntryMode,
    PermissionOutput,
    ProximityData,
    StrategyContext,
    generate_cascade_sniper_proposal,
    ROLLING_FADE_FUEL_MIN_POSITIONS,
    ROLLING_FADE_FUEL_MIN_VALUE,
)
from runtime.liquidations.rolling_volume_tracker import RollingFadeSignal


def _make_permission(ts: float = 0) -> PermissionOutput:
    return PermissionOutput(
        result="ALLOWED",
        mandate_id="test",
        action_id="test",
        reason_code="test",
        timestamp=ts,
    )


def _make_context(ts: float = 0) -> StrategyContext:
    return StrategyContext(context_id="test", timestamp=ts)


def _make_signal(direction: str = "LONG", ts: float = 0) -> RollingFadeSignal:
    return RollingFadeSignal(
        symbol="SOLUSDT",
        spike_volume=100_000,
        z_score=15.0,
        short_liq_volume=80_000 if direction == "LONG" else 20_000,
        long_liq_volume=20_000 if direction == "LONG" else 80_000,
        liq_count=10,
        spike_ts=ts,
        confirmation_ts=ts,
        fade_direction=direction,
    )


def _make_proximity(
    long_count: int = 0,
    long_value: float = 0,
    short_count: int = 0,
    short_value: float = 0,
    ts: float = 0,
) -> ProximityData:
    return ProximityData(
        coin="SOL",
        current_price=83.0,
        threshold_pct=0.005,
        long_positions_count=long_count,
        long_positions_value=long_value,
        long_closest_liquidation=82.5 if long_count > 0 else None,
        short_positions_count=short_count,
        short_positions_value=short_value,
        short_closest_liquidation=84.0 if short_count > 0 else None,
        total_positions_at_risk=long_count + short_count,
        total_value_at_risk=long_value + short_value,
        timestamp=ts,
    )


class TestRollingFadeFuelGate:
    """Test cascade fuel gate for ROLLING_FADE entries."""

    @pytest.fixture(autouse=True)
    def bypass_warmup(self):
        """Bypass warmup gate so we can test the fuel gate in isolation."""
        with patch(
            "external_policy.ep2_strategy_cascade_sniper._check_warmup_gate",
            return_value=(True, "test_bypass"),
        ):
            yield

    def test_blocked_long_high_fuel(self):
        """LONG entry blocked when many long positions at risk (SOL scenario)."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(long_count=23, long_value=23_500_000, ts=ts),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},  # counter-trend (positive for LONG fade)
        )
        assert result is None

    def test_blocked_short_high_fuel(self):
        """SHORT entry blocked when many short positions at risk."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(short_count=20, short_value=1_000_000, ts=ts),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("SHORT", ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is None

    def test_allowed_low_count(self):
        """Allowed when position count below threshold (few large positions)."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(long_count=3, long_value=2_000_000, ts=ts),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None
        assert result.confidence == "ROLLING_FADE"

    def test_allowed_low_value(self):
        """Allowed when notional value below threshold (many micro positions)."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(long_count=20, long_value=100_000, ts=ts),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None
        assert result.confidence == "ROLLING_FADE"

    def test_allowed_no_proximity(self):
        """Allowed when proximity data is None (skip gate)."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None
        assert result.confidence == "ROLLING_FADE"

    def test_checks_correct_side_long(self):
        """LONG entry checks long fuel, not short fuel."""
        ts = time.time()
        # Short side has lots of fuel, but we're fading longs — should be allowed
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(
                long_count=2, long_value=10_000,
                short_count=30, short_value=10_000_000, ts=ts,
            ),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None

    def test_checks_correct_side_short(self):
        """SHORT entry checks short fuel, not long fuel."""
        ts = time.time()
        # Long side has lots of fuel, but we're fading shorts — should be allowed
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(
                long_count=30, long_value=10_000_000,
                short_count=2, short_value=10_000, ts=ts,
            ),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("SHORT", ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is not None

    def test_exactly_at_threshold_blocked(self):
        """Entry blocked when exactly at threshold values."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(
                long_count=ROLLING_FADE_FUEL_MIN_POSITIONS,
                long_value=ROLLING_FADE_FUEL_MIN_VALUE,
                ts=ts,
            ),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is None

    def test_just_below_threshold_allowed(self):
        """Entry allowed when just below one threshold."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(
                long_count=ROLLING_FADE_FUEL_MIN_POSITIONS - 1,
                long_value=ROLLING_FADE_FUEL_MIN_VALUE,
                ts=ts,
            ),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None

    def test_fuel_in_justification(self):
        """Fuel info appears in justification_ref when entry allowed."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=_make_proximity(long_count=5, long_value=200_000, ts=ts),
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LONG", ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None
        assert "fuel:5pos/$200,000" in result.justification_ref
