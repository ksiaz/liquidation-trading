"""Tests for GravityObserver zone arrival detection and state machine."""
import pytest
from unittest.mock import MagicMock
from runtime.liquidations.gravity_observer import GravityObserver
from runtime.liquidations.liquidity_map import LiquidityZone


def _make_zone(center, side="bid", gravity=10000, persistence=0.8,
               current_size=50000):
    band_w = center * 10 / 10000  # 10bp band
    return LiquidityZone(
        center_price=center,
        band_low=center - band_w / 2,
        band_high=center + band_w / 2,
        side=side,
        gravity=gravity,
        persistence=persistence,
        avg_size_usd=gravity / max(persistence, 0.01),
        max_size_usd=gravity / max(persistence, 0.01) * 1.5,
        samples_seen=int(persistence * 100),
        total_samples=100,
        current_size_usd=current_size,
    )


def _mock_liq_map(zones):
    m = MagicMock()
    def _get_zones(coin, side="both", min_gravity=0):
        result = [z for z in zones if z.gravity >= min_gravity]
        if side != "both":
            result = [z for z in result if z.side == side]
        result.sort(key=lambda z: z.gravity, reverse=True)
        return result

    m.get_zones.side_effect = _get_zones
    m.is_warmed_up.return_value = True

    def _zones_above(coin, price, min_gravity=0):
        return sorted(
            [z for z in zones if z.side == "ask" and z.center_price > price
             and z.gravity >= min_gravity],
            key=lambda z: z.gravity, reverse=True
        )

    def _zones_below(coin, price, min_gravity=0):
        return sorted(
            [z for z in zones if z.side == "bid" and z.center_price < price
             and z.gravity >= min_gravity],
            key=lambda z: z.gravity, reverse=True
        )

    m.get_zones_above.side_effect = _zones_above
    m.get_zones_below.side_effect = _zones_below
    m.get_depth_between.return_value = 5000.0
    return m


def _mock_of_calc(imbalance=0.5, fills=20):
    m = MagicMock()
    m.get_imbalance_60s.return_value = imbalance
    m.get_trade_count_60s.return_value = fills
    return m


class TestZoneArrival:
    def test_no_arrival_when_price_outside_zones(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        assert obs.get_active_event("BTC") is None

    def test_arrival_when_price_enters_zone(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event is not None
        assert event.state == "DWELLING"
        assert event.approach_direction == "from_above"

    def test_no_arrival_below_min_gravity(self):
        obs = GravityObserver(min_obs_gravity=20000)
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        assert obs.get_active_event("BTC") is None

    def test_picks_strongest_zone_when_overlapping(self):
        obs = GravityObserver()
        weak = _make_zone(70000, side="bid", gravity=5000)
        strong = _make_zone(70003, side="bid", gravity=50000)
        lm = _mock_liq_map([weak, strong])
        # Mock returns sorted by gravity desc, so strong first
        lm.get_zones.return_value = [strong, weak]
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70003, 1001.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event is not None
        assert event.zone_gravity == 50000

    def test_approach_from_below(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="ask", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 69000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event is not None
        assert event.approach_direction == "from_below"


class TestDwellToTracking:
    def test_exits_to_tracking_when_price_leaves_zone(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        assert obs.get_active_event("BTC").state == "DWELLING"
        # Leave zone — first update sets _brief_exit_ts
        obs.on_price_update("BTC", 71000, 1005.0, lm, of)
        # Second update >10s later confirms exit
        obs.on_price_update("BTC", 71000, 1016.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event.state == "TRACKING"
        assert event.exit_direction == "upward"

    def test_reentry_within_grace_continues_dwell(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)
        # Brief exit
        obs.on_price_update("BTC", 71000, 1005.0, lm, of)
        # Re-enter within 10s
        obs.on_price_update("BTC", 70000, 1008.0, lm, of)
        event = obs.get_active_event("BTC")
        assert event.state == "DWELLING"


class TestOutcomeTracking:
    def _enter_and_exit_zone(self, obs, lm, of, exit_price=70200,
                             exit_direction="upward"):
        """Helper: enter zone from above, exit after grace period."""
        obs.on_price_update("BTC", 71000, 1000.0, lm, of)     # prev price
        obs.on_price_update("BTC", 70000, 1001.0, lm, of)     # enter zone
        obs.on_price_update("BTC", exit_price, 1005.0, lm, of) # first exit tick
        obs.on_price_update("BTC", exit_price, 1016.0, lm, of) # confirm after grace
        return obs.get_active_event("BTC")

    def test_finalized_after_120s(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        event = self._enter_and_exit_zone(obs, lm, of)
        assert event.state == "TRACKING"
        obs.on_price_update("BTC", 70300, event.zone_exit_ts + 121, lm, of)
        assert obs.get_active_event("BTC") is None
        assert len(obs.get_recent_events()) == 1

    def test_mfe_tracked(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        event = self._enter_and_exit_zone(obs, lm, of)
        exit_ts = event.zone_exit_ts
        obs.on_price_update("BTC", 70500, exit_ts + 10, lm, of)
        event = obs.get_active_event("BTC")
        assert event.mfe_30s > 0
        assert event.highest_since_exit == 70500

    def test_mfe_30s_frozen_after_window(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        event = self._enter_and_exit_zone(obs, lm, of)
        exit_ts = event.zone_exit_ts
        obs.on_price_update("BTC", 70300, exit_ts + 20, lm, of)
        old_mfe_30 = obs.get_active_event("BTC").mfe_30s
        assert old_mfe_30 > 0
        obs.on_price_update("BTC", 71000, exit_ts + 40, lm, of)
        assert obs.get_active_event("BTC").mfe_30s == old_mfe_30
        assert obs.get_active_event("BTC").mfe_60s > old_mfe_30

    def test_reversal_flag(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        # Enter from above, exit upward = reversal
        event = self._enter_and_exit_zone(obs, lm, of, exit_price=70200)
        obs.on_price_update("BTC", 70300, event.zone_exit_ts + 121, lm, of)
        events = obs.get_recent_events()
        assert len(events) == 1
        assert events[0].reversal is True

    def test_breach_flag(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        # Enter from above, exit downward = breach
        event = self._enter_and_exit_zone(obs, lm, of, exit_price=69800)
        obs.on_price_update("BTC", 69700, event.zone_exit_ts + 121, lm, of)
        events = obs.get_recent_events()
        assert len(events) == 1
        assert events[0].breached is True
        assert events[0].reversal is False

    def test_pending_persist_populated(self):
        obs = GravityObserver()
        zone = _make_zone(70000, side="bid", gravity=10000)
        lm = _mock_liq_map([zone])
        of = _mock_of_calc()
        event = self._enter_and_exit_zone(obs, lm, of)
        obs.on_price_update("BTC", 70300, event.zone_exit_ts + 121, lm, of)
        assert obs.get_pending_count() == 1
