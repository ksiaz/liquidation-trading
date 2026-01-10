"""
Signal Database Manager

Handles persistence of trading signals to database for recovery after crashes.
"""

import sqlite3
import logging
import time
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SignalDatabase:
    """
    Manages signal persistence to SQLite database.
    
    Features:
    - Save signals to database
    - Load active signals on startup
    - Update signal status (open/closed)
    - Track performance metrics
    - Recovery after crashes
    """
    
    def __init__(self, db_path: str = "liquidation_data.db"):
        self.db_path = db_path
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection and create tables."""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            # Read and execute schema
            schema_path = Path(__file__).parent / "database_signals_schema.sql"
            if schema_path.exists():
                with open(schema_path, 'r') as f:
                    schema = f.read()
                    self.conn.executescript(schema)
            else:
                # Fallback: create tables inline
                self._create_tables_inline()
            
            self.conn.commit()
            logger.info("Signal database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize signal database: {e}")
            raise
    
    def _create_tables_inline(self):
        """Create tables inline if schema file not found."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                type TEXT NOT NULL,
                entry REAL NOT NULL,
                target REAL NOT NULL,
                stop REAL NOT NULL,
                current_price REAL,
                confidence REAL NOT NULL,
                reason TEXT,
                regime TEXT,
                nearby_zones INTEGER,
                risk_reward REAL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                outcome TEXT,
                unrealized_pnl_pct REAL DEFAULT 0,
                realized_pnl_pct REAL,
                distance_to_target_pct REAL,
                distance_to_stop_pct REAL,
                timestamp REAL NOT NULL,
                entry_time REAL,
                exit_time REAL,
                duration_seconds REAL,
                exit_price REAL,
                close_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol ON signals(symbol)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON signals(status)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON signals(timestamp)
        """)
    
    def save_signal(self, signal: Dict) -> bool:
        """
        Save or update a signal in the database.
        
        Args:
            signal: Signal dictionary with all fields
        
        Returns:
            True if successful, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            
            # Prepare data
            data = {
                'id': signal.get('id'),
                'symbol': signal.get('symbol'),
                'direction': signal.get('direction'),
                'type': signal.get('type'),
                'entry': signal.get('entry'),
                'target': signal.get('target'),
                'stop': signal.get('stop'),
                'current_price': signal.get('current_price'),
                'confidence': signal.get('confidence'),
                'reason': signal.get('reason'),
                'regime': signal.get('regime'),
                'nearby_zones': signal.get('nearby_zones'),
                'risk_reward': signal.get('riskReward'),
                'status': signal.get('status', 'OPEN'),
                'outcome': signal.get('outcome'),
                'unrealized_pnl_pct': signal.get('unrealized_pnl_pct', 0),
                'realized_pnl_pct': signal.get('pnl_pct'),
                'distance_to_target_pct': signal.get('distance_to_target_pct'),
                'distance_to_stop_pct': signal.get('distance_to_stop_pct'),
                'timestamp': signal.get('timestamp', time.time()),
                'entry_time': signal.get('entry_time'),
                'exit_time': signal.get('exit_time'),
                'duration_seconds': signal.get('duration_seconds'),
                'exit_price': signal.get('exit_price'),
                'close_reason': signal.get('close_reason')
            }
            
            # Insert or replace
            cursor.execute("""
                INSERT OR REPLACE INTO signals (
                    id, symbol, direction, type, entry, target, stop, current_price,
                    confidence, reason, regime, nearby_zones, risk_reward,
                    status, outcome, unrealized_pnl_pct, realized_pnl_pct,
                    distance_to_target_pct, distance_to_stop_pct,
                    timestamp, entry_time, exit_time, duration_seconds,
                    exit_price, close_reason
                ) VALUES (
                    :id, :symbol, :direction, :type, :entry, :target, :stop, :current_price,
                    :confidence, :reason, :regime, :nearby_zones, :risk_reward,
                    :status, :outcome, :unrealized_pnl_pct, :realized_pnl_pct,
                    :distance_to_target_pct, :distance_to_stop_pct,
                    :timestamp, :entry_time, :exit_time, :duration_seconds,
                    :exit_price, :close_reason
                )
            """, data)
            
            self.conn.commit()
            logger.debug(f"Saved signal to database: {data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return False
    
    def load_active_signals(self) -> List[Dict]:
        """
        Load all active (OPEN) signals from database.
        
        Returns:
            List of signal dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM signals 
                WHERE status = 'OPEN'
                ORDER BY timestamp DESC
            """)
            
            rows = cursor.fetchall()
            signals = []
            
            for row in rows:
                signal = dict(row)
                # Convert back to expected format
                signal['riskReward'] = signal.pop('risk_reward', None)
                signal['pnl_pct'] = signal.pop('realized_pnl_pct', 0)
                signals.append(signal)
            
            logger.info(f"Loaded {len(signals)} active signals from database")
            return signals
            
        except Exception as e:
            logger.error(f"Failed to load active signals: {e}")
            return []
    
    def get_signal_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recent signal history.
        
        Args:
            limit: Maximum number of signals to return
        
        Returns:
            List of signal dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM signals 
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get signal history: {e}")
            return []
    
    def update_signal_status(self, signal_id: str, status: str, outcome: str = None, 
                            exit_price: float = None, pnl_pct: float = None,
                            close_reason: str = None):
        """
        Update signal status (e.g., when closed).
        
        Args:
            signal_id: Signal ID
            status: New status (OPEN, CLOSED)
            outcome: WIN, LOSS, or None
            exit_price: Exit price if closed
            pnl_pct: Realized P&L percentage
            close_reason: Reason for closing
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE signals 
                SET status = ?, outcome = ?, exit_price = ?, 
                    realized_pnl_pct = ?, exit_time = ?, close_reason = ?
                WHERE id = ?
            """, (status, outcome, exit_price, pnl_pct, time.time(), close_reason, signal_id))
            
            self.conn.commit()
            logger.info(f"Updated signal {signal_id}: {status} - {outcome}")
            
        except Exception as e:
            logger.error(f"Failed to update signal status: {e}")
    
    def get_performance_stats(self) -> Dict:
        """
        Get aggregated performance statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        try:
            cursor = self.conn.cursor()
            
            # Overall stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open,
                    AVG(CASE WHEN outcome IS NOT NULL THEN realized_pnl_pct ELSE NULL END) as avg_pnl
                FROM signals
            """)
            
            row = cursor.fetchone()
            
            total = row['total'] or 0
            wins = row['wins'] or 0
            losses = row['losses'] or 0
            open_count = row['open'] or 0
            avg_pnl = row['avg_pnl'] or 0
            
            win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
            
            return {
                'total_signals': total,
                'wins': wins,
                'losses': losses,
                'open': open_count,
                'win_rate': win_rate,
                'avg_pnl_per_trade': avg_pnl
            }
            
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Signal database connection closed")


if __name__ == "__main__":
    """Test signal database."""
    
    logging.basicConfig(level=logging.INFO)
    
    db = SignalDatabase("test_signals.db")
    
    # Test signal
    test_signal = {
        'id': 'TEST_1',
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'type': 'FUNDING_FADE',
        'entry': 95000,
        'target': 96500,
        'stop': 94500,
        'confidence': 0.85,
        'reason': 'Test signal',
        'riskReward': 3.0,
        'timestamp': time.time()
    }
    
    # Save signal
    db.save_signal(test_signal)
    
    # Load active signals
    active = db.load_active_signals()
    print(f"Active signals: {len(active)}")
    
    # Update status
    db.update_signal_status('TEST_1', 'CLOSED', 'WIN', 96500, 1.58, 'Target hit')
    
    # Get stats
    stats = db.get_performance_stats()
    print(f"Stats: {stats}")
    
    db.close()
