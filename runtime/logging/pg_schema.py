"""
PostgreSQL Schema Setup.

Translates all SQLite schemas to PostgreSQL DDL.
Idempotent — safe to run on every startup.

Sources:
- execution_db.py (49 tables)
- position/repository.py (1 table)
- ep4_ghost_tracker.py (1 table)
- persistence/execution_state_repository.py (5 tables)
"""


def ensure_schema(conn):
    """Create all tables and indexes. Idempotent."""
    cur = conn.cursor()

    # =========================================================================
    # From execution.db — Core Tables
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS execution_cycles (
            id INTEGER PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
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
            snapshot_generation_ms DOUBLE PRECISION,
            primitive_computation_ms DOUBLE PRECISION,
            policy_evaluation_ms DOUBLE PRECISION,
            arbitration_ms DOUBLE PRECISION,
            memory_usage_mb DOUBLE PRECISION,
            cpu_percent DOUBLE PRECISION,
            regime_state TEXT,
            vwap DOUBLE PRECISION,
            atr_5m DOUBLE PRECISION,
            atr_30m DOUBLE PRECISION,
            orderflow_imbalance DOUBLE PRECISION,
            liquidation_zscore DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS m2_nodes (
            id BIGSERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            node_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            price_center DOUBLE PRECISION NOT NULL,
            price_band DOUBLE PRECISION NOT NULL,
            state TEXT,
            active SMALLINT,
            strength DOUBLE PRECISION,
            confidence DOUBLE PRECISION,
            decay_rate DOUBLE PRECISION,
            first_seen_ts DOUBLE PRECISION,
            last_interaction_ts DOUBLE PRECISION,
            age_seconds DOUBLE PRECISION,
            liquidation_count INTEGER,
            trade_execution_count INTEGER,
            liquidation_proximity_count INTEGER,
            volume_total DOUBLE PRECISION,
            creation_reason TEXT,
            presence_intervals_json TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS primitive_values (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            zone_penetration_depth DOUBLE PRECISION,
            zone_penetration_direction TEXT,
            displacement_anchor_dwell_time DOUBLE PRECISION,
            price_velocity DOUBLE PRECISION,
            traversal_compactness DOUBLE PRECISION,
            acceptance_ratio DOUBLE PRECISION,
            acceptance_accepted_range DOUBLE PRECISION,
            acceptance_rejected_range DOUBLE PRECISION,
            central_tendency_deviation DOUBLE PRECISION,
            absence_duration DOUBLE PRECISION,
            persistence_duration DOUBLE PRECISION,
            persistence_presence_pct DOUBLE PRECISION,
            void_span_max DOUBLE PRECISION,
            event_non_occurrence_count INTEGER,
            resting_size_bid DOUBLE PRECISION,
            resting_size_ask DOUBLE PRECISION,
            order_consumption_size DOUBLE PRECISION,
            order_consumption_rate DOUBLE PRECISION,
            absorption_event SMALLINT,
            refill_event SMALLINT,
            liquidation_density DOUBLE PRECISION,
            directional_continuity_value DOUBLE PRECISION,
            trade_burst_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS policy_evaluations (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            policy_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            primitives_available TEXT,
            conditions_checked TEXT,
            generated_proposal SMALLINT,
            proposal_action_type TEXT,
            proposal_reason TEXT,
            triggering_primitives TEXT,
            evaluation_time_ms DOUBLE PRECISION
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mandates (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            policy_evaluation_id INTEGER,
            symbol TEXT NOT NULL,
            mandate_type TEXT NOT NULL,
            authority DOUBLE PRECISION NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            source_policy TEXT,
            triggering_primitives TEXT,
            price_at_mandate DOUBLE PRECISION,
            m2_nodes_active_count INTEGER,
            submitted_to_arbitration SMALLINT,
            was_arbitration_winner SMALLINT,
            arbitration_conflict_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS arbitration_rounds (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            mandate_count INTEGER,
            conflicting_mandates TEXT,
            winning_mandate_id INTEGER,
            winning_policy TEXT,
            resolution_reason TEXT,
            exit_supremacy_invoked SMALLINT,
            arbitration_time_ms DOUBLE PRECISION
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS liquidation_events (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT,
            price DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            created_node_id TEXT,
            reinforced_node_id TEXT,
            price_change_1m_pct DOUBLE PRECISION,
            ingested_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ohlc_candles (
            id SERIAL PRIMARY KEY,
            symbol TEXT NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            open DOUBLE PRECISION NOT NULL,
            high DOUBLE PRECISION NOT NULL,
            low DOUBLE PRECISION NOT NULL,
            close DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION,
            trade_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orderbook_events (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            best_bid_price DOUBLE PRECISION NOT NULL,
            best_bid_qty DOUBLE PRECISION NOT NULL,
            best_ask_price DOUBLE PRECISION NOT NULL,
            best_ask_qty DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orderbook_depth (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            bids TEXT NOT NULL,
            asks TEXT NOT NULL,
            bid_total_qty DOUBLE PRECISION,
            ask_total_qty DOUBLE PRECISION,
            mid_price DOUBLE PRECISION,
            spread_bps DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mark_prices (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            mark_price DOUBLE PRECISION NOT NULL,
            index_price DOUBLE PRECISION,
            funding_rate DOUBLE PRECISION,
            next_funding_time DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_events (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            volume DOUBLE PRECISION NOT NULL,
            is_buyer_maker SMALLINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ghost_trades (
            id SERIAL PRIMARY KEY,
            trade_id TEXT NOT NULL,
            cycle_id INTEGER,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity DOUBLE PRECISION NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            position_side TEXT NOT NULL,
            is_entry SMALLINT NOT NULL,
            pnl DOUBLE PRECISION,
            account_balance_after DOUBLE PRECISION NOT NULL,
            entry_cycle_id INTEGER,
            exit_cycle_id INTEGER,
            winning_policy_name TEXT,
            active_primitives TEXT,
            spread_bps DOUBLE PRECISION,
            concurrent_positions INTEGER,
            holding_duration_sec DOUBLE PRECISION,
            exit_reason TEXT,
            entry_trade_id TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ghost_trade_rejections (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            attempted_action TEXT NOT NULL,
            attempted_side TEXT,
            rejection_reason TEXT NOT NULL,
            mandate_id INTEGER,
            policy_name TEXT,
            account_balance DOUBLE PRECISION,
            account_equity DOUBLE PRECISION,
            open_positions_count INTEGER,
            current_price DOUBLE PRECISION,
            spread_bps DOUBLE PRECISION,
            triggering_primitives TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS policy_outcomes (
            id SERIAL PRIMARY KEY,
            cycle_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            mandate_type TEXT NOT NULL,
            authority DOUBLE PRECISION NOT NULL,
            policy_name TEXT,
            active_primitives TEXT,
            executed_action TEXT,
            execution_success SMALLINT,
            rejection_reason TEXT,
            ghost_trade_id INTEGER,
            realized_pnl DOUBLE PRECISION,
            holding_duration_sec DOUBLE PRECISION,
            exit_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS m2_node_events (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            event_type TEXT NOT NULL,
            node_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            side TEXT,
            volume DOUBLE PRECISION,
            strength_after DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # =========================================================================
    # Hyperliquid Integration Tables
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_positions (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            wallet_address TEXT NOT NULL,
            coin TEXT NOT NULL,
            side TEXT NOT NULL,
            position_size DOUBLE PRECISION NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            liquidation_price DOUBLE PRECISION NOT NULL,
            leverage DOUBLE PRECISION,
            margin_used DOUBLE PRECISION,
            unrealized_pnl DOUBLE PRECISION,
            position_value DOUBLE PRECISION,
            distance_to_liquidation_pct DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_liquidation_proximity (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            coin TEXT NOT NULL,
            current_price DOUBLE PRECISION NOT NULL,
            threshold_pct DOUBLE PRECISION NOT NULL,
            long_positions_count INTEGER,
            long_positions_size DOUBLE PRECISION,
            long_positions_value DOUBLE PRECISION,
            long_avg_distance_pct DOUBLE PRECISION,
            long_closest_liquidation DOUBLE PRECISION,
            short_positions_count INTEGER,
            short_positions_size DOUBLE PRECISION,
            short_positions_value DOUBLE PRECISION,
            short_avg_distance_pct DOUBLE PRECISION,
            short_closest_liquidation DOUBLE PRECISION,
            total_positions_at_risk INTEGER,
            total_value_at_risk DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_tracked_wallets (
            id SERIAL PRIMARY KEY,
            wallet_address TEXT NOT NULL UNIQUE,
            wallet_type TEXT,
            label TEXT,
            is_active SMALLINT DEFAULT 1,
            added_at TIMESTAMP DEFAULT NOW(),
            last_seen_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_cascade_events (
            id SERIAL PRIMARY KEY,
            timestamp DOUBLE PRECISION NOT NULL,
            coin TEXT NOT NULL,
            event_type TEXT NOT NULL,
            current_price DOUBLE PRECISION NOT NULL,
            threshold_pct DOUBLE PRECISION NOT NULL,
            positions_at_risk INTEGER,
            value_at_risk DOUBLE PRECISION,
            dominant_side TEXT,
            closest_liquidation DOUBLE PRECISION,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # HLP24 Raw Data Tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_position_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            poll_cycle_id INTEGER NOT NULL,
            wallet_address TEXT NOT NULL,
            coin TEXT NOT NULL,
            szi TEXT NOT NULL,
            entry_px TEXT NOT NULL,
            liquidation_px TEXT,
            leverage_type TEXT,
            leverage_value DOUBLE PRECISION,
            margin_used TEXT,
            position_value TEXT,
            unrealized_pnl TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_wallet_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            poll_cycle_id INTEGER NOT NULL,
            wallet_address TEXT NOT NULL,
            account_value TEXT,
            total_margin_used TEXT,
            withdrawable TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_liquidation_events_raw (
            id SERIAL PRIMARY KEY,
            detected_ts BIGINT NOT NULL,
            wallet_address TEXT NOT NULL,
            coin TEXT NOT NULL,
            last_known_szi TEXT NOT NULL,
            last_known_entry_px TEXT NOT NULL,
            last_known_liquidation_px TEXT,
            last_known_position_value TEXT,
            last_known_unrealized_pnl TEXT,
            prev_snapshot_id INTEGER,
            detection_method TEXT DEFAULT 'position_disappearance',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_oi_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            coin TEXT NOT NULL,
            open_interest TEXT NOT NULL,
            funding_rate TEXT,
            premium TEXT,
            day_ntl_vlm TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_mark_prices_raw (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            coin TEXT NOT NULL,
            mark_px TEXT NOT NULL,
            oracle_px TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_funding_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            coin TEXT NOT NULL,
            funding_rate TEXT NOT NULL,
            next_funding_ts BIGINT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS binance_funding_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            coin TEXT NOT NULL,
            funding_rate TEXT NOT NULL,
            funding_time BIGINT,
            mark_price TEXT,
            index_price TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS spot_price_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_ts BIGINT NOT NULL,
            coin TEXT NOT NULL,
            price TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_wallet_discovery (
            id SERIAL PRIMARY KEY,
            wallet_address TEXT NOT NULL,
            discovery_ts BIGINT NOT NULL,
            source_type TEXT NOT NULL,
            source_coin TEXT,
            source_value DOUBLE PRECISION,
            source_metadata TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_poll_cycles (
            id SERIAL PRIMARY KEY,
            cycle_ts BIGINT NOT NULL,
            cycle_type TEXT NOT NULL,
            wallets_polled INTEGER DEFAULT 0,
            positions_found INTEGER DEFAULT 0,
            liquidations_detected INTEGER DEFAULT 0,
            api_errors INTEGER DEFAULT 0,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_wallet_polling_config (
            wallet_address TEXT PRIMARY KEY,
            tier INTEGER NOT NULL,
            last_poll_ts BIGINT,
            next_poll_ts BIGINT,
            poll_count INTEGER DEFAULT 0,
            consecutive_empty INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # HLP25 Validation Tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_labeled_cascades (
            id SERIAL PRIMARY KEY,
            coin TEXT NOT NULL,
            start_ts BIGINT NOT NULL,
            end_ts BIGINT NOT NULL,
            oi_drop_pct TEXT NOT NULL,
            liquidation_count INTEGER NOT NULL,
            wave_count INTEGER,
            price_start TEXT,
            price_end TEXT,
            price_5min_after TEXT,
            outcome TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_cascade_waves (
            id SERIAL PRIMARY KEY,
            cascade_id INTEGER NOT NULL REFERENCES hl_labeled_cascades(id),
            wave_num INTEGER NOT NULL,
            start_ts BIGINT NOT NULL,
            end_ts BIGINT NOT NULL,
            liquidation_count INTEGER NOT NULL,
            oi_drop_pct TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_validation_results (
            id SERIAL PRIMARY KEY,
            hypothesis_name TEXT NOT NULL,
            run_ts BIGINT NOT NULL,
            total_events INTEGER NOT NULL,
            supporting_events INTEGER NOT NULL,
            success_rate DOUBLE PRECISION NOT NULL,
            calibrated_threshold DOUBLE PRECISION,
            status TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_threshold_configs (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            method TEXT NOT NULL,
            date_set TEXT NOT NULL,
            rationale TEXT NOT NULL,
            sharpe_ratio DOUBLE PRECISION,
            win_rate DOUBLE PRECISION,
            trades_per_month DOUBLE PRECISION,
            validation_sharpe DOUBLE PRECISION,
            validation_degradation_pct DOUBLE PRECISION,
            status TEXT NOT NULL DEFAULT 'HYPOTHESIS',
            sensitivity_range_pct DOUBLE PRECISION,
            is_robust INTEGER DEFAULT 0,
            next_review_date TEXT,
            regime TEXT,
            strategy_name TEXT,
            version INTEGER DEFAULT 1,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_threshold_optimization_runs (
            id SERIAL PRIMARY KEY,
            threshold_name TEXT NOT NULL,
            run_ts BIGINT NOT NULL,
            method TEXT NOT NULL,
            optimal_value DOUBLE PRECISION NOT NULL,
            in_sample_sharpe DOUBLE PRECISION,
            out_of_sample_sharpe DOUBLE PRECISION,
            degradation_pct DOUBLE PRECISION,
            is_robust INTEGER DEFAULT 0,
            grid_min DOUBLE PRECISION,
            grid_max DOUBLE PRECISION,
            grid_step DOUBLE PRECISION,
            candidates_json TEXT,
            sensitivity_json TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Edge Preservation Tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_metric_snapshots (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            window_name TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            sample_count INTEGER NOT NULL,
            mean_value DOUBLE PRECISION,
            p50 DOUBLE PRECISION,
            p75 DOUBLE PRECISION,
            p95 DOUBLE PRECISION,
            p99 DOUBLE PRECISION,
            max_value DOUBLE PRECISION,
            min_value DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_decay_signals (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            metric_name TEXT NOT NULL,
            recent_window TEXT NOT NULL,
            baseline_window TEXT NOT NULL,
            recent_value DOUBLE PRECISION NOT NULL,
            baseline_value DOUBLE PRECISION NOT NULL,
            change_pct DOUBLE PRECISION NOT NULL,
            z_score DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Catastrophe Playbooks
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_catastrophe_events (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT,
            previous_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_kill_switch_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            triggered INTEGER NOT NULL DEFAULT 0,
            trigger_ts_ns BIGINT,
            trigger_reason TEXT,
            manual_override_required INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_recovery_attempts (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            failure_type TEXT NOT NULL,
            attempt_num INTEGER NOT NULL,
            success INTEGER NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Trade Gating
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_gating_decisions (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            decision TEXT NOT NULL,
            execution_state TEXT NOT NULL,
            reason TEXT NOT NULL,
            size_factor DOUBLE PRECISION NOT NULL,
            delay_ns BIGINT NOT NULL DEFAULT 0,
            latency_p50_ns BIGINT,
            latency_p95_ns BIGINT,
            latency_p99_ns BIGINT,
            slippage_mean_bps DOUBLE PRECISION,
            slippage_p95_bps DOUBLE PRECISION,
            sample_count INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Strategy Performance
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_strategy_performance (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            strategy_id TEXT NOT NULL,
            window_type TEXT NOT NULL,
            trade_count INTEGER NOT NULL,
            win_count INTEGER NOT NULL,
            loss_count INTEGER NOT NULL,
            win_rate DOUBLE PRECISION NOT NULL,
            total_pnl DOUBLE PRECISION NOT NULL,
            total_pnl_bps DOUBLE PRECISION NOT NULL,
            gross_profit DOUBLE PRECISION NOT NULL,
            gross_loss DOUBLE PRECISION NOT NULL,
            profit_factor DOUBLE PRECISION NOT NULL,
            expectancy_bps DOUBLE PRECISION NOT NULL,
            avg_slippage_bps DOUBLE PRECISION NOT NULL,
            max_slippage_bps DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Alpha Decay Governor
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_governor_decisions (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            action TEXT NOT NULL,
            severity TEXT NOT NULL,
            reason TEXT NOT NULL,
            strategy_id TEXT,
            symbol TEXT,
            size_factor DOUBLE PRECISION NOT NULL,
            win_rate DOUBLE PRECISION,
            expectancy_bps DOUBLE PRECISION,
            profit_factor DOUBLE PRECISION,
            sample_count INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Capital Governor
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_capital_governor_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            scaling_state TEXT NOT NULL,
            confidence_score DOUBLE PRECISION NOT NULL,
            allowed_capital_fraction DOUBLE PRECISION NOT NULL,
            freeze_until_ns BIGINT,
            freeze_reason TEXT,
            quarantine_active INTEGER DEFAULT 0,
            quarantine_pct DOUBLE PRECISION DEFAULT 0.0,
            last_ath_ns BIGINT,
            ath_value DOUBLE PRECISION,
            consecutive_wins INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_capital_governor_decisions (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            scaling_state TEXT NOT NULL,
            confidence_score DOUBLE PRECISION NOT NULL,
            allowed_capital_fraction DOUBLE PRECISION NOT NULL,
            edge_stability DOUBLE PRECISION,
            market_stability DOUBLE PRECISION,
            execution_quality DOUBLE PRECISION,
            impact_containment DOUBLE PRECISION,
            drawdown_discipline DOUBLE PRECISION,
            strategy_diversification DOUBLE PRECISION,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Meta Governor
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_meta_governor_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            trust_state TEXT NOT NULL,
            trust_score DOUBLE PRECISION NOT NULL,
            allows_trading INTEGER NOT NULL,
            allows_entries INTEGER NOT NULL,
            allows_exits INTEGER NOT NULL,
            capital_override DOUBLE PRECISION,
            requires_manual_reset INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_meta_governor_decisions (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            trust_state TEXT NOT NULL,
            trust_score DOUBLE PRECISION NOT NULL,
            data_trust DOUBLE PRECISION,
            execution_trust DOUBLE PRECISION,
            alpha_trust DOUBLE PRECISION,
            risk_trust DOUBLE PRECISION,
            consistency_trust DOUBLE PRECISION,
            allows_trading INTEGER NOT NULL,
            capital_override DOUBLE PRECISION,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hl_unknown_threat_signals (
            id SERIAL PRIMARY KEY,
            ts_ns BIGINT NOT NULL,
            metric_name TEXT NOT NULL,
            observed_value DOUBLE PRECISION NOT NULL,
            baseline_mean DOUBLE PRECISION NOT NULL,
            baseline_std DOUBLE PRECISION NOT NULL,
            z_score DOUBLE PRECISION NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # =========================================================================
    # From positions.db
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            direction TEXT,
            quantity TEXT NOT NULL,
            entry_price TEXT,
            updated_at DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            strategy_id TEXT,
            entry_context TEXT
        )
    """)

    # =========================================================================
    # From ghost_trades.db
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ghost_positions (
            trade_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty DOUBLE PRECISION NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            entry_time DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            entry_reason TEXT,
            strategy_id TEXT,
            exit_price DOUBLE PRECISION,
            exit_time DOUBLE PRECISION,
            pnl DOUBLE PRECISION,
            zone_context TEXT
        )
    """)

    # =========================================================================
    # From execution_state.db
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stop_orders (
            entry_order_id TEXT PRIMARY KEY,
            stop_order_id TEXT,
            state TEXT NOT NULL,
            stop_price DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            size DOUBLE PRECISION NOT NULL,
            placement_attempts INTEGER DEFAULT 0,
            last_error TEXT,
            placed_at_ns BIGINT,
            triggered_at_ns BIGINT,
            filled_at_ns BIGINT,
            fill_price DOUBLE PRECISION,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS trailing_stops (
            entry_order_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            current_stop_price DOUBLE PRECISION NOT NULL,
            initial_stop_price DOUBLE PRECISION NOT NULL,
            highest_price DOUBLE PRECISION NOT NULL,
            lowest_price DOUBLE PRECISION NOT NULL,
            break_even_triggered INTEGER DEFAULT 0,
            updates_count INTEGER DEFAULT 0,
            current_atr DOUBLE PRECISION,
            config_json TEXT NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            updated_at DOUBLE PRECISION NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS seen_fill_ids (
            fill_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            order_id TEXT NOT NULL,
            processed_at DOUBLE PRECISION NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS closing_timeouts (
            symbol TEXT PRIMARY KEY,
            entered_closing_at DOUBLE PRECISION NOT NULL,
            timeout_sec DOUBLE PRECISION NOT NULL,
            created_at DOUBLE PRECISION NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tracked_positions (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            coin TEXT NOT NULL,
            side TEXT NOT NULL,
            size DOUBLE PRECISION NOT NULL,
            notional DOUBLE PRECISION NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            liq_price DOUBLE PRECISION NOT NULL,
            current_price DOUBLE PRECISION NOT NULL,
            distance_pct DOUBLE PRECISION NOT NULL,
            leverage DOUBLE PRECISION NOT NULL,
            danger_level INTEGER DEFAULT 0,
            updated_at DOUBLE PRECISION NOT NULL,
            opened_at DOUBLE PRECISION,
            discovered_at DOUBLE PRECISION NOT NULL
        )
    """)

    # =========================================================================
    # From candidate_zones.py — Zone Archive
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS archived_zones (
            id SERIAL PRIMARY KEY,
            zone_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price_center DOUBLE PRECISION NOT NULL,
            price_low DOUBLE PRECISION NOT NULL,
            price_high DOUBLE PRECISION NOT NULL,
            created_at DOUBLE PRECISION NOT NULL,
            expired_at DOUBLE PRECISION NOT NULL,
            initial_positions_at_risk INTEGER,
            initial_value_at_risk DOUBLE PRECISION,
            dominant_side TEXT,
            price_visits INTEGER DEFAULT 0,
            price_rejections INTEGER DEFAULT 0,
            price_breakthroughs INTEGER DEFAULT 0,
            time_in_zone_sec DOUBLE PRECISION DEFAULT 0,
            max_penetration_depth DOUBLE PRECISION DEFAULT 0,
            total_volume_in_zone DOUBLE PRECISION DEFAULT 0,
            buy_volume_in_zone DOUBLE PRECISION DEFAULT 0,
            sell_volume_in_zone DOUBLE PRECISION DEFAULT 0,
            absorption_events INTEGER DEFAULT 0,
            was_validated SMALLINT DEFAULT 0,
            final_strength DOUBLE PRECISION DEFAULT 0,
            price_bucket TEXT NOT NULL
        )
    """)

    # =========================================================================
    # From cold_storage.py — Cold Storage
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cold_market_snapshots (
            ts_us BIGINT NOT NULL,
            symbol TEXT NOT NULL,
            open_interest BIGINT,
            funding_rate BIGINT,
            mark_price BIGINT,
            index_price BIGINT,
            bid_depth_1pct BIGINT,
            ask_depth_1pct BIGINT,
            volume_24h BIGINT,
            PRIMARY KEY (ts_us, symbol)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cold_trades (
            id SERIAL PRIMARY KEY,
            ts_us BIGINT NOT NULL,
            symbol TEXT NOT NULL,
            price BIGINT,
            size BIGINT,
            side TEXT,
            is_liquidation SMALLINT DEFAULT 0,
            trade_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cold_events (
            event_id TEXT PRIMARY KEY,
            ts_start_us BIGINT NOT NULL,
            ts_end_us BIGINT,
            symbol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT,
            metrics TEXT,
            label TEXT
        )
    """)

    # =========================================================================
    # From paper_trade_store.py — Paper Trades
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id SERIAL PRIMARY KEY,
            trade_id TEXT UNIQUE NOT NULL,
            coin TEXT NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            entry_time DOUBLE PRECISION NOT NULL,
            size DOUBLE PRECISION NOT NULL,
            liquidated_wallet TEXT,
            liquidation_value DOUBLE PRECISION,
            take_profit_price DOUBLE PRECISION,
            stop_loss_price DOUBLE PRECISION,
            exit_price DOUBLE PRECISION,
            exit_time DOUBLE PRECISION,
            pnl DOUBLE PRECISION,
            status TEXT NOT NULL,
            highest_price DOUBLE PRECISION,
            breakeven_triggered SMALLINT DEFAULT 0,
            original_stop_loss DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_trade_stats (
            date TEXT PRIMARY KEY,
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            total_pnl DOUBLE PRECISION DEFAULT 0,
            largest_win DOUBLE PRECISION DEFAULT 0,
            largest_loss DOUBLE PRECISION DEFAULT 0,
            updated_at DOUBLE PRECISION
        )
    """)

    # =========================================================================
    # From indexed_wallets.py — Indexed Wallet Store
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS indexed_wallets (
            address TEXT PRIMARY KEY,
            first_block_seen INTEGER,
            last_block_seen INTEGER,
            first_seen_timestamp DOUBLE PRECISION,
            last_seen_timestamp DOUBLE PRECISION,
            total_tx_count INTEGER DEFAULT 0,
            total_volume_usd DOUBLE PRECISION DEFAULT 0,
            coins_traded TEXT DEFAULT '[]',
            is_active SMALLINT DEFAULT 0,
            position_value DOUBLE PRECISION DEFAULT 0,
            last_position_check DOUBLE PRECISION DEFAULT 0,
            created_at DOUBLE PRECISION,
            updated_at DOUBLE PRECISION
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS indexing_stats (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DOUBLE PRECISION
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS indexed_wallet_positions (
            id SERIAL PRIMARY KEY,
            wallet_address TEXT NOT NULL,
            coin TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price DOUBLE PRECISION,
            position_size DOUBLE PRECISION,
            position_value DOUBLE PRECISION,
            leverage DOUBLE PRECISION,
            liquidation_price DOUBLE PRECISION,
            margin_used DOUBLE PRECISION,
            unrealized_pnl DOUBLE PRECISION,
            distance_to_liq_pct DOUBLE PRECISION,
            daily_volume DOUBLE PRECISION DEFAULT 0,
            impact_score DOUBLE PRECISION DEFAULT 0,
            liq_touched SMALLINT DEFAULT 0,
            liq_breached SMALLINT DEFAULT 0,
            recent_high DOUBLE PRECISION DEFAULT 0,
            recent_low DOUBLE PRECISION DEFAULT 0,
            updated_at DOUBLE PRECISION,
            UNIQUE(wallet_address, coin)
        )
    """)

    # =========================================================================
    # From wallet_registry.py — Wallet Registry
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallet_registry (
            address TEXT PRIMARY KEY,
            label TEXT,
            wallet_type TEXT,
            source TEXT,
            position_value DOUBLE PRECISION DEFAULT 0,
            last_active DOUBLE PRECISION,
            first_seen DOUBLE PRECISION,
            notes TEXT DEFAULT ''
        )
    """)

    # =========================================================================
    # From signal_database.py — Signals
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            type TEXT NOT NULL,
            entry DOUBLE PRECISION NOT NULL,
            target DOUBLE PRECISION NOT NULL,
            stop DOUBLE PRECISION NOT NULL,
            current_price DOUBLE PRECISION,
            confidence DOUBLE PRECISION NOT NULL,
            reason TEXT,
            regime TEXT,
            nearby_zones INTEGER,
            risk_reward DOUBLE PRECISION,
            status TEXT NOT NULL DEFAULT 'OPEN',
            outcome TEXT,
            unrealized_pnl_pct DOUBLE PRECISION DEFAULT 0,
            realized_pnl_pct DOUBLE PRECISION,
            distance_to_target_pct DOUBLE PRECISION,
            distance_to_stop_pct DOUBLE PRECISION,
            timestamp DOUBLE PRECISION NOT NULL,
            entry_time DOUBLE PRECISION,
            exit_time DOUBLE PRECISION,
            duration_seconds DOUBLE PRECISION,
            exit_price DOUBLE PRECISION,
            close_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # =========================================================================
    # Market State Snapshots (per-symbol market context)
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id BIGSERIAL PRIMARY KEY,
            ts DOUBLE PRECISION NOT NULL,
            symbol TEXT NOT NULL,
            trigger TEXT NOT NULL,
            price DOUBLE PRECISION,
            vwap DOUBLE PRECISION,
            vwap_distance DOUBLE PRECISION,
            vwap_z DOUBLE PRECISION,
            atr_5m DOUBLE PRECISION,
            atr_30m DOUBLE PRECISION,
            atr_ratio DOUBLE PRECISION,
            atr_5m_pct DOUBLE PRECISION,
            orderflow_ratio DOUBLE PRECISION,
            orderflow_fill_count INTEGER,
            orderflow_neutralized BOOLEAN,
            liq_z DOUBLE PRECISION,
            rolling_liq_volume DOUBLE PRECISION,
            rolling_liq_z DOUBLE PRECISION,
            regime TEXT,
            cascade_state TEXT,
            proximity_count INTEGER,
            proximity_usd_at_risk DOUBLE PRECISION,
            closest_liq_pct DOUBLE PRECISION,
            bid_depth_2pct DOUBLE PRECISION,
            ask_depth_2pct DOUBLE PRECISION,
            absorption_ratio_longs DOUBLE PRECISION,
            absorption_ratio_shorts DOUBLE PRECISION,
            cap_confidence DOUBLE PRECISION,
            has_position BOOLEAN,
            position_side TEXT,
            feed_age_ms INTEGER,
            raw_of_fills_60s INTEGER,
            raw_liq_events_baseline INTEGER,
            raw_liq_rate_1m DOUBLE PRECISION,
            raw_burst_count INTEGER,
            raw_burst_volume DOUBLE PRECISION,
            raw_rolling_history_count INTEGER,
            raw_rolling_warmed_up BOOLEAN,
            raw_l2_age_ms INTEGER,
            raw_cap_fills INTEGER
        )
    """)

    # =========================================================================
    # Indexes (all tables)
    # =========================================================================

    _indexes = [
        # Core tables
        ("idx_cycles_timestamp", "execution_cycles", "timestamp"),
        ("idx_nodes_cycle", "m2_nodes", "cycle_id"),
        ("idx_nodes_symbol", "m2_nodes", "symbol"),
        ("idx_primitives_cycle", "primitive_values", "cycle_id"),
        ("idx_primitives_symbol", "primitive_values", "symbol"),
        ("idx_policy_eval_cycle", "policy_evaluations", "cycle_id"),
        ("idx_mandates_cycle", "mandates", "cycle_id"),
        ("idx_mandates_symbol", "mandates", "symbol"),
        ("idx_arbitration_cycle", "arbitration_rounds", "cycle_id"),
        ("idx_liquidations_timestamp", "liquidation_events", "timestamp"),
        ("idx_candles_symbol_ts", "ohlc_candles", "symbol, timestamp"),
        ("idx_orderbook_symbol_ts", "orderbook_events", "symbol, timestamp"),
        ("idx_trades_symbol_ts", "trade_events", "symbol, timestamp"),
        ("idx_policy_outcomes_cycle", "policy_outcomes", "cycle_id"),
        ("idx_policy_outcomes_symbol_ts", "policy_outcomes", "symbol, timestamp"),
        ("idx_policy_outcomes_trade", "policy_outcomes", "ghost_trade_id"),
        ("idx_ghost_trades_symbol", "ghost_trades", "symbol"),
        ("idx_ghost_trades_timestamp", "ghost_trades", "timestamp"),
        ("idx_ghost_trades_cycle", "ghost_trades", "cycle_id"),
        ("idx_ghost_rejections_symbol", "ghost_trade_rejections", "symbol"),
        ("idx_ghost_rejections_cycle", "ghost_trade_rejections", "cycle_id"),
        # HL tables
        ("idx_hl_positions_ts", "hl_positions", "timestamp"),
        ("idx_hl_positions_wallet", "hl_positions", "wallet_address"),
        ("idx_hl_positions_coin", "hl_positions", "coin"),
        ("idx_hl_proximity_ts", "hl_liquidation_proximity", "timestamp"),
        ("idx_hl_proximity_coin", "hl_liquidation_proximity", "coin"),
        ("idx_hl_cascade_ts", "hl_cascade_events", "timestamp"),
        ("idx_hl_cascade_coin", "hl_cascade_events", "coin"),
        ("idx_hl_pos_snap_ts", "hl_position_snapshots", "snapshot_ts"),
        ("idx_hl_pos_snap_wallet", "hl_position_snapshots", "wallet_address"),
        ("idx_hl_pos_snap_coin", "hl_position_snapshots", "coin"),
        ("idx_hl_pos_snap_cycle", "hl_position_snapshots", "poll_cycle_id"),
        ("idx_hl_wallet_snap_ts", "hl_wallet_snapshots", "snapshot_ts"),
        ("idx_hl_wallet_snap_addr", "hl_wallet_snapshots", "wallet_address"),
        ("idx_hl_liq_events_raw_ts", "hl_liquidation_events_raw", "detected_ts"),
        ("idx_hl_liq_events_raw_wallet", "hl_liquidation_events_raw", "wallet_address"),
        ("idx_hl_liq_events_raw_coin", "hl_liquidation_events_raw", "coin"),
        ("idx_hl_oi_snap_ts", "hl_oi_snapshots", "snapshot_ts"),
        ("idx_hl_oi_snap_coin", "hl_oi_snapshots", "coin"),
        ("idx_hl_mark_raw_ts", "hl_mark_prices_raw", "snapshot_ts"),
        ("idx_hl_mark_raw_coin", "hl_mark_prices_raw", "coin"),
        ("idx_hl_funding_ts", "hl_funding_snapshots", "snapshot_ts"),
        ("idx_hl_funding_coin", "hl_funding_snapshots", "coin"),
        ("idx_binance_funding_ts", "binance_funding_snapshots", "snapshot_ts"),
        ("idx_binance_funding_coin", "binance_funding_snapshots", "coin"),
        ("idx_spot_price_ts", "spot_price_snapshots", "snapshot_ts"),
        ("idx_spot_price_coin", "spot_price_snapshots", "coin"),
        ("idx_hl_disc_addr", "hl_wallet_discovery", "wallet_address"),
        ("idx_hl_disc_ts", "hl_wallet_discovery", "discovery_ts"),
        ("idx_hl_cycles_ts", "hl_poll_cycles", "cycle_ts"),
        ("idx_hl_poll_tier", "hl_wallet_polling_config", "tier"),
        ("idx_hl_poll_next", "hl_wallet_polling_config", "next_poll_ts"),
        ("idx_hl_cascades_coin", "hl_labeled_cascades", "coin"),
        ("idx_hl_cascades_ts", "hl_labeled_cascades", "start_ts"),
        ("idx_hl_waves_cascade", "hl_cascade_waves", "cascade_id"),
        ("idx_hl_validation_name", "hl_validation_results", "hypothesis_name"),
        ("idx_hl_validation_ts", "hl_validation_results", "run_ts"),
        ("idx_hl_thresh_name", "hl_threshold_configs", "name"),
        ("idx_hl_thresh_status", "hl_threshold_configs", "status"),
        ("idx_hl_metric_snap_ts", "hl_metric_snapshots", "ts_ns"),
        ("idx_hl_metric_snap_name", "hl_metric_snapshots", "metric_name"),
        ("idx_hl_decay_ts", "hl_decay_signals", "ts_ns"),
        ("idx_hl_catastrophe_ts", "hl_catastrophe_events", "ts_ns"),
        ("idx_hl_recovery_ts", "hl_recovery_attempts", "ts_ns"),
        ("idx_hl_gating_ts", "hl_gating_decisions", "ts_ns"),
        ("idx_hl_strat_perf_ts", "hl_strategy_performance", "ts_ns"),
        ("idx_hl_strat_perf_strategy", "hl_strategy_performance", "strategy_id"),
        ("idx_hl_governor_ts", "hl_governor_decisions", "ts_ns"),
        ("idx_hl_cap_gov_dec_ts", "hl_capital_governor_decisions", "ts_ns"),
        ("idx_hl_meta_gov_dec_ts", "hl_meta_governor_decisions", "ts_ns"),
        ("idx_hl_threat_ts", "hl_unknown_threat_signals", "ts_ns"),
        # positions
        ("idx_positions_state", "positions", "state"),
        # ghost_positions
        ("idx_ghost_positions_status", "ghost_positions", "status"),
        ("idx_ghost_positions_symbol", "ghost_positions", "symbol"),
        # execution_state
        ("idx_stop_orders_symbol", "stop_orders", "symbol"),
        ("idx_stop_orders_state", "stop_orders", "state"),
        ("idx_trailing_stops_symbol", "trailing_stops", "symbol"),
        ("idx_seen_fills_processed", "seen_fill_ids", "processed_at"),
        ("idx_tracked_positions_wallet", "tracked_positions", "wallet"),
        ("idx_tracked_positions_coin", "tracked_positions", "coin"),
        # archived_zones
        ("idx_archived_zones_symbol_bucket", "archived_zones", "symbol, price_bucket"),
        ("idx_archived_zones_created", "archived_zones", "created_at"),
        # cold_storage
        ("idx_cold_snapshots_symbol_ts", "cold_market_snapshots", "symbol, ts_us"),
        ("idx_cold_trades_symbol_ts", "cold_trades", "symbol, ts_us"),
        ("idx_cold_trades_liq", "cold_trades", "is_liquidation"),
        ("idx_cold_events_symbol_ts", "cold_events", "symbol, ts_start_us"),
        ("idx_cold_events_type", "cold_events", "event_type"),
        # paper_trades
        ("idx_paper_trades_coin", "paper_trades", "coin"),
        ("idx_paper_trades_status", "paper_trades", "status"),
        ("idx_paper_trades_entry_time", "paper_trades", "entry_time DESC"),
        # indexed_wallets
        ("idx_iw_volume", "indexed_wallets", "total_volume_usd DESC"),
        ("idx_iw_last_block", "indexed_wallets", "last_block_seen DESC"),
        ("idx_iw_position_value", "indexed_wallets", "position_value DESC"),
        ("idx_iw_is_active", "indexed_wallets", "is_active"),
        ("idx_iw_last_check", "indexed_wallets", "last_position_check"),
        ("idx_iwp_liq_distance", "indexed_wallet_positions", "distance_to_liq_pct ASC"),
        ("idx_iwp_value", "indexed_wallet_positions", "position_value DESC"),
        ("idx_iwp_impact", "indexed_wallet_positions", "impact_score DESC"),
        # wallet_registry
        ("idx_wr_position_value", "wallet_registry", "position_value DESC"),
        ("idx_wr_last_active", "wallet_registry", "last_active DESC"),
        # signals
        ("idx_signals_symbol", "signals", "symbol"),
        ("idx_signals_status", "signals", "status"),
        ("idx_signals_timestamp", "signals", "timestamp"),
        # market_snapshots
        ("idx_ms_symbol_ts", "market_snapshots", "symbol, ts DESC"),
        ("idx_ms_ts", "market_snapshots", "ts DESC"),
    ]

    # Partial indexes for market_snapshots (events vs periodic)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ms_event_trigger_ts
        ON market_snapshots (trigger, ts DESC)
        WHERE trigger != 'PERIODIC'
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ms_periodic_ts
        ON market_snapshots (ts)
        WHERE trigger = 'PERIODIC'
    """)

    for idx_name, table, columns in _indexes:
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})"
        )

    conn.commit()
    print(f"[PG] Schema ensured: {len(_indexes)} indexes", flush=True)
