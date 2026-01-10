"""
Database Replay Feed Adapters

Stream historical events from PostgreSQL for replay.

SCOPE: Read-only streaming from database.
- No preloading entire datasets
- Emit in timestamp order
- Same interface as live feeds

PRINCIPLE: Data correctness > completeness > performance
"""

import psycopg2
import json
from typing import Optional
from masterframe.data_ingestion import (
    OrderbookSnapshot,
    AggressiveTrade,
    LiquidationEvent,
    Kline,
)
from masterframe.replay import Event


class DatabaseOrderbookFeed:
    """
    Replay feed for orderbook events from database.
    
    RULE: Stream from cursor - no preloading.
    RULE: Emit in timestamp order.
    RULE: Same interface as live feed adapter.
    """
    
    def __init__(
        self,
        connection_string: str,
        symbol: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ):
        """
        Initialize database orderbook feed.
        
        Args:
            connection_string: PostgreSQL connection string
            symbol: Trading pair
            start_time: Optional start timestamp
            end_time: Optional end timestamp
        """
        self.conn = psycopg2.connect(connection_string)
        self.symbol = symbol
        self.start_time = start_time
        self.end_time = end_time
        
        self.cursor = None
        self._current = None
        self._initialize_cursor()
    
    def _initialize_cursor(self) -> None:
        """Initialize streaming cursor."""
        sql = """
            SELECT timestamp, bids, asks
            FROM orderbook_events
            WHERE symbol = %s
        """
        
        params = [self.symbol]
        
        if self.start_time is not None:
            sql += " AND timestamp >= %s"
            params.append(self.start_time)
        
        if self.end_time is not None:
            sql += " AND timestamp < %s"
            params.append(self.end_time)
        
        sql += " ORDER BY timestamp"
        
        self.cursor = self.conn.cursor()
        self.cursor.execute(sql, params)
        
        # Fetch first row
        self._advance()
    
    def _advance(self) -> None:
        """Advance to next row."""
        row = self.cursor.fetchone()
        
        if row is None:
            self._current = None
        else:
            # Parse row into OrderbookSnapshot
            timestamp, bids_json, asks_json = row
            
            bids_parsed = tuple(tuple(level) for level in json.loads(bids_json))
            asks_parsed = tuple(tuple(level) for level in json.loads(asks_json))
            
            mid_price = (bids_parsed[0][0] + asks_parsed[0][0]) / 2.0
            
            self._current = OrderbookSnapshot(
                timestamp=timestamp,
                bids=bids_parsed,
                asks=asks_parsed,
                mid_price=mid_price
            )
    
    def has_more(self) -> bool:
        """Check if more events available."""
        return self._current is not None
    
    def peek_next_timestamp(self) -> Optional[float]:
        """Get next timestamp without consuming."""
        if self._current is None:
            return None
        return self._current.timestamp
    
    def emit_next(self) -> Optional[Event]:
        """Emit next event and advance."""
        if self._current is None:
            return None
        
        event = Event(
            timestamp=self._current.timestamp,
            event_type='orderbook',
            data=self._current
        )
        
        self._advance()
        return event
    
    def close(self) -> None:
        """Close database resources."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


class DatabaseTradeFeed:
    """Replay feed for trade events from database."""
    
    def __init__(
        self,
        connection_string: str,
        symbol: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ):
        self.conn = psycopg2.connect(connection_string)
        self.symbol = symbol
        self.start_time = start_time
        self.end_time = end_time
        
        self.cursor = None
        self._current = None
        self._initialize_cursor()
    
    def _initialize_cursor(self) -> None:
        sql = """
            SELECT timestamp, price, quantity, is_buyer_maker
            FROM trade_events
            WHERE symbol = %s
        """
        
        params = [self.symbol]
        
        if self.start_time is not None:
            sql += " AND timestamp >= %s"
            params.append(self.start_time)
        
        if self.end_time is not None:
            sql += " AND timestamp < %s"
            params.append(self.end_time)
        
        sql += " ORDER BY timestamp"
        
        self.cursor = self.conn.cursor()
        self.cursor.execute(sql, params)
        self._advance()
    
    def _advance(self) -> None:
        row = self.cursor.fetchone()
        
        if row is None:
            self._current = None
        else:
            timestamp, price, quantity, is_buyer_maker = row
            
            self._current = AggressiveTrade(
                timestamp=timestamp,
                price=price,
                quantity=quantity,
                is_buyer_aggressor=not is_buyer_maker  # aggressor is opposite of maker
            )
    
    def has_more(self) -> bool:
        return self._current is not None
    
    def peek_next_timestamp(self) -> Optional[float]:
        if self._current is None:
            return None
        return self._current.timestamp
    
    def emit_next(self) -> Optional[Event]:
        if self._current is None:
            return None
        
        event = Event(
            timestamp=self._current.timestamp,
            event_type='trade',
            data=self._current
        )
        
        self._advance()
        return event
    
    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


class DatabaseLiquidationFeed:
    """Replay feed for liquidation events from database."""
    
    def __init__(
        self,
        connection_string: str,
        symbol: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ):
        self.conn = psycopg2.connect(connection_string)
        self.symbol = symbol
        self.start_time = start_time
        self.end_time = end_time
        
        self.cursor = None
        self._current = None
        self._initialize_cursor()
    
    def _initialize_cursor(self) -> None:
        sql = """
            SELECT timestamp, side, price, quantity
            FROM liquidation_events
            WHERE symbol = %s
        """
        
        params = [self.symbol]
        
        if self.start_time is not None:
            sql += " AND timestamp >= %s"
            params.append(self.start_time)
        
        if self.end_time is not None:
            sql += " AND timestamp < %s"
            params.append(self.end_time)
        
        sql += " ORDER BY timestamp"
        
        self.cursor = self.conn.cursor()
        self.cursor.execute(sql, params)
        self._advance()
    
    def _advance(self) -> None:
        row = self.cursor.fetchone()
        
        if row is None:
            self._current = None
        else:
            timestamp, side, price, quantity = row
            
            self._current = LiquidationEvent(
                timestamp=timestamp,
                symbol=self.symbol,
                side=side,
                quantity=quantity,
                price=price,
                value_usd=price * quantity
            )
    
    def has_more(self) -> bool:
        return self._current is not None
    
    def peek_next_timestamp(self) -> Optional[float]:
        if self._current is None:
            return None
        return self._current.timestamp
    
    def emit_next(self) -> Optional[Event]:
        if self._current is None:
            return None
        
        event = Event(
            timestamp=self._current.timestamp,
            event_type='liquidation',
            data=self._current
        )
        
        self._advance()
        return event
    
    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()


class DatabaseCandleFeed:
    """Replay feed for candle events from database."""
    
    def __init__(
        self,
        connection_string: str,
        symbol: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ):
        self.conn = psycopg2.connect(connection_string)
        self.symbol = symbol
        self.start_time = start_time
        self.end_time = end_time
        
        self.cursor = None
        self._current = None
        self._initialize_cursor()
    
    def _initialize_cursor(self) -> None:
        sql = """
            SELECT timestamp, open, high, low, close, volume, is_closed
            FROM candle_events
            WHERE symbol = %s
        """
        
        params = [self.symbol]
        
        if self.start_time is not None:
            sql += " AND timestamp >= %s"
            params.append(self.start_time)
        
        if self.end_time is not None:
            sql += " AND timestamp < %s"
            params.append(self.end_time)
        
        sql += " ORDER BY timestamp"
        
        self.cursor = self.conn.cursor()
        self.cursor.execute(sql, params)
        self._advance()
    
    def _advance(self) -> None:
        row = self.cursor.fetchone()
        
        if row is None:
            self._current = None
        else:
            timestamp, open_price, high, low, close, volume, is_closed = row
            
            self._current = Kline(
                timestamp=timestamp,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                interval='1m'  # Default to 1m, could be parameterized
            )
    
    def has_more(self) -> bool:
        return self._current is not None
    
    def peek_next_timestamp(self) -> Optional[float]:
        if self._current is None:
            return None
        return self._current.timestamp
    
    def emit_next(self) -> Optional[Event]:
        if self._current is None:
            return None
        
        event = Event(
            timestamp=self._current.timestamp,
            event_type='kline',
            data=self._current
        )
        
        self._advance()
        return event
    
    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
