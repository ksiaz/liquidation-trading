"""
PostgreSQL Signal Database Manager

Handles persistence of trading signals to PostgreSQL database.
Integrates with existing liquidation database.
"""

import psycopg2
import psycopg2.extras
import logging
import time
from typing import Dict, List, Optional
from database import DatabaseManager

logger = logging.getLogger(__name__)


class PostgresSignalDatabase:
    """
    Manages signal persistence to PostgreSQL database.
    
    Features:
    - Save signals to PostgreSQL
    - Load active signals on startup
    - Update signal status (open/closed)
    - Track performance metrics
    - Recovery after crashes
    """
    
    def __init__(self, db_manager: DatabaseManager = None):
        """
        Initialize with existing database manager.
        
        Args:
            db_manager: Existing DatabaseManager instance (optional)
        """
        if db_manager:
            self.db = db_manager
        else:
            self.db = DatabaseManager()
        
        self._init_schema()
    
    def _init_schema(self):
        """Initialize signals table schema."""
        try:
            with open('database_signals_schema_postgres.sql', 'r') as f:
                schema = f.read()
                self.db.execute_query(schema)
            logger.info("Signal database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize signal schema: {e}")
            # Create tables inline as fallback
            self._create_tables_inline()
    
    def _create_tables_inline(self):
        """Create tables inline if schema file not found."""
        query = """
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            type TEXT NOT NULL,
            entry DECIMAL(20, 8) NOT NULL,
            target DECIMAL(20, 8) NOT NULL,
            stop DECIMAL(20, 8) NOT NULL,
            current_price DECIMAL(20, 8),
            confidence DECIMAL(5, 4) NOT NULL,
            reason TEXT,
            regime TEXT,
            nearby_zones INTEGER,
            risk_reward DECIMAL(10, 4),
            status TEXT NOT NULL DEFAULT 'OPEN',
            outcome TEXT,
            unrealized_pnl_pct DECIMAL(10, 4) DEFAULT 0,
            realized_pnl_pct DECIMAL(10, 4),
            distance_to_target_pct DECIMAL(10, 4),
            distance_to_stop_pct DECIMAL(10, 4),
            timestamp DECIMAL(20, 6) NOT NULL,
            entry_time DECIMAL(20, 6),
            exit_time DECIMAL(20, 6),
            duration_seconds DECIMAL(20, 2),
            exit_price DECIMAL(20, 8),
            close_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
        """
        self.db.execute_query(query)
    
    def save_signal(self, signal: Dict) -> bool:
        """
        Save or update a signal in the database.
        
        Args:
            signal: Signal dictionary with all fields
        
        Returns:
            True if successful, False otherwise
        """
        try:
            query = """
            INSERT INTO signals (
                id, symbol, direction, type, entry, target, stop, current_price,
                confidence, reason, regime, nearby_zones, risk_reward,
                status, outcome, unrealized_pnl_pct, realized_pnl_pct,
                distance_to_target_pct, distance_to_stop_pct,
                timestamp, entry_time, exit_time, duration_seconds,
                exit_price, close_reason
            ) VALUES (
                %(id)s, %(symbol)s, %(direction)s, %(type)s, %(entry)s, %(target)s, 
                %(stop)s, %(current_price)s, %(confidence)s, %(reason)s, %(regime)s,
                %(nearby_zones)s, %(risk_reward)s, %(status)s, %(outcome)s,
                %(unrealized_pnl_pct)s, %(realized_pnl_pct)s,
                %(distance_to_target_pct)s, %(distance_to_stop_pct)s,
                %(timestamp)s, %(entry_time)s, %(exit_time)s, %(duration_seconds)s,
                %(exit_price)s, %(close_reason)s
            )
            ON CONFLICT (id) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                status = EXCLUDED.status,
                outcome = EXCLUDED.outcome,
                unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                realized_pnl_pct = EXCLUDED.realized_pnl_pct,
                distance_to_target_pct = EXCLUDED.distance_to_target_pct,
                distance_to_stop_pct = EXCLUDED.distance_to_stop_pct,
                exit_time = EXCLUDED.exit_time,
                exit_price = EXCLUDED.exit_price,
                close_reason = EXCLUDED.close_reason,
                updated_at = CURRENT_TIMESTAMP
            """
            
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
            
            self.db.execute_query(query, data)
            logger.debug(f"Saved signal to PostgreSQL: {data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save signal to PostgreSQL: {e}")
            return False
    
    def load_active_signals(self) -> List[Dict]:
        """
        Load all active (OPEN) signals from database.
        
        Returns:
            List of signal dictionaries
        """
        try:
            query = """
            SELECT * FROM signals 
            WHERE status = 'OPEN'
            ORDER BY timestamp DESC
            """
            
            rows = self.db.fetch_all(query)
            signals = []
            
            for row in rows:
                signal = dict(row)
                # Convert back to expected format
                signal['riskReward'] = signal.pop('risk_reward', None)
                signal['pnl_pct'] = signal.pop('realized_pnl_pct', 0)
                signals.append(signal)
            
            logger.info(f"Loaded {len(signals)} active signals from PostgreSQL")
            return signals
            
        except Exception as e:
            logger.error(f"Failed to load active signals from PostgreSQL: {e}")
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
            query = """
            SELECT * FROM signals 
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            rows = self.db.fetch_all(query, (limit,))
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get signal history from PostgreSQL: {e}")
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
            query = """
            UPDATE signals 
            SET status = %s, outcome = %s, exit_price = %s, 
                realized_pnl_pct = %s, exit_time = %s, close_reason = %s
            WHERE id = %s
            """
            
            self.db.execute_query(query, (
                status, outcome, exit_price, pnl_pct, 
                time.time(), close_reason, signal_id
            ))
            
            logger.info(f"Updated signal {signal_id} in PostgreSQL: {status} - {outcome}")
            
        except Exception as e:
            logger.error(f"Failed to update signal status in PostgreSQL: {e}")
    
    def get_performance_stats(self) -> Dict:
        """
        Get aggregated performance statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        try:
            query = """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open,
                AVG(CASE WHEN outcome IS NOT NULL THEN realized_pnl_pct ELSE NULL END) as avg_pnl
            FROM signals
            """
            
            row = self.db.fetch_one(query)
            
            if row:
                total = row['total'] or 0
                wins = row['wins'] or 0
                losses = row['losses'] or 0
                open_count = row['open'] or 0
                avg_pnl = float(row['avg_pnl']) if row['avg_pnl'] else 0
                
                win_rate = (wins / (wins + losses)        try:
            # Check if signals table exists
            self.db.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'signals'
                )
            """)
            
            table_exists = self.db.cursor.fetchone()[0]
            
            if not table_exists:
                logger.warning("Signals table does not exist. Run create_signals_table.py to set up the schema.")
            else:
                logger.info("PostgreSQL signal database initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize signal schema: {e}")
stats from PostgreSQL: {e}")
            return {}
