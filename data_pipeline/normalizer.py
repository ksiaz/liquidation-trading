"""
Event Normalizer

Converts live feed events to normalized schemas.

RULE: 1:1 mapping - no processing.
RULE: Preserve all fields.
RULE: No derived metrics.
"""

from .live_feeds import (
    LiveOrderbookSnapshot,
    LiveTrade,
    LiveLiquidation,
    LiveKline,
)
from .normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
    generate_event_id,
    serialize_orderbook_levels,
)


class EventNormalizer:
    """
    Convert live feed events to normalized schemas.
    
    RULE: Direct field mapping only.
    RULE: No calculations or transformations.
    RULE: No filtering or aggregation.
    """
    
    @staticmethod
    def normalize_orderbook(live: LiveOrderbookSnapshot) -> OrderbookEvent:
        """
        Convert live orderbook to normalized schema.
        
        Args:
            live: Live orderbook snapshot
            
        Returns:
            Normalized orderbook event
        """
        return OrderbookEvent(
            event_id=generate_event_id(),
            timestamp=live.timestamp,
            receive_time=live.receive_time,
            symbol=live.symbol,
            bids=serialize_orderbook_levels(live.bids),
            asks=serialize_orderbook_levels(live.asks),
        )
    
    @staticmethod
    def normalize_trade(live: LiveTrade) -> TradeEvent:
        """
        Convert live trade to normalized schema.
        
        Args:
            live: Live trade event
            
        Returns:
            Normalized trade event
        """
        return TradeEvent(
            event_id=generate_event_id(),
            timestamp=live.timestamp,
            receive_time=live.receive_time,
            symbol=live.symbol,
            price=live.price,
            quantity=live.quantity,
            is_buyer_maker=live.is_buyer_maker,
        )
    
    @staticmethod
    def normalize_liquidation(live: LiveLiquidation) -> LiquidationEvent:
        """
        Convert live liquidation to normalized schema.
        
        Args:
            live: Live liquidation event
            
        Returns:
            Normalized liquidation event
        """
        return LiquidationEvent(
            event_id=generate_event_id(),
            timestamp=live.timestamp,
            receive_time=live.receive_time,
            symbol=live.symbol,
            side=live.side,
            price=live.price,
            quantity=live.quantity,
        )
    
    @staticmethod
    def normalize_candle(live: LiveKline) -> CandleEvent:
        """
        Convert live kline to normalized schema.
        
        Args:
            live: Live kline event
            
        Returns:
            Normalized candle event
        """
        return CandleEvent(
            event_id=generate_event_id(),
            timestamp=live.timestamp,
            receive_time=live.receive_time,
            symbol=live.symbol,
            open=live.open,
            high=live.high,
            low=live.low,
            close=live.close,
            volume=live.volume,
            is_closed=live.is_closed,
        )
