import pytest
import time
from runtime.liquidations.wall_tracker import WallTracker, WallStatus

class TestWallTracker:
    def test_no_events_returns_none(self):
        wt = WallTracker()
        status = wt.get_wall_status("BTC")
        assert status is None

    def test_single_reversal_tracked(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.4,
                             gravity=100000, timestamp=1000)
        status = wt.get_wall_status("BTC", now=1001)
        assert status is not None
        assert status.consecutive_reversals == 1
        assert status.is_ob is True  # min_size_ratio 0.4 = 60% absorbed >= 50% threshold

    def test_three_consecutive_reversals(self):
        wt = WallTracker()
        for i in range(3):
            wt.on_zone_finalized("BTC", zone_center=70000 + i * 5,
                                 zone_side="bid", reversal=True, breached=False,
                                 min_size_ratio=0.8, gravity=50000,
                                 timestamp=1000 + i * 30)
        status = wt.get_wall_status("BTC", now=1061)  # just after last event
        assert status.consecutive_reversals == 3

    def test_breach_resets_consecutive(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        wt.on_zone_finalized("BTC", zone_center=70005, zone_side="bid",
                             reversal=False, breached=True, min_size_ratio=0.9,
                             gravity=50000, timestamp=1030)
        status = wt.get_wall_status("BTC", now=1031)
        assert status.consecutive_reversals == 0

    def test_different_price_band_new_wall(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # 70800 = 114bp from 70000 → outside 100bp band → new wall
        wt.on_zone_finalized("BTC", zone_center=70800, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1010)
        status = wt.get_wall_status("BTC", now=1011)
        assert status.consecutive_reversals == 1

    def test_ob_detection_deep_absorption(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.6,
                             gravity=50000, timestamp=1000)
        status = wt.get_wall_status("BTC", now=1001)
        assert status.is_ob is False
        assert status.absorbed_zones == 1

        wt.on_zone_finalized("BTC", zone_center=70003, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.4,
                             gravity=50000, timestamp=1030)
        status = wt.get_wall_status("BTC", now=1031)
        assert status.is_ob is True

    def test_prior_visit_tracking(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # Gap > 15min → new wall at same level, prior visit counted
        wt.on_zone_finalized("BTC", zone_center=70002, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=2000)
        status = wt.get_wall_status("BTC", now=2001)
        assert status.prior_reversals >= 1

    def test_stale_wall_expires(self):
        wt = WallTracker()
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.8,
                             gravity=50000, timestamp=1000)
        # 20 minutes later → stale (>900s)
        status = wt.get_wall_status("BTC", now=1000 + 1200)
        assert status is None

    def test_gold_signal_requires_ob_prior_last3(self):
        wt = WallTracker()
        # Prior visit
        wt.on_zone_finalized("BTC", zone_center=70000, zone_side="bid",
                             reversal=True, breached=False, min_size_ratio=0.3,
                             gravity=100000, timestamp=1000)
        # Gap > 15min → new wall at same level
        for i in range(3):
            wt.on_zone_finalized("BTC", zone_center=70000 + i * 3,
                                 zone_side="bid", reversal=True, breached=False,
                                 min_size_ratio=0.3, gravity=100000,
                                 timestamp=2000 + i * 30)
        status = wt.get_wall_status("BTC", now=2061)
        assert status.gold_signal is True
        assert status.prior_reversals >= 1
        assert status.consecutive_reversals >= 3
        assert status.is_ob is True
