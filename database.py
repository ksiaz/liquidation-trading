"""
Database schema and setup for liquidation trading system.

Creates PostgreSQL tables for storing liquidation events and metadata.
"""

import os
from datetime import datetime
import psycopg2
from psycopg2 import sql, extras
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class DatabaseManager:
    """Manages PostgreSQL database connection and operations."""
    
    def __init__(self):
        """Initialize database connection."""
        self.conn = None
        self.cursor = None
        self._connect()
    
    def _connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'liquidation_trading'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', '')
            )
            self.cursor = self.conn.cursor()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def create_tables(self):
        """Create database tables if they don't exist."""
        
        # Main liquidations table
        create_liquidations_table = """
        CREATE TABLE IF NOT EXISTS liquidations (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            trade_time TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            price DECIMAL(20, 8) NOT NULL,
            avg_price DECIMAL(20, 8) NOT NULL,
            value_usd DECIMAL(20, 2) NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Indexes for better query performance
        CREATE INDEX IF NOT EXISTS idx_liquidations_timestamp ON liquidations(timestamp);
        CREATE INDEX IF NOT EXISTS idx_liquidations_symbol ON liquidations(symbol);
        CREATE INDEX IF NOT EXISTS idx_liquidations_side ON liquidations(side);
        CREATE INDEX IF NOT EXISTS idx_liquidations_value ON liquidations(value_usd);
        CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_timestamp ON liquidations(symbol, timestamp);
        """
        
        # Aggregated statistics table
        create_stats_table = """
        CREATE TABLE IF NOT EXISTS liquidation_stats (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            total_events INTEGER NOT NULL,
            total_value_usd DECIMAL(20, 2) NOT NULL,
            avg_value_usd DECIMAL(20, 2) NOT NULL,
            max_value_usd DECIMAL(20, 2) NOT NULL,
            min_value_usd DECIMAL(20, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, symbol, side)
        );
        
        CREATE INDEX IF NOT EXISTS idx_stats_date ON liquidation_stats(date);
        CREATE INDEX IF NOT EXISTS idx_stats_symbol ON liquidation_stats(symbol);
        """
        
        # Session metadata table
        create_sessions_table = """
        CREATE TABLE IF NOT EXISTS monitor_sessions (
            id SERIAL PRIMARY KEY,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP,
            total_events INTEGER DEFAULT 0,
            significant_events INTEGER DEFAULT 0,
            total_value_usd DECIMAL(20, 2) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'running',
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        # Order book snapshots table
        create_orderbook_snapshots_table = """
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            best_bid DECIMAL(20, 8),
            best_ask DECIMAL(20, 8),
            spread DECIMAL(20, 8),
            spread_pct DECIMAL(10, 6),
            bid_volume_10 DECIMAL(20, 8),
            ask_volume_10 DECIMAL(20, 8),
            bid_value_10 DECIMAL(20, 2),
            ask_value_10 DECIMAL(20, 2),
            imbalance DECIMAL(10, 6),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_ob_snapshots_symbol_time ON orderbook_snapshots(symbol, timestamp);
        CREATE INDEX IF NOT EXISTS idx_ob_snapshots_timestamp ON orderbook_snapshots(timestamp);
        """
        
        # Order book depth analysis table
        create_orderbook_depth_table = """
        CREATE TABLE IF NOT EXISTS orderbook_depth (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            liquidity_0_5pct_down DECIMAL(20, 8),
            liquidity_1pct_down DECIMAL(20, 8),
            liquidity_2pct_down DECIMAL(20, 8),
            liquidity_0_5pct_up DECIMAL(20, 8),
            liquidity_1pct_up DECIMAL(20, 8),
            liquidity_2pct_up DECIMAL(20, 8),
            avg_liquidity DECIMAL(20, 8),
            cliff_detected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_ob_depth_symbol_time ON orderbook_depth(symbol, timestamp);
        """
        
        # Large orders / walls table
        create_orderbook_walls_table = """
        CREATE TABLE IF NOT EXISTS orderbook_walls (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(4) NOT NULL,
            price DECIMAL(20, 8),
            size DECIMAL(20, 8),
            value_usd DECIMAL(20, 2),
            event_type VARCHAR(20),
            duration_seconds INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_ob_walls_symbol_time ON orderbook_walls(symbol, timestamp);
        CREATE INDEX IF NOT EXISTS idx_ob_walls_event ON orderbook_walls(event_type, timestamp);
        """
        
        # Trading signals table
        create_trading_signals_table = """
        CREATE TABLE IF NOT EXISTS trading_signals (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            entry_price DECIMAL(20, 8) NOT NULL,
            confidence INTEGER NOT NULL,
            snr DECIMAL(10, 4) NOT NULL,
            timeframe INTEGER NOT NULL,
            signals_confirmed INTEGER NOT NULL,
            signals_total INTEGER NOT NULL,
            
            -- Signal breakdown
            imbalance_divergence BOOLEAN DEFAULT FALSE,
            depth_building BOOLEAN DEFAULT FALSE,
            volume_exhaustion BOOLEAN DEFAULT FALSE,
            funding_divergence BOOLEAN DEFAULT FALSE,
            liquidity_confirmation BOOLEAN DEFAULT FALSE,
            
            -- Market context
            wave_trend_bias VARCHAR(20),
            chop_filtered BOOLEAN DEFAULT FALSE,
            
            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON trading_signals(timestamp);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON trading_signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_direction ON trading_signals(direction);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, timestamp);
        """

        
        try:
            self.cursor.execute(create_liquidations_table)
            self.cursor.execute(create_stats_table)
            self.cursor.execute(create_sessions_table)
            self.cursor.execute(create_orderbook_snapshots_table)
            self.cursor.execute(create_orderbook_depth_table)
            self.cursor.execute(create_orderbook_walls_table)
            self.cursor.execute(create_trading_signals_table)
            self.conn.commit()
            logger.info("Database tables created successfully")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to create tables: {e}")
            raise
    
    def insert_liquidation(self, event):
        """
        Insert a single liquidation event.
        
        Args:
            event: Liquidation event dictionary
        """
        query = """
        INSERT INTO liquidations 
        (timestamp, trade_time, symbol, side, quantity, price, avg_price, value_usd, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            self.cursor.execute(query, (
                event['timestamp'],
                event['trade_time'],
                event['symbol'],
                event['side'],
                event['quantity'],
                event['price'],
                event['avg_price'],
                event['value_usd'],
                event['status']
            ))
        except Exception as e:
            logger.error(f"Failed to insert liquidation: {e}")
            raise
    
    def insert_liquidations_batch(self, events):
        """
        Insert multiple liquidation events efficiently.
        
        Args:
            events: List of liquidation event dictionaries
        """
        if not events:
            return
        
        query = """
        INSERT INTO liquidations 
        (timestamp, trade_time, symbol, side, quantity, price, avg_price, value_usd, status)
        VALUES %s
        """
        
        values = [
            (
                event['timestamp'],
                event['trade_time'],
                event['symbol'],
                event['side'],
                event['quantity'],
                event['price'],
                event['avg_price'],
                event['value_usd'],
                event['status']
            )
            for event in events
        ]
        
        try:
            extras.execute_values(self.cursor, query, values)
            logger.debug(f"Inserted {len(events)} liquidations")
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            raise
    
    def commit(self):
        """Commit current transaction."""
        try:
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            raise
    
    def rollback(self):
        """Rollback current transaction."""
        self.conn.rollback()
    
    def get_stats(self, symbol=None, start_date=None, end_date=None):
        """
        Get liquidation statistics.
        
        Args:
            symbol: Filter by symbol (optional)
            start_date: Start date (optional)
            end_date: End date (optional)
        
        Returns:
            Dictionary with statistics
        """
        query = """
        SELECT 
            COUNT(*) as total_events,
            SUM(value_usd) as total_value,
            AVG(value_usd) as avg_value,
            MAX(value_usd) as max_value,
            MIN(value_usd) as min_value
        FROM liquidations
        WHERE 1=1
        """
        
        params = []
        
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)
        
        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date)
        
        self.cursor.execute(query, params)
        result = self.cursor.fetchone()
        
        return {
            'total_events': result[0] or 0,
            'total_value': float(result[1] or 0),
            'avg_value': float(result[2] or 0),
            'max_value': float(result[3] or 0),
            'min_value': float(result[4] or 0)
        }
    
    def get_recent_liquidations(self, limit=100, symbol=None):
        """
        Get recent liquidation events.
        
        Args:
            limit: Number of events to retrieve
            symbol: Filter by symbol (optional)
        
        Returns:
            List of liquidation dictionaries
        """
        query = """
        SELECT timestamp, trade_time, symbol, side, quantity, 
               price, avg_price, value_usd, status
        FROM liquidations
        WHERE 1=1
        """
        
        params = []
        
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol)
        
        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)
        
        self.cursor.execute(query, params)
        
        results = []
        for row in self.cursor.fetchall():
            results.append({
                'timestamp': row[0],
                'trade_time': row[1],
                'symbol': row[2],
                'side': row[3],
                'quantity': float(row[4]),
                'price': float(row[5]),
                'avg_price': float(row[6]),
                'value_usd': float(row[7]),
                'status': row[8]
            })
        
        return results
    
    def close(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    """Test database setup."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("Testing database connection and setup...")
    
    try:
        db = DatabaseManager()
        print("✓ Connected to database")
        
        db.create_tables()
        print("✓ Tables created")
        
        # Test insert
        test_event = {
            'timestamp': datetime.now(),
            'trade_time': datetime.now(),
            'symbol': 'BTCUSDT',
            'side': 'SELL',
            'quantity': 0.1,
            'price': 50000,
            'avg_price': 50000,
            'value_usd': 5000,
            'status': 'FILLED'
        }
        
        db.insert_liquidation(test_event)
        db.commit()
        print("✓ Test event inserted")
        
        # Get stats
        stats = db.get_stats()
        print(f"✓ Database stats: {stats['total_events']} events")
        
        db.close()
        print("\n✅ Database setup complete!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
