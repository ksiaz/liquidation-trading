"""
Unit Tests for Data Ingestion & Normalization Module

Tests implement requirements from OBUnitTest.md:
- TEST 1.1: Timestamp alignment
- TEST 1.2: Misaligned timestamps
- TEST 1.3: Missing stream
- TEST 1.4: Warm-up period

RULE: All tests are deterministic.
RULE: No randomness or data mocking.
RULE: Tests must FAIL CLOSED.
"""

import pytest
import time
from masterframe.data_ingestion import (
    OrderbookSnapshot,
    AggressiveTrade,
    LiquidationEvent,
    Kline,
    SynchronizedData,
    RollingBuffer,
    DataSynchronizer,
)


class TestRollingBuffer:
    """Test generic rolling buffer behavior."""
    
    def test_warm_up_period(self):
        """TEST 1.4 - Buffer returns None until min_size reached."""
        buffer = RollingBuffer[int](max_size=10, min_size=5, max_age_seconds=60.0)
        
        # Not warm initially
        assert not buffer.is_warm()
        assert buffer.get_items() is None
        assert buffer.get_latest() is None
        
        # Add 4 items - still not warm
        current_time = time.time()
        for i in range(4):
            buffer.push(i, current_time + i)
        
        assert not buffer.is_warm()
        assert buffer.get_items() is None
        
        # Add 5th item - now warm
        buffer.push(4, current_time + 4)
        assert buffer.is_warm()
        assert buffer.get_items() is not None
        assert len(buffer.get_items()) == 5
    
    def test_stale_entry_eviction(self):
        """Verify stale entries are removed."""
        buffer = RollingBuffer[str](max_size=10, min_size=1, max_age_seconds=10.0)
        
        base_time = time.time()
        
        # Add items at different times
        buffer.push("old1", base_time)
        buffer.push("old2", base_time + 1)
        buffer.push("recent", base_time + 15)  # This should evict old items
        
        # Buffer should only have "recent" after eviction
        assert buffer.is_warm()
        items = buffer.get_items()
        assert len(items) == 1
        assert items[0] == "recent"
    
    def test_no_interpolation(self):
        """Verify buffer never interpolates missing data."""
        buffer = RollingBuffer[int](max_size=10, min_size=3, max_age_seconds=60.0)
        
        current_time = time.time()
        
        # Add items with gaps
        buffer.push(1, current_time)
        buffer.push(2, current_time + 10)  # 10 second gap
        buffer.push(3, current_time + 20)  # another gap
        
        # Should have exactly 3 items, no interpolation
        assert buffer.is_warm()
        items = buffer.get_items()
        assert len(items) == 3
        assert items == (1, 2, 3)


class TestDataSynchronizer:
    """Test time-aligned data synchronization."""
    
    def create_test_orderbook(self, timestamp: float) -> OrderbookSnapshot:
        """Create test orderbook snapshot."""
        return OrderbookSnapshot(
            timestamp=timestamp,
            bids=((100.0, 1.0), (99.0, 2.0)),
            asks=((101.0, 1.0), (102.0, 2.0)),
            mid_price=100.5
        )
    
    def create_test_trade(self, timestamp: float, is_buy: bool) -> AggressiveTrade:
        """Create test trade."""
        return AggressiveTrade(
            timestamp=timestamp,
            price=100.0,
            quantity=0.5,
            is_buyer_aggressor=is_buy
        )
    
    def create_test_liquidation(self, timestamp: float) -> LiquidationEvent:
        """Create test liquidation."""
        return LiquidationEvent(
            timestamp=timestamp,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.1,
            price=100.0,
            value_usd=10.0
        )
    
    def create_test_kline(self, timestamp: float, interval: str) -> Kline:
        """Create test kline."""
        return Kline(
            timestamp=timestamp,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval=interval
        )
    
    def test_warm_up_period_returns_none(self):
        """TEST 1.4 - System returns None during warm-up period."""
        sync = DataSynchronizer("BTCUSDT")
        
        current_time = time.time()
        
        # Get snapshot before buffers are warm
        snapshot = sync.get_aligned_snapshot(current_time)
        
        # EXPECT: None (insufficient data)
        assert snapshot is None
    
    def test_missing_stream_returns_none(self):
        """TEST 1.3 - Missing stream causes None return."""
        sync = DataSynchronizer("BTCUSDT")
        
        current_time = time.time()
        
        # Warm up only some buffers (missing liquidations)
        for i in range(30):
            ts = current_time - 30 + i
            sync.push_orderbook(self.create_test_orderbook(ts))
            sync.push_trade(self.create_test_trade(ts, True))
            sync.push_kline(self.create_test_kline(ts, '1m'))
            sync.push_kline(self.create_test_kline(ts, '5m'))
            # Deliberately NOT pushing liquidations
        
        # EXPECT: None (missing liquidation stream)
        snapshot = sync.get_aligned_snapshot(current_time)
        assert snapshot is None
    
    def test_aligned_timestamps_returns_data(self):
        """TEST 1.1 - Aligned timestamps produce valid snapshot."""
        sync = DataSynchronizer("BTCUSDT")
        
        current_time = time.time()
        
        # Warm up all buffers with aligned timestamps
        # Use timestamps in the past for buffering, then update with current
        # Need at least 10 5m klines (MIN_KLINES_5M = 10)
        for i in range(50):
            ts = current_time - 50 + i
            sync.push_orderbook(self.create_test_orderbook(ts))
            sync.push_trade(self.create_test_trade(ts, i % 2 == 0))
            sync.push_liquidation(self.create_test_liquidation(ts))
            sync.push_kline(self.create_test_kline(ts, '1m'))
            
            # Push 5m kline every 3 iterations to get enough 5m klines
            if i % 3 == 0:
                sync.push_kline(self.create_test_kline(ts, '5m'))
        
        # Push final data at current_time to ensure alignment
        sync.push_orderbook(self.create_test_orderbook(current_time))
        sync.push_kline(self.create_test_kline(current_time, '1m'))
        sync.push_kline(self.create_test_kline(current_time, '5m'))
        
        # EXPECT: Valid synchronized data
        snapshot = sync.get_aligned_snapshot(current_time)
        assert snapshot is not None
        assert isinstance(snapshot, SynchronizedData)
        assert snapshot.orderbook is not None
        assert snapshot.kline_1m is not None
        assert snapshot.kline_5m is not None
        assert len(snapshot.trades) > 0
        assert len(snapshot.liquidations) > 0
    
    def test_misaligned_timestamps_returns_none(self):
        """TEST 1.2 - Misaligned timestamps cause skip."""
        sync = DataSynchronizer("BTCUSDT")
        
        current_time = time.time()
        
        # Warm up all buffers
        for i in range(35):
            ts = current_time - 35 + i
            sync.push_orderbook(self.create_test_orderbook(ts))
            sync.push_trade(self.create_test_trade(ts, True))
            sync.push_liquidation(self.create_test_liquidation(ts))
            sync.push_kline(self.create_test_kline(ts, '1m'))
            if i % 5 == 0:
                sync.push_kline(self.create_test_kline(ts, '5m'))
        
        # Push one more kline with timestamp way in the past (misaligned)
        old_timestamp = current_time - 100  # More than tolerance
        sync.push_kline(self.create_test_kline(old_timestamp, '5m'))
        
        # EXPECT: None (timestamps misaligned beyond tolerance)
        snapshot = sync.get_aligned_snapshot(current_time)
        assert snapshot is None
    
    def test_deterministic_behavior(self):
        """Verify same inputs produce same outputs."""
        sync1 = DataSynchronizer("BTCUSDT")
        sync2 = DataSynchronizer("BTCUSDT")
        
        # Use fixed timestamp for determinism
        base_time = 1704196800.0  # Fixed epoch time
        
        # Feed identical data to both synchronizers
        # Need at least 10 5m klines
        for i in range(50):
            ts = base_time + i
            
            ob = self.create_test_orderbook(ts)
            trade = self.create_test_trade(ts, i % 2 == 0)
            liq = self.create_test_liquidation(ts)
            kline_1m = self.create_test_kline(ts, '1m')
            
            sync1.push_orderbook(ob)
            sync1.push_trade(trade)
            sync1.push_liquidation(liq)
            sync1.push_kline(kline_1m)
            
            sync2.push_orderbook(ob)
            sync2.push_trade(trade)
            sync2.push_liquidation(liq)
            sync2.push_kline(kline_1m)
            
            if i % 3 == 0:
                kline_5m = self.create_test_kline(ts, '5m')
                sync1.push_kline(kline_5m)
                sync2.push_kline(kline_5m)
        
        # Get snapshots at same time - use the last timestamp
        query_time = base_time + 49
        
        # Push final aligned data at query_time
        ob = self.create_test_orderbook(query_time)
        kline_1m = self.create_test_kline(query_time, '1m')
        kline_5m = self.create_test_kline(query_time, '5m')
        
        sync1.push_orderbook(ob)
        sync1.push_kline(kline_1m)
        sync1.push_kline(kline_5m)
        
        sync2.push_orderbook(ob)
        sync2.push_kline(kline_1m)
        sync2.push_kline(kline_5m)
        
        snapshot1 = sync1.get_aligned_snapshot(query_time)
        snapshot2 = sync2.get_aligned_snapshot(query_time)
        
        # EXPECT: Identical results
        assert snapshot1 is not None
        assert snapshot2 is not None
        assert snapshot1.timestamp == snapshot2.timestamp
        assert len(snapshot1.trades) == len(snapshot2.trades)
        assert len(snapshot1.liquidations) == len(snapshot2.liquidations)
    
    def test_no_forward_looking_data(self):
        """Verify only past/current data is accessible."""
        sync = DataSynchronizer("BTCUSDT")
        
        current_time = time.time()
        
        # Warm up buffers
        for i in range(35):
            ts = current_time - 35 + i
            sync.push_orderbook(self.create_test_orderbook(ts))
            sync.push_trade(self.create_test_trade(ts, True))
            sync.push_liquidation(self.create_test_liquidation(ts))
            sync.push_kline(self.create_test_kline(ts, '1m'))
            if i % 5 == 0:
                sync.push_kline(self.create_test_kline(ts, '5m'))
        
        # Add future data
        future_time = current_time + 100
        sync.push_orderbook(self.create_test_orderbook(future_time))
        
        # Query at current time
        snapshot = sync.get_aligned_snapshot(current_time)
        
        # EXPECT: Snapshot uses only current/past data, not future
        # The future orderbook should cause misalignment
        assert snapshot is None or snapshot.orderbook.timestamp <= current_time


class TestDataTypes:
    """Test immutability of data types."""
    
    def test_orderbook_immutable(self):
        """Verify OrderbookSnapshot is immutable."""
        ob = OrderbookSnapshot(
            timestamp=time.time(),
            bids=((100.0, 1.0),),
            asks=((101.0, 1.0),),
            mid_price=100.5
        )
        
        # Attempting to modify should raise error
        with pytest.raises(Exception):  # dataclass frozen=True raises
            ob.mid_price = 999.0
    
    def test_trade_immutable(self):
        """Verify AggressiveTrade is immutable."""
        trade = AggressiveTrade(
            timestamp=time.time(),
            price=100.0,
            quantity=1.0,
            is_buyer_aggressor=True
        )
        
        with pytest.raises(Exception):
            trade.price = 999.0
    
    def test_kline_interval_validation(self):
        """Verify kline interval is preserved."""
        kline_1m = Kline(
            timestamp=time.time(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            interval='1m'
        )
        
        assert kline_1m.interval == '1m'
        
        kline_5m = Kline(
            timestamp=time.time(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=5000.0,
            interval='5m'
        )
        
        assert kline_5m.interval == '5m'


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
