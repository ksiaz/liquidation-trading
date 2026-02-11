"""
Signal Database Manager

Handles persistence of trading signals to PostgreSQL for recovery after crashes.
"""

import logging
import time
from typing import Dict, List, Optional

from runtime.logging.pg_pool import get_conn, put_conn

logger = logging.getLogger(__name__)


class SignalDatabase:
    """
    Manages signal persistence to PostgreSQL database.

    Features:
    - Save signals to database
    - Load active signals on startup
    - Update signal status (open/closed)
    - Track performance metrics
    - Recovery after crashes
    """

    def __init__(self, **kwargs):
        logger.info("Signal database initialized (PostgreSQL)")

    def save_signal(self, signal: Dict) -> bool:
        """Save or update a signal in the database."""
        try:
            conn = get_conn()
            try:
                cur = conn.cursor()

                data = (
                    signal.get('id'),
                    signal.get('symbol'),
                    signal.get('direction'),
                    signal.get('type'),
                    signal.get('entry'),
                    signal.get('target'),
                    signal.get('stop'),
                    signal.get('current_price'),
                    signal.get('confidence'),
                    signal.get('reason'),
                    signal.get('regime'),
                    signal.get('nearby_zones'),
                    signal.get('riskReward'),
                    signal.get('status', 'OPEN'),
                    signal.get('outcome'),
                    signal.get('unrealized_pnl_pct', 0),
                    signal.get('pnl_pct'),
                    signal.get('distance_to_target_pct'),
                    signal.get('distance_to_stop_pct'),
                    signal.get('timestamp', time.time()),
                    signal.get('entry_time'),
                    signal.get('exit_time'),
                    signal.get('duration_seconds'),
                    signal.get('exit_price'),
                    signal.get('close_reason'),
                )

                cur.execute("""
                    INSERT INTO signals (
                        id, symbol, direction, type, entry, target, stop, current_price,
                        confidence, reason, regime, nearby_zones, risk_reward,
                        status, outcome, unrealized_pnl_pct, realized_pnl_pct,
                        distance_to_target_pct, distance_to_stop_pct,
                        timestamp, entry_time, exit_time, duration_seconds,
                        exit_price, close_reason
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        symbol = EXCLUDED.symbol,
                        direction = EXCLUDED.direction,
                        type = EXCLUDED.type,
                        entry = EXCLUDED.entry,
                        target = EXCLUDED.target,
                        stop = EXCLUDED.stop,
                        current_price = EXCLUDED.current_price,
                        confidence = EXCLUDED.confidence,
                        reason = EXCLUDED.reason,
                        regime = EXCLUDED.regime,
                        nearby_zones = EXCLUDED.nearby_zones,
                        risk_reward = EXCLUDED.risk_reward,
                        status = EXCLUDED.status,
                        outcome = EXCLUDED.outcome,
                        unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                        realized_pnl_pct = EXCLUDED.realized_pnl_pct,
                        distance_to_target_pct = EXCLUDED.distance_to_target_pct,
                        distance_to_stop_pct = EXCLUDED.distance_to_stop_pct,
                        timestamp = EXCLUDED.timestamp,
                        entry_time = EXCLUDED.entry_time,
                        exit_time = EXCLUDED.exit_time,
                        duration_seconds = EXCLUDED.duration_seconds,
                        exit_price = EXCLUDED.exit_price,
                        close_reason = EXCLUDED.close_reason,
                        updated_at = NOW()
                """, data)

                conn.commit()
                logger.debug(f"Saved signal to database: {signal.get('id')}")
                return True
            finally:
                put_conn(conn)

        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return False

    def load_active_signals(self) -> List[Dict]:
        """Load all active (OPEN) signals from database."""
        try:
            conn = get_conn()
            try:
                import psycopg2.extras
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT * FROM signals
                    WHERE status = 'OPEN'
                    ORDER BY timestamp DESC
                """)

                signals = []
                for row in cur.fetchall():
                    signal = dict(row)
                    signal['riskReward'] = signal.pop('risk_reward', None)
                    signal['pnl_pct'] = signal.pop('realized_pnl_pct', 0)
                    signals.append(signal)

                logger.info(f"Loaded {len(signals)} active signals from database")
                return signals
            finally:
                put_conn(conn)

        except Exception as e:
            logger.error(f"Failed to load active signals: {e}")
            return []

    def get_signal_history(self, limit: int = 50) -> List[Dict]:
        """Get recent signal history."""
        try:
            conn = get_conn()
            try:
                import psycopg2.extras
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT * FROM signals
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (limit,))

                return [dict(row) for row in cur.fetchall()]
            finally:
                put_conn(conn)

        except Exception as e:
            logger.error(f"Failed to get signal history: {e}")
            return []

    def update_signal_status(self, signal_id: str, status: str, outcome: str = None,
                            exit_price: float = None, pnl_pct: float = None,
                            close_reason: str = None):
        """Update signal status (e.g., when closed)."""
        try:
            conn = get_conn()
            try:
                conn.cursor().execute("""
                    UPDATE signals
                    SET status = %s, outcome = %s, exit_price = %s,
                        realized_pnl_pct = %s, exit_time = %s, close_reason = %s
                    WHERE id = %s
                """, (status, outcome, exit_price, pnl_pct, time.time(), close_reason, signal_id))

                conn.commit()
                logger.info(f"Updated signal {signal_id}: {status} - {outcome}")
            finally:
                put_conn(conn)

        except Exception as e:
            logger.error(f"Failed to update signal status: {e}")

    def get_performance_stats(self) -> Dict:
        """Get aggregated performance statistics."""
        try:
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) as open,
                        AVG(CASE WHEN outcome IS NOT NULL THEN realized_pnl_pct ELSE NULL END) as avg_pnl
                    FROM signals
                """)

                row = cur.fetchone()

                total = row[0] or 0
                wins = row[1] or 0
                losses = row[2] or 0
                open_count = row[3] or 0
                avg_pnl = row[4] or 0

                win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

                return {
                    'total_signals': total,
                    'wins': wins,
                    'losses': losses,
                    'open': open_count,
                    'win_rate': win_rate,
                    'avg_pnl_per_trade': avg_pnl
                }
            finally:
                put_conn(conn)

        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}

    def close(self):
        """No-op — pool manages connections."""
        pass
