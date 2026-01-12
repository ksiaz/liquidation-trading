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

# Constants
TOP_10_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
    "TRXUSDT", "DOTUSDT"
]

class CollectorService:
    def __init__(self, observation_system: ObservationSystem):
        self._obs = observation_system
        self._running = False
        self._logger = logging.getLogger("CollectorService")
        
        # Initialize execution database for logging FIRST
        self._execution_db = ResearchDatabase(db_path="logs/execution.db")
        
        # Inject event logger into observation system's M2 store
        if not hasattr(self._obs._m2_store, '_event_logger') or self._obs._m2_store._event_logger is None:
            self._obs._m2_store._event_logger = self._execution_db

        # Phase 8: M6 Integration
        self.policy_adapter = PolicyAdapter(AdapterConfig(), execution_db=self._execution_db)
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
        
    async def start(self):
        """Start all collectors."""
        self._running = True
        
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
            current_time = time.time()
            try:
                # 1. Advance System Time
                self._obs.advance_time(current_time)

                # 2. Query Observation Snapshot
                snapshot = self._obs.query({'type': 'snapshot'})

                # 3. M6 Execution Cycle (only if observation is ACTIVE)
                if snapshot.status == ObservationStatus.ACTIVE:
                    self._execute_m6_cycle(snapshot, current_time)

            except Exception as e:
                # Fail silently per constitutional rules - log but don't halt
                self._logger.debug(f"Clock/Execution cycle error: {e}")
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
            # Log execution cycle FIRST to establish context
            cycle_id = None
            if hasattr(self, '_execution_db'):
                cycle_id = self._log_cycle_to_db(snapshot, [], timestamp)
                # print(f"DEBUG M6: Started cycle {cycle_id} for {len(snapshot.symbols_active)} symbols")

            # Collect mandates from all active symbols
            all_mandates = []

            for symbol in snapshot.symbols_active:
                # Invoke PolicyAdapter for this symbol
                mandates = self.policy_adapter.generate_mandates(
                    observation_snapshot=snapshot,
                    symbol=symbol,
                    timestamp=timestamp,
                    cycle_id=cycle_id
                )
                all_mandates.extend(mandates)

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
            self._logger.debug(f"M6 execution cycle error: {e}")
            pass
    
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
            self._logger.debug(f"DB logging error: {e}")
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
                                elif 'forceOrder' in stream:
                                    event_type = "LIQUIDATION"
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

                                # INGEST
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
    
    # Initialize Observation System
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
