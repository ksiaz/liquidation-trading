"""
Feed Parity Validation Tests

Prove live feeds and replay feeds are interchangeable.

RULE: No branching on data source.
RULE: Same handler functions work for both.
RULE: Same event shapes.

This validates V4 replay invariant: Interface Parity.
"""

import pytest
import sys
from unittest.mock import MagicMock
sys.path.append('d:/liquidation-trading')

from masterframe.replay import Event
from data_pipeline.replay.db_feeds import (
    DatabaseOrderbookFeed,
    DatabaseTradeFeed,
    DatabaseLiquidationFeed,
    DatabaseCandleFeed,
)


class TestInterfaceParity:
    """Test all feeds expose same interface."""
    
    def test_all_feeds_have_required_methods(self):
        """All feed types have required interface methods."""
        required_methods = ['has_more', 'peek_next_timestamp', 'emit_next']
        
        feed_classes = [
            DatabaseOrderbookFeed,
            DatabaseTradeFeed,
            DatabaseLiquidationFeed,
            DatabaseCandleFeed,
        ]
        
        for feed_class in feed_classes:
            for method in required_methods:
                assert hasattr(feed_class, method), \
                    f"{feed_class.__name__} missing {method}"
    
    def test_method_signatures_consistent(self):
        """Interface methods have consistent signatures."""
        # All feeds have same method signatures
        # has_more() -> bool
        # peek_next_timestamp() -> Optional[float]
        # emit_next() -> Optional[Event]
        
        import inspect
        
        # Check has_more signature
        sig = inspect.signature(DatabaseOrderbookFeed.has_more)
        assert len(sig.parameters) == 1  # self only
        
        # Check peek_next_timestamp signature
        sig = inspect.signature(DatabaseOrderbookFeed.peek_next_timestamp)
        assert len(sig.parameters) == 1  # self only
        
        # Check emit_next signature
        sig = inspect.signature(DatabaseOrderbookFeed.emit_next)
        assert len(sig.parameters) == 1  # self only


class TestEventShapeParity:
    """Test events have identical structure."""
    
    def test_event_wrapper_uniform(self):
        """All feeds emit Event objects."""
        # Mock feed
        from unittest.mock import patch
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            None
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            event = feed.emit_next()
        
        # Verify Event structure
        assert hasattr(event, 'timestamp')
        assert hasattr(event, 'event_type')
        assert hasattr(event, 'data')
        assert isinstance(event.timestamp, float)
        assert isinstance(event.event_type, str)
    
    def test_all_feeds_emit_same_event_type(self):
        """All feeds emit Event wrapper."""
        from unittest.mock import patch
        
        # Test orderbook feed
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            None
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            event = feed.emit_next()
            assert isinstance(event, Event)
        
        # Test trade feed
        mock_cursor.fetchone.side_effect = [
            (1000.0, 50000.0, 1.0, True),
            None
        ]
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseTradeFeed("postgresql://test", "BTCUSDT")
            event = feed.emit_next()
            assert isinstance(event, Event)


class TestHandlerCompatibility:
    """Test single handler works with all feeds."""
    
    def test_handler_processes_any_feed(self):
        """Single handler function works with any feed type."""
        from unittest.mock import patch
        
        # Define source-agnostic handler
        events_received = []
        
        def universal_handler(event):
            """Handler that works with any feed."""
            # RULE: No branching on source
            # RULE: No isinstance checks
            
            result = {
                'timestamp': event.timestamp,
                'type': event.event_type,
                'has_data': event.data is not None
            }
            events_received.append(result)
            return result
        
        # Test with database orderbook feed
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            None
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            event = feed.emit_next()
            result = universal_handler(event)
        
        # Handler worked
        assert result['timestamp'] == 1000.0
        assert result['type'] == 'orderbook'
        assert result['has_data'] == True
        
        # Test with trade feed
        events_received.clear()
        mock_cursor.fetchone.side_effect = [
            (2000.0, 50000.0, 1.0, True),
            None
        ]
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseTradeFeed("postgresql://test", "BTCUSDT")
            event = feed.emit_next()
            result = universal_handler(event)
        
        # Same handler, different feed type
        assert result['timestamp'] == 2000.0
        assert result['type'] == 'trade'
        assert result['has_data'] == True


class TestOrderingParity:
    """Test ordering guarantees are identical."""
    
    def test_timestamp_monotonicity(self):
        """Feeds maintain timestamp ordering."""
        from unittest.mock import patch
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Multiple events in order
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            (2000.0, '[[50100.0, 1.0]]', '[[50101.0, 1.0]]'),
            (3000.0, '[[50200.0, 1.0]]', '[[50201.0, 1.0]]'),
            None
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            
            timestamps = []
            while feed.has_more():
                event = feed.emit_next()
                timestamps.append(event.timestamp)
            
            # Verify monotonic ordering
            for i in range(len(timestamps) - 1):
                assert timestamps[i] <= timestamps[i+1], \
                    "Timestamps not monotonic"
    
    def test_peek_does_not_consume(self):
        """peek_next_timestamp() doesn't advance cursor."""
        from unittest.mock import patch
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]')
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            
            # Peek multiple times
            ts1 = feed.peek_next_timestamp()
            ts2 = feed.peek_next_timestamp()
            ts3 = feed.peek_next_timestamp()
            
            # All should be same (not consumed)
            assert ts1 == ts2 == ts3 == 1000.0


class TestNoSourceAwareness:
    """Test consumer code can't detect source."""
    
    def test_no_type_checking_required(self):
        """Consumer doesn't need isinstance checks."""
        from unittest.mock import patch
        
        def process_feed(feed):
            """
            Process any feed without knowing its type.
            
            RULE: No isinstance checks.
            RULE: No hasattr for source detection.
            """
            events = []
            
            # Use interface only
            while feed.has_more():
                ts = feed.peek_next_timestamp()
                assert ts is not None
                
                event = feed.emit_next()
                events.append(event)
            
            return events
        
        # Works with any feed type
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (1000.0, '[[50000.0, 1.0]]', '[[50001.0, 1.0]]'),
            None
        ]
        mock_conn.cursor.return_value = mock_cursor
        
        with patch('data_pipeline.replay.db_feeds.psycopg2.connect', return_value=mock_conn):
            feed = DatabaseOrderbookFeed("postgresql://test", "BTCUSDT")
            events = process_feed(feed)
            
            assert len(events) == 1
            assert events[0].timestamp == 1000.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
