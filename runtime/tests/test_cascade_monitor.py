# runtime/tests/test_cascade_monitor.py
import pytest
from runtime.liquidations.cascade_monitor import CascadeLifecycleMonitor

class TestCascadeMonitor:
    def test_quiet_no_snapshots(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=5.0, price=70000, ts=1000)  # below _Z_ACTIVE=8
        assert mon.get_phase("BTC") == "QUIET"
        assert mon.get_buffer_size("BTC") == 0

    def test_active_on_z_above_threshold(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=10.0, price=70000, ts=1000)
        assert mon.get_phase("BTC") == "ACTIVE"
        assert mon.get_buffer_size("BTC") == 1

    def test_tracks_peak_z(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=10.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=25.0, price=69900, ts=1001)
        mon.update("BTC", liq_z=15.0, price=69950, ts=1002)
        state = mon._states["BTC"]
        assert state.peak_z == 25.0
        assert mon.get_buffer_size("BTC") == 3

    def test_fading_when_z_drops_below_half_peak(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=20.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=40.0, price=69800, ts=1001)  # peak
        mon.update("BTC", liq_z=15.0, price=69850, ts=1002)  # < 40*0.5=20 → FADING
        assert mon.get_phase("BTC") == "FADING"

    def test_done_when_z_below_done_threshold(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=2.0, price=69950, ts=1001)  # < _Z_DONE=3.0 → DONE
        assert mon.get_phase("BTC") == "QUIET"

    def test_done_on_timeout(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=5.0, price=69950, ts=1000 + 121)  # > 120s, z < _Z_ACTIVE
        assert mon.get_phase("BTC") == "QUIET"

    def test_snapshot_fields(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000,
                   vwap_distance=0.5, atr_5m=100, atr_30m=300,
                   orderflow=0.35, burst_volume=50000, liq_side="LONG")
        buf = mon._states["BTC"].buffer
        snap = buf[0]
        assert snap["liq_z"] == 15.0
        assert snap["price"] == 70000
        assert snap["price_at_start"] == 70000
        assert snap["orderflow"] == 0.35

    def test_n_coins_active(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000)
        mon.update("ETH", liq_z=12.0, price=2000, ts=1000)
        mon.update("SOL", liq_z=5.0, price=90, ts=1000)  # quiet (below 8)
        mon.update("BTC", liq_z=14.0, price=70010, ts=1001)
        btc_snap = mon._states["BTC"].buffer[-1]
        assert btc_snap["n_coins_active"] == 1  # ETH active, SOL quiet

    def test_z_velocity(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=10.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=20.0, price=69900, ts=1001)
        mon.update("BTC", liq_z=30.0, price=69800, ts=1002)
        snap = mon._states["BTC"].buffer[-1]
        assert snap["z_velocity"] == pytest.approx(10.0, abs=0.5)

    def test_get_active_cascade_id(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000)
        cid = mon.get_active_cascade_id("BTC")
        assert cid is not None
        assert mon.get_active_cascade_id("ETH") is None

    def test_flush_returns_buffer(self):
        mon = CascadeLifecycleMonitor()
        mon.update("BTC", liq_z=15.0, price=70000, ts=1000)
        mon.update("BTC", liq_z=25.0, price=69800, ts=1001)
        mon.update("BTC", liq_z=2.0, price=69850, ts=1002)  # < _Z_DONE → DONE
        assert len(mon._pending_flush) > 0
