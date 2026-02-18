"""
Market State Queries

Convenience functions for querying persisted market snapshots.
All operate on the PG market_snapshots table via BRD.
"""

from typing import List, Dict, Optional


def context_window(buffered_db, symbol: str, center_ts: float, window_sec: float = 30.0) -> List[dict]:
    """Snapshots around a timestamp (±window_sec)."""
    sql = """
        SELECT * FROM market_snapshots
        WHERE symbol = %s AND ts BETWEEN %s AND %s
        ORDER BY ts
    """
    return buffered_db.read_sql(sql, (symbol, center_ts - window_sec, center_ts + window_sec))


def trade_context(buffered_db, symbol: str, trade_ts: float) -> Optional[dict]:
    """Nearest snapshot to a trade timestamp."""
    sql = """
        SELECT * FROM market_snapshots
        WHERE symbol = %s
        ORDER BY ABS(ts - %s)
        LIMIT 1
    """
    rows = buffered_db.read_sql(sql, (symbol, trade_ts))
    return rows[0] if rows else None


def event_snapshots(buffered_db, trigger: str, symbol: Optional[str] = None, limit: int = 50) -> List[dict]:
    """Recent event snapshots by trigger type."""
    if symbol:
        sql = """
            SELECT * FROM market_snapshots
            WHERE trigger = %s AND symbol = %s
            ORDER BY ts DESC LIMIT %s
        """
        return buffered_db.read_sql(sql, (trigger, symbol, limit))
    else:
        sql = """
            SELECT * FROM market_snapshots
            WHERE trigger = %s
            ORDER BY ts DESC LIMIT %s
        """
        return buffered_db.read_sql(sql, (trigger, limit))


def regime_distribution(buffered_db, symbol: str, hours: float = 24.0) -> List[dict]:
    """Time spent in each regime (in seconds, assuming 10s sample interval)."""
    import time
    cutoff = time.time() - (hours * 3600)
    sql = """
        SELECT regime, COUNT(*) * 10 as seconds
        FROM market_snapshots
        WHERE symbol = %s AND trigger = 'PERIODIC' AND ts > %s
        GROUP BY regime
        ORDER BY seconds DESC
    """
    return buffered_db.read_sql(sql, (symbol, cutoff))


def pipeline_faults(buffered_db, hours: float = 24.0) -> List[dict]:
    """Rows where raw counts suggest calculator faults."""
    import time
    cutoff = time.time() - (hours * 3600)
    sql = """
        SELECT ts, symbol, raw_liq_events_baseline, liq_z, raw_liq_rate_1m,
               raw_of_fills_60s, orderflow_ratio, orderflow_neutralized,
               feed_age_ms, raw_l2_age_ms
        FROM market_snapshots
        WHERE ts > %s AND trigger = 'PERIODIC'
          AND (
            (raw_liq_events_baseline > 50 AND (liq_z IS NULL OR liq_z < 0.5))
            OR feed_age_ms > 10000
            OR raw_l2_age_ms > 30000
          )
        ORDER BY ts DESC LIMIT 100
    """
    return buffered_db.read_sql(sql, (cutoff,))
