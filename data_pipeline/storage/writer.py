"""
Database Writer

Write-only persistence layer for market events.

SCOPE: Database writes ONLY.
- No reads
- No queries
- No processing

RULES:
- Immediate writes (no buffering)
- Fail closed on DB errors
- No retries that reorder data

PRINCIPLE: Data correctness > completeness > performance
"""

import psycopg2
from typing import Optional
from ..normalized_events import (
    OrderbookEvent,
    TradeEvent,
    LiquidationEvent,
    CandleEvent,
)


class DatabaseWriter:
    """
    Write-only persistence for market events.
    
    RULE: Immediate writes - no buffering.
    RULE: Fail closed on DB errors.
    RULE: No retries that reorder data.
    """
    
    def __init__(self, connection_string: str):
        """
        Initialize database writer.
        
        Args:
            connection_string: PostgreSQL connection string
                Format: "postgresql://user:pass@host:port/dbname"
        
        Raises:
            RuntimeError: If connection fails
        """
        self.conn_string = connection_string
        self.conn: Optional[psycopg2.extensions.connection] = None
        self._connect()
    
    def _connect(self) -> None:
        """
        Establish database connection.
        
        RULE: Fail immediately if DB unavailable.
        
        Raises:
            RuntimeError: If connection fails
        """
        try:
            self.conn = psycopg2.connect(self.conn_string)
            # Autocommit = immediate durability per write
            self.conn.autocommit = True
        except Exception as e:
            raise RuntimeError(f"Failed to connect to database: {e}")
    
    def write_orderbook(self, event: OrderbookEvent) -> None:
        """
        Write orderbook event to database.
        
        RULE: If write fails → raise exception (fail closed).
        
        Args:
            event: Normalized orderbook event
            
        Raises:
            RuntimeError: If write fails
        """
        sql = """
            INSERT INTO orderbook_events
            (event_id, timestamp, receive_time, symbol, bids, asks, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    event.event_id,
                    event.timestamp,
                    event.receive_time,
                    event.symbol,
                    event.bids,
                    event.asks,
                    1  # schema_version
                ))
        except Exception as e:
            # Fail closed - propagate error to caller
            raise RuntimeError(f"Failed to write orderbook event: {e}")
    
    def write_trade(self, event: TradeEvent) -> None:
        """
        Write trade event to database.
        
        Args:
            event: Normalized trade event
            
        Raises:
            RuntimeError: If write fails
        """
        sql = """
            INSERT INTO trade_events
            (event_id, timestamp, receive_time, symbol, price, quantity, is_buyer_maker, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    event.event_id,
                    event.timestamp,
                    event.receive_time,
                    event.symbol,
                    event.price,
                    event.quantity,
                    event.is_buyer_maker,
                    1  # schema_version
                ))
        except Exception as e:
            raise RuntimeError(f"Failed to write trade event: {e}")
    
    def write_liquidation(self, event: LiquidationEvent) -> None:
        """
        Write liquidation event to database.
        
        Args:
            event: Normalized liquidation event
            
        Raises:
            RuntimeError: If write fails
        """
        sql = """
            INSERT INTO liquidation_events
            (event_id, timestamp, receive_time, symbol, side, price, quantity, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    event.event_id,
                    event.timestamp,
                    event.receive_time,
                    event.symbol,
                    event.side,
                    event.price,
                    event.quantity,
                    1  # schema_version
                ))
        except Exception as e:
            raise RuntimeError(f"Failed to write liquidation event: {e}")
    
    def write_bookticker(self, event: 'BookTickerEvent') -> None:
        """
        Write book ticker event to database.
        
        Args:
            event: Normalized book ticker event
            
        Raises:
            RuntimeError: If write fails
        """
        sql = """
            INSERT INTO bookticker_events
            (event_id, timestamp, receive_time, symbol, best_bid_price, best_bid_qty, 
             best_ask_price, best_ask_qty, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    event.event_id,
                    event.timestamp,
                    event.receive_time,
                    event.symbol,
                    event.best_bid_price,
                    event.best_bid_qty,
                    event.best_ask_price,
                    event.best_ask_qty,
                    1  # schema_version
                ))
        except Exception as e:
            raise RuntimeError(f"Failed to write book ticker event: {e}")
    
    def write_candle(self, event: CandleEvent) -> None:
        """
        Write candle event to database.
        
        Args:
            event: Normalized candle event
            
        Raises:
            RuntimeError: If write fails
        """
        sql = """
            INSERT INTO candle_events
            (event_id, timestamp, receive_time, symbol, open, high, low, close, volume, is_closed, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, (
                    event.event_id,
                    event.timestamp,
                    event.receive_time,
                    event.symbol,
                    event.open,
                    event.high,
                    event.low,
                    event.close,
                    event.volume,
                    event.is_closed,
                    1  # schema_version
                ))
        except Exception as e:
            raise RuntimeError(f"Failed to write candle event: {e}")
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
