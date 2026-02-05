#!/usr/bin/env python3
"""
Verification database for paper trade analysis.

Stores:
- Zone events (detection, displacement, retest, outcome)
- Cascade alerts and corresponding liquidations
- Price snapshots for post-hoc analysis

SQLite for simplicity - no external dependencies.
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

DB_PATH = '/tmp/paper_trade_verification.db'


def get_connection():
    """Get database connection, creating tables if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn


def _create_tables(conn):
    """Create verification tables."""
    conn.executescript("""
        -- Zone events: track lifecycle of each detected zone
        CREATE TABLE IF NOT EXISTS zone_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            zone_type TEXT NOT NULL,  -- 'demand' or 'supply'
            zone_center REAL,
            zone_low REAL,
            zone_high REAL,
            node_count INTEGER,
            avg_strength REAL,
            displacement_detected INTEGER DEFAULT 0,
            displacement_time REAL,
            retest_detected INTEGER DEFAULT 0,
            retest_time REAL,
            entry_proposed INTEGER DEFAULT 0,
            entry_time REAL,
            -- Outcome tracking (filled in later)
            max_favorable_excursion REAL,
            max_adverse_excursion REAL,
            zone_respected INTEGER,  -- 1 if price bounced, 0 if broke through
            outcome_recorded_at REAL,
            metadata TEXT  -- JSON for extra data
        );

        CREATE INDEX IF NOT EXISTS idx_zone_symbol ON zone_events(symbol);
        CREATE INDEX IF NOT EXISTS idx_zone_timestamp ON zone_events(timestamp);

        -- Cascade alerts: track alerts and their verification
        CREATE TABLE IF NOT EXISTS cascade_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            positions_count INTEGER,
            value_at_risk REAL,
            dominant_side TEXT,  -- 'LONG' or 'SHORT'
            closest_liq_price REAL,
            -- Verification against actual liquidations
            liq_burst_detected INTEGER DEFAULT 0,
            liq_burst_time REAL,
            liq_burst_value REAL,
            time_to_burst REAL,  -- seconds between alert and burst
            false_positive INTEGER DEFAULT 0,
            metadata TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cascade_symbol ON cascade_alerts(symbol);
        CREATE INDEX IF NOT EXISTS idx_cascade_timestamp ON cascade_alerts(timestamp);

        -- Liquidation events: raw liquidations for verification
        CREATE TABLE IF NOT EXISTS liquidation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            value_usd REAL,
            price REAL,
            source TEXT DEFAULT 'HL'  -- 'HL' or 'BINANCE'
        );

        CREATE INDEX IF NOT EXISTS idx_liq_symbol ON liquidation_events(symbol);
        CREATE INDEX IF NOT EXISTS idx_liq_timestamp ON liquidation_events(timestamp);

        -- Price snapshots: periodic price recording
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            hl_price REAL,
            binance_price REAL,
            drift_pct REAL
        );

        CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_snapshots(symbol);
        CREATE INDEX IF NOT EXISTS idx_price_timestamp ON price_snapshots(timestamp);

        -- Verification metrics: aggregated stats
        CREATE TABLE IF NOT EXISTS verification_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL,
            symbol TEXT,
            metadata TEXT
        );
    """)
    conn.commit()


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
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO zone_events
        (timestamp, symbol, zone_type, zone_center, zone_low, zone_high, node_count, avg_strength)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp or datetime.now().timestamp(), symbol, zone_type,
          zone_center, zone_low, zone_high, node_count, avg_strength))
    conn.commit()
    zone_id = cursor.lastrowid
    conn.close()
    return zone_id


def update_zone_displacement(zone_id: int, timestamp: float):
    """Mark zone as having displacement detected."""
    conn = get_connection()
    conn.execute("""
        UPDATE zone_events
        SET displacement_detected = 1, displacement_time = ?
        WHERE id = ?
    """, (timestamp, zone_id))
    conn.commit()
    conn.close()


def update_zone_retest(zone_id: int, timestamp: float):
    """Mark zone as having retest detected."""
    conn = get_connection()
    conn.execute("""
        UPDATE zone_events
        SET retest_detected = 1, retest_time = ?
        WHERE id = ?
    """, (timestamp, zone_id))
    conn.commit()
    conn.close()


def update_zone_outcome(
    zone_id: int,
    max_favorable: float,
    max_adverse: float,
    zone_respected: bool,
    timestamp: Optional[float] = None
):
    """Record zone outcome after entry."""
    conn = get_connection()
    conn.execute("""
        UPDATE zone_events
        SET max_favorable_excursion = ?, max_adverse_excursion = ?,
            zone_respected = ?, outcome_recorded_at = ?
        WHERE id = ?
    """, (max_favorable, max_adverse, 1 if zone_respected else 0,
          timestamp or datetime.now().timestamp(), zone_id))
    conn.commit()
    conn.close()


def get_recent_zones(symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get recent zone events."""
    conn = get_connection()
    if symbol:
        rows = conn.execute("""
            SELECT * FROM zone_events WHERE symbol = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (symbol, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM zone_events ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


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
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO cascade_alerts
        (timestamp, symbol, positions_count, value_at_risk, dominant_side, closest_liq_price)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (timestamp or datetime.now().timestamp(), symbol, positions_count,
          value_at_risk, dominant_side, closest_liq_price))
    conn.commit()
    alert_id = cursor.lastrowid
    conn.close()
    return alert_id


def verify_cascade_alert(
    alert_id: int,
    liq_burst_detected: bool,
    liq_burst_time: Optional[float],
    liq_burst_value: Optional[float],
    time_to_burst: Optional[float]
):
    """Update cascade alert with verification results."""
    conn = get_connection()
    conn.execute("""
        UPDATE cascade_alerts
        SET liq_burst_detected = ?, liq_burst_time = ?, liq_burst_value = ?,
            time_to_burst = ?, false_positive = ?
        WHERE id = ?
    """, (1 if liq_burst_detected else 0, liq_burst_time, liq_burst_value,
          time_to_burst, 0 if liq_burst_detected else 1, alert_id))
    conn.commit()
    conn.close()


def get_recent_cascade_alerts(symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Get recent cascade alerts."""
    conn = get_connection()
    if symbol:
        rows = conn.execute("""
            SELECT * FROM cascade_alerts WHERE symbol = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (symbol, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM cascade_alerts ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


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
    conn = get_connection()
    conn.execute("""
        INSERT INTO liquidation_events (timestamp, symbol, side, value_usd, price, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (timestamp or datetime.now().timestamp(), symbol, side, value_usd, price, source))
    conn.commit()
    conn.close()


def get_liquidations_in_window(
    symbol: str,
    start_time: float,
    end_time: float
) -> List[Dict]:
    """Get liquidations within a time window."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM liquidation_events
        WHERE symbol = ? AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp
    """, (symbol, start_time, end_time)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


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

    conn = get_connection()
    conn.execute("""
        INSERT INTO price_snapshots (timestamp, symbol, hl_price, binance_price, drift_pct)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp or datetime.now().timestamp(), symbol, hl_price, binance_price, drift_pct))
    conn.commit()
    conn.close()


# =============================================================================
# Metrics Recording
# =============================================================================

def record_metric(metric_name: str, metric_value: float, symbol: Optional[str] = None):
    """Record a verification metric."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO verification_metrics (timestamp, metric_name, metric_value, symbol)
        VALUES (?, ?, ?, ?)
    """, (datetime.now().timestamp(), metric_name, metric_value, symbol))
    conn.commit()
    conn.close()


# =============================================================================
# Analysis Queries
# =============================================================================

def get_zone_stats() -> Dict[str, Any]:
    """Get zone detection statistics."""
    conn = get_connection()

    stats = {}

    # Total zones
    row = conn.execute("SELECT COUNT(*) as cnt FROM zone_events").fetchone()
    stats['total_zones'] = row['cnt']

    # By type
    rows = conn.execute("""
        SELECT zone_type, COUNT(*) as cnt FROM zone_events GROUP BY zone_type
    """).fetchall()
    stats['by_type'] = {row['zone_type']: row['cnt'] for row in rows}

    # Displacement rate
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN displacement_detected = 1 THEN 1 ELSE 0 END) as disp,
            COUNT(*) as total
        FROM zone_events
    """).fetchone()
    stats['displacement_rate'] = row['disp'] / row['total'] if row['total'] > 0 else 0

    # Retest rate (of those with displacement)
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN retest_detected = 1 THEN 1 ELSE 0 END) as retest,
            COUNT(*) as total
        FROM zone_events WHERE displacement_detected = 1
    """).fetchone()
    stats['retest_rate'] = row['retest'] / row['total'] if row['total'] > 0 else 0

    # Zone respected rate
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN zone_respected = 1 THEN 1 ELSE 0 END) as respected,
            COUNT(*) as total
        FROM zone_events WHERE outcome_recorded_at IS NOT NULL
    """).fetchone()
    stats['zone_respected_rate'] = row['respected'] / row['total'] if row['total'] > 0 else 0

    conn.close()
    return stats


def get_cascade_stats() -> Dict[str, Any]:
    """Get cascade alert statistics."""
    conn = get_connection()

    stats = {}

    # Total alerts
    row = conn.execute("SELECT COUNT(*) as cnt FROM cascade_alerts").fetchone()
    stats['total_alerts'] = row['cnt']

    # Verified (had liquidation burst)
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN liq_burst_detected = 1 THEN 1 ELSE 0 END) as verified,
            SUM(CASE WHEN false_positive = 1 THEN 1 ELSE 0 END) as false_pos,
            COUNT(*) as total
        FROM cascade_alerts
    """).fetchone()
    stats['verified_rate'] = row['verified'] / row['total'] if row['total'] > 0 else 0
    stats['false_positive_rate'] = row['false_pos'] / row['total'] if row['total'] > 0 else 0

    # Average time to burst
    row = conn.execute("""
        SELECT AVG(time_to_burst) as avg_time
        FROM cascade_alerts WHERE liq_burst_detected = 1
    """).fetchone()
    stats['avg_time_to_burst'] = row['avg_time']

    conn.close()
    return stats


if __name__ == '__main__':
    # Initialize database
    conn = get_connection()
    print(f"Database initialized at {DB_PATH}")

    # Show stats if any data exists
    zone_stats = get_zone_stats()
    cascade_stats = get_cascade_stats()

    print(f"\nZone Stats: {zone_stats}")
    print(f"Cascade Stats: {cascade_stats}")
