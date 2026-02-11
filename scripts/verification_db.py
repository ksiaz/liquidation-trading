#!/usr/bin/env python3
"""
Verification database for paper trade analysis.

Stores:
- Zone events (detection, displacement, retest, outcome)
- Cascade alerts and corresponding liquidations
- Price snapshots for post-hoc analysis

PostgreSQL backed via pg_pool.
"""
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import psycopg2.extras
from runtime.logging.pg_pool import get_conn, put_conn, init_pool


def _ensure_tables():
    """Create verification tables if they don't exist."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            -- Zone events: track lifecycle of each detected zone
            CREATE TABLE IF NOT EXISTS zone_events (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION NOT NULL,
                symbol TEXT NOT NULL,
                zone_type TEXT NOT NULL,  -- 'demand' or 'supply'
                zone_center DOUBLE PRECISION,
                zone_low DOUBLE PRECISION,
                zone_high DOUBLE PRECISION,
                node_count INTEGER,
                avg_strength DOUBLE PRECISION,
                displacement_detected SMALLINT DEFAULT 0,
                displacement_time DOUBLE PRECISION,
                retest_detected SMALLINT DEFAULT 0,
                retest_time DOUBLE PRECISION,
                entry_proposed SMALLINT DEFAULT 0,
                entry_time DOUBLE PRECISION,
                -- Outcome tracking (filled in later)
                max_favorable_excursion DOUBLE PRECISION,
                max_adverse_excursion DOUBLE PRECISION,
                zone_respected SMALLINT,  -- 1 if price bounced, 0 if broke through
                outcome_recorded_at DOUBLE PRECISION,
                metadata TEXT  -- JSON for extra data
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_zone_symbol ON zone_events(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_zone_timestamp ON zone_events(timestamp)")

        cursor.execute("""
            -- Cascade alerts: track alerts and their verification
            CREATE TABLE IF NOT EXISTS cascade_alerts (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION NOT NULL,
                symbol TEXT NOT NULL,
                positions_count INTEGER,
                value_at_risk DOUBLE PRECISION,
                dominant_side TEXT,  -- 'LONG' or 'SHORT'
                closest_liq_price DOUBLE PRECISION,
                -- Verification against actual liquidations
                liq_burst_detected SMALLINT DEFAULT 0,
                liq_burst_time DOUBLE PRECISION,
                liq_burst_value DOUBLE PRECISION,
                time_to_burst DOUBLE PRECISION,  -- seconds between alert and burst
                false_positive SMALLINT DEFAULT 0,
                metadata TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cascade_symbol ON cascade_alerts(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cascade_timestamp ON cascade_alerts(timestamp)")

        cursor.execute("""
            -- Liquidation events: raw liquidations for verification
            CREATE TABLE IF NOT EXISTS verification_liquidation_events (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                value_usd DOUBLE PRECISION,
                price DOUBLE PRECISION,
                source TEXT DEFAULT 'HL'  -- 'HL' or 'BINANCE'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vliq_symbol ON verification_liquidation_events(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vliq_timestamp ON verification_liquidation_events(timestamp)")

        cursor.execute("""
            -- Price snapshots: periodic price recording
            CREATE TABLE IF NOT EXISTS price_snapshots (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION NOT NULL,
                symbol TEXT NOT NULL,
                hl_price DOUBLE PRECISION,
                binance_price DOUBLE PRECISION,
                drift_pct DOUBLE PRECISION
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_snapshots(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_timestamp ON price_snapshots(timestamp)")

        cursor.execute("""
            -- Verification metrics: aggregated stats
            CREATE TABLE IF NOT EXISTS verification_metrics (
                id SERIAL PRIMARY KEY,
                timestamp DOUBLE PRECISION NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value DOUBLE PRECISION,
                symbol TEXT,
                metadata TEXT
            )
        """)

        conn.commit()
    finally:
        put_conn(conn)


# =============================================================================
# Zone Event Recording
# =============================================================================

def record_zone_detected(
    symbol: str,
    zone_type: str,
    zone_center: float,
    zone_low: float,
    zone_high: float,
    node_count: int,
    avg_strength: float,
    timestamp: Optional[float] = None
) -> int:
    """Record a newly detected zone. Returns zone_id."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO zone_events
            (timestamp, symbol, zone_type, zone_center, zone_low, zone_high, node_count, avg_strength)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (timestamp or datetime.now().timestamp(), symbol, zone_type,
              zone_center, zone_low, zone_high, node_count, avg_strength))
        zone_id = cursor.fetchone()[0]
        conn.commit()
        return zone_id
    finally:
        put_conn(conn)


def update_zone_displacement(zone_id: int, timestamp: float):
    """Mark zone as having displacement detected."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE zone_events
            SET displacement_detected = 1, displacement_time = %s
            WHERE id = %s
        """, (timestamp, zone_id))
        conn.commit()
    finally:
        put_conn(conn)


def update_zone_retest(zone_id: int, timestamp: float):
    """Mark zone as having retest detected."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE zone_events
            SET retest_detected = 1, retest_time = %s
            WHERE id = %s
        """, (timestamp, zone_id))
        conn.commit()
    finally:
        put_conn(conn)


def update_zone_outcome(
    zone_id: int,
    max_favorable: float,
    max_adverse: float,
    zone_respected: bool,
    timestamp: Optional[float] = None
):
    """Record zone outcome after entry."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE zone_events
            SET max_favorable_excursion = %s, max_adverse_excursion = %s,
                zone_respected = %s, outcome_recorded_at = %s
            WHERE id = %s
        """, (max_favorable, max_adverse, 1 if zone_respected else 0,
              timestamp or datetime.now().timestamp(), zone_id))
        conn.commit()
    finally:
        put_conn(conn)


def get_recent_zones(symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get recent zone events."""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if symbol:
            cursor.execute("""
                SELECT * FROM zone_events WHERE symbol = %s
                ORDER BY timestamp DESC LIMIT %s
            """, (symbol, limit))
        else:
            cursor.execute("""
                SELECT * FROM zone_events ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        put_conn(conn)


# =============================================================================
# Cascade Alert Recording
# =============================================================================

def record_cascade_alert(
    symbol: str,
    positions_count: int,
    value_at_risk: float,
    dominant_side: str,
    closest_liq_price: float,
    timestamp: Optional[float] = None
) -> int:
    """Record a cascade alert. Returns alert_id."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cascade_alerts
            (timestamp, symbol, positions_count, value_at_risk, dominant_side, closest_liq_price)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (timestamp or datetime.now().timestamp(), symbol, positions_count,
              value_at_risk, dominant_side, closest_liq_price))
        alert_id = cursor.fetchone()[0]
        conn.commit()
        return alert_id
    finally:
        put_conn(conn)


def verify_cascade_alert(
    alert_id: int,
    liq_burst_detected: bool,
    liq_burst_time: Optional[float],
    liq_burst_value: Optional[float],
    time_to_burst: Optional[float]
):
    """Update cascade alert with verification results."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE cascade_alerts
            SET liq_burst_detected = %s, liq_burst_time = %s, liq_burst_value = %s,
                time_to_burst = %s, false_positive = %s
            WHERE id = %s
        """, (1 if liq_burst_detected else 0, liq_burst_time, liq_burst_value,
              time_to_burst, 0 if liq_burst_detected else 1, alert_id))
        conn.commit()
    finally:
        put_conn(conn)


def get_recent_cascade_alerts(symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get recent cascade alerts."""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if symbol:
            cursor.execute("""
                SELECT * FROM cascade_alerts WHERE symbol = %s
                ORDER BY timestamp DESC LIMIT %s
            """, (symbol, limit))
        else:
            cursor.execute("""
                SELECT * FROM cascade_alerts ORDER BY timestamp DESC LIMIT %s
            """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        put_conn(conn)


# =============================================================================
# Liquidation Recording
# =============================================================================

def record_liquidation(
    symbol: str,
    side: str,
    value_usd: float,
    price: float,
    source: str = 'HL',
    timestamp: Optional[float] = None
):
    """Record a liquidation event."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO verification_liquidation_events (timestamp, symbol, side, value_usd, price, source)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (timestamp or datetime.now().timestamp(), symbol, side, value_usd, price, source))
        conn.commit()
    finally:
        put_conn(conn)


def get_liquidations_in_window(
    symbol: str,
    start_time: float,
    end_time: float
) -> List[Dict]:
    """Get liquidations within a time window."""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""
            SELECT * FROM verification_liquidation_events
            WHERE symbol = %s AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp
        """, (symbol, start_time, end_time))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        put_conn(conn)


# =============================================================================
# Price Snapshots
# =============================================================================

def record_price_snapshot(
    symbol: str,
    hl_price: Optional[float],
    binance_price: Optional[float],
    timestamp: Optional[float] = None
):
    """Record a price snapshot."""
    drift_pct = None
    if hl_price and binance_price:
        drift_pct = (hl_price - binance_price) / binance_price * 100

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_snapshots (timestamp, symbol, hl_price, binance_price, drift_pct)
            VALUES (%s, %s, %s, %s, %s)
        """, (timestamp or datetime.now().timestamp(), symbol, hl_price, binance_price, drift_pct))
        conn.commit()
    finally:
        put_conn(conn)


# =============================================================================
# Metrics Recording
# =============================================================================

def record_metric(metric_name: str, metric_value: float, symbol: Optional[str] = None):
    """Record a verification metric."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO verification_metrics (timestamp, metric_name, metric_value, symbol)
            VALUES (%s, %s, %s, %s)
        """, (datetime.now().timestamp(), metric_name, metric_value, symbol))
        conn.commit()
    finally:
        put_conn(conn)


# =============================================================================
# Analysis Queries
# =============================================================================

def get_zone_stats() -> Dict[str, Any]:
    """Get zone detection statistics."""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        stats = {}

        # Total zones
        cursor.execute("SELECT COUNT(*) as cnt FROM zone_events")
        row = cursor.fetchone()
        stats['total_zones'] = row['cnt']

        # By type
        cursor.execute("""
            SELECT zone_type, COUNT(*) as cnt FROM zone_events GROUP BY zone_type
        """)
        rows = cursor.fetchall()
        stats['by_type'] = {row['zone_type']: row['cnt'] for row in rows}

        # Displacement rate
        cursor.execute("""
            SELECT
                SUM(CASE WHEN displacement_detected = 1 THEN 1 ELSE 0 END) as disp,
                COUNT(*) as total
            FROM zone_events
        """)
        row = cursor.fetchone()
        stats['displacement_rate'] = row['disp'] / row['total'] if row['total'] > 0 else 0

        # Retest rate (of those with displacement)
        cursor.execute("""
            SELECT
                SUM(CASE WHEN retest_detected = 1 THEN 1 ELSE 0 END) as retest,
                COUNT(*) as total
            FROM zone_events WHERE displacement_detected = 1
        """)
        row = cursor.fetchone()
        stats['retest_rate'] = row['retest'] / row['total'] if row['total'] > 0 else 0

        # Zone respected rate
        cursor.execute("""
            SELECT
                SUM(CASE WHEN zone_respected = 1 THEN 1 ELSE 0 END) as respected,
                COUNT(*) as total
            FROM zone_events WHERE outcome_recorded_at IS NOT NULL
        """)
        row = cursor.fetchone()
        stats['zone_respected_rate'] = row['respected'] / row['total'] if row['total'] > 0 else 0

        return stats
    finally:
        put_conn(conn)


def get_cascade_stats() -> Dict[str, Any]:
    """Get cascade alert statistics."""
    conn = get_conn()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        stats = {}

        # Total alerts
        cursor.execute("SELECT COUNT(*) as cnt FROM cascade_alerts")
        row = cursor.fetchone()
        stats['total_alerts'] = row['cnt']

        # Verified (had liquidation burst)
        cursor.execute("""
            SELECT
                SUM(CASE WHEN liq_burst_detected = 1 THEN 1 ELSE 0 END) as verified,
                SUM(CASE WHEN false_positive = 1 THEN 1 ELSE 0 END) as false_pos,
                COUNT(*) as total
            FROM cascade_alerts
        """)
        row = cursor.fetchone()
        stats['verified_rate'] = row['verified'] / row['total'] if row['total'] > 0 else 0
        stats['false_positive_rate'] = row['false_pos'] / row['total'] if row['total'] > 0 else 0

        # Average time to burst
        cursor.execute("""
            SELECT AVG(time_to_burst) as avg_time
            FROM cascade_alerts WHERE liq_burst_detected = 1
        """)
        row = cursor.fetchone()
        stats['avg_time_to_burst'] = row['avg_time']

        return stats
    finally:
        put_conn(conn)


if __name__ == '__main__':
    # Initialize pool and tables
    init_pool()
    _ensure_tables()
    print("Database tables initialized in PostgreSQL")

    # Show stats if any data exists
    zone_stats = get_zone_stats()
    cascade_stats = get_cascade_stats()

    print(f"\nZone Stats: {zone_stats}")
    print(f"Cascade Stats: {cascade_stats}")
