"""
Unit Tests for Database Replay Feeds

Tests verify streaming feed adapters without actual database.

RULE: Mock database cursors.
RULE: Test interface compatibility.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
sys.path.append('d:/liquidation-trading')

from data_pipeline.replay.db_feeds import (
    DatabaseOrderbookFeed,
    DatabaseTradeFeed,
    DatabaseLiquidationFeed,
    DatabaseCandleFeed,
)


class TestDatabaseOrderbookFeed:
    """Test orderbook replay feed."""
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_initialization(self, mock_connect):
        """Feed initializes with connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No data
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
        
        assert feed.symbol == "BTCUSDT"
        mock_connect.assert_called_once()
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_has_more_with_data(self, mock_connect):
        """has_more() returns True when data available."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock data row
        mock_cursor.fetchone.return_value = (
            1000.0,  # timestamp
            '[[50000.0, 1.0]]',  # bids JSON
            '[[50001.0, 1.0]]'   # asks JSON
        )
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
        
        assert feed.has_more() == True
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_has_more_no_data(self, mock_connect):
        """has_more() returns False when no data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
        
        assert feed.has_more() == False
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_peek_next_timestamp(self, mock_connect):
        """peek_next_timestamp() returns timestamp without consuming."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            1234.0,
            '[[50000.0, 1.0]]',
            '[[50001.0, 1.0]]'
        )
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
        
        ts = feed.peek_next_timestamp()
        assert ts == 1234.0
        
        # Peek again - should be same
        ts2 = feed.peek_next_timestamp()
        assert ts2 == 1234.0
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_emit_next(self, mock_connect):
        """emit_next() consumes event and advances."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Two rows, then None
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            (2000.0, '[[50100.0, 1.0]]', '[[50101.0, 1.0]]'),
            None
        ]
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
        
        # Emit first
        event1 = feed.emit_next()
        assert event1 is not None
        assert event1.timestamp == 1000.0
        assert event1.event_type == 'orderbook'
        
        # Emit second
        event2 = feed.emit_next()
        assert event2 is not None
        assert event2.timestamp == 2000.0
        
        # No more
        event3 = feed.emit_next()
        assert event3 is None
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_time_range_filter(self, mock_connect):
        """Time range parameters added to SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseOrderbookFeed(
            "postgresql://test", 
            "BTCUSDT",
            start_time=100.0,
            end_time=200.0
        )
        
        # Verify SQL includes time filters
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        assert "timestamp >=" in sql
        assert "timestamp <" in sql
        assert 100.0 in params
        assert 200.0 in params


class TestDatabaseTradeFeed:
    """Test trade replay feed."""
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_emit_trade_event(self, mock_connect):
        """Trade events emitted correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_cursor.fetchone.side_effect = [
            (1000.0, 50000.0, 1.5, True),  # trade data
            None
        ]
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseTradeFeed("postgresql://test", "BTCUSDT")
        
        event = feed.emit_next()
        
        assert event.timestamp == 1000.0
        assert event.event_type == 'trade'
        assert event.data.price == 50000.0
        assert event.data.quantity == 1.5


class TestDatabaseLiquidationFeed:
    """Test liquidation replay feed."""
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_emit_liquidation_event(self, mock_connect):
        """Liquidation events emitted correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_cursor.fetchone.side_effect = [
            (1000.0, "SELL", 50000.0, 2.0),
            None
        ]
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseLiquidationFeed("postgresql://test", "BTCUSDT")
        
        event = feed.emit_next()
        
        assert event.timestamp == 1000.0
        assert event.event_type == 'liquidation'
        assert event.data.side == "SELL"
        assert event.data.quantity == 2.0


class TestDatabaseCandleFeed:
    """Test candle replay feed."""
    
    @patch('data_pipeline.replay.db_feeds.psycopg2.connect')
    def test_emit_candle_event(self, mock_connect):
        """Candle events emitted correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_cursor.fetchone.side_effect = [
            (1000.0, 50000.0, 50100.0, 49900.0, 50050.0, 1000.0, True),
            None
        ]
        
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        feed = DatabaseCandleFeed("postgresql://test", "BTCUSDT")
        
        event = feed.emit_next()
        
        assert event.timestamp == 1000.0
        assert event.event_type == 'kline'
        assert event.data.open == 50000.0
        assert event.data.close == 50050.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
