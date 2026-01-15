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

# Import Regime Classification (Phase 5)
from runtime.regime import RegimeState, RegimeMetrics, classify_regime
from runtime.indicators import VWAPCalculator, MultiTimeframeATR
from runtime.orderflow import MultiWindowOrderflow
from runtime.liquidations import LiquidationZScoreCalculator

# Constants
TOP_10_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
    "TRXUSDT", "DOTUSDT"
]

class CollectorService:
    def __init__(self, observation_system: ObservationSystem, warmup_duration_sec: int = 5):
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
        self.policy_adapter = PolicyAdapter(AdapterConfig(
            enable_geometry=True,        # TESTING: Enable for immediate mandate generation (no regime needed)
            enable_kinematics=False,     # OLD: Baseline kinematics strategy (replaced by EFFCS)
            enable_absence=False,        # Absence primitives not implemented
            enable_orderbook_test=False,  # Test policy (disabled)
            # Phase 5: Enable regime-gated strategies
            enable_slbrs=True,           # NEW: SLBRS strategy (SIDEWAYS regime)
            enable_effcs=True            # NEW: EFFCS strategy (EXPANSION regime)
        ))
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

        # Phase 5: Regime Classification Infrastructure
        # Initialize regime metric calculators (per-symbol tracking)
        self._vwap_calculators: Dict[str, VWAPCalculator] = {}
        self._atr_calculators: Dict[str, MultiTimeframeATR] = {}
        self._orderflow_calculators: Dict[str, MultiWindowOrderflow] = {}
        self._liquidation_calculators: Dict[str, LiquidationZScoreCalculator] = {}

        # Track current prices for regime calculation
        self._current_prices: Dict[str, float] = {}

        # Track regime state per symbol
        self._regime_states: Dict[str, RegimeState] = {}

        # Track regime metrics per symbol (Phase 5)
        self._regime_metrics: Dict[str, RegimeMetrics] = {}

        # Track previous regime state for transition logging (Phase 6)
        self._prev_regime_states: Dict[str, RegimeState] = {}
        
    async def start(self):
        """Start all collectors."""
        self._running = True
        # Don't set _startup_time here - will be set on first stream data
        # self._startup_time = time.time()  # REMOVED: causes clock skew with Binance time

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
            # Set startup time on first call using stream timestamp
            if self._startup_time is None:
                self._startup_time = timestamp

            # Check warm-up period - skip mandate generation if still warming up
            elapsed = timestamp - self._startup_time
            if elapsed < self._warmup_duration_sec:
                # Still in warm-up - allow observation layer to build state
                print(f"DEBUG M6: Still in warmup - {elapsed:.1f}s / {self._warmup_duration_sec}s")
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

            # Phase 5: Compute regime metrics and classify regime for each symbol
            for symbol in snapshot.symbols_active:
                try:
                    # Get current price
                    price = self._current_prices.get(symbol)
                    if price is None:
                        continue  # No price data yet

                    # Get calculators
                    vwap_calc = self._vwap_calculators.get(symbol)
                    atr_calc = self._atr_calculators.get(symbol)
                    orderflow_calc = self._orderflow_calculators.get(symbol)
                    liquidation_calc = self._liquidation_calculators.get(symbol)

                    if not all([vwap_calc, atr_calc, orderflow_calc, liquidation_calc]):
                        print(f"DEBUG Regime: {symbol} - Calculators not ready: VWAP={vwap_calc is not None}, ATR={atr_calc is not None}, Orderflow={orderflow_calc is not None}, Liq={liquidation_calc is not None}")
                        continue  # Calculators not initialized yet

                    # Compute regime metrics
                    vwap_distance = vwap_calc.get_distance(price)
                    atr_5m = atr_calc.get_atr_5m()
                    atr_30m = atr_calc.get_atr_30m()
                    orderflow_imbalance = orderflow_calc.get_imbalance_30s()
                    liquidation_zscore = liquidation_calc.get_zscore(timestamp)

                    # Check if all metrics available
                    if None in [vwap_distance, atr_5m, atr_30m, orderflow_imbalance, liquidation_zscore]:
                        print(f"DEBUG Regime: {symbol} - Metrics not ready: VWAP_dist={vwap_distance}, ATR_5m={atr_5m}, ATR_30m={atr_30m}, OFI={orderflow_imbalance}, Liq_Z={liquidation_zscore}")
                        continue  # Metrics not ready yet

                    # Create regime metrics object
                    print(f"DEBUG Regime: {symbol} - Metrics ready! VWAP_dist={vwap_distance:.2f}, ATR_5m={atr_5m:.2f}, ATR_30m={atr_30m:.2f}, OFI={orderflow_imbalance:.3f}, Liq_Z={liquidation_zscore:.2f}")
                    regime_metrics = RegimeMetrics(
                        vwap_distance=vwap_distance,
                        atr_5m=atr_5m,
                        atr_30m=atr_30m,
                        orderflow_imbalance=orderflow_imbalance,
                        liquidation_zscore=liquidation_zscore
                    )

                    # Classify regime
                    regime_state = classify_regime(regime_metrics)
                    print(f"DEBUG Regime: {symbol} - Regime classified as {regime_state.name}")

                    # Phase 6: Log regime transitions
                    prev_regime = self._prev_regime_states.get(symbol)
                    if prev_regime is not None and prev_regime != regime_state:
                        # Regime transition detected
                        self._logger.info(
                            f"Regime transition: {symbol} {prev_regime.name} → {regime_state.name} "
                            f"(VWAP dist={vwap_distance:.1f}, ATR 5m/30m={atr_5m:.1f}/{atr_30m:.1f}, "
                            f"orderflow={orderflow_imbalance:.3f}, liq_z={liquidation_zscore:.2f})"
                        )

                    # Store regime state and metrics for this symbol
                    self._regime_states[symbol] = regime_state
                    self._regime_metrics[symbol] = regime_metrics
                    self._prev_regime_states[symbol] = regime_state

                except Exception as e:
                    # Don't fail cycle if regime classification fails
                    self._logger.debug(f"Regime classification error for {symbol}: {e}")
                    continue

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

                    # Get regime state and metrics for this symbol (Phase 5)
                    regime_state = self._regime_states.get(symbol)
                    regime_metrics = self._regime_metrics.get(symbol)
                    current_price = self._current_prices.get(symbol)

                    # Phase 6: Log which strategy will evaluate
                    if regime_state is not None:
                        active_strategy = "None (DISABLED)"
                        if regime_state.name == "SIDEWAYS_ACTIVE" and self.policy_adapter.config.enable_slbrs:
                            active_strategy = "SLBRS"
                        elif regime_state.name == "EXPANSION_ACTIVE" and self.policy_adapter.config.enable_effcs:
                            active_strategy = "EFFCS"

                        self._logger.debug(
                            f"Strategy evaluation: {symbol} regime={regime_state.name} → {active_strategy}"
                        )

                    # Invoke PolicyAdapter for this symbol
                    mandates = self.policy_adapter.generate_mandates(
                        observation_snapshot=snapshot,
                        symbol=symbol,
                        timestamp=timestamp,
                        position_state=position_state,
                        regime_state=regime_state,  # Phase 5: Pass regime state
                        regime_metrics=regime_metrics,  # Phase 5: Pass regime metrics
                        current_price=current_price  # Phase 5: Pass current price
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
                mark_prices=mark_prices
            )
            
            # Log mandates and arbitration (linked to cycle)
            if hasattr(self, '_execution_db') and cycle_id is not None:
                # Log mandates
                for mandate in all_mandates:
                    try:
                        self._execution_db.log_mandate(
                            cycle_id=cycle_id,
                            symbol=mandate.symbol,
                            mandate_type=mandate.type.name,
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
                                executed_action = action.action_type.name

                        self._execution_db.log_policy_outcome(
                            cycle_id=cycle_id,
                            symbol=mandate.symbol,
                            timestamp=timestamp,
                            mandate_type=mandate.type.name,
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
                                conflicting_mandates=str([m.type.name for m in symbol_mandates]),
                                winning_mandate_type=winner.type.name,
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
        print(f"DEBUG: _process_ghost_trades called")
        try:
            execution_log = self.executor.get_execution_log()
            print(f"DEBUG: execution_log has {len(execution_log)} entries")

            # Process new execution results since last check
            new_results = execution_log[self._last_execution_index:]
            print(f"DEBUG: Processing {len(new_results)} new results (last_index={self._last_execution_index})")

            for idx, result in enumerate(new_results):
                print(f"DEBUG: Processing result {idx}: action={result.action.name}, symbol={result.symbol}, success={result.success}")
                # Only process successful actions for symbols in TOP_10
                if not result.success or result.symbol not in TOP_10_SYMBOLS:
                    print(f"DEBUG: Skipping result {idx}: not successful or not in TOP_10_SYMBOLS")
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
                    print(f"DEBUG: Processing ENTRY action for {result.symbol}")

                    # Query position state machine to get actual direction
                    # (executor hardcodes LONG for now, but this will work when direction is added to mandates)
                    # Default to LONG if position doesn't exist or has no direction
                    side = "LONG"
                    print(f"DEBUG: Initialized side = {side}")

                    try:
                        position = self.executor.state_machine.get_position(result.symbol)
                        print(f"DEBUG: Got position = {position}")
                        if position and hasattr(position, 'direction') and position.direction:
                            side = position.direction.value if hasattr(position.direction, 'value') else str(position.direction)
                            print(f"DEBUG: Updated side from position = {side}")
                    except Exception as e:
                        print(f"DEBUG: Exception getting position direction: {e}")
                        # Use default LONG if anything fails
                        pass

                    print(f"DEBUG: Final side value before open_position = {side}")
                    print(f"DEBUG: About to call ghost_tracker.open_position with side={side}")

                    success, error, trade = self.ghost_tracker.open_position(
                        symbol=result.symbol,
                        side=side,
                        cycle_id=cycle_id,
                        policy_name=policy_name,
                        active_primitives=active_primitives
                    )

                    print(f"DEBUG: open_position returned: success={success}, error={error}")

                    if success and trade:
                        print(f"DEBUG: About to print GHOST ENTRY with side={side}")
                        print(f"GHOST: ENTRY {result.symbol} {side} {trade.quantity:.4f} @ ${trade.price:,.2f} [{len(active_primitives or [])} primitives]")
                    else:
                        print(f"GHOST: ENTRY_REJECTED {result.symbol} - {error}")

                        # Log rejection
                        if snapshot:
                            print(f"DEBUG: About to log_rejection with side={side}")
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
                            print(f"DEBUG: log_rejection completed")

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
            print(f"ERROR in ghost trade processing: {e}")
            import traceback
            traceback.print_exc()  # Print full traceback for debugging

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
            
            # Phase 6: Collect regime data for logging (use first symbol with regime data)
            regime_state_for_log = None
            regime_metrics_for_log = None

            for symbol in snapshot.symbols_active:
                if symbol in self._regime_states and symbol in self._regime_metrics:
                    regime_state_for_log = self._regime_states[symbol].name
                    metrics = self._regime_metrics[symbol]
                    regime_metrics_for_log = {
                        'vwap': self._vwap_calculators[symbol].get_vwap() if symbol in self._vwap_calculators else None,
                        'atr_5m': metrics.atr_5m,
                        'atr_30m': metrics.atr_30m,
                        'orderflow_imbalance': metrics.orderflow_imbalance,
                        'liquidation_zscore': metrics.liquidation_zscore
                    }
                    break  # Use first symbol's regime data

            # Log core execution cycle
            cycle_id = self._execution_db.log_cycle(
                timestamp=timestamp,
                observation_status=snapshot.status.name,
                m2_metrics=m2_metrics,
                symbols_active=list(snapshot.symbols_active),
                primitives_computing=primitives_computing,
                primitives_total=len(snapshot.primitives) * 17,
                regime_state=regime_state_for_log,
                regime_metrics=regime_metrics_for_log
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

                # Generic extraction helper for other primitives
                def extract_value(primitive):
                    """Extract numeric value from primitive (float or dataclass)."""
                    if primitive is None:
                        return None
                    if isinstance(primitive, (int, float)):
                        return float(primitive)
                    # For dataclass objects, try common attribute names
                    for attr in ['velocity', 'value', 'ratio', 'depth', 'density', 'duration',
                                 'continuity_score', 'acceptance_ratio', 'total_duration_seconds',
                                 'total_persistence_duration', 'dwell_time', 'size', 'rate']:
                        if hasattr(primitive, attr):
                            val = getattr(primitive, attr)
                            if isinstance(val, (int, float)):
                                return float(val)
                    # Fallback: return first numeric attribute found
                    for attr_name in dir(primitive):
                        if not attr_name.startswith('_') and not callable(getattr(primitive, attr_name)):
                            try:
                                val = getattr(primitive, attr_name)
                                if isinstance(val, (int, float)):
                                    return float(val)
                            except:
                                pass
                    return None

                # Extract core primitives using direct attribute access with error handling
                try:
                    pen = bundle.zone_penetration.penetration_depth if bundle.zone_penetration else None
                except (AttributeError, TypeError):
                    pen = None

                try:
                    comp = bundle.traversal_compactness.compactness_ratio if bundle.traversal_compactness else None
                except (AttributeError, TypeError):
                    comp = None

                try:
                    dev = bundle.central_tendency_deviation.deviation_value if bundle.central_tendency_deviation else None
                except (AttributeError, TypeError):
                    dev = None

                primitives['zone_penetration_depth'] = pen
                primitives['displacement_anchor_dwell_time'] = extract_value(bundle.displacement_origin_anchor)
                primitives['price_velocity'] = extract_value(bundle.price_traversal_velocity)
                primitives['traversal_compactness'] = comp
                primitives['central_tendency_deviation'] = dev

                # Structural absence/persistence
                if bundle.structural_absence_duration is not None:
                    primitives['absence_duration'] = getattr(bundle.structural_absence_duration, 'absence_duration', None)
                else:
                    primitives['absence_duration'] = None

                primitives['liquidation_density'] = extract_value(bundle.liquidation_density)

                # Traversal void span - extract max_void_duration
                if bundle.traversal_void_span is not None:
                    primitives['void_span_max'] = getattr(bundle.traversal_void_span, 'max_void_duration', None)
                else:
                    primitives['void_span_max'] = None

                # Event non-occurrence counter
                if bundle.event_non_occurrence_counter is not None:
                    primitives['event_non_occurrence_count'] = getattr(bundle.event_non_occurrence_counter, 'non_occurrence_count', None)
                else:
                    primitives['event_non_occurrence_count'] = None

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

                # Trade burst - extract trade_count
                if bundle.trade_burst is not None:
                    primitives['trade_burst_count'] = getattr(bundle.trade_burst, 'trade_count', None)
                else:
                    primitives['trade_burst_count'] = None

                # Order book primitives - extract bid/ask separately
                if bundle.resting_size is not None:
                    primitives['resting_size_bid'] = getattr(bundle.resting_size, 'bid_size', None)
                    primitives['resting_size_ask'] = getattr(bundle.resting_size, 'ask_size', None)
                else:
                    primitives['resting_size_bid'] = None
                    primitives['resting_size_ask'] = None

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
        """Connect to Binance Filtered Stream with exponential backoff reconnection."""
        import websockets

        # Reduce stream count to avoid Windows socket limits (test with fewer symbols)
        test_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # Start with 3 symbols instead of 10

        streams = [
            f"{s.lower()}@aggTrade" for s in test_symbols
        ] + [
            f"{s.lower()}@forceOrder" for s in test_symbols
        ] + [
            f"{s.lower()}@bookTicker" for s in test_symbols
        ] + [
            f"{s.lower()}@depth20@100ms" for s in test_symbols
        ] + [
            f"{s.lower()}@markPrice@1s" for s in test_symbols
        ]  # 5 streams per symbol = 15 streams for 3 symbols

        stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        # Exponential backoff parameters
        reconnect_delay = 1  # Start with 1 second
        max_reconnect_delay = 60  # Cap at 60 seconds

        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    import websockets
                    # Binance Futures WebSocket keepalive requirements:
                    # - Server sends ping every 3 minutes
                    # - Must respond with pong within 10 minutes or disconnect
                    # Configure client to send ping every 60s and wait up to 300s for pong
                    async with websockets.connect(
                        stream_url,
                        ping_interval=60,    # Send ping every 60 seconds
                        ping_timeout=300,    # Wait up to 5 minutes for pong
                        close_timeout=10     # Clean connection close timeout
                    ) as ws:
                        print("Connected to Binance Stream")
                        reconnect_delay = 1  # Reset backoff on successful connection
                        while self._running:
                            try:
                                msg = await ws.recv()
                                data = json.loads(msg)
                                stream = data['stream']
                                payload = data['data']

                                # Parse Symbol & Type
                                symbol = stream.split('@')[0].upper()
                                event_type = "UNKNOWN"

                                # DEBUG: Log what stream we received
                                print(f"DEBUG STREAM: Received stream='{stream}', symbol={symbol}")

                                if 'aggtrade' in stream.lower():
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

                                    # Phase 5: Update regime calculators with trade data
                                    try:
                                        price = float(payload.get('p', 0))
                                        volume = float(payload.get('q', 0))
                                        timestamp = int(payload.get('T', 0)) / 1000.0 if 'T' in payload else time.time()
                                        is_buyer_maker = payload.get('m', False)

                                        # Initialize calculators for symbol if needed
                                        if symbol not in self._vwap_calculators:
                                            self._vwap_calculators[symbol] = VWAPCalculator()
                                        if symbol not in self._atr_calculators:
                                            # Use period=3 for testing (needs 15min for 5m, 90min for 30m instead of 70min/7hrs)
                                            self._atr_calculators[symbol] = MultiTimeframeATR(period=3)
                                        if symbol not in self._orderflow_calculators:
                                            self._orderflow_calculators[symbol] = MultiWindowOrderflow()
                                        if symbol not in self._liquidation_calculators:
                                            self._liquidation_calculators[symbol] = LiquidationZScoreCalculator()

                                        # Update VWAP
                                        self._vwap_calculators[symbol].update(price, volume, timestamp)

                                        # Update ATR
                                        self._atr_calculators[symbol].update_trade(price, timestamp)

                                        # Update orderflow imbalance
                                        self._orderflow_calculators[symbol].update(is_buyer_maker, volume, timestamp)

                                        # Track current price
                                        self._current_prices[symbol] = price
                                    except:
                                        pass
                                elif 'forceorder' in stream.lower():
                                    event_type = "LIQUIDATION"
                                    print(f"DEBUG STREAM: Received forceOrder for {symbol}")
                                    # Log raw liquidation event
                                    if 'o' in payload:
                                        order = payload['o']
                                        try:
                                            print(f"DEBUG: About to log liquidation event")
                                            print(f"DEBUG: order dict = {order}")
                                            side_value = order.get('S', 'UNKNOWN')
                                            print(f"DEBUG: side_value = {side_value}")

                                            self._execution_db.log_liquidation_event(
                                                timestamp=ts if 'ts' in locals() else time.time(),
                                                symbol=order.get('s', symbol),
                                                side=side_value,
                                                price=float(order.get('p', 0)),
                                                volume=float(order.get('q', 0))
                                            )
                                            print(f"DEBUG: Liquidation event logged successfully")
                                        except Exception as e:
                                            print(f"ERROR logging liquidation: {e}")
                                            import traceback
                                            traceback.print_exc()

                                    # Phase 5: Update liquidation Z-score calculator
                                    try:
                                        if 'o' in payload:
                                            order = payload['o']
                                            quantity = float(order.get('q', 0))
                                            timestamp = ts if 'ts' in locals() else time.time()

                                            # Initialize calculator for symbol if needed
                                            if symbol not in self._liquidation_calculators:
                                                self._liquidation_calculators[symbol] = LiquidationZScoreCalculator()

                                            # Update liquidation Z-score
                                            self._liquidation_calculators[symbol].update(quantity, timestamp)
                                    except:
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
                                elif 'bookticker' in stream.lower():
                                    event_type = "DEPTH"
                                    # Log order book update for ground truth validation
                                    try:
                                        if 'b' in payload and 'B' in payload and 'a' in payload and 'A' in payload:
                                            ts_orderbook = int(payload.get('T', 0)) / 1000.0 if payload.get('T') else time.time()
                                            self._execution_db.log_orderbook_event(
                                                symbol=symbol,
                                                timestamp=ts_orderbook,
                                                best_bid_price=float(payload['b']),
                                                best_bid_qty=float(payload['B']),
                                                best_ask_price=float(payload['a']),
                                                best_ask_qty=float(payload['A'])
                                            )
                                    except:
                                        pass
                                elif 'depth20' in stream.lower():
                                    event_type = "DEPTH_L2"
                                    # Log L2 orderbook depth (20 levels)
                                    try:
                                        ts_depth = int(payload.get('T', 0)) / 1000.0 if payload.get('T') else time.time()
                                        bids = payload.get('b', [])
                                        asks = payload.get('a', [])
                                        if bids or asks:
                                            self._execution_db.log_orderbook_depth(
                                                symbol=symbol,
                                                timestamp=ts_depth,
                                                bids=bids,
                                                asks=asks
                                            )
                                            # Update mark price from mid if available
                                            if bids and asks:
                                                mid = (float(bids[0][0]) + float(asks[0][0])) / 2
                                                self._mark_prices[symbol] = Decimal(str(mid))
                                    except:
                                        pass
                                elif 'markprice' in stream.lower():
                                    event_type = "MARK_PRICE"
                                    # Log official mark price with funding info
                                    try:
                                        ts_mark = int(payload.get('E', 0)) / 1000.0 if payload.get('E') else time.time()
                                        mark_price = float(payload.get('p', 0))
                                        if mark_price > 0:
                                            self._execution_db.log_mark_price(
                                                symbol=symbol,
                                                timestamp=ts_mark,
                                                mark_price=mark_price,
                                                index_price=float(payload.get('i', 0)) if payload.get('i') else None,
                                                funding_rate=float(payload.get('r', 0)) if payload.get('r') else None,
                                                next_funding_time=float(payload.get('T', 0)) / 1000.0 if payload.get('T') else None
                                            )
                                            # Update authoritative mark price
                                            self._mark_prices[symbol] = Decimal(str(mark_price))
                                    except:
                                        pass

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
                                import traceback
                                traceback.print_exc()  # Print full stack trace
                                await asyncio.sleep(1)

                except Exception as e:
                    print(f"Connection Failed: {e}. Retrying in {reconnect_delay}s...")
                    import traceback
                    traceback.print_exc()  # Print full traceback
                    await asyncio.sleep(reconnect_delay)
                    # Exponential backoff: double the delay, capped at max
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)


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
