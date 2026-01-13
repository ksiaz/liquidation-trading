"""
Runtime Collector Service

The Driver of the Observation System.
Responsibility:
1. IO: Connect to Binance WebSockets.
2. Clock: Drive System Time (advance_time).
3. Ingest: Feed Raw Data to M5 (ingest_observation).
4. Loop: Asyncio Main Loop.
5. M6: Invoke PolicyAdapter and Execution (Phase 8)
"""

import asyncio
import json
import time
import logging
from typing import List, Dict, Callable
from collections import deque
from decimal import Decimal
import aiohttp

# Import sealed Observation System
from observation.governance import ObservationSystem
from observation.types import ObservationSnapshot, ObservationStatus

# Import M6 components (Phase 8)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState
from runtime.logging.execution_db import ResearchDatabase

# Import Ghost Tracker
from execution.ep4_ghost_tracker import GhostPositionTracker
import os

# Constants
TOP_10_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
    "TRXUSDT", "DOTUSDT"
]

class CollectorService:
    def __init__(self, observation_system: ObservationSystem, warmup_duration_sec: int = 60):
        self._obs = observation_system
        self._running = False
        self._logger = logging.getLogger("CollectorService")

        # Warm-up period to allow observation layer to build meaningful state
        self._startup_time = None  # Set when service starts
        self._warmup_duration_sec = warmup_duration_sec
        self._warmup_complete = False

        # Initialize execution database for logging FIRST
        self._execution_db = ResearchDatabase(db_path="logs/execution.db")
        
        # Inject event logger into observation system's M2 store
        if not hasattr(self._obs._m2_store, '_event_logger') or self._obs._m2_store._event_logger is None:
            self._obs._m2_store._event_logger = self._execution_db

        # Phase 8: M6 Integration
        self.policy_adapter = PolicyAdapter(AdapterConfig())
        self.arbitrator = MandateArbitrator()
        self.executor = ExecutionController(RiskConfig())

        # Track mark prices for execution (estimated from trade stream)
        self._mark_prices: Dict[str, Decimal] = {}

        # Mock account state (in production, this comes from exchange API)
        self._account = AccountState(
            equity=Decimal("100000.0"),
            margin_available=Decimal("100000.0"),
            timestamp=time.time()
        )
        
        # Track latest stream time to drive system clock
        self._last_stream_time = None

        # Ghost Trading Tracker ($1000 initial, 5% position size, all 10 symbols)
        api_key = os.environ.get("BINANCE_API_KEY")
        self.ghost_tracker = GhostPositionTracker(
            initial_balance=1000.0,
            position_size_pct=0.05,
            symbols=TOP_10_SYMBOLS,  # All 10 symbols for testing
            api_key=api_key,
            db_conn=self._execution_db.conn  # Pass database connection for logging
        )

        # Track execution log index to process new results
        self._last_execution_index = 0

        # Store latest cycle context for ghost tracker
        self._latest_cycle_id = None
        self._latest_snapshot = None
        
    async def start(self):
        """Start all collectors."""
        self._running = True
        self._startup_time = time.time()  # Record startup time for warm-up period

        # self._logger.info(f"Warmup period duration: {self._warmup_duration_sec}s from startup")

        # 1. Start Clock Driver (Heartbeat)
        asyncio.create_task(self._drive_clock())
        
        # 2. Start WebSocket Consumers (Simulated for now, or ported real logic)
        # For Remediation Phase, we will implement the SHELL of the collectors 
        # that drives the real M5, effectively verifying integration.
        # Ideally we port the actual binance connection logic here.
        # Given the task complexity, I will port the structure and stub the actual socket for safety,
        # or reuse the logic if I can import 'scripts' (but I shouldn't).
        # I will re-implement the basic websocket client here.
        
        await self._run_binance_stream()

    async def _drive_clock(self):
        """Push Wall Clock time to System every 100ms and drive M6 execution cycle."""
        while self._running:
            # Use latest stream time if available, otherwise fallback to system time (or wait)
            # User mandate: Use Binance time for everything.
            if self._last_stream_time is not None:
                current_time = self._last_stream_time
            else:
                # Wait for first stream event
                await asyncio.sleep(0.1)
                continue

            try:
                # 1. Advance System Time
                self._obs.advance_time(current_time)

                # 2. Query Observation Snapshot
                snapshot = self._obs.query({'type': 'snapshot'})

                # 3. M6 Execution Cycle (only if observation is not FAILED)
                if snapshot.status != ObservationStatus.FAILED:
                    self._execute_m6_cycle(snapshot, current_time)

                    # 4. Process Ghost Trades based on execution results
                    self._process_ghost_trades()

            except Exception as e:
                # Fail silently per constitutional rules - log but don't halt
                self._logger.debug(f"Clock/Execution cycle exception: {e}")
                pass

            await asyncio.sleep(0.1)

    def _execute_m6_cycle(self, snapshot: ObservationSnapshot, timestamp: float):
        """Execute one M6 cycle: Policies -> Arbitration -> Execution.

        Pure mechanical flow - no interpretation.

        Args:
            snapshot: Current observation snapshot
            timestamp: Current timestamp
        """
        try:
            # Check warm-up period - skip mandate generation if still warming up
            if self._startup_time is not None:
                elapsed = timestamp - self._startup_time
                if elapsed < self._warmup_duration_sec:
                    # Still in warm-up - allow observation layer to build state
                    return
                elif not self._warmup_complete:
                    # Warm-up just completed
                    self._warmup_complete = True
                    self._logger.info(f"Mandate generation suppression period ended at {elapsed:.1f}s")
                    print(f"Mandate generation suppression period ended at {elapsed:.1f}s")

            # Log execution cycle FIRST to establish context
            cycle_id = None
            if hasattr(self, '_execution_db'):
                cycle_id = self._log_cycle_to_db(snapshot, [], timestamp)
                # print(f"DEBUG M6: Started cycle {cycle_id} for {len(snapshot.symbols_active)} symbols")

            # Store for ghost tracker
            self._latest_cycle_id = cycle_id
            self._latest_snapshot = snapshot

            # Collect mandates from all active symbols
            all_mandates = []
            mandate_primitives_map = {}  # Track primitives for each mandate

            # DEBUG EXIT: Show all position states once per cycle
            import os
            if os.environ.get('DEBUG_EXIT') or True:
                open_positions = []
                for sym in snapshot.symbols_active:
                    pos = self.executor.state_machine.get_position(sym)
                    if pos and pos.state.name != 'FLAT':
                        open_positions.append(f"{sym}:{pos.state.name}")
                if open_positions:
                    print(f"[EXIT_DEBUG] Open positions this cycle: {', '.join(open_positions)}")

            for symbol in snapshot.symbols_active:
                try:
                    # Query position state from executor (per MANDATE EMISSION RULES.md Line 29)
                    position = self.executor.state_machine.get_position(symbol)
                    position_state = position.state if position else None

                    # Extract active primitives BEFORE generating mandates
                    active_primitives = self._extract_active_primitive_names(symbol, snapshot)

                    # Invoke PolicyAdapter for this symbol
                    mandates = self.policy_adapter.generate_mandates(
                        observation_snapshot=snapshot,
                        symbol=symbol,
                        timestamp=timestamp
                    )
                    if mandates:
                        print(f"✓ MANDATE GENERATED: {symbol} - {len(mandates)} mandate(s)")
                        for m in mandates:
                            print(f"  Type: {m.type.name}, Authority: {m.authority}")
                            # Track primitives for this mandate
                            mandate_primitives_map[id(m)] = active_primitives
                    all_mandates.extend(mandates)
                except Exception as e:
                    # CRITICAL: Don't silently swallow exceptions - log and continue
                    self._logger.debug(f"Policy generation exception for {symbol}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue to next symbol

            if all_mandates:
                print(f"🎯 CYCLE {cycle_id}: {len(all_mandates)} TOTAL MANDATES from {len(set(m.symbol for m in all_mandates))} symbols")

            # Arbitrate conflicts (resolve to single action per symbol or HOLD)
            actions_by_symbol = self.arbitrator.arbitrate_all(all_mandates)

            # Execute actions
            mark_prices = self._mark_prices  # Pass current mark prices
            cycle_stats = self.executor.process_cycle(
                mandates=all_mandates,
                account=self._account,
                mark_prices=mark_prices,
                cycle_id=cycle_id
            )
            
            # Log mandates and arbitration (linked to cycle)
            if hasattr(self, '_execution_db') and cycle_id is not None:
                # Log mandates
                for mandate in all_mandates:
                    try:
                        self._execution_db.log_mandate(
                            cycle_id=cycle_id,
                            symbol=mandate.symbol,
                            mandate_type=mandate.type.value,
                            authority=mandate.authority,
                            timestamp=mandate.timestamp
                        )
                    except:
                        pass

                # Log policy outcomes (mandate -> primitives linkage)
                for mandate in all_mandates:
                    try:
                        active_primitives = mandate_primitives_map.get(id(mandate), [])

                        # Determine executed action from arbitration
                        executed_action = None
                        if mandate.symbol in actions_by_symbol:
                            action = actions_by_symbol[mandate.symbol]
                            if action:
                                executed_action = action.action_type.value

                        self._execution_db.log_policy_outcome(
                            cycle_id=cycle_id,
                            symbol=mandate.symbol,
                            timestamp=timestamp,
                            mandate_type=mandate.type.value,
                            authority=mandate.authority,
                            policy_name=mandate.policy_name if hasattr(mandate, 'policy_name') else None,
                            active_primitives=active_primitives,
                            executed_action=executed_action,
                            execution_success=None,  # Will be updated when ghost trade completes
                            rejection_reason=None
                        )
                    except Exception as e:
                        # Don't fail cycle if outcome logging fails
                        pass

                # Log arbitration (symbol-level)
                arbitrated = {}
                for mandate in all_mandates:
                    if mandate.symbol not in arbitrated:
                        arbitrated[mandate.symbol] = []
                    arbitrated[mandate.symbol].append(mandate)
                
                for symbol, symbol_mandates in arbitrated.items():
                    if len(symbol_mandates) > 1:  # Conflict
                        try:
                            # Determine winner
                            winner = max(symbol_mandates, key=lambda m: m.authority)
                            self._execution_db.log_arbitration_round(
                                cycle_id=cycle_id,
                                symbol=symbol,
                                mandate_count=len(symbol_mandates),
                                conflicting_mandates=str([m.type.value for m in symbol_mandates]),
                                winning_mandate_type=winner.type.value,
                                resolution_reason=f"Authority: {winner.authority}"
                            )
                        except:
                            pass

        except Exception as e:
            # Log but don't halt system
            self._logger.debug(f"M6 execution cycle exception: {e}")
            pass

    def _process_ghost_trades(self):
        """Process ghost trades based on new execution results.

        Checks execution log for new successful ENTRY/EXIT actions
        and executes corresponding ghost trades.
        """
        try:
            execution_log = self.executor.get_execution_log()

            # Process new execution results since last check
            new_results = execution_log[self._last_execution_index:]

            for result in new_results:
                # Only process successful actions for symbols in TOP_10
                if not result.success or result.symbol not in TOP_10_SYMBOLS:
                    continue

                # Get cycle context from result (captured at execution time)
                cycle_id = result.cycle_id if hasattr(result, 'cycle_id') else None
                snapshot = self._latest_snapshot

                # Extract active primitives for this symbol
                active_primitives = None
                policy_name = None

                if snapshot and result.symbol in snapshot.primitives:
                    bundle = snapshot.primitives[result.symbol]
                    active_primitives = []

                    # List all non-None primitives
                    if bundle.zone_penetration is not None:
                        active_primitives.append("zone_penetration")
                    if bundle.displacement_origin_anchor is not None:
                        active_primitives.append("displacement_origin_anchor")
                    if bundle.price_traversal_velocity is not None:
                        active_primitives.append("price_traversal_velocity")
                    if bundle.traversal_compactness is not None:
                        active_primitives.append("traversal_compactness")
                    if bundle.price_acceptance_ratio is not None:
                        active_primitives.append("price_acceptance_ratio")
                    if bundle.central_tendency_deviation is not None:
                        active_primitives.append("central_tendency_deviation")
                    if bundle.structural_absence_duration is not None:
                        active_primitives.append("structural_absence_duration")
                    if bundle.structural_persistence_duration is not None:
                        active_primitives.append("structural_persistence_duration")
                    if bundle.traversal_void_span is not None:
                        active_primitives.append("traversal_void_span")
                    if bundle.event_non_occurrence_counter is not None:
                        active_primitives.append("event_non_occurrence_counter")
                    if bundle.resting_size is not None:
                        active_primitives.append("resting_size")
                    if bundle.order_consumption is not None:
                        active_primitives.append("order_consumption")
                    if bundle.absorption_event is not None:
                        active_primitives.append("absorption_event")
                    if bundle.refill_event is not None:
                        active_primitives.append("refill_event")
                    if bundle.liquidation_density is not None:
                        active_primitives.append("liquidation_density")
                    if bundle.directional_continuity is not None:
                        active_primitives.append("directional_continuity")
                    if bundle.trade_burst is not None:
                        active_primitives.append("trade_burst")

                # Try to extract policy name from result (if available)
                if hasattr(result.action, 'strategy_id') and result.action.strategy_id:
                    policy_name = result.action.strategy_id

                # Handle ENTRY actions
                if result.action.name == "ENTRY":
                    # Query position state machine to get actual direction
                    # (executor hardcodes LONG for now, but this will work when direction is added to mandates)
                    position = self.executor.state_machine.get_position(result.symbol)
                    side = "LONG" if position.direction and position.direction.value == "LONG" else "SHORT"

                    success, error, trade = self.ghost_tracker.open_position(
                        symbol=result.symbol,
                        side=side,
                        cycle_id=cycle_id,
                        policy_name=policy_name,
                        active_primitives=active_primitives
                    )

                    if success and trade:
                        print(f"GHOST: ENTRY {result.symbol} {side} {trade.quantity:.4f} @ ${trade.price:,.2f} [{len(active_primitives or [])} primitives]")
                    else:
                        print(f"GHOST: ENTRY_REJECTED {result.symbol} - {error}")

                        # Log rejection
                        if snapshot:
                            self.ghost_tracker.log_rejection(
                                cycle_id=cycle_id or 0,
                                timestamp=result.timestamp,
                                symbol=result.symbol,
                                attempted_action="ENTRY",
                                attempted_side=side,
                                rejection_reason=error,
                                policy_name=policy_name,
                                triggering_primitives=active_primitives
                            )

                # Handle EXIT actions
                elif result.action.name == "EXIT":
                    if self.ghost_tracker.has_open_position(result.symbol):
                        success, error, trade = self.ghost_tracker.close_position(
                            symbol=result.symbol,
                            cycle_id=cycle_id,
                            exit_reason="MANDATE_EXIT"
                        )

                        if success and trade:
                            print(f"GHOST: EXIT {result.symbol} {trade.quantity:.4f} @ ${trade.price:,.2f}, PNL: ${trade.pnl:+.2f}, Hold: {trade.holding_duration_sec:.0f}s")
                        else:
                            print(f"GHOST: EXIT_REJECTED {result.symbol} - {error}")

                # Handle REDUCE actions (partial close)
                elif result.action.name == "REDUCE":
                    if self.ghost_tracker.has_open_position(result.symbol):
                        # Reduce by 50% for now (in full implementation, use actual quantity)
                        position = self.ghost_tracker.get_open_position(result.symbol)
                        if position:
                            reduce_qty = position.quantity * 0.5

                            success, error, trade = self.ghost_tracker.close_position(
                                symbol=result.symbol,
                                quantity=reduce_qty,
                                cycle_id=cycle_id,
                                exit_reason="PARTIAL_REDUCE"
                            )

                            if success and trade:
                                print(f"GHOST: REDUCE {result.symbol} {trade.quantity:.4f} @ ${trade.price:,.2f}, PNL: ${trade.pnl:+.2f}")

            # Update last processed index
            self._last_execution_index = len(execution_log)

        except Exception as e:
            # self._logger.debug(f"Ghost trade processing: {e}")
            pass

    def _extract_active_primitive_names(self, symbol: str, snapshot: ObservationSnapshot) -> List[str]:
        """Extract names of non-None primitives for a symbol.

        Args:
            symbol: Symbol to extract primitives for
            snapshot: Current observation snapshot

        Returns:
            List of primitive names that are non-None
        """
        if symbol not in snapshot.primitives:
            return []

        bundle = snapshot.primitives[symbol]
        active_primitives = []

        # Check each primitive field and add name if not None
        primitive_fields = [
            ('zone_penetration', bundle.zone_penetration),
            ('displacement_origin_anchor', bundle.displacement_origin_anchor),
            ('price_traversal_velocity', bundle.price_traversal_velocity),
            ('traversal_compactness', bundle.traversal_compactness),
            ('central_tendency_deviation', bundle.central_tendency_deviation),
            ('structural_absence_duration', bundle.structural_absence_duration),
            ('traversal_void_span', bundle.traversal_void_span),
            ('event_non_occurrence_counter', bundle.event_non_occurrence_counter),
            ('structural_persistence_duration', bundle.structural_persistence_duration),
            ('resting_size', bundle.resting_size),
            ('order_consumption', bundle.order_consumption),
            ('absorption_event', bundle.absorption_event),
            ('refill_event', bundle.refill_event),
            ('price_acceptance_ratio', bundle.price_acceptance_ratio),
            ('liquidation_density', bundle.liquidation_density),
            ('directional_continuity', bundle.directional_continuity),
            ('trade_burst', bundle.trade_burst),
        ]

        for name, value in primitive_fields:
            if value is not None:
                active_primitives.append(name)

        return active_primitives

    def _log_cycle_to_db(self, snapshot: ObservationSnapshot, mandates: list, timestamp: float) -> int:
        """Log comprehensive execution cycle data to research database.
        
        Args:
            snapshot: Current observation snapshot
            mandates: List of mandates generated this cycle
            timestamp: Cycle timestamp
            
        Returns:
            cycle_id for linking related records
        """
        try:
            # Get M2 metrics
            m2_metrics = self._obs._m2_store.get_metrics()
            
            # Calculate primitive counts
            primitives_computing = 0
            for bundle in snapshot.primitives.values():
                if bundle.zone_penetration is not None: primitives_computing += 1
                if bundle.displacement_origin_anchor is not None: primitives_computing += 1
                if bundle.price_traversal_velocity is not None: primitives_computing += 1
                if bundle.traversal_compactness is not None: primitives_computing += 1
                if bundle.price_acceptance_ratio is not None: primitives_computing += 1
                if bundle.central_tendency_deviation is not None: primitives_computing += 1
                if bundle.structural_absence_duration is not None: primitives_computing += 1
                if bundle.structural_persistence_duration is not None: primitives_computing += 1
                if bundle.traversal_void_span is not None: primitives_computing += 1
                if bundle.event_non_occurrence_counter is not None: primitives_computing += 1
                if bundle.resting_size is not None: primitives_computing += 1
                if bundle.order_consumption is not None: primitives_computing += 1
                if bundle.absorption_event is not None: primitives_computing += 1
                if bundle.refill_event is not None: primitives_computing += 1
                if bundle.liquidation_density is not None: primitives_computing += 1
                if bundle.directional_continuity is not None: primitives_computing += 1
                if bundle.trade_burst is not None: primitives_computing += 1
            
            # Log core execution cycle
            cycle_id = self._execution_db.log_cycle(
                timestamp=timestamp,
                observation_status=snapshot.status.name,
                m2_metrics=m2_metrics,
                symbols_active=list(snapshot.symbols_active),
                primitives_computing=primitives_computing,
                primitives_total=len(snapshot.primitives) * 17
            )
            
            # Log M2 node snapshots (capture ALL nodes for research, not just active)
            all_nodes = []
            
            # Get all node types
            if hasattr(self._obs._m2_store, 'get_all_nodes'):
                all_nodes = self._obs._m2_store.get_all_nodes()
            else:
                # Fallback: try to get nodes from different states
                active = self._obs._m2_store.get_active_nodes()
                all_nodes.extend(active)
                
                # Try to get dormant/archived if methods exist
                if hasattr(self._obs._m2_store, '_dormant_nodes'):
                    all_nodes.extend(self._obs._m2_store._dormant_nodes.values())
                if hasattr(self._obs._m2_store, '_archived_nodes'):
                    all_nodes.extend(self._obs._m2_store._archived_nodes.values())
            
            if all_nodes:
                node_dicts = []
                for node in all_nodes:
                    node_dict = {
                        'id': node.id,
                        'symbol': node.symbol,
                        'side': node.side if hasattr(node, 'side') else None,
                        'price_center': node.price_center,
                        'price_band': node.price_band,
                        'active': node.active if hasattr(node, 'active') else True,
                        'strength': node.strength,
                        'confidence': node.confidence if hasattr(node, 'confidence') else 1.0,
                        'decay_rate': node.decay_rate if hasattr(node, 'decay_rate') else 0.0,
                        'first_seen_ts': node.first_seen_ts if hasattr(node, 'first_seen_ts') else timestamp,
                        'last_interaction_ts': node.last_interaction_ts if hasattr(node, 'last_interaction_ts') else timestamp,
                        'age_seconds': timestamp - (node.first_seen_ts if hasattr(node, 'first_seen_ts') else timestamp),
                        'liquidation_count': node.liquidation_count if hasattr(node, 'liquidation_count') else 0,
                        'trade_execution_count': node.trade_execution_count if hasattr(node, 'trade_execution_count') else 0,
                        'creation_reason': node.creation_reason if hasattr(node, 'creation_reason') else 'unknown',
                        'presence_intervals': node.presence_intervals if hasattr(node, 'presence_intervals') else []
                    }
                    node_dicts.append(node_dict)
                
                self._execution_db.log_m2_nodes(cycle_id, node_dicts)
            
            # Log full primitive values
            # Primitives can be floats OR dataclasses - use generic approach
            primitives_by_symbol = {}
            for symbol, bundle in snapshot.primitives.items():
                primitives = {}
                
                # Generic extraction helper
                def extract_value(primitive):
                    """Extract numeric value from primitive (float or dataclass)."""
                    if primitive is None:
                        return None
                    if isinstance(primitive, (int, float)):
                        return float(primitive)
                    # It's a dataclass - try common attribute names
                    for attr in ['value', 'ratio', 'depth', 'density', 'duration', 'continuity_score', 
                                 'acceptance_ratio', 'total_duration_seconds', 'total_persistence_duration']:
                        if hasattr(primitive, attr):
                            val = getattr(primitive, attr)
                            if isinstance(val, (int, float)):
                                return float(val)
                    # Fallback: return first numeric attribute found
                    for attr_name in dir(primitive):
                        if not attr_name.startswith('_'):
                            try:
                                val = getattr(primitive, attr_name)
                                if isinstance(val, (int, float)):
                                    return float(val)
                            except:
                                pass
                    return None
                
                # Extract values safely
                primitives['zone_penetration_depth'] = extract_value(bundle.zone_penetration)
                primitives['displacement_anchor_dwell_time'] = extract_value(bundle.displacement_origin_anchor)
                primitives['price_velocity'] = extract_value(bundle.price_traversal_velocity)
                primitives['traversal_compactness'] = extract_value(bundle.traversal_compactness)
                primitives['central_tendency_deviation'] = extract_value(bundle.central_tendency_deviation)
                primitives['absence_duration'] = extract_value(bundle.structural_absence_duration)
                primitives['liquidation_density'] = extract_value(bundle.liquidation_density)
                
                # Special cases with multiple values
                if bundle.price_acceptance_ratio is not None:
                    primitives['acceptance_ratio'] = extract_value(bundle.price_acceptance_ratio)
                    if hasattr(bundle.price_acceptance_ratio, 'accepted_range'):
                        primitives['acceptance_accepted_range'] = float(bundle.price_acceptance_ratio.accepted_range)
                    if hasattr(bundle.price_acceptance_ratio, 'rejected_range'):
                        primitives['acceptance_rejected_range'] = float(bundle.price_acceptance_ratio.rejected_range)
                
                if bundle.structural_persistence_duration is not None:
                    primitives['persistence_duration'] = extract_value(bundle.structural_persistence_duration)
                    if hasattr(bundle.structural_persistence_duration, 'persistence_ratio'):
                        primitives['persistence_presence_pct'] = float(bundle.structural_persistence_duration.persistence_ratio) * 100
               
                primitives['directional_continuity_value'] = extract_value(bundle.directional_continuity)
                primitives['resting_size_bid'] = extract_value(bundle.resting_size)
                primitives['order_consumption_size'] = extract_value(bundle.order_consumption)
                primitives['absorption_event'] = bundle.absorption_event is not None
                primitives['refill_event'] = bundle.refill_event is not None
                
                primitives_by_symbol[symbol] = primitives
            
            self._execution_db.log_primitive_values(cycle_id, primitives_by_symbol)

            return cycle_id

        except Exception as e:
            self._logger.debug(f"DB logging exception: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _run_binance_stream(self):
        """Connect to Binance Filtered Stream."""
        import websockets
        
        streams = [
            f"{s.lower()}@aggTrade" for s in TOP_10_SYMBOLS
        ] + [
            f"{s.lower()}@forceOrder" for s in TOP_10_SYMBOLS
        ] + [
            f"{s.lower()}@depth@100ms" for s in TOP_10_SYMBOLS
        ] + [
            f"{s.lower()}@kline_1m" for s in TOP_10_SYMBOLS
        ]
        
        stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
        
        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    import websockets
                    async with websockets.connect(stream_url) as ws:
                        print("Connected to Binance Stream")
                        while self._running:
                            try:
                                msg = await ws.recv()
                                data = json.loads(msg)
                                stream = data['stream']
                                payload = data['data']
                                
                                # Parse Symbol & Type
                                symbol = stream.split('@')[0].upper()
                                event_type = "UNKNOWN"

                                if 'aggTrade' in stream:
                                    event_type = "TRADE"
                                    # Track mark price from trades
                                    if 'p' in payload:
                                        self._mark_prices[symbol] = Decimal(str(payload['p']))
                                    # Log trade event for ground truth validation
                                    try:
                                        self._execution_db.log_trade_event(
                                            symbol=symbol,
                                            timestamp=int(payload.get('T', 0)) / 1000.0 if 'T' in payload else time.time(),
                                            price=float(payload.get('p', 0)),
                                            volume=float(payload.get('q', 0)),
                                            is_buyer_maker=payload.get('m', False)
                                        )
                                    except:
                                        pass
                                elif 'forceOrder' in stream:
                                    event_type = "LIQUIDATION"
                                    print(f"DEBUG STREAM: Received forceOrder for {symbol}")
                                    # Log raw liquidation event
                                    if 'o' in payload:
                                        order = payload['o']
                                        try:
                                            self._execution_db.log_liquidation_event(
                                                timestamp=ts if 'ts' in locals() else time.time(),
                                                symbol=order.get('s', symbol),
                                                side=order.get('S', 'UNKNOWN'),
                                                price=float(order.get('p', 0)),
                                                volume=float(order.get('q', 0))
                                            )
                                        except Exception as e:
                                            pass
                                elif 'kline' in stream:
                                    event_type = "KLINE"
                                    # Log OHLC candle
                                    if 'k' in payload:
                                        k = payload['k']
                                        if k.get('x', False):  # Only closed candles
                                            try:
                                                self._execution_db.log_ohlc_candle(
                                                    symbol=symbol,
                                                    timestamp=int(k['t']) / 1000.0,
                                                    open_price=float(k['o']),
                                                    high=float(k['h']),
                                                    low=float(k['l']),
                                                    close=float(k['c']),
                                                    volume=float(k.get('v', 0)),
                                                    trade_count=int(k.get('n', 0))
                                                )
                                            except:
                                                pass
                                elif 'depth' in stream:
                                    event_type = "DEPTH"

                                # TIMESTAMP EXTRACTION
                                ts = time.time()
                                if 'T' in payload:
                                    ts = int(payload['T']) / 1000.0
                                elif 'E' in payload:
                                    ts = int(payload['E']) / 1000.0

                                # Update authoritative system clock
                                if self._last_stream_time is None or ts > self._last_stream_time:
                                    self._last_stream_time = ts

                                # INGEST                                
                                if event_type == "LIQUIDATION":
                                    print(f"DEBUG INGEST: {symbol} LIQUIDATION detected. TS={ts}")
                                    
                                self._obs.ingest_observation(ts, symbol, event_type, payload)
                                
                            except Exception as e:
                                print(f"Processing Error: {e}")
                                await asyncio.sleep(1)
                                
                except Exception as e:
                    print(f"Connection Failed: {e}. Retrying in 5s...")
                    await asyncio.sleep(5)


    def get_execution_log(self):
        """Get execution trace from controller.

        Returns:
            List of execution records
        """
        return self.executor.get_execution_log()

    async def stop(self):
        self._running = False


async def main():
    """Main entry point for collector service."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize Observation System with ground truth validation
    obs_system = ObservationSystem(allowed_symbols=TOP_10_SYMBOLS)
    
    # Create and start collector
    collector = CollectorService(obs_system)
    
    print(f"[COLLECTOR] Starting with {len(TOP_10_SYMBOLS)} symbols: {TOP_10_SYMBOLS}")
    print("[COLLECTOR] Connecting to Binance Futures WebSocket...")
    print("[COLLECTOR] M6 Execution Pipeline: ACTIVE")
    
    try:
        await collector.start()
    except KeyboardInterrupt:
        print("\n[COLLECTOR] Shutdown requested...")
        await collector.stop()
        print("[COLLECTOR] Stopped.")


if __name__ == "__main__":
    # Fix for Windows event loop policy (aiodns requires SelectorEventLoop)
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
