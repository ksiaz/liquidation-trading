from typing import Dict, List, Any, Optional
from .types import ObservationSnapshot, SystemCounters, ObservationStatus, SystemHaltedException, M4PrimitiveBundle
from .internal.m1_ingestion import M1IngestionEngine
from .internal.m3_temporal import M3TemporalEngine

# M2 Continuity Store (Internal Memory)
from memory.m2_continuity_store import ContinuityMemoryStore

# M5 Access Layer (For M4 primitive computation)
from memory.m5_access import MemoryAccess

# Order book primitives
from memory.m4_orderbook_primitives import (
    RestingSizeAtPrice,
    compute_resting_size,
    detect_order_consumption,
    detect_absorption_event,
    detect_refill_event
)

# Detection thresholds (structural boundaries, not interpretation)
_OB_SIZE_CHANGE_THRESHOLD = 0.1  # Minimum size delta to record (contract units)
_OB_PRICE_STABILITY_PCT = 1.0     # Maximum price movement for absorption (percentage)
_OB_PRICE_WINDOW_SEC = 2.0        # Time window for price correlation (seconds)

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
                normalized_event = self._m1.normalize_depth(symbol, payload)

            # Dispatch to M3 (Temporal & Pressure) if it's a trade
            if normalized_event and event_type == 'TRADE':
                self._m3.process_trade(
                    timestamp=normalized_event['timestamp'],
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    quantity=normalized_event['quantity'],
                    side=normalized_event['side']
                )

            # Update M2 nodes with orderbook state if it's a depth event
            if normalized_event and event_type == 'DEPTH':
                self._m2_store.update_orderbook_state(
                    symbol=normalized_event['symbol'],
                    timestamp=normalized_event['timestamp'],
                    bid_size=normalized_event['bid_size'],
                    ask_size=normalized_event['ask_size'],
                    best_bid_price=normalized_event['best_bid_price'],
                    best_ask_price=normalized_event['best_ask_price']
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
        self._update_liveness()
        
        # Trigger M3 to close windows
        try:
            self._m3.advance_time(new_timestamp)
        except Exception as e:
            self._trigger_failure(f"M3 Temporal Failure: {e}")

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
        # Initialize all primitives to None
        resting_size_primitive = None
        consumption_primitive = None
        absorption_primitive = None
        refill_primitive = None

        try:
            # Get current and previous depth snapshots
            current_depth = self._m1.latest_depth.get(symbol)
            previous_depth = self._m1.previous_depth.get(symbol)

            if current_depth:
                # Extract current state
                current_bid = current_depth.get('bid_size', 0.0)
                current_ask = current_depth.get('ask_size', 0.0)
                best_bid = current_depth.get('best_bid_price')
                best_ask = current_depth.get('best_ask_price')
                current_ts = current_depth.get('timestamp', self._system_time)

                # Compute resting size
                if current_bid > 0 or current_ask > 0:
                    resting_size_primitive = compute_resting_size(
                        bid_size=current_bid,
                        ask_size=current_ask,
                        best_bid_price=best_bid,
                        best_ask_price=best_ask,
                        timestamp=current_ts
                    )

                # Detect consumption and refill if we have previous state
                if previous_depth:
                    prev_bid = previous_depth.get('bid_size', 0.0)
                    prev_ask = previous_depth.get('ask_size', 0.0)
                    prev_ts = previous_depth.get('timestamp', 0.0)

                    # Skip if timestamps are identical (duplicate update)
                    if prev_ts < current_ts:
                        # Detect bid consumption
                        if prev_bid > 0 and best_bid:
                            consumption_primitive = detect_order_consumption(
                                previous_size=prev_bid,
                                current_size=current_bid,
                                side='bid',
                                price_level=best_bid,
                                timestamp=current_ts,
                                min_consumption_threshold=_OB_SIZE_CHANGE_THRESHOLD
                            )

                        # Detect ask consumption if no bid consumption
                        if consumption_primitive is None and prev_ask > 0 and best_ask:
                            consumption_primitive = detect_order_consumption(
                                previous_size=prev_ask,
                                current_size=current_ask,
                                side='ask',
                                price_level=best_ask,
                                timestamp=current_ts,
                                min_consumption_threshold=_OB_SIZE_CHANGE_THRESHOLD
                            )

                        # Detect absorption (consumption + price stability)
                        if consumption_primitive:
                            # Get price before/after from recent trades
                            prices = list(self._m1.recent_prices.get(symbol, []))
                            if len(prices) >= 2:
                                # Find prices around previous and current timestamps
                                price_before = None
                                price_after = None

                                for ts, price in prices:
                                    if ts <= prev_ts + _OB_PRICE_WINDOW_SEC:
                                        price_before = price
                                    if ts <= current_ts and ts > prev_ts:
                                        price_after = price

                                if price_before and price_after:
                                    absorption_primitive = detect_absorption_event(
                                        consumed_size=consumption_primitive.consumed_size,
                                        price_before=price_before,
                                        price_after=price_after,
                                        side=consumption_primitive.side,
                                        timestamp=current_ts,
                                        max_price_movement_pct=_OB_PRICE_STABILITY_PCT
                                    )

                        # Detect refill (size increase)
                        if prev_bid > 0 and best_bid:
                            refill_primitive = detect_refill_event(
                                previous_size=prev_bid,
                                current_size=current_bid,
                                side='bid',
                                price_level=best_bid,
                                timestamp=current_ts,
                                min_refill_threshold=_OB_SIZE_CHANGE_THRESHOLD
                            )

                        # Detect ask refill if no bid refill
                        if refill_primitive is None and prev_ask > 0 and best_ask:
                            refill_primitive = detect_refill_event(
                                previous_size=prev_ask,
                                current_size=current_ask,
                                side='ask',
                                price_level=best_ask,
                                timestamp=current_ts,
                                min_refill_threshold=_OB_SIZE_CHANGE_THRESHOLD
                            )

        except Exception as e:
            # Computation failures should not crash snapshot creation
            # Return None primitives and continue
            pass

        # Return bundle with computed primitives
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=resting_size_primitive,
            order_consumption=consumption_primitive,
            absorption_event=absorption_primitive,
            refill_event=refill_primitive,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None
        )
