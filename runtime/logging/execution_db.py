"""
Comprehensive Research Logging Database

Captures complete system state for analysis:
- M2 node lifecycle
- Full primitive values (not just booleans)
- Policy decision tracking
- Arbitration conflict resolution
- Market context correlation
- Performance profiling

Constitutional: Factual logging only, no interpretation.
"""

import sqlite3
import time
import json
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime


class ResearchDatabase:
    """SQLite database for comprehensive execution logging."""
    
    def __init__(self, db_path: str = "logs/execution.db"):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        # Ensure logs directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        self._create_schema()
    
    def _create_schema(self):
        """Create complete research database schema."""
        cursor = self.conn.cursor()
        
        # Table 1: Execution Cycles (Core)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                observation_status TEXT NOT NULL,
                
                m2_active_nodes INTEGER,
                m2_dormant_nodes INTEGER,
                m2_archived_nodes INTEGER,
                m2_total_created INTEGER,
                m2_total_interactions INTEGER,
                
                symbols_active_count INTEGER,
                symbols_active_list TEXT,
                
                primitives_computing_total INTEGER,
                primitives_possible_total INTEGER,
                
                snapshot_generation_ms REAL,
                primitive_computation_ms REAL,
                policy_evaluation_ms REAL,
                arbitration_ms REAL,
                
                memory_usage_mb REAL,
                cpu_percent REAL,
                
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table 2: M2 Memory Nodes (Full State)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS m2_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                
                node_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT,
                
                price_center REAL NOT NULL,
                price_band REAL NOT NULL,
                
                state TEXT,
                active BOOLEAN,
                
                strength REAL,
                confidence REAL,
                decay_rate REAL,
                
                first_seen_ts REAL,
                last_interaction_ts REAL,
                age_seconds REAL,
                
                liquidation_count INTEGER,
                trade_execution_count INTEGER,
                liquidation_proximity_count INTEGER,
                
                volume_total REAL,
                creation_reason TEXT,
                
                presence_intervals_json TEXT,
                
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
            )
        """)
        
        # Table 3: Primitive Values (Actual Values)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS primitive_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                
                zone_penetration_depth REAL,
                zone_penetration_direction TEXT,
                displacement_anchor_dwell_time REAL,
                
                price_velocity REAL,
                traversal_compactness REAL,
                acceptance_ratio REAL,
                acceptance_accepted_range REAL,
                acceptance_rejected_range REAL,
                
                central_tendency_deviation REAL,
                
                absence_duration REAL,
                
                persistence_duration REAL,
                persistence_presence_pct REAL,
                
                void_span_max REAL,
                event_non_occurrence_count INTEGER,
                
                resting_size_bid REAL,
                resting_size_ask REAL,
                order_consumption_size REAL,
                order_consumption_rate REAL,
                absorption_event BOOLEAN,
                refill_event BOOLEAN,
                
                liquidation_density REAL,
                directional_continuity_value REAL,
                trade_burst_count INTEGER,
                
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
            )
        """)
        
        # Table 4: Policy Evaluations (Decision Tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                policy_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                
                primitives_available TEXT,
                conditions_checked TEXT,
                
                generated_proposal BOOLEAN,
                proposal_action_type TEXT,
                proposal_reason TEXT,
                
                triggering_primitives TEXT,
                evaluation_time_ms REAL,
                
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
            )
        """)
        
        # Table 5: Mandates (Enhanced)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mandates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                policy_evaluation_id INTEGER,
                
                symbol TEXT NOT NULL,
                mandate_type TEXT NOT NULL,
                authority REAL NOT NULL,
                timestamp REAL NOT NULL,
                
                source_policy TEXT,
                triggering_primitives TEXT,
                
                price_at_mandate REAL,
                m2_nodes_active_count INTEGER,
                
                submitted_to_arbitration BOOLEAN,
                was_arbitration_winner BOOLEAN,
                arbitration_conflict_count INTEGER,
                
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
            )
        """)
        
        # Table 6: Arbitration Rounds (Conflict Resolution)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arbitration_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                
                mandate_count INTEGER,
                conflicting_mandates TEXT,
                
                winning_mandate_id INTEGER,
                winning_policy TEXT,
                resolution_reason TEXT,
                
                exit_supremacy_invoked BOOLEAN,
                arbitration_time_ms REAL,
                
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id)
            )
        """)
        
        # Table 7: Liquidation Events (Market Context)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,
                
                side TEXT,
                price REAL NOT NULL,
                volume REAL NOT NULL,
                
                created_node_id TEXT,
                reinforced_node_id TEXT,
                
                price_change_1m_pct REAL,
                
                ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table 8: OHLC Candles (Price Context)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ohlc_candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp REAL NOT NULL,
                
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                
                volume REAL,
                trade_count INTEGER
            )
        """)
        
        # Table 9: M2 Node Events (Event-level capture)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS m2_node_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                
                node_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                side TEXT,
                volume REAL,
                
                strength_after REAL,
                
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycles_timestamp ON execution_cycles(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_cycle ON m2_nodes(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_symbol ON m2_nodes(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_primitives_cycle ON primitive_values(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_primitives_symbol ON primitive_values(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_eval_cycle ON policy_evaluations(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mandates_cycle ON mandates(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mandates_symbol ON mandates(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_arbitration_cycle ON arbitration_rounds(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_timestamp ON liquidation_events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_symbol_ts ON ohlc_candles(symbol, timestamp)")
        
        self.conn.commit()
    
    def log_cycle(
        self,
        timestamp: float,
        observation_status: str,
        m2_metrics: Dict[str, int],
        symbols_active: List[str],
        primitives_computing: int,
        primitives_total: int,
        performance: Optional[Dict[str, float]] = None
    ) -> int:
        """Log execution cycle (Phase 1 - Core).
        
        Returns:
            cycle_id for linking related data
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO execution_cycles (
                timestamp, observation_status,
                m2_active_nodes, m2_dormant_nodes, m2_archived_nodes,
                m2_total_created, m2_total_interactions,
                symbols_active_count, symbols_active_list,
                primitives_computing_total, primitives_possible_total,
                snapshot_generation_ms, primitive_computation_ms,
                policy_evaluation_ms, arbitration_ms,
                memory_usage_mb, cpu_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, observation_status,
            m2_metrics.get('active_nodes', 0),
            m2_metrics.get('dormant_nodes', 0),
            m2_metrics.get('archived_nodes', 0),
            m2_metrics.get('total_nodes_created', 0),
            m2_metrics.get('total_interactions', 0),
            len(symbols_active),
            json.dumps(symbols_active),
            primitives_computing,
            primitives_total,
            performance.get('snapshot_generation_ms') if performance else None,
            performance.get('primitive_computation_ms') if performance else None,
            performance.get('policy_evaluation_ms') if performance else None,
            performance.get('arbitration_ms') if performance else None,
            performance.get('memory_usage_mb') if performance else None,
            performance.get('cpu_percent') if performance else None
        ))
        
        cycle_id = cursor.lastrowid
        self.conn.commit()
        return cycle_id
    
    def log_m2_nodes(self, cycle_id: int, nodes: List[Dict[str, Any]]):
        """Log M2 node snapshots."""
        cursor = self.conn.cursor()
        
        for node in nodes:
            cursor.execute("""
                INSERT INTO m2_nodes (
                    cycle_id, node_id, symbol, side,
                    price_center, price_band,
                    state, active, strength, confidence, decay_rate,
                    first_seen_ts, last_interaction_ts, age_seconds,
                    liquidation_count, trade_execution_count, liquidation_proximity_count,
                    volume_total, creation_reason, presence_intervals_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle_id, node['id'], node['symbol'], node.get('side'),
                node['price_center'], node['price_band'],
                node.get('state', 'ACTIVE'), node.get('active', True),
                node.get('strength'), node.get('confidence'), node.get('decay_rate'),
                node.get('first_seen_ts'), node.get('last_interaction_ts'),
                node.get('age_seconds'),
                node.get('liquidation_count', 0),
                node.get('trade_execution_count', 0),
                node.get('liquidation_proximity_count', 0),
                node.get('volume_total'),
                node.get('creation_reason'),
                json.dumps(node.get('presence_intervals', []))
            ))
        
        self.conn.commit()
    
    def log_primitive_values(self, cycle_id: int, primitives_by_symbol: Dict[str, Dict[str, Any]]):
        """Log full primitive values (not just booleans)."""
        cursor = self.conn.cursor()
        
        for symbol, primitives in primitives_by_symbol.items():
            cursor.execute("""
                INSERT INTO primitive_values (
                    cycle_id, symbol,
                    zone_penetration_depth, zone_penetration_direction,
                    displacement_anchor_dwell_time,
                    price_velocity, traversal_compactness,
                    acceptance_ratio, acceptance_accepted_range, acceptance_rejected_range,
                    central_tendency_deviation,
                    absence_duration,
                    persistence_duration, persistence_presence_pct,
                    void_span_max, event_non_occurrence_count,
                    resting_size_bid, resting_size_ask,
                    order_consumption_size, order_consumption_rate,
                    absorption_event, refill_event,
                    liquidation_density, directional_continuity_value, trade_burst_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle_id, symbol,
                primitives.get('zone_penetration_depth'),
                primitives.get('zone_penetration_direction'),
                primitives.get('displacement_anchor_dwell_time'),
                primitives.get('price_velocity'),
                primitives.get('traversal_compactness'),
                primitives.get('acceptance_ratio'),
                primitives.get('acceptance_accepted_range'),
                primitives.get('acceptance_rejected_range'),
                primitives.get('central_tendency_deviation'),
                primitives.get('absence_duration'),
                primitives.get('persistence_duration'),
                primitives.get('persistence_presence_pct'),
                primitives.get('void_span_max'),
                primitives.get('event_non_occurrence_count'),
                primitives.get('resting_size_bid'),
                primitives.get('resting_size_ask'),
                primitives.get('order_consumption_size'),
                primitives.get('order_consumption_rate'),
                primitives.get('absorption_event'),
                primitives.get('refill_event'),
                primitives.get('liquidation_density'),
                primitives.get('directional_continuity_value'),
                primitives.get('trade_burst_count')
            ))
        
        self.conn.commit()
    
    def log_liquidation_event(
        self,
        timestamp: float,
        symbol: str,
        side: str,
        price: float,
        volume: float,
        node_result: Optional[Dict[str, Any]] = None
    ):
        """Log liquidation event for market context."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO liquidation_events (
                timestamp, symbol, side, price, volume,
                created_node_id, reinforced_node_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, symbol, side, price, volume,
            node_result.get('created_node_id') if node_result else None,
            node_result.get('reinforced_node_id') if node_result else None
        ))
        
        self.conn.commit()
    
    def log_m2_node_event(
        self,
        timestamp: float,
        event_type: str,
        node_id: str,
        symbol: str,
        price: float,
        side: str,
        volume: float,
        strength_after: float
    ):
        """Log individual M2 node event (CREATED, REINFORCED, etc.)."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO m2_node_events (
                timestamp, event_type, node_id, symbol,
                price, side, volume, strength_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, event_type, node_id, symbol,
            price, side, volume, strength_after
        ))
        
        self.conn.commit()
    
    def close(self):
        """Close database connection."""
        self.conn.close()
