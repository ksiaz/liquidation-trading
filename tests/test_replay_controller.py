"""
Unit Tests for Replay Controller

Tests verify:
- Complete replay orchestration
- Deterministic execution
- Event counting
- Result collection

RULE: All tests are deterministic.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion import (
    OrderbookSnapshot, AggressiveTrade, 
    LiquidationEvent, Kline
)
from masterframe.replay import ReplayController


class TestReplayController:
    """Test replay controller orchestration."""
    
    def create_sample_data(self, count: int = 50):
        """Helper to create sample historical data."""
        base_time = 1000.0
        
        orderbooks = [OrderbookSnapshot(
            timestamp=base_time + i,
            bids=((100.0 - i * 0.1, 1.0),),
            asks=((101.0 + i * 0.1, 1.0),),
            mid_price=100.5 + i * 0.05
        ) for i in range(count)]
        
        trades = [AggressiveTrade(
            timestamp=base_time + i,
            price=100.0 + i * 0.1,
            quantity=0.5,
            is_buyer_aggressor=i % 2 == 0
        ) for i in range(count)]
        
        liqs = [LiquidationEvent(
            timestamp=base_time + i,
            symbol="BTCUSDT",
            side="SELL" if i % 2 == 0 else "BUY",
            quantity=0.1,
            price=100.0 + i * 0.1,
            value_usd=10.0
        ) for i in range(count)]
        
        klines_1m = [Kline(
            timestamp=base_time + i,
            open=100.0,
            high=101.0 + i * 0.1,
            low=99.0 - i * 0.05,
            close=100.5 + i * 0.05,
            volume=1000.0 + i * 10,
            interval='1m'
        ) for i in range(count)]
        
        klines_5m = [Kline(
            timestamp=base_time + i * 5,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=5000.0,
            interval='5m'
        ) for i in range(count // 5)]
        
        return orderbooks, trades, liqs, klines_1m, klines_5m
    
    def test_complete_replay(self):
        """Run complete replay with sample data."""
        controller = ReplayController(symbol="BTCUSDT")
        
        # Create data
        orderbooks, trades, liqs, klines_1m, klines_5m = self.create_sample_data(50)
        
        # Run replay
        summary = controller.run_replay(
            orderbooks=orderbooks,
            trades=trades,
            liquidations=liqs,
            klines_1m=klines_1m,
            klines_5m=klines_5m
        )
        
        # EXPECT: Summary with results
        assert summary['symbol'] == "BTCUSDT"
        assert summary['events_processed'] > 0
        assert summary['events_scheduled'] > 0
        assert 'executions' in summary
        assert 'final_time' in summary
        assert isinstance(summary['results'], list)
    
    def test_deterministic_results(self):
        """Same data produces same results."""
        # Create data once
        orderbooks, trades, liqs, klines_1m, klines_5m = self.create_sample_data(30)
        
        # Run replay twice
        controller1 = ReplayController(symbol="BTCUSDT")
        summary1 = controller1.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        controller2 = ReplayController(symbol="BTCUSDT")
        summary2 = controller2.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        # EXPECT: Identical results
        assert summary1['events_processed'] == summary2['events_processed']
        assert summary1['executions'] == summary2['executions']
        assert summary1['final_time'] == summary2['final_time']
    
    def test_event_counting(self):
        """Events are correctly counted."""
        controller = ReplayController()
        
        orderbooks, trades, liqs, klines_1m, klines_5m = self.create_sample_data(20)
        
        summary = controller.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        # Total events = orderbooks + trades + liqs + klines_1m + klines_5m
        expected_events = 20 + 20 + 20 + 20 + 4  # 84 total
        assert summary['events_scheduled'] == expected_events
        assert summary['events_processed'] == expected_events
    
    def test_result_collection(self):
        """Results are collected correctly."""
        controller = ReplayController()
        
        orderbooks, trades, liqs, klines_1m, klines_5m = self.create_sample_data(25)
        
        summary = controller.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        # Get results
        results = controller.get_results()
        
        # EXPECT: Results list matches summary
        assert len(results) == summary['executions']
        assert results == summary['results']
        
        # Each result should have required fields
        if len(results) > 0:
            result = results[0]
            assert 'timestamp' in result
            assert 'regime' in result
            assert 'execution_count' in result
    
    def test_get_execution_count(self):
        """Execution count accessor works."""
        controller = ReplayController()
        
        assert controller.get_execution_count() == 0
        
        orderbooks, trades, liqs, klines_1m, klines_5m = self.create_sample_data(15)
        
        controller.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        assert controller.get_execution_count() == len(controller.get_results())


class TestReplayControllerIntegration:
    """Test full integration."""
    
    def test_end_to_end_replay(self):
        """Complete end-to-end replay."""
        # Create realistic data
        base_time = 1704196800.0  # Jan 2, 2024
        count = 100
        
        orderbooks = [OrderbookSnapshot(
            timestamp=base_time + i,
            bids=((50000.0, 1.0), (49999.0, 2.0)),
            asks=((50001.0, 1.0), (50002.0, 2.0)),
            mid_price=50000.5
        ) for i in range(count)]
        
        trades = [AggressiveTrade(
            timestamp=base_time + i,
            price=50000.0,
            quantity=0.1,
            is_buyer_aggressor=True
        ) for i in range(count)]
        
        liqs = [LiquidationEvent(
            timestamp=base_time + i,
            symbol="BTCUSDT",
            side="SELL",
            quantity=0.5,
            price=50000.0,
            value_usd=25000.0
        ) for i in range(count)]
        
        klines_1m = [Kline(
            timestamp=base_time + i,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50000.0,
            volume=10.0,
            interval='1m'
        ) for i in range(count)]
        
        klines_5m = [Kline(
            timestamp=base_time + i * 5,
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50000.0,
            volume=50.0,
            interval='5m'
        ) for i in range(count // 5)]
        
        # Run replay
        controller = ReplayController(symbol="BTCUSDT")
        summary = controller.run_replay(
            orderbooks, trades, liqs, klines_1m, klines_5m
        )
        
        # Validate
        assert summary['symbol'] == "BTCUSDT"
        assert summary['events_processed'] > 0
        assert summary['final_time'] >= base_time


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
