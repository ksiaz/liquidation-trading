"""
Unit Tests for Derived Metrics Module

Tests implement requirements from PROMPT 2:
- VWAP calculation and session reset
- ATR(1m, 5m, 30m) with 14-period window
- Volume flows (10s, 30s windows)
- Liquidation z-score (60m baseline)
- Open interest delta
- Deterministic behavior

RULE: All tests are deterministic.
RULE: No randomness or data mocking.
"""

import pytest
import time
from datetime import datetime, timezone
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion import AggressiveTrade, Kline, LiquidationEvent
from masterframe.metrics import DerivedMetrics, MetricsEngine
from masterframe.metrics.vwap import VWAPCalculator
from masterframe.metrics.atr import ATRCalculator
from masterframe.metrics.volume_flow import VolumeFlowCalculator
from masterframe.metrics.liquidation_zscore import LiquidationZScoreCalculator
from masterframe.metrics.oi_delta import OITracker
from masterframe.metrics.resample import resample_klines_to_30m


class TestVWAP:
    """Test VWAP calculator."""
    
    def test_vwap_calculation(self):
        """Known price/volume → exact VWAP."""
        calc = VWAPCalculator()
        
        # Create trades with known values
        base_time = time.time()
        trades = (
            AggressiveTrade(base_time, 100.0, 1.0, True),  # 100 * 1 = 100
            AggressiveTrade(base_time + 1, 110.0, 2.0, False),  # 110 * 2 = 220
            AggressiveTrade(base_time + 2, 105.0, 3.0, True),  # 105 * 3 = 315
        )
        
        calc.update(trades, base_time + 2)
        vwap = calc.get_vwap()
        
        # VWAP = (100 + 220 + 315) / (1 + 2 + 3) = 635 / 6 = 105.833...
        assert vwap is not None
        assert abs(vwap - 105.833333) < 0.001
    
    def test_vwap_returns_none_until_first_trade(self):
        """VWAP returns None until first trade."""
        calc = VWAPCalculator()
        
        assert calc.get_vwap() is None
        
        # Update with empty trades
        calc.update((), time.time())
        assert calc.get_vwap() is None
    
    def test_vwap_session_reset(self):
        """VWAP resets at session boundary."""
        calc = VWAPCalculator()
        
        # Create timestamp for today 23:59
        now = datetime.now(timezone.utc)
        today_end = now.replace(hour=23, minute=59, second=0, microsecond=0)
        today_ts = today_end.timestamp()
        
        # Add trades today
        trades_today = (
            AggressiveTrade(today_ts, 100.0, 1.0, True),
        )
        calc.update(trades_today, today_ts)
        vwap_today = calc.get_vwap()
        assert vwap_today == 100.0
        
        # Now add trades tomorrow (new session)
        tomorrow_ts = today_ts + 120  # 2 minutes later (new day)
        trades_tomorrow = (
            AggressiveTrade(tomorrow_ts, 200.0, 1.0, True),
        )
        calc.update(trades_tomorrow, tomorrow_ts)
        vwap_tomorrow = calc.get_vwap()
        
        # Should reset to just the new trade
        assert vwap_tomorrow == 200.0


class TestATR:
    """Test ATR calculator."""
    
    def create_kline(self, ts: float, o: float, h: float, l: float, c: float, interval='1m'):
        return Kline(ts, o, h, l, c, 1000.0, interval)
    
    def test_atr_returns_none_until_14_candles(self):
        """ATR returns None until 14 candles available."""
        calc = ATRCalculator('1m')
        
        assert calc.get_atr() is None
        
        # Add 13 candles
        base_time = time.time()
        klines = tuple(
            self.create_kline(base_time + i*60, 100.0, 101.0, 99.0, 100.5)
            for i in range(13)
        )
        calc.update(klines)
        
        assert calc.get_atr() is None
        
        # Add 14th candle
        klines_14 = klines + (self.create_kline(base_time + 13*60, 100.0, 101.0, 99.0, 100.5),)
        calc.update(klines_14)
        
        assert calc.get_atr() is not None
    
    def test_atr_calculation(self):
        """Fixed-range candles → correct ATR."""
        calc = ATRCalculator('1m')
        
        base_time = time.time()
        # Create 14 candles with consistent 2.0 true range
        klines = []
        for i in range(14):
            klines.append(self.create_kline(
                base_time + i*60,
                o=100.0,
                h=102.0,  # high - low = 2.0
                l=100.0,
                c=101.0
            ))
        
        calc.update(tuple(klines))
        atr = calc.get_atr()
        
        # With consistent TR of 2.0, initial SMA should be 2.0
        assert atr is not None
        assert abs(atr - 2.0) < 0.01
    
    def test_atr_different_intervals(self):
        """Verify ATR works for 1m, 5m, 30m."""
        for interval in ('1m', '5m', '30m'):
            calc = ATRCalculator(interval)
            
            base_time = time.time()
            klines = tuple(
                self.create_kline(base_time + i*300, 100.0, 102.0, 99.0, 101.0, interval)
                for i in range(14)
            )
            
            calc.update(klines)
            atr = calc.get_atr()
            
            assert atr is not None
            assert atr > 0


class TestVolumeFlow:
    """Test volume flow calculator."""
    
    def test_volume_calculation_10s(self):
        """Controlled trades → correct buy/sell volumes (10s)."""
        calc = VolumeFlowCalculator()
        
        current_time = time.time()
        trades = (
            AggressiveTrade(current_time - 5, 100.0, 1.0, True),  # Buy
            AggressiveTrade(current_time - 3, 100.0, 2.0, False),  # Sell
            AggressiveTrade(current_time - 1, 100.0, 0.5, True),  # Buy
        )
        
        result = calc.calculate_volumes(trades, 10.0, current_time)
        
        assert result is not None
        buy_vol, sell_vol = result
        assert buy_vol == 1.5  # 1.0 + 0.5
        assert sell_vol == 2.0
    
    def test_volume_calculation_30s(self):
        """Controlled trades → correct buy/sell volumes (30s)."""
        calc = VolumeFlowCalculator()
        
        current_time = time.time()
        trades = (
            AggressiveTrade(current_time - 25, 100.0, 1.0, True),
            AggressiveTrade(current_time - 15, 100.0, 2.0, False),
            AggressiveTrade(current_time - 5, 100.0, 3.0, True),
        )
        
        result = calc.calculate_volumes(trades, 30.0, current_time)
        
        assert result is not None
        buy_vol, sell_vol = result
        assert buy_vol == 4.0  # 1.0 + 3.0
        assert sell_vol == 2.0
    
    def test_volume_returns_none_for_empty_window(self):
        """Returns None if no trades in window."""
        calc = VolumeFlowCalculator()
        
        current_time = time.time()
        # Trades outside window
        trades = (
            AggressiveTrade(current_time - 100, 100.0, 1.0, True),
        )
        
        result = calc.calculate_volumes(trades, 10.0, current_time)
        assert result is None


class TestLiquidationZScore:
    """Test liquidation z-score calculator."""
    
    def test_zscore_constant_rate(self):
        """Constant liquidation rate → z ≈ 0."""
        calc = LiquidationZScoreCalculator()
        
        current_time = time.time()
        # Create 60 minutes of constant rate (1 liquidation per minute)
        liquidations = []
        for i in range(60):
            minute_time = current_time - (60 - i) * 60
            liquidations.append(
                LiquidationEvent(minute_time, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)
            )
        
        zscore = calc.calculate_zscore(tuple(liquidations), current_time)
        
        # With constant rate, z-score should be near 0
        assert zscore is not None
        assert abs(zscore) < 0.5
    
    def test_zscore_spike(self):
        """Liquidation spike → z > threshold."""
        calc = LiquidationZScoreCalculator()
        
        current_time = time.time()
        # Create baseline: 1 liquidation per minute for 59 minutes
        liquidations = []
        for i in range(59):
            minute_time = current_time - (60 - i) * 60
            liquidations.append(
                LiquidationEvent(minute_time, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)
            )
        
        # Add spike in last minute: 10 liquidations
        for i in range(10):
            liquidations.append(
                LiquidationEvent(current_time - 30 + i, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)
            )
        
        zscore = calc.calculate_zscore(tuple(liquidations), current_time)
        
        # Spike should produce positive z-score
        assert zscore is not None
        assert zscore > 2.0
    
    def test_zscore_returns_none_insufficient_data(self):
        """Returns None until 60 minutes of data."""
        calc = LiquidationZScoreCalculator()
        
        current_time = time.time()
        # Only 20 minutes of data (less than 60 required)
        liquidations = tuple(
            LiquidationEvent(current_time - i*60, "BTCUSDT", "SELL", 0.1, 100.0, 10.0)
            for i in range(20)
        )
        
        zscore = calc.calculate_zscore(liquidations, current_time)
        assert zscore is None


class TestOITracker:
    """Test open interest delta tracker."""
    
    def test_oi_delta_calculation(self):
        """OI change → correct delta."""
        tracker = OITracker()
        
        # First update (no previous)
        tracker.update(1000.0)
        assert tracker.get_delta() is None
        
        # Second update
        tracker.update(1050.0)
        delta = tracker.get_delta()
        assert delta == 50.0
        
        # Third update
        tracker.update(1030.0)
        delta = tracker.get_delta()
        assert delta == -20.0
    
    def test_oi_returns_none_if_unavailable(self):
        """Returns None if OI unavailable."""
        tracker = OITracker()
        
        tracker.update(None)
        assert tracker.get_delta() is None
        
        tracker.update(1000.0)
        assert tracker.get_delta() is None  # Still None (no previous)
        
        tracker.update(None)
        assert tracker.get_delta() is None  # Current unavailable


class TestResample:
    """Test 30m kline resampling."""
    
    def create_kline(self, ts: float, o: float, h: float, l: float, c: float, v: float):
        return Kline(ts, o, h, l, c, v, '5m')
    
    def test_resample_5m_to_30m(self):
        """6 x 5m klines → 1 x 30m kline."""
        base_time = time.time()
        
        klines_5m = tuple(
            self.create_kline(
                base_time + i*300,
                o=100.0 + i,
                h=102.0 + i,
                l=99.0 + i,
                c=101.0 + i,
                v=100.0
            )
            for i in range(6)
        )
        
        klines_30m = resample_klines_to_30m(klines_5m)
        
        assert klines_30m is not None
        assert len(klines_30m) == 1
        
        k30 = klines_30m[0]
        assert k30.open == 100.0  # First open
        assert k30.close == 106.0  # Last close
        assert k30.high == 107.0  # Max high
        assert k30.low == 99.0    # Min low
        assert k30.volume == 600.0  # Sum volumes
        assert k30.interval == '30m'
    
    def test_resample_insufficient_data(self):
        """< 6 klines → None."""
        klines_5m = tuple(
            self.create_kline(time.time() + i*300, 100.0, 101.0, 99.0, 100.5, 100.0)
            for i in range(5)
        )
        
        result = resample_klines_to_30m(klines_5m)
        assert result is None


class TestDeterministic:
    """Test deterministic behavior across all metrics."""
    
    def test_deterministic_behavior(self):
        """Same inputs → same outputs."""
        # Create two identical calculators
        calc1 = VWAPCalculator()
        calc2 = VWAPCalculator()
        
        # Feed identical trades
        base_time = 1704196800.0  # Fixed timestamp
        trades = (
            AggressiveTrade(base_time, 100.0, 1.0, True),
            AggressiveTrade(base_time + 1, 110.0, 2.0, False),
        )
        
        calc1.update(trades, base_time + 1)
        calc2.update(trades, base_time + 1)
        
        vwap1 = calc1.get_vwap()
        vwap2 = calc2.get_vwap()
        
        assert vwap1 is not None
        assert vwap2 is not None
        assert vwap1 == vwap2


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
