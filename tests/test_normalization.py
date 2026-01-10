"""
Unit Tests for Event Normalization

Tests verify schema normalization without processing.

RULE: No trading logic.
RULE: 1:1 mapping verification.
"""

import pytest
import json
import sys
sys.path.append('d:/liquidation-trading')

from data_pipeline import (
    LiveOrderbookSnapshot,
    LiveTrade,
    LiveLiquidation,
    LiveKline,
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
    EventNormalizer,
)
from data_pipeline.normalized_events import (
    generate_event_id,
    serialize_orderbook_levels,
    deserialize_orderbook_levels,
)


class TestNormalizedEventSchemas:
    """Test normalized event immutability."""
    
    def test_orderbook_event_immutable(self):
        """OrderbookEvent is immutable."""
        event = OrderbookEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            bids="[[100.0, 1.0]]",
            asks="[[101.0, 1.0]]"
        )
        
        with pytest.raises(AttributeError):
            event.timestamp = 2000.0
    
    def test_trade_event_immutable(self):
        """TradeEvent is immutable."""
        event = TradeEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            price=100.0,
            quantity=1.0,
            is_buyer_maker=True
        )
        
        with pytest.raises(AttributeError):
            event.price = 200.0
    
    def test_liquidation_event_immutable(self):
        """LiquidationEvent is immutable."""
        event = LiquidationEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            side="SELL",
            price=100.0,
            quantity=1.0
        )
        
        with pytest.raises(AttributeError):
            event.side = "BUY"
    
    def test_candle_event_immutable(self):
        """CandleEvent is immutable."""
        event = CandleEvent(
            event_id="test-id",
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
            is_closed=True
        )
        
        with pytest.raises(AttributeError):
            event.close = 200.0


class TestEventNormalization:
    """Test normalization layer."""
    
    def test_normalize_orderbook(self):
        """Orderbook normalization preserves all fields."""
        live = LiveOrderbookSnapshot(
            timestamp=1609459200.0,
            receive_time=1609459200.1,
            symbol="BTCUSDT",
            bids=((50000.0, 1.5), (49999.0, 2.0)),
            asks=((50001.0, 1.2), (50002.0, 0.8))
        )
        
        normalized = EventNormalizer.normalize_orderbook(live)
        
        # Verify all fields preserved
        assert normalized.timestamp == 1609459200.0
        assert normalized.receive_time == 1609459200.1
        assert normalized.symbol == "BTCUSDT"
        
        # Verify UUID generated
        assert len(normalized.event_id) > 0
        
        # Verify JSON serialization
        bids = json.loads(normalized.bids)
        asks = json.loads(normalized.asks)
        assert bids == [[50000.0, 1.5], [49999.0, 2.0]]
        assert asks == [[50001.0, 1.2], [50002.0, 0.8]]
    
    def test_normalize_trade(self):
        """Trade normalization preserves all fields."""
        live = LiveTrade(
            timestamp=1609459200.0,
            receive_time=1609459200.1,
            symbol="BTCUSDT",
            price=50000.50,
            quantity=0.1,
            is_buyer_maker=False
        )
        
        normalized = EventNormalizer.normalize_trade(live)
        
        # All fields preserved
        assert normalized.timestamp == 1609459200.0
        assert normalized.receive_time == 1609459200.1
        assert normalized.symbol == "BTCUSDT"
        assert normalized.price == 50000.50
        assert normalized.quantity == 0.1
        assert normalized.is_buyer_maker == False
        assert len(normalized.event_id) > 0
    
    def test_normalize_liquidation(self):
        """Liquidation normalization preserves all fields."""
        live = LiveLiquidation(
            timestamp=1609459200.0,
            receive_time=1609459200.1,
            symbol="BTCUSDT",
            side="SELL",
            price=50000.0,
            quantity=1.5
        )
        
        normalized = EventNormalizer.normalize_liquidation(live)
        
        # All fields preserved
        assert normalized.timestamp == 1609459200.0
        assert normalized.receive_time == 1609459200.1
        assert normalized.symbol == "BTCUSDT"
        assert normalized.side == "SELL"
        assert normalized.price == 50000.0
        assert normalized.quantity == 1.5
        assert len(normalized.event_id) > 0
    
    def test_normalize_candle(self):
        """Candle normalization preserves all fields."""
        live = LiveKline(
            timestamp=1609459200.0,
            receive_time=1609459200.1,
            symbol="BTCUSDT",
            open=50000.0,
            high=50100.0,
            low=49900.0,
            close=50050.0,
            volume=1000.0,
            is_closed=True
        )
        
        normalized = EventNormalizer.normalize_candle(live)
        
        # All fields preserved
        assert normalized.timestamp == 1609459200.0
        assert normalized.receive_time == 1609459200.1
        assert normalized.symbol == "BTCUSDT"
        assert normalized.open == 50000.0
        assert normalized.high == 50100.0
        assert normalized.low == 49900.0
        assert normalized.close == 50050.0
        assert normalized.volume == 1000.0
        assert normalized.is_closed == True
        assert len(normalized.event_id) > 0


class TestOrderbookSerialization:
    """Test orderbook JSON serialization."""
    
    def test_serialize_levels(self):
        """Levels serialize to JSON correctly."""
        levels = ((50000.0, 1.5), (49999.0, 2.0))
        
        json_str = serialize_orderbook_levels(levels)
        
        # Valid JSON
        parsed = json.loads(json_str)
        assert parsed == [[50000.0, 1.5], [49999.0, 2.0]]
    
    def test_deserialize_levels(self):
        """Levels deserialize from JSON correctly."""
        json_str = "[[50000.0, 1.5], [49999.0, 2.0]]"
        
        levels = deserialize_orderbook_levels(json_str)
        
        assert levels == [(50000.0, 1.5), (49999.0, 2.0)]
    
    def test_round_trip(self):
        """Serialize → deserialize preserves data."""
        original = ((50000.0, 1.5), (49999.0, 2.0))
        
        json_str = serialize_orderbook_levels(original)
        reconstructed = deserialize_orderbook_levels(json_str)
        
        assert list(original) == reconstructed


class TestUUIDGeneration:
    """Test UUID generation."""
    
    def test_generate_unique_ids(self):
        """Each call generates unique ID."""
        id1 = generate_event_id()
        id2 = generate_event_id()
        
        assert id1 != id2
        assert len(id1) > 0
        assert len(id2) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
