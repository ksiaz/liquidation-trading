"""
Unit Tests for Database Writer

Tests verify write-only persistence without actual database.

RULE: Mock database connections.
RULE: Verify fail-closed behavior.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
sys.path.append('d:/liquidation-trading')

from data_pipeline.normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
)
from data_pipeline.storage.writer import DatabaseWriter


class TestDatabaseWriter:
    """Test database writer."""
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_connection_success(self, mock_connect):
        """Writer connects to database successfully."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        
        # Connection established
        assert writer.conn == mock_conn
        mock_connect.assert_called_once_with("postgresql://test")
        assert mock_conn.autocommit == True
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_connection_failure_raises(self, mock_connect):
        """Connection failure raises RuntimeError."""
        mock_connect.side_effect = Exception("DB unavailable")
        
        with pytest.raises(RuntimeError, match="Failed to connect"):
            DatabaseWriter("postgresql://test")
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_write_orderbook(self, mock_connect):
        """Orderbook events are written correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        event = OrderbookEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            bids="[[100.0, 1.0]]",
            asks="[[101.0, 1.0]]"
        )
        
        writer.write_orderbook(event)
        
        # Verify SQL execution
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO orderbook_events" in sql
        assert params[0] == "test-id"
        assert params[1] == 1000.0
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_write_trade(self, mock_connect):
        """Trade events are written correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        event = TradeEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            price=50000.0,
            quantity=1.0,
            is_buyer_maker=True
        )
        
        writer.write_trade(event)
        
        # Verify SQL execution
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO trade_events" in sql
        assert params[4] == 50000.0  # price
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_write_liquidation(self, mock_connect):
        """Liquidation events are written correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        event = LiquidationEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            side="SELL",
            price=50000.0,
            quantity=1.0
        )
        
        writer.write_liquidation(event)
        
        # Verify SQL execution
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO liquidation_events" in sql
        assert params[4] == "SELL"  # side
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_write_candle(self, mock_connect):
        """Candle events are written correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        event = CandleEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=1000.0,
            is_closed=True
        )
        
        writer.write_candle(event)
        
        # Verify SQL execution
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "INSERT INTO candle_events" in sql
        assert params[7] == 50050.0  # close
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_write_failure_raises(self, mock_connect):
        """Write failure raises RuntimeError (fail-closed)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB write failed")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        event = TradeEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            price=50000.0,
            quantity=1.0,
            is_buyer_maker=True
        )
        
        # EXPECT: Exception raised (fail closed)
        with pytest.raises(RuntimeError, match="Failed to write"):
            writer.write_trade(event)
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_context_manager(self, mock_connect):
        """Writer works as context manager."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        with DatabaseWriter("postgresql://test") as writer:
            assert writer.conn == mock_conn
        
        # Connection closed
        mock_conn.close.assert_called_once()
    
    @patch('data_pipeline.storage.writer.psycopg2.connect')
    def test_close(self, mock_connect):
        """close() closes connection."""
        mock_conn = Mock()
        mock_connect.return_value = mock_conn
        
        writer = DatabaseWriter("postgresql://test")
        writer.close()
        
        mock_conn.close.assert_called_once()
        assert writer.conn is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
