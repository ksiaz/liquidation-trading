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

        # Table 8.4: Order Book Events (Best Bid/Ask Updates)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orderbook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,

                best_bid_price REAL NOT NULL,
                best_bid_qty REAL NOT NULL,
                best_ask_price REAL NOT NULL,
                best_ask_qty REAL NOT NULL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 8.1: Orderbook Depth (L2 - 20 levels)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orderbook_depth (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,

                bids TEXT NOT NULL,
                asks TEXT NOT NULL,

                bid_total_qty REAL,
                ask_total_qty REAL,
                mid_price REAL,
                spread_bps REAL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 8.2: Mark Prices (Official Binance Mark Price)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mark_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,

                mark_price REAL NOT NULL,
                index_price REAL,
                funding_rate REAL,
                next_funding_time REAL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 8.5: Trade Events (Ground Truth for Validation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                symbol TEXT NOT NULL,

                price REAL NOT NULL,
                volume REAL NOT NULL,

                is_buyer_maker BOOLEAN,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 8.6: Policy Outcomes (Primitive Performance Attribution)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS policy_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                timestamp REAL NOT NULL,

                mandate_type TEXT NOT NULL,
                authority REAL NOT NULL,
                policy_name TEXT,

                active_primitives TEXT,

                executed_action TEXT,
                execution_success BOOLEAN,
                rejection_reason TEXT,

                ghost_trade_id INTEGER,
                realized_pnl REAL,
                holding_duration_sec REAL,
                exit_reason TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cycle_id) REFERENCES execution_cycles(id),
                FOREIGN KEY (ghost_trade_id) REFERENCES ghost_trades(id)
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
        
        # Phase 6: Add regime tracking columns (migration-safe)
        # Check if columns exist before adding
        cursor.execute("PRAGMA table_info(execution_cycles)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        if 'regime_state' not in existing_columns:
            try:
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN regime_state TEXT")
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN vwap REAL")
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN atr_5m REAL")
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN atr_30m REAL")
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN orderflow_imbalance REAL")
                cursor.execute("ALTER TABLE execution_cycles ADD COLUMN liquidation_zscore REAL")
                self.conn.commit()
            except sqlite3.OperationalError:
                # Columns might already exist from a previous migration
                pass

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_ts ON orderbook_events(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trade_events(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_outcomes_cycle ON policy_outcomes(cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_outcomes_symbol_ts ON policy_outcomes(symbol, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_outcomes_trade ON policy_outcomes(ghost_trade_id)")

        # =====================================================================
        # Hyperliquid Integration Tables
        # =====================================================================

        # Table: Hyperliquid positions (position snapshots)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                wallet_address TEXT NOT NULL,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                position_size REAL NOT NULL,
                entry_price REAL NOT NULL,
                liquidation_price REAL NOT NULL,
                leverage REAL,
                margin_used REAL,
                unrealized_pnl REAL,
                position_value REAL,
                distance_to_liquidation_pct REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Hyperliquid liquidation proximity (aggregated)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_liquidation_proximity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                coin TEXT NOT NULL,
                current_price REAL NOT NULL,
                threshold_pct REAL NOT NULL,

                long_positions_count INTEGER,
                long_positions_size REAL,
                long_positions_value REAL,
                long_avg_distance_pct REAL,
                long_closest_liquidation REAL,

                short_positions_count INTEGER,
                short_positions_size REAL,
                short_positions_value REAL,
                short_avg_distance_pct REAL,
                short_closest_liquidation REAL,

                total_positions_at_risk INTEGER,
                total_value_at_risk REAL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Hyperliquid wallet tracking (which wallets we monitor)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_tracked_wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL UNIQUE,
                wallet_type TEXT,
                label TEXT,
                is_active BOOLEAN DEFAULT 1,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT
            )
        """)

        # Table: Hyperliquid cascade events (when proximity threshold crossed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_cascade_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                coin TEXT NOT NULL,
                event_type TEXT NOT NULL,
                current_price REAL NOT NULL,
                threshold_pct REAL NOT NULL,
                positions_at_risk INTEGER,
                value_at_risk REAL,
                dominant_side TEXT,
                closest_liquidation REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Hyperliquid indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_positions_ts ON hl_positions(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_positions_wallet ON hl_positions(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_positions_coin ON hl_positions(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_proximity_ts ON hl_liquidation_proximity(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_proximity_coin ON hl_liquidation_proximity(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_cascade_ts ON hl_cascade_events(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_cascade_coin ON hl_cascade_events(coin)")

        # =====================================================================
        # HLP24-Compliant Raw Data Tables (Append-Only, No Computed Fields)
        # Store raw API responses exactly as received. Labels computed at query time.
        # =====================================================================

        # Table: Raw position snapshots (store API response strings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_ts INTEGER NOT NULL,
                poll_cycle_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                coin TEXT NOT NULL,
                szi TEXT NOT NULL,
                entry_px TEXT NOT NULL,
                liquidation_px TEXT,
                leverage_type TEXT,
                leverage_value REAL,
                margin_used TEXT,
                position_value TEXT,
                unrealized_pnl TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Raw wallet account snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_wallet_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_ts INTEGER NOT NULL,
                poll_cycle_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                account_value TEXT,
                total_margin_used TEXT,
                withdrawable TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Liquidation events (detected from position disappearance)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_liquidation_events_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_ts INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                coin TEXT NOT NULL,
                last_known_szi TEXT NOT NULL,
                last_known_entry_px TEXT NOT NULL,
                last_known_liquidation_px TEXT,
                last_known_position_value TEXT,
                last_known_unrealized_pnl TEXT,
                prev_snapshot_id INTEGER,
                detection_method TEXT DEFAULT 'position_disappearance',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: OI/Funding snapshots (raw API response)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_oi_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_ts INTEGER NOT NULL,
                coin TEXT NOT NULL,
                open_interest TEXT NOT NULL,
                funding_rate TEXT,
                premium TEXT,
                day_ntl_vlm TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Mark price snapshots (raw)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_mark_prices_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_ts INTEGER NOT NULL,
                coin TEXT NOT NULL,
                mark_px TEXT NOT NULL,
                oracle_px TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Funding rate snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_funding_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_ts INTEGER NOT NULL,
                coin TEXT NOT NULL,
                funding_rate TEXT NOT NULL,
                next_funding_ts INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Wallet discovery provenance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_wallet_discovery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address TEXT NOT NULL,
                discovery_ts INTEGER NOT NULL,
                source_type TEXT NOT NULL,
                source_coin TEXT,
                source_value REAL,
                source_metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Poll cycle tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_poll_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_ts INTEGER NOT NULL,
                cycle_type TEXT NOT NULL,
                wallets_polled INTEGER DEFAULT 0,
                positions_found INTEGER DEFAULT 0,
                liquidations_detected INTEGER DEFAULT 0,
                api_errors INTEGER DEFAULT 0,
                duration_ms INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table: Wallet polling configuration (tiered intervals)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hl_wallet_polling_config (
                wallet_address TEXT PRIMARY KEY,
                tier INTEGER NOT NULL,
                last_poll_ts INTEGER,
                next_poll_ts INTEGER,
                poll_count INTEGER DEFAULT 0,
                consecutive_empty INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # HLP24 table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_pos_snap_ts ON hl_position_snapshots(snapshot_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_pos_snap_wallet ON hl_position_snapshots(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_pos_snap_coin ON hl_position_snapshots(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_pos_snap_cycle ON hl_position_snapshots(poll_cycle_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_wallet_snap_ts ON hl_wallet_snapshots(snapshot_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_wallet_snap_addr ON hl_wallet_snapshots(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_liq_events_raw_ts ON hl_liquidation_events_raw(detected_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_liq_events_raw_wallet ON hl_liquidation_events_raw(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_liq_events_raw_coin ON hl_liquidation_events_raw(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_oi_snap_ts ON hl_oi_snapshots(snapshot_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_oi_snap_coin ON hl_oi_snapshots(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_mark_raw_ts ON hl_mark_prices_raw(snapshot_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_mark_raw_coin ON hl_mark_prices_raw(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_funding_ts ON hl_funding_snapshots(snapshot_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_funding_coin ON hl_funding_snapshots(coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_disc_addr ON hl_wallet_discovery(wallet_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_disc_ts ON hl_wallet_discovery(discovery_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_cycles_ts ON hl_poll_cycles(cycle_ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_poll_tier ON hl_wallet_polling_config(tier)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hl_poll_next ON hl_wallet_polling_config(next_poll_ts)")

        self.conn.commit()
    
    def log_cycle(
        self,
        timestamp: float,
        observation_status: str,
        m2_metrics: Dict[str, int],
        symbols_active: List[str],
        primitives_computing: int,
        primitives_total: int,
        performance: Optional[Dict[str, float]] = None,
        regime_state: Optional[str] = None,
        regime_metrics: Optional[Dict[str, float]] = None
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
                memory_usage_mb, cpu_percent,
                regime_state, vwap, atr_5m, atr_30m, orderflow_imbalance, liquidation_zscore
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            performance.get('cpu_percent') if performance else None,
            regime_state,
            regime_metrics.get('vwap') if regime_metrics else None,
            regime_metrics.get('atr_5m') if regime_metrics else None,
            regime_metrics.get('atr_30m') if regime_metrics else None,
            regime_metrics.get('orderflow_imbalance') if regime_metrics else None,
            regime_metrics.get('liquidation_zscore') if regime_metrics else None
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
    
    def log_ohlc_candle(
        self,
        symbol: str,
        timestamp: float,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float = 0,
        trade_count: int = 0
    ):
        """Log 1-minute OHLC candle."""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO ohlc_candles (
                symbol, timestamp, open, high, low, close, volume, trade_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, timestamp, open_price, high, low, close, volume, trade_count
        ))
        self.conn.commit()

    def log_orderbook_event(
        self,
        symbol: str,
        timestamp: float,
        best_bid_price: float,
        best_bid_qty: float,
        best_ask_price: float,
        best_ask_qty: float
    ):
        """Log order book best bid/ask update."""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO orderbook_events (
                symbol, timestamp, best_bid_price, best_bid_qty,
                best_ask_price, best_ask_qty
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol, timestamp, best_bid_price, best_bid_qty,
            best_ask_price, best_ask_qty
        ))
        self.conn.commit()

    def log_orderbook_depth(
        self,
        symbol: str,
        timestamp: float,
        bids: list,
        asks: list
    ):
        """Log L2 orderbook depth (20 levels).

        Args:
            symbol: Trading pair
            timestamp: Event timestamp
            bids: List of [price, qty] pairs for bids
            asks: List of [price, qty] pairs for asks
        """
        cursor = self.conn.cursor()

        # Calculate aggregates
        bid_total = sum(float(b[1]) for b in bids) if bids else 0
        ask_total = sum(float(a[1]) for a in asks) if asks else 0

        best_bid = float(bids[0][0]) if bids else 0
        best_ask = float(asks[0][0]) if asks else 0
        mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
        spread_bps = ((best_ask - best_bid) / mid_price * 10000) if mid_price else 0

        cursor.execute("""
            INSERT INTO orderbook_depth (
                symbol, timestamp, bids, asks,
                bid_total_qty, ask_total_qty, mid_price, spread_bps
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, timestamp, json.dumps(bids), json.dumps(asks),
            bid_total, ask_total, mid_price, spread_bps
        ))
        self.conn.commit()

    def log_mark_price(
        self,
        symbol: str,
        timestamp: float,
        mark_price: float,
        index_price: float = None,
        funding_rate: float = None,
        next_funding_time: float = None
    ):
        """Log official mark price from Binance.

        Args:
            symbol: Trading pair
            timestamp: Event timestamp
            mark_price: Official mark price
            index_price: Index price (optional)
            funding_rate: Current funding rate (optional)
            next_funding_time: Next funding timestamp (optional)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO mark_prices (
                symbol, timestamp, mark_price, index_price,
                funding_rate, next_funding_time
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            symbol, timestamp, mark_price, index_price,
            funding_rate, next_funding_time
        ))
        self.conn.commit()

    def log_trade_event(
        self,
        symbol: str,
        timestamp: float,
        price: float,
        volume: float,
        is_buyer_maker: bool = False
    ):
        """Log individual trade event for ground truth validation."""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO trade_events (
                symbol, timestamp, price, volume, is_buyer_maker
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            symbol, timestamp, price, volume, is_buyer_maker
        ))
        self.conn.commit()

    def log_policy_outcome(
        self,
        cycle_id: int,
        symbol: str,
        timestamp: float,
        mandate_type: str,
        authority: float,
        policy_name: str,
        active_primitives: List[str],
        executed_action: str = None,
        execution_success: bool = None,
        rejection_reason: str = None,
        ghost_trade_id: int = None,
        realized_pnl: float = None,
        holding_duration_sec: float = None,
        exit_reason: str = None
    ):
        """Log policy outcome linking primitives to execution results.

        Called when a mandate is generated to record which primitives were active.
        Can be updated later when ghost trade completes to add PNL/exit data.
        """
        cursor = self.conn.cursor()

        import json
        primitives_json = json.dumps(active_primitives) if active_primitives else None

        cursor.execute("""
            INSERT INTO policy_outcomes (
                cycle_id, symbol, timestamp,
                mandate_type, authority, policy_name,
                active_primitives,
                executed_action, execution_success, rejection_reason,
                ghost_trade_id, realized_pnl, holding_duration_sec, exit_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cycle_id, symbol, timestamp,
            mandate_type, authority, policy_name,
            primitives_json,
            executed_action, execution_success, rejection_reason,
            ghost_trade_id, realized_pnl, holding_duration_sec, exit_reason
        ))
        self.conn.commit()

        return cursor.lastrowid

    def log_mandate(
        self,
        cycle_id: int,
        symbol: str,
        mandate_type: str,
        authority: float,
        timestamp: float
    ):
        """Log generated mandate."""
        if cycle_id is None: return
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO mandates (
                cycle_id, symbol, mandate_type, authority, timestamp
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            cycle_id, symbol, mandate_type, authority, timestamp
        ))
        
        self.conn.commit()

    def log_arbitration_round(
        self,
        cycle_id: int,
        symbol: str,
        mandate_count: int,
        conflicting_mandates: str,
        winning_mandate_type: str,
        resolution_reason: str
    ):
        """Log arbitration conflict resolution."""
        if cycle_id is None: return
        cursor = self.conn.cursor()
        
        # Matches table: cycle_id, symbol, mandate_count, conflicting_mandates, winning_policy, resolution_reason
        cursor.execute("""
            INSERT INTO arbitration_rounds (
                cycle_id, symbol, mandate_count, conflicting_mandates,
                winning_policy, resolution_reason
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            cycle_id, symbol, mandate_count, conflicting_mandates,
            winning_mandate_type, resolution_reason
        ))
        
        self.conn.commit()

    def log_policy_evaluation(
        self,
        cycle_id: int,
        symbol: str,
        policy_name: str,
        is_active: bool,
        confidence: float,
        components: Dict[str, Any]
    ):
        """Log policy evaluation details."""
        if cycle_id is None: return
        cursor = self.conn.cursor()
        
        # Matches table: cycle_id, policy_name, symbol, generated_proposal, triggering_primitives, proposal_reason
        cursor.execute("""
            INSERT INTO policy_evaluations (
                cycle_id, policy_name, symbol,
                generated_proposal, triggering_primitives, proposal_reason
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            cycle_id, policy_name, symbol,
            1 if is_active else 0,
            json.dumps(components),
            f"Confidence: {confidence}"
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

    # =========================================================================
    # Hyperliquid Logging Methods
    # =========================================================================

    def log_hl_position(
        self,
        timestamp: float,
        wallet_address: str,
        coin: str,
        side: str,
        position_size: float,
        entry_price: float,
        liquidation_price: float,
        leverage: float = None,
        margin_used: float = None,
        unrealized_pnl: float = None,
        position_value: float = None,
        distance_to_liquidation_pct: float = None
    ):
        """Log Hyperliquid position snapshot.

        Args:
            timestamp: Position snapshot timestamp
            wallet_address: Ethereum address of position holder
            coin: Asset symbol (e.g., "BTC", "ETH")
            side: Position side ("LONG" or "SHORT")
            position_size: Absolute position size
            entry_price: Position entry price
            liquidation_price: Liquidation price
            leverage: Position leverage
            margin_used: Margin used by position
            unrealized_pnl: Current unrealized PnL
            position_value: Notional position value
            distance_to_liquidation_pct: Distance from current price to liquidation
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_positions (
                timestamp, wallet_address, coin, side,
                position_size, entry_price, liquidation_price,
                leverage, margin_used, unrealized_pnl,
                position_value, distance_to_liquidation_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, wallet_address, coin, side,
            position_size, entry_price, liquidation_price,
            leverage, margin_used, unrealized_pnl,
            position_value, distance_to_liquidation_pct
        ))
        self.conn.commit()

    def log_hl_liquidation_proximity(
        self,
        timestamp: float,
        coin: str,
        current_price: float,
        threshold_pct: float,
        long_positions_count: int = 0,
        long_positions_size: float = 0.0,
        long_positions_value: float = 0.0,
        long_avg_distance_pct: float = None,
        long_closest_liquidation: float = None,
        short_positions_count: int = 0,
        short_positions_size: float = 0.0,
        short_positions_value: float = 0.0,
        short_avg_distance_pct: float = None,
        short_closest_liquidation: float = None,
        total_positions_at_risk: int = 0,
        total_value_at_risk: float = 0.0
    ):
        """Log aggregated liquidation proximity data.

        Core data for the "priming" strategy - tracks how much is about to liquidate.

        Args:
            timestamp: Calculation timestamp
            coin: Asset symbol
            current_price: Current market price
            threshold_pct: Proximity threshold (e.g., 0.005 = 0.5%)
            long_*: Aggregated long position data at risk
            short_*: Aggregated short position data at risk
            total_*: Combined totals
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_liquidation_proximity (
                timestamp, coin, current_price, threshold_pct,
                long_positions_count, long_positions_size, long_positions_value,
                long_avg_distance_pct, long_closest_liquidation,
                short_positions_count, short_positions_size, short_positions_value,
                short_avg_distance_pct, short_closest_liquidation,
                total_positions_at_risk, total_value_at_risk
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, coin, current_price, threshold_pct,
            long_positions_count, long_positions_size, long_positions_value,
            long_avg_distance_pct, long_closest_liquidation,
            short_positions_count, short_positions_size, short_positions_value,
            short_avg_distance_pct, short_closest_liquidation,
            total_positions_at_risk, total_value_at_risk
        ))
        self.conn.commit()

    def log_hl_cascade_event(
        self,
        timestamp: float,
        coin: str,
        event_type: str,
        current_price: float,
        threshold_pct: float,
        positions_at_risk: int,
        value_at_risk: float,
        dominant_side: str = None,
        closest_liquidation: float = None,
        notes: str = None
    ):
        """Log cascade/proximity alert event.

        Triggered when significant liquidation proximity detected.

        Args:
            timestamp: Event timestamp
            coin: Asset symbol
            event_type: Type of event (e.g., "CLUSTER_DETECTED", "CASCADE_IMMINENT")
            current_price: Price at event time
            threshold_pct: Threshold that triggered event
            positions_at_risk: Number of positions at risk
            value_at_risk: Total value at risk (USD)
            dominant_side: Which side has more exposure ("LONG" or "SHORT")
            closest_liquidation: Nearest liquidation price
            notes: Additional context
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_cascade_events (
                timestamp, coin, event_type, current_price, threshold_pct,
                positions_at_risk, value_at_risk, dominant_side,
                closest_liquidation, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp, coin, event_type, current_price, threshold_pct,
            positions_at_risk, value_at_risk, dominant_side,
            closest_liquidation, notes
        ))
        self.conn.commit()

    def add_hl_tracked_wallet(
        self,
        wallet_address: str,
        wallet_type: str = None,
        label: str = None
    ) -> int:
        """Add a wallet to the tracking list.

        Args:
            wallet_address: Ethereum address
            wallet_type: Type (e.g., "WHALE", "HLP", "SYSTEM")
            label: Human-readable label

        Returns:
            Row ID of inserted wallet
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO hl_tracked_wallets (
                wallet_address, wallet_type, label
            ) VALUES (?, ?, ?)
        """, (wallet_address.lower(), wallet_type, label))
        self.conn.commit()

        return cursor.lastrowid

    def get_hl_tracked_wallets(self, active_only: bool = True) -> List[Dict]:
        """Get list of tracked wallets.

        Args:
            active_only: Only return active wallets

        Returns:
            List of wallet records
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM hl_tracked_wallets"
        if active_only:
            query += " WHERE is_active = 1"

        cursor.execute(query)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_latest_hl_proximity(self, coin: str) -> Optional[Dict]:
        """Get most recent liquidation proximity for a coin.

        Args:
            coin: Asset symbol

        Returns:
            Latest proximity record or None
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM hl_liquidation_proximity
            WHERE coin = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (coin,))

        row = cursor.fetchone()
        return dict(row) if row else None

    # =========================================================================
    # HLP24-Compliant Raw Data Logging Methods
    # Store raw API responses exactly as received. No computed fields.
    # =========================================================================

    def start_hl_poll_cycle(self, cycle_type: str) -> int:
        """Start a new poll cycle for batch tracking.

        Args:
            cycle_type: Type of cycle ('tier1', 'tier2', 'tier3', 'discovery')

        Returns:
            poll_cycle_id for linking snapshots
        """
        cursor = self.conn.cursor()
        cycle_ts = int(time.time() * 1_000_000_000)  # nanoseconds

        cursor.execute("""
            INSERT INTO hl_poll_cycles (cycle_ts, cycle_type)
            VALUES (?, ?)
        """, (cycle_ts, cycle_type))

        self.conn.commit()
        return cursor.lastrowid

    def end_hl_poll_cycle(
        self,
        cycle_id: int,
        wallets_polled: int = 0,
        positions_found: int = 0,
        liquidations_detected: int = 0,
        api_errors: int = 0,
        duration_ms: int = None
    ):
        """Complete a poll cycle with statistics.

        Args:
            cycle_id: The poll cycle ID from start_hl_poll_cycle
            wallets_polled: Number of wallets polled
            positions_found: Number of positions found
            liquidations_detected: Number of liquidations detected
            api_errors: Number of API errors encountered
            duration_ms: Total duration in milliseconds
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE hl_poll_cycles
            SET wallets_polled = ?,
                positions_found = ?,
                liquidations_detected = ?,
                api_errors = ?,
                duration_ms = ?
            WHERE id = ?
        """, (wallets_polled, positions_found, liquidations_detected,
              api_errors, duration_ms, cycle_id))

        self.conn.commit()

    def log_hl_position_snapshot_raw(
        self,
        snapshot_ts: int,
        poll_cycle_id: int,
        wallet_address: str,
        coin: str,
        szi: str,
        entry_px: str,
        liquidation_px: str = None,
        leverage_type: str = None,
        leverage_value: float = None,
        margin_used: str = None,
        position_value: str = None,
        unrealized_pnl: str = None
    ) -> int:
        """Log raw position snapshot from API response.

        Stores API response strings exactly as received.
        No computed or derived fields.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            poll_cycle_id: ID of the poll cycle this belongs to
            wallet_address: Wallet address (stored lowercase)
            coin: Asset symbol (e.g., "BTC")
            szi: Signed size string from API
            entry_px: Entry price string from API
            liquidation_px: Liquidation price string (optional)
            leverage_type: "isolated" or "cross" (optional)
            leverage_value: Numeric leverage (optional)
            margin_used: Margin used string (optional)
            position_value: Position value string (optional)
            unrealized_pnl: Unrealized PnL string (optional)

        Returns:
            Row ID of inserted snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_position_snapshots (
                snapshot_ts, poll_cycle_id, wallet_address, coin,
                szi, entry_px, liquidation_px, leverage_type, leverage_value,
                margin_used, position_value, unrealized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_ts, poll_cycle_id, wallet_address.lower(), coin,
            szi, entry_px, liquidation_px, leverage_type, leverage_value,
            margin_used, position_value, unrealized_pnl
        ))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_wallet_snapshot_raw(
        self,
        snapshot_ts: int,
        poll_cycle_id: int,
        wallet_address: str,
        account_value: str = None,
        total_margin_used: str = None,
        withdrawable: str = None
    ) -> int:
        """Log raw wallet account snapshot from API response.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            poll_cycle_id: ID of the poll cycle
            wallet_address: Wallet address
            account_value: Account value string from API
            total_margin_used: Total margin used string
            withdrawable: Withdrawable amount string

        Returns:
            Row ID of inserted snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_wallet_snapshots (
                snapshot_ts, poll_cycle_id, wallet_address,
                account_value, total_margin_used, withdrawable
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (snapshot_ts, poll_cycle_id, wallet_address.lower(),
              account_value, total_margin_used, withdrawable))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_liquidation_event_raw(
        self,
        detected_ts: int,
        wallet_address: str,
        coin: str,
        last_known_szi: str,
        last_known_entry_px: str,
        last_known_liquidation_px: str = None,
        last_known_position_value: str = None,
        last_known_unrealized_pnl: str = None,
        prev_snapshot_id: int = None,
        detection_method: str = 'position_disappearance'
    ) -> int:
        """Log liquidation event detected from position disappearance.

        A position disappearing IS the liquidation event.
        Stores last known state before disappearance.

        Args:
            detected_ts: Detection timestamp in nanoseconds
            wallet_address: Wallet that was liquidated
            coin: Asset that was liquidated
            last_known_szi: Last known signed size
            last_known_entry_px: Last known entry price
            last_known_liquidation_px: Last known liquidation price
            last_known_position_value: Last known position value
            last_known_unrealized_pnl: Last known unrealized PnL
            prev_snapshot_id: Reference to last position snapshot
            detection_method: How liquidation was detected

        Returns:
            Row ID of inserted event
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_liquidation_events_raw (
                detected_ts, wallet_address, coin,
                last_known_szi, last_known_entry_px, last_known_liquidation_px,
                last_known_position_value, last_known_unrealized_pnl,
                prev_snapshot_id, detection_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            detected_ts, wallet_address.lower(), coin,
            last_known_szi, last_known_entry_px, last_known_liquidation_px,
            last_known_position_value, last_known_unrealized_pnl,
            prev_snapshot_id, detection_method
        ))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_oi_snapshot_raw(
        self,
        snapshot_ts: int,
        coin: str,
        open_interest: str,
        funding_rate: str = None,
        premium: str = None,
        day_ntl_vlm: str = None
    ) -> int:
        """Log OI/funding snapshot from API.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            open_interest: Open interest string from API
            funding_rate: Funding rate string
            premium: Oracle-mark premium string
            day_ntl_vlm: 24h notional volume string

        Returns:
            Row ID of inserted snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_oi_snapshots (
                snapshot_ts, coin, open_interest, funding_rate, premium, day_ntl_vlm
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (snapshot_ts, coin, open_interest, funding_rate, premium, day_ntl_vlm))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_mark_price_raw(
        self,
        snapshot_ts: int,
        coin: str,
        mark_px: str,
        oracle_px: str = None
    ) -> int:
        """Log mark price snapshot.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            mark_px: Mark price string from API
            oracle_px: Oracle price string (optional)

        Returns:
            Row ID of inserted snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_mark_prices_raw (snapshot_ts, coin, mark_px, oracle_px)
            VALUES (?, ?, ?, ?)
        """, (snapshot_ts, coin, mark_px, oracle_px))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_funding_snapshot(
        self,
        snapshot_ts: int,
        coin: str,
        funding_rate: str,
        next_funding_ts: int = None
    ) -> int:
        """Log funding rate snapshot.

        Args:
            snapshot_ts: Timestamp in nanoseconds
            coin: Asset symbol
            funding_rate: Funding rate string
            next_funding_ts: Next funding timestamp

        Returns:
            Row ID of inserted snapshot
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_funding_snapshots (snapshot_ts, coin, funding_rate, next_funding_ts)
            VALUES (?, ?, ?, ?)
        """, (snapshot_ts, coin, funding_rate, next_funding_ts))

        self.conn.commit()
        return cursor.lastrowid

    def log_hl_wallet_discovery(
        self,
        wallet_address: str,
        discovery_ts: int,
        source_type: str,
        source_coin: str = None,
        source_value: float = None,
        source_metadata: str = None
    ) -> int:
        """Log wallet discovery provenance.

        Tracks HOW wallets were discovered for audit trail.

        Args:
            wallet_address: Discovered wallet address
            discovery_ts: Discovery timestamp in nanoseconds
            source_type: Discovery source ('trade', 'liquidation', 'manual', 'hyperdash')
            source_coin: Coin if discovered from trade
            source_value: Trade/liquidation value that triggered discovery
            source_metadata: JSON string with additional context

        Returns:
            Row ID of inserted record
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO hl_wallet_discovery (
                wallet_address, discovery_ts, source_type,
                source_coin, source_value, source_metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (wallet_address.lower(), discovery_ts, source_type,
              source_coin, source_value, source_metadata))

        self.conn.commit()
        return cursor.lastrowid

    def set_hl_wallet_tier(
        self,
        wallet_address: str,
        tier: int,
        next_poll_ts: int = None
    ):
        """Set or update wallet polling tier.

        Args:
            wallet_address: Wallet address
            tier: Polling tier (1=5s, 2=30s, 3=300s)
            next_poll_ts: Next scheduled poll timestamp
        """
        cursor = self.conn.cursor()
        now = int(time.time() * 1_000_000_000)

        cursor.execute("""
            INSERT INTO hl_wallet_polling_config (
                wallet_address, tier, next_poll_ts, created_at, updated_at
            ) VALUES (?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(wallet_address) DO UPDATE SET
                tier = excluded.tier,
                next_poll_ts = excluded.next_poll_ts,
                updated_at = datetime('now')
        """, (wallet_address.lower(), tier, next_poll_ts))

        self.conn.commit()

    def get_hl_wallets_due_for_poll(self, tier: int, current_ts: int) -> List[str]:
        """Get wallets that are due for polling in a specific tier.

        Args:
            tier: Polling tier to check
            current_ts: Current timestamp in nanoseconds

        Returns:
            List of wallet addresses due for polling
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT wallet_address FROM hl_wallet_polling_config
            WHERE tier = ? AND (next_poll_ts IS NULL OR next_poll_ts <= ?)
        """, (tier, current_ts))

        return [row[0] for row in cursor.fetchall()]

    def update_hl_wallet_poll_stats(
        self,
        wallet_address: str,
        last_poll_ts: int,
        next_poll_ts: int,
        had_positions: bool
    ):
        """Update wallet polling statistics after a poll.

        Args:
            wallet_address: Wallet that was polled
            last_poll_ts: Timestamp of this poll
            next_poll_ts: Scheduled next poll timestamp
            had_positions: Whether wallet had any positions
        """
        cursor = self.conn.cursor()

        if had_positions:
            cursor.execute("""
                UPDATE hl_wallet_polling_config
                SET last_poll_ts = ?,
                    next_poll_ts = ?,
                    poll_count = poll_count + 1,
                    consecutive_empty = 0,
                    updated_at = datetime('now')
                WHERE wallet_address = ?
            """, (last_poll_ts, next_poll_ts, wallet_address.lower()))
        else:
            cursor.execute("""
                UPDATE hl_wallet_polling_config
                SET last_poll_ts = ?,
                    next_poll_ts = ?,
                    poll_count = poll_count + 1,
                    consecutive_empty = consecutive_empty + 1,
                    updated_at = datetime('now')
                WHERE wallet_address = ?
            """, (last_poll_ts, next_poll_ts, wallet_address.lower()))

        self.conn.commit()

    # =========================================================================
    # HLP24 Query Methods (for replay/analysis)
    # =========================================================================

    def get_hl_position_history(
        self,
        wallet_address: str,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict]:
        """Get position snapshot history for a wallet/coin.

        Args:
            wallet_address: Wallet address
            coin: Asset symbol
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of position snapshots in chronological order
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM hl_position_snapshots
            WHERE wallet_address = ? AND coin = ?
              AND snapshot_ts >= ? AND snapshot_ts <= ?
            ORDER BY snapshot_ts ASC
        """, (wallet_address.lower(), coin, start_ts, end_ts))

        return [dict(row) for row in cursor.fetchall()]

    def get_hl_liquidations_in_window(
        self,
        start_ts: int,
        end_ts: int,
        coin: str = None
    ) -> List[Dict]:
        """Get liquidation events in a time window.

        Args:
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)
            coin: Optional filter by coin

        Returns:
            List of liquidation events
        """
        cursor = self.conn.cursor()

        if coin:
            cursor.execute("""
                SELECT * FROM hl_liquidation_events_raw
                WHERE detected_ts >= ? AND detected_ts <= ? AND coin = ?
                ORDER BY detected_ts ASC
            """, (start_ts, end_ts, coin))
        else:
            cursor.execute("""
                SELECT * FROM hl_liquidation_events_raw
                WHERE detected_ts >= ? AND detected_ts <= ?
                ORDER BY detected_ts ASC
            """, (start_ts, end_ts))

        return [dict(row) for row in cursor.fetchall()]

    def get_hl_oi_history(
        self,
        coin: str,
        start_ts: int,
        end_ts: int
    ) -> List[Dict]:
        """Get OI snapshot history for a coin.

        Args:
            coin: Asset symbol
            start_ts: Start timestamp (nanoseconds)
            end_ts: End timestamp (nanoseconds)

        Returns:
            List of OI snapshots in chronological order
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM hl_oi_snapshots
            WHERE coin = ? AND snapshot_ts >= ? AND snapshot_ts <= ?
            ORDER BY snapshot_ts ASC
        """, (coin, start_ts, end_ts))

        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection."""
        self.conn.close()
