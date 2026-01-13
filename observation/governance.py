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
                
            # Dispatch to M3 (Temporal & Pressure) if it's a trade
            if normalized_event and event_type == 'TRADE':
                self._m3.process_trade(
                    timestamp=normalized_event['timestamp'],
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    quantity=normalized_event['quantity'],
                    side=normalized_event['side']
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
        # Query M2 for active nodes (this will return empty list until M2 is populated)
        # For now, gracefully handle empty M2 by returning None primitives
        # Future implementation will compute real primitives when M2 is populated

        try:
            # Attempt to get active nodes for this symbol
            # M2 store query (spatial filter by symbol would require current price)
            # For now, we don't have symbol-specific nodes, so return None primitives

            # This stub maintains correct call structure without requiring
            # fully populated M2 store or complex query parameter construction

            # Future implementation will:
            # 1. Query M2 for nodes associated with symbol
            # 2. Build query params from node data
            # 3. Call M5 access layer for each primitive
            # 4. Assemble M4PrimitiveBundle from results

            pass
        except Exception:
            # Computation failures should not crash snapshot creation
            # Return None primitives and continue
            pass

        # Return bundle with all primitives as None until M2 is populated
        # This maintains structural correctness while deferring implementation
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
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None
        )
