"""
Unit tests for ROLLING_FADE burst volume gate and stop-loss cooldown.

1. Volume gate: blocks entry when burst USD volume is below per-coin minimum
   (restored from 652e89d, lost in f82673d rewrite).
2. Stop-loss cooldown: blocks all cascade entries for 5 min after a stop-out
   on the same symbol.
"""

import time
from unittest.mock import patch

import pytest

from external_policy.ep2_strategy_cascade_sniper import (
    EntryMode,
    PermissionOutput,
    StrategyContext,
    generate_cascade_sniper_proposal,
    EXHAUSTION_FADE_MIN_BURST_BY_COIN,
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


def _make_signal(
    symbol: str = "SOLUSDT",
    direction: str = "LONG",
    spike_volume: float = 10_000,
    ts: float = 0,
) -> RollingFadeSignal:
    return RollingFadeSignal(
        symbol=symbol,
        spike_volume=spike_volume,
        z_score=15.0,
        short_liq_volume=spike_volume * 0.8 if direction == "LONG" else spike_volume * 0.2,
        long_liq_volume=spike_volume * 0.2 if direction == "LONG" else spike_volume * 0.8,
        liq_count=10,
        spike_ts=ts,
        confirmation_ts=ts,
        fade_direction=direction,
    )


class TestRollingFadeVolumeGate:
    """Test minimum burst volume gate for ROLLING_FADE entries."""

    @pytest.fixture(autouse=True)
    def bypass_warmup(self):
        with patch(
            "external_policy.ep2_strategy_cascade_sniper._check_warmup_gate",
            return_value=(True, "test_bypass"),
        ):
            yield

    def test_dust_volume_blocked(self):
        """$135 burst (WLD dust case) should be blocked."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("WLDUSDT", "SHORT", spike_volume=135, ts=ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is None

    def test_adequate_volume_passes(self):
        """$1000 burst (above $500 default) should pass."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("WLDUSDT", "SHORT", spike_volume=1000, ts=ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is not None
        assert result.confidence == "ROLLING_FADE"

    def test_btc_needs_higher_volume(self):
        """BTC has $2500 minimum from EXHAUSTION_FADE_MIN_BURST_BY_COIN."""
        ts = time.time()
        btc_min = EXHAUSTION_FADE_MIN_BURST_BY_COIN.get("BTC", 500)
        assert btc_min > 500, "BTC should have higher threshold than default"

        # $1000 passes default but not BTC threshold
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("BTCUSDT", "LONG", spike_volume=1000, ts=ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is None

    def test_btc_above_threshold_passes(self):
        """BTC with burst above its threshold should pass."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("BTCUSDT", "LONG", spike_volume=5000, ts=ts),
            price_returns={"ret_1m": 0.002},
        )
        assert result is not None

    def test_exactly_at_threshold_passes(self):
        """Burst exactly at $500 default should pass (>= check)."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LINKUSDT", "SHORT", spike_volume=500, ts=ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is not None

    def test_just_below_threshold_blocked(self):
        """Burst at $499 (just below $500) should be blocked."""
        ts = time.time()
        result = generate_cascade_sniper_proposal(
            permission=_make_permission(ts),
            proximity=None,
            liquidations=None,
            context=_make_context(ts),
            entry_mode=EntryMode.ROLLING_FADE,
            rolling_fade_signal=_make_signal("LINKUSDT", "SHORT", spike_volume=499, ts=ts),
            price_returns={"ret_1m": -0.002},
        )
        assert result is None
