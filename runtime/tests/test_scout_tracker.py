import time
import pytest
from runtime.liquidations.scout_tracker import ScoutPosition, ScoutTracker, ZoneSnapshot


def _make_zone(**kwargs):
    defaults = dict(
        center_price=94950.0, band_low=94900.0, band_high=95000.0,
        initial_size_usd=500000.0, gravity=300000.0, side="bid",
    )
    defaults.update(kwargs)
    return ZoneSnapshot(**defaults)


def test_open_scout_position():
    tracker = ScoutTracker()
    pos = tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=time.time(), zone=_make_zone(),
    )
    assert pos is not None
    assert pos.symbol == "BTCUSDT"
    assert pos.side == "LONG"
    assert tracker.has_open("BTCUSDT")


def test_one_scout_per_symbol():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=time.time(), zone=_make_zone(),
    )
    pos2 = tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95100.0, timestamp=time.time(), zone=_make_zone(),
    )
    assert pos2 is None


def test_close_scout_position():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="ETHUSDT", side="SHORT", quantity=0.05,
        entry_price=2100.0, timestamp=time.time(),
        zone=_make_zone(center_price=2110, band_low=2105, band_high=2115,
                        initial_size_usd=200000, gravity=150000, side="ask"),
    )
    pnl = tracker.close_position("ETHUSDT", exit_price=2090.0, exit_reason="ZONE_HEALTH")
    assert pnl is not None
    assert pnl > 0
    assert not tracker.has_open("ETHUSDT")


def test_zone_health_check_healthy():
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts, zone=_make_zone(),
    )
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=400000.0,
        current_price=95050.0, timestamp=ts + 5,
    )
    assert not should_exit


def test_zone_health_eaten_and_lingering():
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts, zone=_make_zone(),
    )
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=150000.0,
        current_price=94960.0, timestamp=ts + 15,
    )
    assert should_exit
    assert "eaten" in reason.lower()


def test_zone_health_max_dwell():
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts, zone=_make_zone(),
    )
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=500000.0,
        current_price=94960.0, timestamp=ts + 35,
    )
    assert should_exit
    assert "dwell" in reason.lower()


def test_zone_health_breach():
    tracker = ScoutTracker()
    ts = time.time()
    tracker.open_position(
        symbol="BTCUSDT", side="LONG", quantity=0.001,
        entry_price=95000.0, timestamp=ts, zone=_make_zone(),
    )
    should_exit, reason = tracker.check_zone_health(
        "BTCUSDT", current_zone_size_usd=500000.0,
        current_price=94850.0, timestamp=ts + 3,
    )
    assert should_exit
    assert "breach" in reason.lower()


def test_pnl_long():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="SOLUSDT", side="LONG", quantity=1.0,
        entry_price=100.0, timestamp=time.time(),
        zone=_make_zone(center_price=99.5, band_low=99.0, band_high=100.0,
                        initial_size_usd=50000, gravity=30000),
    )
    pnl = tracker.close_position("SOLUSDT", exit_price=100.5, exit_reason="TRAILING_STOP")
    assert abs(pnl - 0.50) < 0.01


def test_pnl_short():
    tracker = ScoutTracker()
    tracker.open_position(
        symbol="SOLUSDT", side="SHORT", quantity=1.0,
        entry_price=100.0, timestamp=time.time(),
        zone=_make_zone(center_price=100.5, band_low=100.0, band_high=101.0,
                        initial_size_usd=50000, gravity=30000, side="ask"),
    )
    pnl = tracker.close_position("SOLUSDT", exit_price=99.5, exit_reason="TRAILING_STOP")
    assert abs(pnl - 0.50) < 0.01


def test_multiple_symbols():
    scout = ScoutTracker()
    ts = time.time()
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        scout.open_position(sym, "LONG", 1.0, 100.0, ts, _make_zone())
    assert len(scout.get_all_open()) == 3
    scout.close_position("ETHUSDT", 100.5, "ZONE_HEALTH")
    assert len(scout.get_all_open()) == 2


def test_zone_health_not_triggered_when_bouncing():
    scout = ScoutTracker()
    ts = time.time()
    scout.open_position("BTCUSDT", "LONG", 0.001, 95000.0, ts, _make_zone())
    should_exit, _ = scout.check_zone_health(
        "BTCUSDT", current_zone_size_usd=480000,
        current_price=95200.0, timestamp=ts + 8)
    assert not should_exit


def test_short_zone_breach():
    scout = ScoutTracker()
    ts = time.time()
    scout.open_position(
        "ETHUSDT", "SHORT", 0.05, 2100.0, ts,
        zone=_make_zone(center_price=2110, band_low=2105, band_high=2115,
                        initial_size_usd=200000, gravity=150000, side="ask"),
    )
    should_exit, reason = scout.check_zone_health(
        "ETHUSDT", current_zone_size_usd=200000,
        current_price=2120.0, timestamp=ts + 3)
    assert should_exit
    assert "breach" in reason.lower()
