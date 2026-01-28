import time
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from .types import ObservationSnapshot, SystemCounters, ObservationStatus, SystemHaltedException, M4PrimitiveBundle
from .internal.m1_ingestion import M1IngestionEngine
from .internal.m3_temporal import M3TemporalEngine

# Tier B-6: Cascade observation primitives
from memory.m4_cascade_proximity import LiquidationCascadeProximity, compute_liquidation_cascade_proximity
from memory.m4_cascade_state import CascadeStateObservation, compute_cascade_state, CascadePhase
from memory.m4_leverage_concentration import LeverageConcentrationRatio, compute_leverage_concentration
from memory.m4_open_interest_bias import OpenInterestDirectionalBias, compute_open_interest_bias

if TYPE_CHECKING:
    from runtime.hyperliquid.collector import HyperliquidCollector

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

# Zone geometry primitives
from memory.m4_zone_geometry import (
    ZonePenetrationDepth,
    compute_zone_penetration_depth,
    DisplacementOriginAnchor,
    identify_displacement_origin_anchor
)

# Traversal kinematics primitives
from memory.m4_traversal_kinematics import (
    PriceTraversalVelocity,
    compute_price_traversal_velocity,
    TraversalCompactness,
    compute_traversal_compactness
)

# Price distribution primitives
from memory.m4_price_distribution import (
    CentralTendencyDeviation,
    compute_central_tendency_deviation,
    PriceAcceptanceRatio,
    compute_price_acceptance_ratio
)

# Traversal voids primitives
from memory.m4_traversal_voids import (
    TraversalVoidSpan,
    compute_traversal_void_span
)

# Structural absence primitives
from memory.m4_structural_absence import (
    StructuralAbsenceDuration,
    compute_structural_absence_duration
)

# Structural persistence primitives
from memory.m4_structural_persistence import (
    StructuralPersistenceDuration,
    compute_structural_persistence_duration
)

# Event absence primitives
from memory.m4_event_absence import (
    EventNonOccurrenceCounter,
    compute_event_non_occurrence_counter
)

# Liquidation clustering primitives
from memory.m4_liquidation_clustering import (
    LiquidationDensity,
    compute_liquidation_density
)

# Trade flow primitives
from memory.m4_trade_flow import (
    DirectionalContinuity,
    compute_directional_continuity,
    TradeBurst,
    compute_trade_burst
)

# Detection thresholds (structural boundaries, not interpretation)
_OB_SIZE_CHANGE_THRESHOLD = 0.1  # Minimum size delta to record (contract units)
_OB_PRICE_STABILITY_PCT = 1.0     # Maximum price movement for absorption (percentage)
_OB_PRICE_WINDOW_SEC = 2.0        # Time window for price correlation (seconds)

# Zone geometry parameters (structural boundaries)
_ZONE_BAND_PCT = 0.5  # Zone width as percentage of current price
_MIN_TRADES_FOR_KINEMATICS = 10  # Minimum trades needed for velocity/compactness

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

        # Hyperliquid collector (optional, for cascade primitives)
        self._hl_collector: Optional['HyperliquidCollector'] = None

        # Hyperliquid liquidation tracking for cascade state
        self._hl_liquidation_timestamps: Dict[str, List[float]] = {}  # symbol -> timestamps
        self._hl_liquidation_values: Dict[str, List[float]] = {}      # symbol -> values
        self._hl_liquidation_max_symbols = 500  # Memory guard
        self._hl_liquidation_pruned = 0
        
    def set_hyperliquid_source(self, hl_collector: 'HyperliquidCollector') -> None:
        """
        Inject Hyperliquid collector as data source for cascade primitives.

        The collector provides:
        - Position proximity data (for LiquidationCascadeProximity)
        - Position leverage data (for LeverageConcentrationRatio)
        - Position direction data (for OpenInterestDirectionalBias)

        Constitutional compliance: Data flows through M4 primitives, not direct injection.
        """
        self._hl_collector = hl_collector

    def record_hl_liquidation(self, symbol: str, timestamp: float, value: float) -> None:
        """
        Record Hyperliquid liquidation event for cascade state tracking.

        Args:
            symbol: Trading symbol
            timestamp: Event timestamp
            value: USD value liquidated
        """
        # Memory guard: check limit before adding new symbol
        if symbol not in self._hl_liquidation_timestamps:
            if len(self._hl_liquidation_timestamps) >= self._hl_liquidation_max_symbols:
                self.prune_hl_liquidation_tracking()
                # If still at limit, skip this symbol
                if len(self._hl_liquidation_timestamps) >= self._hl_liquidation_max_symbols:
                    return
            self._hl_liquidation_timestamps[symbol] = []
            self._hl_liquidation_values[symbol] = []

        self._hl_liquidation_timestamps[symbol].append(timestamp)
        self._hl_liquidation_values[symbol].append(value)

        # Prune old entries (keep last 120 seconds)
        cutoff = timestamp - 120.0
        while (self._hl_liquidation_timestamps[symbol] and
               self._hl_liquidation_timestamps[symbol][0] < cutoff):
            self._hl_liquidation_timestamps[symbol].pop(0)
            self._hl_liquidation_values[symbol].pop(0)

        # Memory guard: remove empty symbol entries
        if not self._hl_liquidation_timestamps[symbol]:
            del self._hl_liquidation_timestamps[symbol]
            del self._hl_liquidation_values[symbol]

    def prune_hl_liquidation_tracking(self, max_age_sec: float = 120.0) -> int:
        """
        Prune empty symbol entries from liquidation tracking.

        Memory guard to prevent unbounded symbol growth.

        Args:
            max_age_sec: Maximum age for entries (default 120s)

        Returns:
            Number of symbols pruned.
        """
        now = time.time()
        cutoff = now - max_age_sec
        to_remove = []

        for symbol in list(self._hl_liquidation_timestamps.keys()):
            timestamps = self._hl_liquidation_timestamps[symbol]
            # Prune old entries
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
                self._hl_liquidation_values[symbol].pop(0)
            # Mark empty symbols for removal
            if not timestamps:
                to_remove.append(symbol)

        for symbol in to_remove:
            del self._hl_liquidation_timestamps[symbol]
            del self._hl_liquidation_values[symbol]
            self._hl_liquidation_pruned += 1

        return len(to_remove)

    def get_hl_liquidation_metrics(self) -> dict:
        """Get liquidation tracking metrics."""
        return {
            'symbols_tracked': len(self._hl_liquidation_timestamps),
            'max_symbols': self._hl_liquidation_max_symbols,
            'symbols_pruned': self._hl_liquidation_pruned,
        }

    def get_hl_oracle_price(self, symbol: str) -> Optional[float]:
        """
        Get latest Hyperliquid oracle price for a symbol.

        Oracle prices come from SetGlobalAction and are authoritative
        for liquidation calculations.
        """
        return self._m1.get_latest_hl_price(symbol)

    def get_all_hl_prices(self) -> Dict[str, float]:
        """
        Get all latest Hyperliquid oracle prices.

        Returns dict of symbol -> oracle_price.
        """
        return self._m1.get_all_hl_prices()

    def ingest_observation(self, timestamp: float, symbol: str, event_type: str, payload: Dict) -> None:
        """
        Push external fact into memory.
        """
        # Only log TRADE events to reduce verbosity
        if event_type == 'TRADE':
            print(f"DEBUG Governance: TRADE ingest - symbol={symbol}, timestamp={timestamp}, system_time={self._system_time}")

        if self._status == ObservationStatus.FAILED:
            return # Dead system accepts no input

        # Invariant B: Causality (No future data, no ancient history without backfill flag)
        # Tolerance: 30 seconds lag, 5 seconds future (clock skew)
        if timestamp < self._system_time - 30.0:
            # Drop ancient history (Log warning?)
            print(f"DEBUG Governance: DROPPING {event_type} for {symbol} - timestamp {timestamp} < system_time {self._system_time} - 30")
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
            elif event_type == 'HL_PRICE':
                normalized_event = self._m1.normalize_hl_price(symbol, payload)
            elif event_type == 'HL_LIQUIDATION':
                normalized_event = self._m1.normalize_hl_liquidation(symbol, payload)
            elif event_type == 'HL_POSITION':
                normalized_event = self._m1.normalize_hl_position(symbol, payload)
            elif event_type == 'HL_ORDER':
                normalized_event = self._m1.normalize_hl_order(symbol, payload)

            # Dispatch to M3 (Temporal & Pressure) if it's a trade
            if normalized_event and event_type == 'TRADE':
                self._m3.process_trade(
                    timestamp=normalized_event['timestamp'],
                    symbol=normalized_event['symbol'],
                    price=normalized_event['price'],
                    quantity=normalized_event['quantity'],
                    side=normalized_event['side']
                )

                # M2 Population: Associate trade with nearby nodes
                self._associate_trade_with_nodes(normalized_event)

            # M2 Population: Create/update nodes from liquidations
            if normalized_event and event_type == 'LIQUIDATION':
                self._create_or_update_node_from_liquidation(normalized_event)

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

            # Record HL liquidations for cascade state tracking
            if normalized_event and event_type == 'HL_LIQUIDATION':
                self.record_hl_liquidation(
                    symbol=normalized_event['symbol'],
                    timestamp=normalized_event['timestamp'],
                    value=normalized_event['value']
                )
        except Exception as e:
            # Internal crash -> FAILED state
             self._trigger_failure(f"Internal Processing Error: {e}")

    def advance_time(self, new_timestamp: float) -> None:
        """
        Force memory system to recognize time passage.
        """
        # Only log first few times or significant changes
        if self._system_time == 0.0 or new_timestamp - self._system_time > 10:
            print(f"DEBUG Governance: advance_time - old={self._system_time}, new={new_timestamp}")

        if self._status == ObservationStatus.FAILED:
            return

        if new_timestamp < self._system_time:
            # Invariant A: Time Monotonicity
            self._trigger_failure(f"Time Regression: {new_timestamp} < {self._system_time}")
            return

        # M2 Lifecycle Management: Update node states every 10 seconds
        prev_interval = int(self._system_time / 10.0)
        new_interval = int(new_timestamp / 10.0)

        if new_interval > prev_interval:
            try:
                # Apply decay to all nodes
                self._m2_store.decay_nodes(new_timestamp)
                # Update node states (ACTIVE → DORMANT → ARCHIVED)
                self._m2_store.update_memory_states(new_timestamp)
            except Exception as e:
                self._trigger_failure(f"M2 Lifecycle Failure: {e}")

        self._system_time = new_timestamp
        self._update_liveness()

        # Note: Status remains UNINITIALIZED until failure (per EPISTEMIC_CONSTITUTION)
        # UNINITIALIZED means "no failure detected", not "not ready"

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

    def _create_or_update_node_from_liquidation(self, normalized_event: Dict) -> None:
        """Create or update M2 node from liquidation event.

        Args:
            normalized_event: Normalized liquidation event from M1
        """
        symbol = normalized_event['symbol']
        price = normalized_event['price']
        side = normalized_event['side']
        timestamp = normalized_event['timestamp']
        volume = normalized_event.get('quote_qty', 0.0)

        # Generate node ID: {symbol}_{side}_{price_bucket}
        # Price bucket: round to 0.1% precision
        import math
        price_precision = max(1, int(-math.log10(price * 0.001)))
        price_bucket = round(price, price_precision)
        node_id = f"{symbol}_{side}_{price_bucket}"

        # Check if node exists
        existing_node = self._m2_store.get_node(node_id)

        if existing_node:
            # Update existing node
            self._m2_store.record_liquidation_at_node(node_id, timestamp, side)
        else:
            # Create new node
            price_band = price * 0.001  # 10 bps (0.1%)
            self._m2_store.add_or_update_node(
                node_id=node_id,
                symbol=symbol,
                price_center=price_bucket,
                price_band=price_band,
                side="both",  # Liquidations can trigger in either direction
                timestamp=timestamp,
                creation_reason="liquidation",
                initial_strength=0.5,
                volume=volume
            )

    def _associate_trade_with_nodes(self, normalized_event: Dict) -> None:
        """Associate trade with nearby M2 nodes.

        Updates nodes that overlap with the trade price.
        Creates new node if trade is large and no nearby nodes exist.

        Args:
            normalized_event: Normalized trade event from M1
        """
        symbol = normalized_event['symbol']
        price = normalized_event['price']
        timestamp = normalized_event['timestamp']
        volume = normalized_event.get('quote_qty', 0.0)
        side = normalized_event['side']  # FIX: Extract 'side' - used at lines 316, 326
        is_taker_sell = normalized_event['side'] == 'SELL'

        # Find nodes near this price
        nearby_nodes = self._m2_store.get_nodes_near_price(symbol, price)

        if nearby_nodes:
            # Update all nearby nodes with trade evidence
            for node in nearby_nodes:
                self._m2_store.record_trade_at_node(
                    node_id=node.id,
                    timestamp=timestamp,
                    volume=volume,
                    is_buyer_maker=is_taker_sell  # is_taker_sell = is_buyer_maker (same semantic)
                )
        elif volume >= 1000.0:  # Large trade threshold: $1000
            # Create new node from large trade
            import math
            price_precision = max(1, int(-math.log10(price * 0.001)))
            price_bucket = round(price, price_precision)
            orderbook_face = "bid_face" if is_taker_sell else "ask_face"
            node_id = f"{symbol}_{side}_{price_bucket}"

            # Only create if doesn't exist
            if not self._m2_store.get_node(node_id):
                price_band = price * 0.001  # 10 bps
                self._m2_store.add_or_update_node(
                    node_id=node_id,
                    symbol=symbol,
                    price_center=price_bucket,
                    price_band=price_band,
                    side=side,
                    timestamp=timestamp,
                    creation_reason="large_trade",
                    initial_strength=0.3,
                    volume=volume
                )

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

        # Initialize zone geometry and kinematics primitives to None
        zone_penetration_primitive = None
        traversal_velocity_primitive = None
        traversal_compactness_primitive = None
        central_tendency_primitive = None

        try:
            # Get trade data from M1
            trades = list(self._m1.raw_trades.get(symbol, []))

            # DEBUG: Log trade count (disabled - too verbose)
            # print(f"DEBUG Governance: Computing primitives for {symbol}, trades={len(trades)}, min_required={_MIN_TRADES_FOR_KINEMATICS}")

            if len(trades) >= _MIN_TRADES_FOR_KINEMATICS:
                # Extract price sequence
                prices = [t['price'] for t in trades]
                timestamps = [t['timestamp'] for t in trades]

                # Compute traversal velocity (first to last)
                first_price = prices[0]
                last_price = prices[-1]
                first_ts = timestamps[0]
                last_ts = timestamps[-1]

                if last_ts > first_ts:
                    traversal_velocity_primitive = compute_price_traversal_velocity(
                        traversal_id=f"{symbol}_{int(self._system_time)}",
                        price_start=first_price,
                        price_end=last_price,
                        ts_start=first_ts,
                        ts_end=last_ts
                    )

                # Compute traversal compactness
                if len(prices) >= 2:
                    traversal_compactness_primitive = compute_traversal_compactness(
                        traversal_id=f"{symbol}_{int(self._system_time)}",
                        ordered_prices=prices
                    )

                # Compute zone penetration using dynamic zone around current price
                current_price = last_price
                zone_width = current_price * (_ZONE_BAND_PCT / 100.0)
                zone_low = current_price - zone_width
                zone_high = current_price + zone_width

                zone_penetration_primitive = compute_zone_penetration_depth(
                    zone_id=f"{symbol}_zone_{int(self._system_time)}",
                    zone_low=zone_low,
                    zone_high=zone_high,
                    traversal_prices=prices
                )

                # Compute central tendency deviation
                if len(prices) >= 3:
                    mean_price = sum(prices) / len(prices)
                    central_tendency_primitive = compute_central_tendency_deviation(
                        price=current_price,
                        central_tendency=mean_price
                    )

        except Exception as e:
            # Computation failures should not crash snapshot creation
            # Return None primitives and continue
            pass

        # Detect patterns from M2 nodes
        order_block_primitive = None
        supply_demand_zone_primitive = None

        try:
            from memory.m4_node_patterns import (
                detect_order_block,
                detect_supply_demand_zone,
                find_node_clusters
            )

            # Get M2 nodes for this symbol
            active_nodes = self._m2_store.get_active_nodes_for_symbol(symbol)

            if active_nodes:
                # Detect order blocks from individual nodes
                # Find strongest order block candidate
                order_blocks = []
                for node in active_nodes:
                    ob = detect_order_block(node, self._system_time)
                    if ob:
                        order_blocks.append(ob)

                # Return strongest order block (highest interaction density)
                if order_blocks:
                    order_block_primitive = max(
                        order_blocks,
                        key=lambda ob: ob.interactions_per_hour
                    )

                # Detect supply/demand zones from node clusters
                if len(active_nodes) >= 3:
                    # Get current price for displacement detection
                    current_price = None
                    if trades:
                        current_price = trades[-1]['price']

                    if current_price:
                        # Find clusters
                        clusters = find_node_clusters(active_nodes, max_gap_pct=0.2)

                        # Detect zones from clusters
                        zones = []
                        for cluster in clusters:
                            zone = detect_supply_demand_zone(
                                cluster,
                                current_price,
                                self._system_time
                            )
                            if zone:
                                zones.append(zone)

                        # Return strongest zone (highest total volume)
                        if zones:
                            supply_demand_zone_primitive = max(
                                zones,
                                key=lambda z: z.total_volume
                            )

        except Exception as e:
            # Pattern detection failures should not crash snapshot
            pass

        # Initialize additional primitives to None
        displacement_origin_primitive = None
        traversal_void_primitive = None
        price_acceptance_primitive = None
        liquidation_density_primitive = None
        directional_continuity_primitive = None
        trade_burst_primitive = None
        structural_absence_primitive = None
        structural_persistence_primitive = None
        event_non_occurrence_primitive = None

        try:
            # Get trade data from M1 (may already be fetched above)
            if 'trades' not in locals():
                trades = list(self._m1.raw_trades.get(symbol, []))

            if len(trades) >= _MIN_TRADES_FOR_KINEMATICS:
                # Extract sequences
                prices = [t['price'] for t in trades]
                timestamps = [t['timestamp'] for t in trades]
                trade_sides = [t.get('side', 'UNKNOWN') for t in trades]

                # Displacement origin anchor: use first half as pre-traversal
                if len(prices) >= 4:
                    mid_idx = len(prices) // 2
                    pre_traversal_prices = prices[:mid_idx]
                    pre_traversal_timestamps = timestamps[:mid_idx]

                    displacement_origin_primitive = identify_displacement_origin_anchor(
                        traversal_id=f"{symbol}_displacement_{int(self._system_time)}",
                        pre_traversal_prices=pre_traversal_prices,
                        pre_traversal_timestamps=pre_traversal_timestamps
                    )

                # Traversal void span: find gaps between trades
                if len(timestamps) >= 2:
                    observation_start = timestamps[0]
                    observation_end = timestamps[-1]

                    if observation_end > observation_start:
                        traversal_void_primitive = compute_traversal_void_span(
                            observation_start_ts=observation_start,
                            observation_end_ts=observation_end,
                            traversal_timestamps=tuple(timestamps)
                        )

                # Price acceptance ratio: compute OHLC from trades
                if len(prices) >= 2:
                    candle_open = prices[0]
                    candle_close = prices[-1]
                    candle_high = max(prices)
                    candle_low = min(prices)

                    price_acceptance_primitive = compute_price_acceptance_ratio(
                        candle_open=candle_open,
                        candle_high=candle_high,
                        candle_low=candle_low,
                        candle_close=candle_close
                    )

                # Directional continuity: analyze trade direction consistency
                if len(trade_sides) >= 2:
                    # Filter out UNKNOWN sides
                    valid_sides = [s for s in trade_sides if s in ('BUY', 'SELL')]
                    if len(valid_sides) >= 2:
                        directional_continuity_primitive = compute_directional_continuity(
                            trade_sides=valid_sides
                        )

                # Trade burst: find maximum trade density window
                if len(timestamps) >= 2:
                    trade_burst_primitive = compute_trade_burst(
                        trade_timestamps=timestamps,
                        burst_window_sec=1.0
                    )

            # Liquidation density: analyze liquidation clustering
            liquidations = list(self._m1.raw_liquidations.get(symbol, []))
            if len(liquidations) >= 2 and len(trades) >= 1:
                # Use current price as center
                current_price = trades[-1]['price'] if trades else None
                if current_price:
                    # Use 1% price window for liquidation clustering
                    price_window = current_price * 0.01

                    # Format liquidations for compute function
                    liq_list = [
                        {'price': liq['price'], 'volume': liq.get('quantity', 0.0)}
                        for liq in liquidations
                    ]

                    liquidation_density_primitive = compute_liquidation_density(
                        liquidations=liq_list,
                        price_center=current_price,
                        price_window=price_window
                    )

            # Structural absence/persistence: measure M2 node presence over observation window
            if len(timestamps) >= 2:
                observation_start = timestamps[0]
                observation_end = timestamps[-1]

                if observation_end > observation_start:
                    # Get active M2 nodes for this symbol
                    active_nodes = self._m2_store.get_active_nodes_for_symbol(symbol)

                    if len(active_nodes) > 0:
                        # Build presence intervals from M2 nodes
                        # Each node contributes an interval from first_seen to last_interaction
                        presence_intervals = []
                        for node in active_nodes:
                            # Only include intervals that overlap with observation window
                            interval_start = max(node.first_seen_ts, observation_start)
                            interval_end = min(node.last_interaction_ts, observation_end)

                            if interval_start < interval_end:
                                presence_intervals.append((interval_start, interval_end))

                        if len(presence_intervals) > 0:
                            # Compute structural persistence (how long nodes were present)
                            structural_persistence_primitive = compute_structural_persistence_duration(
                                observation_start_ts=observation_start,
                                observation_end_ts=observation_end,
                                presence_intervals=tuple(presence_intervals)
                            )

                            # Compute structural absence (how long nodes were absent)
                            structural_absence_primitive = compute_structural_absence_duration(
                                observation_start_ts=observation_start,
                                observation_end_ts=observation_end,
                                presence_intervals=tuple(presence_intervals)
                            )

            # Event non-occurrence counter: track expected symbols vs observed symbols
            # This is computed once per cycle, not per symbol, so we'll check if symbol is first
            if symbol == self._symbols[0]:  # Only compute once per cycle
                # Expected: all symbols we're tracking
                expected_symbol_ids = tuple(self._symbols)

                # Observed: symbols with ≥1 trade in M1 buffer
                observed_symbol_ids = tuple(
                    sym for sym in self._symbols
                    if len(list(self._m1.raw_trades.get(sym, []))) > 0
                )

                event_non_occurrence_primitive = compute_event_non_occurrence_counter(
                    expected_event_ids=expected_symbol_ids,
                    observed_event_ids=observed_symbol_ids
                )

        except Exception as e:
            # Additional primitive computation failures should not crash snapshot
            pass

        # Tier B-6: Cascade observation primitives (from Hyperliquid)
        cascade_proximity_primitive = None
        cascade_state_primitive = None
        leverage_concentration_primitive = None
        open_interest_bias_primitive = None

        try:
            if self._hl_collector:
                # Convert symbol to Hyperliquid coin format (BTCUSDT -> BTC)
                hl_coin = symbol.replace('USDT', '').replace('PERP', '')

                # Get proximity data from collector
                hl_proximity = self._hl_collector.get_proximity(hl_coin)

                if hl_proximity:
                    # Convert to constitutional M4 primitive
                    cascade_proximity_primitive = LiquidationCascadeProximity(
                        symbol=symbol,
                        price_level=hl_proximity.current_price,
                        threshold_pct=hl_proximity.threshold_pct,
                        positions_at_risk_count=hl_proximity.total_positions_at_risk,
                        aggregate_position_value=hl_proximity.total_value_at_risk,
                        long_positions_count=hl_proximity.long_positions_count,
                        long_positions_value=hl_proximity.long_positions_value,
                        long_closest_price=hl_proximity.long_closest_liquidation,
                        long_avg_distance_pct=hl_proximity.long_avg_distance_pct,
                        short_positions_count=hl_proximity.short_positions_count,
                        short_positions_value=hl_proximity.short_positions_value,
                        short_closest_price=hl_proximity.short_closest_liquidation,
                        short_avg_distance_pct=hl_proximity.short_avg_distance_pct,
                        timestamp=hl_proximity.timestamp
                    )

                    # Compute cascade state from liquidation events
                    liq_timestamps = self._hl_liquidation_timestamps.get(symbol, [])
                    liq_values = self._hl_liquidation_values.get(symbol, [])

                    cascade_state_primitive = compute_cascade_state(
                        symbol=symbol,
                        positions_at_risk=hl_proximity.total_positions_at_risk,
                        liquidation_timestamps=liq_timestamps,
                        liquidation_values=liq_values,
                        current_time=self._system_time
                    )

                # Get position data for leverage and open interest primitives
                tracker = self._hl_collector._tracker if hasattr(self._hl_collector, '_tracker') else None
                if tracker:
                    # Extract positions for coin (HL uses BTC not BTCUSDT)
                    # Use get_positions method which accesses _positions_by_coin (the aggregated index)
                    raw_positions = tracker.get_positions(hl_coin)
                    positions = []
                    for pos in raw_positions:
                        positions.append({
                            'position_size': pos.position_size,
                            'position_value': pos.position_value,
                            'leverage': pos.leverage,
                            'liquidation_price': pos.liquidation_price
                        })
                    if not positions:
                        # Fallback: try directly from wallet_states
                        for wallet_state in tracker._wallet_states.values():
                            pos = wallet_state.positions.get(hl_coin)
                            if pos:
                                positions.append({
                                    'position_size': pos.position_size,
                                    'position_value': pos.position_value,
                                    'leverage': pos.leverage,
                                    'liquidation_price': pos.liquidation_price
                                })

                    if positions:
                        # Compute leverage concentration
                        leverage_concentration_primitive = compute_leverage_concentration(
                            symbol=symbol,
                            positions=positions,
                            timestamp=self._system_time
                        )

                        # Compute open interest bias
                        open_interest_bias_primitive = compute_open_interest_bias(
                            symbol=symbol,
                            positions=positions,
                            timestamp=self._system_time
                        )

        except Exception:
            # Cascade primitive computation failures should not crash snapshot
            pass

        # Return bundle with computed primitives
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=zone_penetration_primitive,
            displacement_origin_anchor=displacement_origin_primitive,
            price_traversal_velocity=traversal_velocity_primitive,
            traversal_compactness=traversal_compactness_primitive,
            central_tendency_deviation=central_tendency_primitive,
            structural_absence_duration=structural_absence_primitive,
            traversal_void_span=traversal_void_primitive,
            event_non_occurrence_counter=event_non_occurrence_primitive,
            structural_persistence_duration=structural_persistence_primitive,
            resting_size=resting_size_primitive,
            order_consumption=consumption_primitive,
            absorption_event=absorption_primitive,
            refill_event=refill_primitive,
            price_acceptance_ratio=price_acceptance_primitive,
            liquidation_density=liquidation_density_primitive,
            directional_continuity=directional_continuity_primitive,
            trade_burst=trade_burst_primitive,
            order_block=order_block_primitive,
            supply_demand_zone=supply_demand_zone_primitive,
            # Tier B-6 - Cascade observation primitives
            liquidation_cascade_proximity=cascade_proximity_primitive,
            cascade_state=cascade_state_primitive,
            leverage_concentration_ratio=leverage_concentration_primitive,
            open_interest_directional_bias=open_interest_bias_primitive
        )
