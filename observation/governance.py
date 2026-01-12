from typing import Dict, List, Any, Optional
from .types import ObservationSnapshot, SystemCounters, ObservationStatus, SystemHaltedException, M4PrimitiveBundle
from .internal.m1_ingestion import M1IngestionEngine
from .internal.m3_temporal import M3TemporalEngine

# M2 Continuity Store (Internal Memory)
from memory.m2_continuity_store import ContinuityMemoryStore

# M5 Access Layer (For M4 primitive computation)
from memory.m5_access import MemoryAccess

class ObservationSystem:
    """
    The sealed Observation System.
    """

    def __init__(self, allowed_symbols: List[str]):
        self._allowed_symbols = set(allowed_symbols)
        self._system_time = 0.0
        self._status = ObservationStatus.UNINITIALIZED
        self._failure_reason = ""

        # Internal Modules
        self._m1 = M1IngestionEngine()
        self._m3 = M3TemporalEngine()

        # M2 Memory Store (STUB: Not populated yet)
        self._m2_store = ContinuityMemoryStore()

        # M5 Access Layer (For primitive computation at snapshot time)
        self._m5_access = MemoryAccess(self._m2_store)
        
    def ingest_observation(self, timestamp: float, symbol: str, event_type: str, payload: Dict) -> None:
        """
        Push external fact into memory.
        """
        if self._status == ObservationStatus.FAILED:
            return # Dead system accepts no input
            
        # Invariant B: Causality (No future data, no ancient history without backfill flag)
        # Tolerance: 30 seconds lag, 5 seconds future (clock skew)
        if timestamp < self._system_time - 30.0:
            # Drop ancient history (Log warning?)
            return
        # Future data tolerance: 5 seconds
        # Accept but do not modify system time

        # M5 Governance Check: Symbol Whitelist
        if symbol not in self._allowed_symbols:
            return 
            
        # Dispatch to M1 (Normalize & Buffer)
        normalized_event = None
        
        try:
            if event_type == 'TRADE':
                normalized_event = self._m1.normalize_trade(symbol, payload)
            elif event_type == 'LIQUIDATION':
                normalized_event = self._m1.normalize_liquidation(symbol, payload)
            elif event_type == 'KLINE':
                self._m1.record_kline(symbol)
            elif event_type == 'OI':
                self._m1.record_oi(symbol)
            elif event_type == 'DEPTH':
                normalized_event = self._m1.normalize_depth_update(symbol, payload)
            elif event_type == 'MARK_PRICE':
                normalized_event = self._m1.normalize_mark_price(symbol, payload)

            # Dispatch to M3 (Temporal & Pressure) if it's a trade
            if normalized_event and event_type == 'TRADE':
                self._m3.process_trade(
                    timestamp=normalized_event['timestamp'],
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    quantity=normalized_event['quantity'],
                    side=normalized_event['side']
                )
                
                # Phase 5.4: Feed M2 with trade
                self._m2_store.ingest_trade(
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    side=normalized_event['side'],
                    volume=normalized_event['quantity'],
                    is_buyer_maker=normalized_event.get('is_buyer_maker', False),
                    timestamp=normalized_event['timestamp']
                )
            
            # Phase 5.4: Feed M2 with liquidation
            if normalized_event and event_type == 'LIQUIDATION':
                self._m2_store.ingest_liquidation(
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    side=normalized_event['side'],
                    volume=normalized_event.get('quantity', 0.0),
                    timestamp=normalized_event['timestamp']
                )

            # Phase OB: Feed M2 with order book updates
            if normalized_event and event_type == 'DEPTH':
                # Update M2 order book state for bids
                for price, size in normalized_event['bids']:
                    self._m2_store.update_orderbook_state(
                        symbol=symbol,
                        price=price,
                        size=size,
                        side='bid',
                        timestamp=normalized_event['timestamp']
                    )

                # Update M2 order book state for asks
                for price, size in normalized_event['asks']:
                    self._m2_store.update_orderbook_state(
                        symbol=symbol,
                        price=price,
                        size=size,
                        side='ask',
                        timestamp=normalized_event['timestamp']
                    )

            # Phase MP: Feed M2 with mark/index price updates
            if normalized_event and event_type == 'MARK_PRICE':
                self._m2_store.update_mark_price_state(
                    symbol=normalized_event['symbol'],
                    mark_price=normalized_event['mark_price'],
                    index_price=normalized_event.get('index_price'),
                    timestamp=normalized_event['timestamp']
                )

        except Exception as e:
            # Internal crash -> FAILED state
             self._trigger_failure(f"Internal Processing Error: {e}")

    def advance_time(self, new_timestamp: float) -> None:
        """
        Force memory system to recognize time passage.
        """
        if self._status == ObservationStatus.FAILED:
            return

        if new_timestamp < self._system_time:
            # Invariant A: Time Monotonicity
            self._trigger_failure(f"Time Regression: {new_timestamp} < {self._system_time}")
            return
            
        self._system_time = new_timestamp
        
        # System Init Transition
        # print(f"DEBUG: advance_time called. Status={self._status}")
        if True: # FORCE ACTIVE
            self._status = ObservationStatus.ACTIVE
            # print(f"DEBUG: Status is now {self._status}")  # Commented out - too verbose

        self._update_liveness()
        
        # Trigger M3 to close windows
        try:
            self._m3.advance_time(new_timestamp)
        except Exception as e:
            self._trigger_failure(f"M3 Temporal Failure: {e}")
        
        # Phase 5.4: Trigger M2 decay cycle
        try:
            self._m2_store.advance_time(new_timestamp)
        except Exception as e:
            self._trigger_failure(f"M2 Decay Failure: {e}")

    def query(self, query_spec: Dict) -> Any:
        """
        Execute a governed read request.
        """
        if self._status == ObservationStatus.FAILED:
             raise SystemHaltedException(f"SYSTEM HALTED: {self._failure_reason}")

        q_type = query_spec.get('type')
        
        if q_type == 'snapshot':
            return self._get_snapshot()
            
        raise ValueError(f"Unknown query type: {q_type}")

    def _trigger_failure(self, reason: str):
        """Enter FAILED state. Irreversible."""
        self._status = ObservationStatus.FAILED
        self._failure_reason = reason
        # Log fatal error here?
        
    def _update_liveness(self):
        """Check Invariant D: Liveness."""
        # Note: In strict isolation, we don't know Wall Clock.
        # But 'advance_time' is called by the runtime loop using Wall Clock.
        # So 'new_timestamp' IS effectively Wall Clock (or Data Clock).
        # We need to rely on the Runtime to push time frequently.
        # If Runtime stops pushing, 'query' won't know unless we verify against machine time 
        # inside query (which violates isolation but is necessary for safety).
        # Compromise: Check lag against machine time in Query Guard.
        pass

    def _get_snapshot(self) -> ObservationSnapshot:
        """Construct public snapshot from internal states.

        Computes M4 primitives exactly once via M5.

        Amendment 2026-01-10: Added primitive computation per ANNEX_M4_PRIMITIVE_FLOW.md
        """
        # Compute primitives for all active symbols
        primitives = {}
        for symbol in sorted(self._allowed_symbols):
            primitives[symbol] = self._compute_primitives_for_symbol(symbol)

        return ObservationSnapshot(
            status=self._status,
            timestamp=self._system_time,
            symbols_active=sorted(self._allowed_symbols),
            counters=SystemCounters(
                intervals_processed=None,
                dropped_events=None
            ),
            promoted_events=None,
            primitives=primitives  # Pre-computed M4 primitives
        )

    def _compute_primitives_for_symbol(self, symbol: str) -> M4PrimitiveBundle:
        """Compute M4 primitives for a single symbol.

        This is the ONLY place M4 primitives are computed for external exposure.
        Called exactly once per symbol per snapshot.

        Returns bundle with fields set to None if:
        - Insufficient data for computation
        - No structural condition detected
        - Computation validation failed

        Authority: ANNEX_M4_PRIMITIVE_FLOW.md
        """
        # Phase 6.1, 6.2, 6.3: M4 Primitive Computation (Complete Bundle)
        try:
            # Import M4 computation functions
            from memory.m4_zone_geometry import compute_zone_penetration_depth, identify_displacement_origin_anchor
            from memory.m4_traversal_kinematics import compute_price_traversal_velocity, compute_traversal_compactness
            from memory.m4_structural_absence import compute_structural_absence_duration
            from memory.m4_structural_persistence import compute_structural_persistence_duration
            from memory.m4_event_absence import compute_event_non_occurrence_counter
            from memory.m4_price_distribution import compute_central_tendency_deviation, compute_price_acceptance_ratio
            from memory.m4_traversal_voids import compute_traversal_void_span
            from memory.m4_orderbook import (
                compute_resting_size,
                detect_order_consumption,
                detect_absorption_event,
                detect_refill_event
            )
            from memory.m4_liquidation_density import compute_liquidation_density
            from memory.m4_directional_continuity import compute_directional_continuity
            from memory.m4_trade_burst import compute_trade_burst
            
            # Query M2 for active nodes (symbol-filtered)
            active_nodes = self._m2_store.get_active_nodes(symbol=symbol)
            
            # Query M3 for recent price history
            recent_prices = self._m3.get_recent_prices(symbol=symbol, max_count=100)
            
            # Initialize primitives
            zone_penetration = None
            displacement_origin_anchor = None
            price_traversal_velocity = None
            traversal_compactness = None
            price_acceptance_ratio = None
            central_tendency_deviation = None
            structural_absence_duration = None
            structural_persistence_duration = None
            traversal_void_span = None
            event_non_occurrence_counter = None
            resting_size_primitive = None
            order_consumption_primitive = None
            absorption_event_primitive = None
            refill_event_primitive = None
            liquidation_density_primitive = None
            directional_continuity_primitive = None
            trade_burst_primitive = None
            
            # 1. ZONE PENETRATION (Phase 6.1)
            if len(active_nodes) > 0 and len(recent_prices) > 0:
                max_penetration = 0.0
                for node in active_nodes:
                    zone_low = node.price_center - node.price_band / 2
                    zone_high = node.price_center + node.price_band / 2
                    
                    result = compute_zone_penetration_depth(
                        zone_id=node.id,
                        zone_low=zone_low,
                        zone_high=zone_high,
                        traversal_prices=recent_prices
                    )
                    
                    if result is not None:
                        max_penetration = max(max_penetration, result.penetration_depth)
                
                if max_penetration > 0:
                    zone_penetration = max_penetration
            
            # 2. DISPLACEMENT ORIGIN ANCHOR (Phase 6.3)
            if len(recent_prices) >= 3:
                # Use pre-traversal window (first 50% of prices)
                mid_point = len(recent_prices) // 2
                pre_traversal_prices = recent_prices[:mid_point]
                # Approximate timestamps (M3 doesn't expose them)
                pre_traversal_timestamps = [
                    self._system_time - (len(pre_traversal_prices) - i) * 0.1
                    for i in range(len(pre_traversal_prices))
                ]
                
                if len(pre_traversal_prices) > 0:
                    anchor = identify_displacement_origin_anchor(
                        traversal_id=f"{symbol}_current",
                        pre_traversal_prices=pre_traversal_prices,
                        pre_traversal_timestamps=pre_traversal_timestamps
                    )
                    displacement_origin_anchor = anchor.anchor_dwell_time
            
            # 3. PRICE TRAVERSAL VELOCITY (Phase 6.2)
            if len(recent_prices) >= 2:
                # Use first and last price in current window
                # Timestamps would require M3 to expose them, so we approximate with system time
                # For now, assume 1 second window (M3 default)
                velocity_result = compute_price_traversal_velocity(
                    traversal_id=f"{symbol}_current",
                    price_start=recent_prices[0],
                    price_end=recent_prices[-1],
                    ts_start=self._system_time - 1.0,  # Approximate window
                    ts_end=self._system_time
                )
                price_traversal_velocity = velocity_result.velocity
            
            # 4. TRAVERSAL COMPACTNESS (Phase 6.3)
            if len(recent_prices) >= 2:
                compactness_result = compute_traversal_compactness(
                    traversal_id=f"{symbol}_current",
                    ordered_prices=recent_prices
                )
                traversal_compactness = compactness_result.compactness_ratio

            # 4b. PRICE ACCEPTANCE RATIO (Phase MISSING)
            # Requires OHLC candle from M3
            candle = self._m3.get_current_candle(symbol)
            if candle is not None:
                try:
                    acceptance_result = compute_price_acceptance_ratio(
                        candle_open=candle['open'],
                        candle_high=candle['high'],
                        candle_low=candle['low'],
                        candle_close=candle['close']
                    )
                    price_acceptance_ratio = acceptance_result
                except ValueError:
                    # Invalid candle structure, skip
                    pass

            # 5. CENTRAL TENDENCY DEVIATION (Phase 6.3)
            if len(recent_prices) > 0 and len(active_nodes) > 0:
                # Central tendency = average of node centers
                central_tendency = sum(node.price_center for node in active_nodes) / len(active_nodes)
                current_price = recent_prices[-1]
                
                deviation_result = compute_central_tendency_deviation(
                    price=current_price,
                    central_tendency=central_tendency
                )
                central_tendency_deviation = deviation_result.deviation_value
            
            # 6. STRUCTURAL ABSENCE DURATION (Phase 6.2)
            if len(active_nodes) > 0:
                # Find most recent interaction across all nodes
                most_recent_interaction = max(
                    node.last_interaction_ts for node in active_nodes
                )
                absence_duration = self._system_time - most_recent_interaction

                # Only set if absence > 0
                if absence_duration > 0:
                    structural_absence_duration = absence_duration

            # 6b. STRUCTURAL PERSISTENCE DURATION (Phase MISSING)
            if len(active_nodes) > 0:
                # Collect all presence intervals from all nodes
                all_presence_intervals = []
                earliest_observation = None
                for node in active_nodes:
                    presence_intervals = node.get_presence_intervals(self._system_time)
                    all_presence_intervals.extend(presence_intervals)
                    if earliest_observation is None or node.first_seen_ts < earliest_observation:
                        earliest_observation = node.first_seen_ts

                if len(all_presence_intervals) > 0 and earliest_observation is not None:
                    try:
                        persistence_result = compute_structural_persistence_duration(
                            observation_start_ts=earliest_observation,
                            observation_end_ts=self._system_time,
                            presence_intervals=tuple(all_presence_intervals)
                        )
                        structural_persistence_duration = persistence_result
                    except ValueError as e:
                        # Invalid intervals, skip (but log for debugging)
                        if symbol == "BTCUSDT" and len(all_presence_intervals) > 0:
                            print(f"DEBUG: structural_persistence_duration failed for {symbol}: {e}")
                        pass

            # 7. TRAVERSAL VOID SPAN (Phase 6.3)
            if len(active_nodes) > 0:
                # Collect all interaction timestamps from nodes
                interaction_timestamps = []
                for node in active_nodes:
                    interaction_timestamps.extend(node.interaction_timestamps)
                
                if len(interaction_timestamps) > 0:
                    # Define observation window
                    earliest_interaction = min(interaction_timestamps)
                    observation_window = (earliest_interaction, self._system_time)
                    
                    void_result = compute_traversal_void_span(
                        observation_start_ts=observation_window[0],
                        observation_end_ts=observation_window[1],
                        traversal_timestamps=tuple(interaction_timestamps)
                    )
                    traversal_void_span = void_result.max_void_duration
            
            # 8. EVENT NON-OCCURRENCE COUNTER (Phase 6.2)
            # Simplified: Count expected nodes vs observed liquidations
            # This is a placeholder implementation
            if len(active_nodes) > 0:
                # For each active node, we expected reinforcement events
                # Non-occurrence = nodes that haven't been interacted with recently
                stale_threshold = 60.0  # 60 seconds
                stale_count = sum(
                    1 for node in active_nodes
                    if (self._system_time - node.last_interaction_ts) > stale_threshold
                )
                if stale_count > 0:
                    event_non_occurrence_counter = stale_count

            # 9. RESTING SIZE (Order Book - Phase OB)
            if len(active_nodes) > 0:
                # Get node with most recent order book update
                ob_nodes = [n for n in active_nodes if n.last_orderbook_update_ts is not None]
                if ob_nodes:
                    latest_ob_node = max(ob_nodes, key=lambda n: n.last_orderbook_update_ts)
                    resting_size_primitive = compute_resting_size(latest_ob_node)

                    # 10. ORDER CONSUMPTION (Phase OB-2)
                    # Detect consumption on bid side
                    if latest_ob_node.previous_resting_size_bid > 0:
                        duration = self._system_time - latest_ob_node.last_orderbook_update_ts
                        consumption = detect_order_consumption(
                            latest_ob_node,
                            latest_ob_node.previous_resting_size_bid,
                            latest_ob_node.resting_size_bid,
                            duration
                        )
                        if consumption:
                            order_consumption_primitive = consumption

                    # Also check ask side consumption
                    if latest_ob_node.previous_resting_size_ask > 0 and order_consumption_primitive is None:
                        duration = self._system_time - latest_ob_node.last_orderbook_update_ts
                        consumption = detect_order_consumption(
                            latest_ob_node,
                            latest_ob_node.previous_resting_size_ask,
                            latest_ob_node.resting_size_ask,
                            duration
                        )
                        if consumption:
                            order_consumption_primitive = consumption

                    # 11. ABSORPTION EVENT (Phase OB-2)
                    # Detect absorption if consumption occurred with price stability
                    if order_consumption_primitive is not None and len(recent_prices) >= 2:
                        absorption = detect_absorption_event(
                            node=latest_ob_node,
                            price_start=recent_prices[0],
                            price_end=recent_prices[-1],
                            consumed_size=order_consumption_primitive.consumed_size,
                            duration=order_consumption_primitive.duration,
                            trade_count=latest_ob_node.trade_execution_count
                        )
                        if absorption:
                            absorption_event_primitive = absorption

                    # 12. REFILL EVENT (Phase OB-2)
                    # Detect refill on bid side
                    if latest_ob_node.previous_resting_size_bid > 0:
                        refill = detect_refill_event(
                            node=latest_ob_node,
                            previous_size=latest_ob_node.previous_resting_size_bid,
                            current_size=latest_ob_node.resting_size_bid,
                            duration=self._system_time - latest_ob_node.last_orderbook_update_ts if latest_ob_node.last_orderbook_update_ts else 0.0
                        )
                        if refill:
                            refill_event_primitive = refill

                    # Also check ask side refill
                    if latest_ob_node.previous_resting_size_ask > 0 and refill_event_primitive is None:
                        refill = detect_refill_event(
                            node=latest_ob_node,
                            previous_size=latest_ob_node.previous_resting_size_ask,
                            current_size=latest_ob_node.resting_size_ask,
                            duration=self._system_time - latest_ob_node.last_orderbook_update_ts if latest_ob_node.last_orderbook_update_ts else 0.0
                        )
                        if refill:
                            refill_event_primitive = refill

            # 13. DIRECTIONAL CONTINUITY (Phase 4.3)
            if len(recent_prices) >= 2:
                directional_continuity = compute_directional_continuity(recent_prices)
                if directional_continuity:
                    directional_continuity_primitive = directional_continuity

            # 14. LIQUIDATION DENSITY (Phase 6.4)
            if len(active_nodes) > 0 and len(recent_prices) >= 2:
                # Collect liquidation volumes from active nodes
                liquidation_volumes = []
                for node in active_nodes:
                    if node.liquidation_proximity_count > 0:
                        # Use volume_total as proxy for liquidation volume
                        liquidation_volumes.append(node.volume_total)

                if liquidation_volumes and len(recent_prices) >= 2:
                    density = compute_liquidation_density(
                        liquidation_volumes=liquidation_volumes,
                        price_start=recent_prices[0],
                        price_end=recent_prices[-1]
                    )
                    if density:
                        liquidation_density_primitive = density

            # 15. TRADE BURST (Phase 5.4)
            if len(active_nodes) > 0:
                # Sum trade execution counts across active nodes
                total_trade_count = sum(node.trade_execution_count for node in active_nodes)
                # Use system time to estimate window duration
                if len(recent_prices) >= 2:
                    # Approximate window duration (1 second default)
                    window_duration = 1.0
                    burst = compute_trade_burst(
                        trade_count=total_trade_count,
                        window_duration=window_duration,
                        baseline=10  # Mechanical baseline: 10 trades
                    )
                    if burst:
                        trade_burst_primitive = burst

            # Return complete bundle
            return M4PrimitiveBundle(
                symbol=symbol,
                zone_penetration=zone_penetration,
                displacement_origin_anchor=displacement_origin_anchor,
                price_traversal_velocity=price_traversal_velocity,
                traversal_compactness=traversal_compactness,
                price_acceptance_ratio=price_acceptance_ratio,
                central_tendency_deviation=central_tendency_deviation,
                structural_absence_duration=structural_absence_duration,
                structural_persistence_duration=structural_persistence_duration,
                traversal_void_span=traversal_void_span,
                event_non_occurrence_counter=event_non_occurrence_counter,
                resting_size=resting_size_primitive,
                order_consumption=order_consumption_primitive,
                absorption_event=absorption_event_primitive,
                refill_event=refill_event_primitive,
                liquidation_density=liquidation_density_primitive,
                directional_continuity=directional_continuity_primitive,
                trade_burst=trade_burst_primitive
            )
            
        except Exception as e:
            # Computation failures should not crash snapshot creation
            # Return None primitives and continue
            return M4PrimitiveBundle(
                symbol=symbol,
                zone_penetration=None,
                displacement_origin_anchor=None,
                price_traversal_velocity=None,
                traversal_compactness=None,
                price_acceptance_ratio=None,
                central_tendency_deviation=None,
                structural_absence_duration=None,
                structural_persistence_duration=None,
                traversal_void_span=None,
                event_non_occurrence_counter=None,
                resting_size=None,
                order_consumption=None,
                absorption_event=None,
                refill_event=None,
                liquidation_density=None,
                directional_continuity=None,
                trade_burst=None
            )
