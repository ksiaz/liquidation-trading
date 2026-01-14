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
    compute_resting_size
)

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

        try:
            # Compute order book primitives from M1 latest depth snapshot
            depth_snapshot = self._m1.latest_depth.get(symbol)

            if depth_snapshot:
                # Extract data from latest depth snapshot
                bid_size = depth_snapshot.get('bid_size', 0.0)
                ask_size = depth_snapshot.get('ask_size', 0.0)
                best_bid_price = depth_snapshot.get('best_bid_price')
                best_ask_price = depth_snapshot.get('best_ask_price')

                if bid_size > 0 or ask_size > 0:
                    resting_size_primitive = compute_resting_size(
                        bid_size=bid_size,
                        ask_size=ask_size,
                        best_bid_price=best_bid_price,
                        best_ask_price=best_ask_price,
                        timestamp=depth_snapshot.get('timestamp', self._system_time)
                    )
            else:
                # Debug: Check why depth snapshot not found
                import sys
                print(f"DEBUG M4: No depth snapshot for {symbol}. Available: {list(self._m1.latest_depth.keys())[:5]}", file=sys.stderr)

        except Exception as e:
            # Computation failures should not crash snapshot creation
            # Return None primitives and continue
            import sys
            print(f"DEBUG M4: Exception computing primitives for {symbol}: {e}", file=sys.stderr)

        # Return bundle with computed primitives
        # Note: Only resting_size implemented for order book validation
        # Other primitives remain stubbed pending implementation
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
            order_consumption=None,  # TODO: Detect size decreases
            absorption_event=None,   # TODO: Detect consumption + price stability
            refill_event=None,       # TODO: Detect size increases
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None
        )
