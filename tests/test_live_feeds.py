"""
Unit Tests for Live Exchange Feeds

Tests verify data acquisition infrastructure without trading logic.

RULE: No trading logic in tests.
RULE: Mock websocket messages.
"""

import pytest
import sys
sys.path.append('d:/liquidation-trading')

from data_pipeline import (
    LiveOrderbookSnapshot,
    LiveTrade,
    LiveLiquidation,
    LiveKline,
    BinanceFuturesFeeds,
)


class TestLiveDataStructures:
    """Test immutable data structures."""
    
    def test_orderbook_snapshot_immutable(self):
        """Orderbook snapshots are immutable."""
        snapshot = LiveOrderbookSnapshot(
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            bids=((100.0, 1.0),),
            asks=((101.0, 1.0),)
        )
        
        # Cannot modify
        with pytest.raises(AttributeError):
            snapshot.timestamp = 2000.0
    
    def test_trade_immutable(self):
        """Trades are immutable."""
        trade = LiveTrade(
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            price=100.0,
            quantity=1.0,
            is_buyer_maker=True
        )
        
        with pytest.raises(AttributeError):
            trade.price = 200.0
   
    def test_liquidation_immutable(self):
        """Liquidations are immutable."""
        liq = LiveLiquidation(
            timestamp=1000.0,
            receive_time=1000.1,
            symbol="BTCUSDT",
            side="SELL",
            price=100.0,
            quantity=1.0
        )
        
        with pytest.raises(AttributeError):
            liq.side = "BUY"
    
    def test_kline_immutable(self):
        """Klines are immutable."""
        kline = LiveKline(
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
            kline.close = 200.0


class TestBinanceFuturesFeeds:
    """Test feed connector."""
    
    def test_initialization(self):
        """Feed connector initializes correctly."""
        feeds = BinanceFuturesFeeds("BTCUSDT")
        
        assert feeds.symbol == "BTCUSDT"
        assert feeds.symbol_lower == "btcusdt"
        assert len(feeds.streams) == 4
    
    def test_handler_registration(self):
        """Handlers can be registered."""
        feeds = BinanceFuturesFeeds()
        
        called = []
        
        def ob_handler(snapshot):
            called.append('orderbook')
        
        def trade_handler(trade):
            called.append('trade')
        
        feeds.register_orderbook_handler(ob_handler)
        feeds.register_trade_handler(trade_handler)
        
        assert 'orderbook' in feeds._handlers
        assert 'trade' in feeds._handlers
    
    def test_parse_orderbook(self):
        """Orderbook messages parsed correctly."""
        feeds = BinanceFuturesFeeds("BTCUSDT")
        
        # Mock Binance orderbook message
        mock_data = {
            'E': 1609459200000,  # Exchange timestamp (ms)
            'b': [['50000.0', '1.5'], ['49999.0', '2.0']],
            'a': [['50001.0', '1.2'], ['50002.0', '0.8']]
        }
        
        snapshot = feeds._parse_orderbook(mock_data)
        
        # Verify parsing
        assert snapshot.timestamp == 1609459200.0
        assert snapshot.symbol == "BTCUSDT"
        assert len(snapshot.bids) == 2
        assert len(snapshot.asks) == 2
        assert snapshot.bids[0] == (50000.0, 1.5)
        assert snapshot.asks[0] == (50001.0, 1.2)
    
    def test_parse_trade(self):
        """Trade messages parsed correctly."""
        feeds = BinanceFuturesFeeds("BTCUSDT")
        
        # Mock Binance trade message
        mock_data = {
            'T': 1609459200000,
            'p': '50000.50',
            'q': '0.1',
            'm': False  # Buyer is taker (aggressive buy)
        }
        
        trade = feeds._parse_trade(mock_data)
        
        assert trade.timestamp == 1609459200.0
        assert trade.price == 50000.50
        assert trade.quantity == 0.1
        assert trade.is_buyer_maker == False
    
    def test_parse_liquidation(self):
        """Liquidation messages parsed correctly."""
        feeds = BinanceFuturesFeeds("BTCUSDT")
        
        # Mock Binance liquidation message
        mock_data = {
            'E': 1609459200000,
            'o': {
                'S': 'SELL',
                'p': '50000.0',
                'q': '1.5'
            }
        }
        
        liq = feeds._parse_liquidation(mock_data)
        
        assert liq.timestamp == 1609459200.0
        assert liq.side == 'SELL'
        assert liq.price == 50000.0
        assert liq.quantity == 1.5
    
    def test_parse_kline(self):
        """Kline messages parsed correctly."""
        feeds = BinanceFuturesFeeds("BTCUSDT")
        
        # Mock Binance kline message
        mock_data = {
            'k': {
                't': 1609459200000,  # Open time
                'o': '50000.0',
                'h': '50100.0',
                'l': '49900.0',
                'c': '50050.0',
                'v': '1000.0',
                'x': True  # Is closed
            }
        }
        
        kline = feeds._parse_kline(mock_data)
        
        assert kline.timestamp == 1609459200.0
        assert kline.open == 50000.0
        assert kline.high == 50100.0
        assert kline.low == 49900.0
        assert kline.close == 50050.0
        assert kline.volume == 1000.0
        assert kline.is_closed == True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
