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
from typing import List, Dict, Callable, Optional
from collections import deque
from decimal import Decimal
# Import sealed Observation System
from observation.governance import ObservationSystem
from observation.types import ObservationSnapshot, ObservationStatus

# Import M6 components (Phase 8)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState
from runtime.logging.execution_db import ResearchDatabase
from runtime.logging.buffered_db import BufferedResearchDatabase

# Import Ghost Tracker
from execution.ep4_ghost_tracker import GhostPositionTracker
from execution.ep4_ghost_adapter import NormalizedOrderbook
import os

# Import Regime Classification (Phase 5)
from runtime.regime import RegimeState, RegimeMetrics, classify_regime
from runtime.indicators import VWAPCalculator, MultiTimeframeATR
from runtime.orderflow import MultiWindowOrderflow
from runtime.liquidations import LiquidationZScoreCalculator, LiquidationBurstAggregator, LiquidationBurst

# Import Hyperliquid Integration
try:
    from runtime.hyperliquid.collector import HyperliquidCollector, HyperliquidCollectorConfig
    from runtime.hyperliquid.whale_wallets import get_wallet_addresses
    HYPERLIQUID_AVAILABLE = True
except ImportError:
    HYPERLIQUID_AVAILABLE = False

# Import Node Adapter Integration (out-of-process gRPC adapter)
# See docs/NODE_ADAPTER_REDESIGN.md for architecture plan.
try:
    from runtime.node_client import NodeBridge, create_node_bridge, SyncStatusCode
    NODE_ADAPTER_AVAILABLE = True
except ImportError:
    NODE_ADAPTER_AVAILABLE = False

# Import Cascade Sniper types for absorption analysis
from external_policy.ep2_strategy_cascade_sniper import AbsorptionAnalysis, ProximityData

# Import geometry strategy restore function for position state recovery
from external_policy.ep2_strategy_geometry import restore_entry_context_from_positions

# Phase E: StabilityObserver attachment (passive, read-only)
from runtime.stability_observer import stability_observer

# Import Binance Client for ATR warm-up
from runtime.binance.client import BinanceClient

# Import Validation modules for data integrity and manipulation detection
from runtime.validation import (
    DataValidator,
    ManipulationDetector,
    StopHuntDetector,
    LiquidityType
)

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
        # Wrap with buffered wrapper to prevent synchronous SQLite commits from blocking event loop
        # Performance fix: 0.2 cycles/s -> 5 cycles/s (25x improvement)
        _raw_db = ResearchDatabase(db_path="logs/execution.db")
        self._execution_db = BufferedResearchDatabase(
            db=_raw_db,
            flush_interval_sec=1.0,  # Batch commits every 1 second
            max_buffer_size=1000,    # Force flush if buffer exceeds 1000 writes
            enable_high_frequency_logs=False  # Skip trade/orderbook logging by default
        )
        
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
            enable_effcs=True,           # NEW: EFFCS strategy (EXPANSION regime)
            # Phase 6: Cascade Sniper (Hyperliquid proximity)
            enable_cascade_sniper=True,  # NEW: Cascade sniper (liquidation proximity)
            cascade_sniper_entry_mode="CASCADE_MOMENTUM"  # Aggressive: ride the cascade
        ))
        self.arbitrator = MandateArbitrator()
        # Fix: Enable position persistence to survive restarts
        # Without this, EXIT signals never trigger (position state lost on restart)
        self.executor = ExecutionController(RiskConfig(), db_path="logs/positions.db")

        # Restore strategy state from persisted positions
        # This enables EXIT signals for positions opened in previous sessions
        self._restore_strategy_state()

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

        # Memory guard: track last calculator activity for pruning
        self._calculator_last_activity: Dict[str, float] = {}
        self._calculator_max_symbols = 500  # Limit symbols tracked
        self._calculator_inactive_sec = 600.0  # Prune after 10 min inactive
        self._calculators_pruned = 0

        # Phase 6: Liquidation burst aggregator (for cascade sniper)
        self._liquidation_burst_aggregator = LiquidationBurstAggregator(
            window_seconds=10.0,  # 10-second window
            max_events=1000
        )

        # Track current prices for regime calculation
        self._current_prices: Dict[str, float] = {}

        # Track regime state per symbol
        self._regime_states: Dict[str, RegimeState] = {}

        # Track regime metrics per symbol (Phase 5)
        self._regime_metrics: Dict[str, RegimeMetrics] = {}

        # Track previous regime state for transition logging (Phase 6)
        self._prev_regime_states: Dict[str, RegimeState] = {}

        # Hyperliquid Integration (optional)
        # Two modes: Node Adapter (direct node access) or WebSocket Collector
        # Set USE_HL_NODE=true to use node adapter (requires local hl-node running)
        self._hyperliquid_collector = None
        self._hyperliquid_enabled = False
        self._node_integration = None
        self._node_bridge = None
        self._node_psm = None
        self._use_node_mode = os.environ.get("USE_HL_NODE", "false").lower() == "true"

        if self._use_node_mode and NODE_ADAPTER_AVAILABLE:
            # Node Adapter Mode: gRPC client to out-of-process adapter
            # Provides: real-time prices and liquidations from hl-node
            # Requires: hl-adapter/server.py running on localhost:50051
            try:
                adapter_address = os.environ.get("HL_ADAPTER_ADDRESS", "localhost:50051")
                self._logger.info(f"Initializing Hyperliquid node bridge to {adapter_address}...")

                # Derive focus_symbols from TOP_10_SYMBOLS (strip USDT suffix)
                # This ensures gRPC subscription matches trading symbols
                focus_symbols = [s.replace('USDT', '') for s in TOP_10_SYMBOLS]

                self._node_bridge = create_node_bridge(
                    observation_system=self._obs,
                    address=adapter_address,
                    symbols=focus_symbols,
                )

                # Note: Bridge.start() is called in run() to ensure proper async context
                self._hyperliquid_enabled = True
                self._logger.info(f"Hyperliquid node bridge configured for {len(focus_symbols)} symbols")

            except Exception as e:
                self._logger.warning(f"Node bridge init failed: {e}, falling back to WebSocket mode")
                self._use_node_mode = False

        # Initialize HyperliquidCollector for proximity data (whale position tracking)
        # Node mode: gRPC adapter handles prices/liquidations/fills, API handles proximity
        # Non-node mode: API handles everything
        if HYPERLIQUID_AVAILABLE:
            try:
                # Load whale wallet addresses from registry
                whale_addresses = get_wallet_addresses()
                self._logger.info(f"Loading {len(whale_addresses)} whale wallets for tracking")

                # Check if indexer should be enabled via environment variable
                # Default to True to enable blockchain indexer
                enable_indexer = os.environ.get("ENABLE_HL_INDEXER", "true").lower() == "true"

                self._logger.info(f"Indexer enabled: {enable_indexer}")

                hl_config = HyperliquidCollectorConfig(
                    use_testnet=False,
                    proximity_threshold=0.30,  # 30% threshold (whales keep safe distances)
                    min_position_value=100.0,  # Lower to $100 to catch more positions
                    wallet_poll_interval=5.0,
                    track_hlp_vault=True,  # Track liquidator vault
                    additional_wallets=whale_addresses,  # Load known whale wallets
                    enable_dynamic_discovery=True,  # Discover wallets from large trades
                    discovery_min_trade_value=5_000.0,  # Lower to $5k to discover more wallets
                    trade_discovery_interval=60.0,  # Scan every 60s instead of 15min
                    # Blockchain indexer (requires: pip install boto3 lz4 msgpack)
                    enable_indexer=enable_indexer,
                    indexer_lookback_blocks=500_000,  # ~7 days
                    indexer_db_path="indexed_wallets.db",
                    indexer_checkpoint_path="indexer_checkpoint.json"
                )
                self._hyperliquid_collector = HyperliquidCollector(
                    db=self._execution_db,
                    config=hl_config
                )
                self._hyperliquid_enabled = True
                self._logger.info("Hyperliquid WebSocket collector initialized")
            except Exception as e:
                self._logger.warning(f"Hyperliquid collector init failed: {e}")

        # Phase 7: Validation and Manipulation Detection
        self._data_validator = DataValidator()
        self._manipulation_detector = ManipulationDetector()
        self._stop_hunt_detector = StopHuntDetector()
        self._logger.info("Validation and manipulation detection initialized")

        # Diagnostic logging configuration (P1: now opt-in via env)
        self._diag_enabled = os.environ.get('ENABLE_DIAG', '').lower() == 'true'
        self._diag_coins = TOP_10_SYMBOLS  # All symbols for diagnostics
        self._diag_interval = 5  # Log diagnostics every N cycles
        self._diag_cycle_count = 0

    def _restore_strategy_state(self):
        """Restore strategy state from persisted positions.

        Called on startup to reconstruct internal strategy state from the position
        database. This enables EXIT signals to trigger for positions that were
        opened in previous sessions.

        Without this, the geometry strategy's internal tracking (_entry_zone_context,
        _entry_method) would be empty on restart, causing:
        - All positions to appear FLAT to strategies
        - ENTRY signals generated for already-open positions
        - EXIT signals never triggering (no recorded entry to exit from)
        """
        try:
            # Get all non-FLAT positions from state machine
            open_positions = []
            for symbol in TOP_10_SYMBOLS:
                position = self.executor.state_machine.get_position(symbol)
                if position and position.state.name != 'FLAT':
                    open_positions.append({
                        "symbol": symbol,
                        "direction": position.direction.value if position.direction else "LONG",
                        "entry_price": float(position.entry_price) if position.entry_price else 0,
                        "state": position.state.name
                    })

            if open_positions:
                self._logger.info(f"Restoring strategy state for {len(open_positions)} open positions")
                restore_entry_context_from_positions(open_positions)
            else:
                self._logger.debug("No open positions to restore")

        except Exception as e:
            self._logger.warning(f"Failed to restore strategy state: {e}")

    def prune_stale_calculators(self, max_age_sec: float = None) -> int:
        """
        Remove calculators for symbols inactive longer than threshold.

        Memory guard to prevent unbounded calculator growth.

        Args:
            max_age_sec: Maximum age in seconds. If None, uses default.

        Returns:
            Number of symbols pruned.
        """
        if max_age_sec is None:
            max_age_sec = self._calculator_inactive_sec

        now = time.time()
        cutoff = now - max_age_sec
        to_remove = []

        for symbol, last_time in self._calculator_last_activity.items():
            if last_time < cutoff:
                to_remove.append(symbol)

        for symbol in to_remove:
            self._vwap_calculators.pop(symbol, None)
            self._atr_calculators.pop(symbol, None)
            self._orderflow_calculators.pop(symbol, None)
            self._liquidation_calculators.pop(symbol, None)
            self._calculator_last_activity.pop(symbol, None)
            self._current_prices.pop(symbol, None)
            self._regime_states.pop(symbol, None)
            self._regime_metrics.pop(symbol, None)
            self._prev_regime_states.pop(symbol, None)
            self._calculators_pruned += 1

        if to_remove:
            self._logger.debug(f"Pruned {len(to_remove)} stale calculators")

        return len(to_remove)

    def get_calculator_metrics(self) -> dict:
        """Get calculator memory metrics."""
        return {
            'symbols_tracked': len(self._vwap_calculators),
            'max_symbols': self._calculator_max_symbols,
            'calculators_pruned': self._calculators_pruned,
            'inactive_threshold_sec': self._calculator_inactive_sec,
        }

    def get_database_metrics(self) -> dict:
        """Get database buffer metrics."""
        if hasattr(self._execution_db, 'get_stats'):
            return self._execution_db.get_stats()
        return {}

    async def _recover_position_contexts(self):
        """Recover position contexts from database on startup.

        Enables EXIT signals to fire for positions opened in previous sessions.
        """
        try:
            # Get repository from executor's state machine
            repository = getattr(self.executor.state_machine, '_repository', None)
            if not repository:
                self._logger.debug("No position repository configured, skipping context recovery")
                return

            # Load open positions
            open_positions = repository.load_open_positions()
            if not open_positions:
                self._logger.info("No open positions to recover")
                return

            self._logger.info(f"Recovering context for {len(open_positions)} open positions")

            # Load entry contexts for each position
            persisted_contexts = {}
            for symbol in open_positions:
                ctx = repository.get_entry_context(symbol)
                if ctx:
                    persisted_contexts[symbol] = ctx
                    self._logger.info(f"  {symbol}: restored entry context (strategy={ctx.get('entry_method', 'unknown')})")

            # Restore geometry strategy context
            from external_policy.ep2_strategy_geometry import restore_entry_context_from_positions

            # Convert positions to list format expected by restore function
            positions_list = [
                {
                    "symbol": pos.symbol,
                    "direction": pos.direction.value if pos.direction else None,
                    "entry_price": float(pos.entry_price) if pos.entry_price else 0,
                    "state": pos.state.value
                }
                for pos in open_positions.values()
            ]

            restore_entry_context_from_positions(positions_list, persisted_contexts)
            self._logger.info(f"Strategy contexts restored for {len(positions_list)} positions")

        except Exception as e:
            self._logger.warning(f"Position context recovery failed: {e}")

    async def _warm_up_atr_calculators(self, symbols: List[str]):
        """Pre-warm ATR calculators with historical klines.

        Fetches 5m klines from Binance asynchronously to initialize ATR calculators,
        avoiding the 90-minute warm-up delay for regime classification.

        Args:
            symbols: List of symbols to warm up (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        try:
            import asyncio
            client = BinanceClient()
            warmup_count = 0

            # Fetch all klines concurrently
            tasks = [client.get_klines_async(symbol, interval='5m', limit=30) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for symbol, klines_5m in zip(symbols, results):
                if isinstance(klines_5m, Exception):
                    self._logger.warning(f"[ATR-WARMUP] {symbol}: Failed to fetch - {klines_5m}")
                    continue

                if klines_5m and len(klines_5m) >= 6:
                    # Initialize ATR calculator for this symbol
                    if symbol not in self._atr_calculators:
                        self._atr_calculators[symbol] = MultiTimeframeATR(period=3)

                    # Warm up from historical data
                    self._atr_calculators[symbol].warm_up_from_klines(klines_5m)
                    warmup_count += 1

                    # Check if ATR is now available
                    atr_5m = self._atr_calculators[symbol].get_atr_5m()
                    atr_30m = self._atr_calculators[symbol].get_atr_30m()

                    if atr_5m and atr_30m:
                        self._logger.info(
                            f"[ATR-WARMUP] {symbol}: ATR_5m={atr_5m:.2f}, ATR_30m={atr_30m:.2f} (ready)"
                        )
                    else:
                        self._logger.warning(
                            f"[ATR-WARMUP] {symbol}: Insufficient klines ({len(klines_5m)})"
                        )
                else:
                    self._logger.warning(f"[ATR-WARMUP] {symbol}: No klines fetched")

            self._logger.info(f"[ATR-WARMUP] Warmed up {warmup_count}/{len(symbols)} symbols")

        except Exception as e:
            self._logger.warning(f"[ATR-WARMUP] Failed: {e}")

    async def start(self):
        """Start all collectors."""
        self._running = True
        # Don't set _startup_time here - will be set on first stream data
        # self._startup_time = time.time()  # REMOVED: causes clock skew with Binance time

        # 0a. Recover persisted positions and strategy contexts (for restart recovery)
        await self._recover_position_contexts()

        # self._logger.info(f"Warmup period duration: {self._warmup_duration_sec}s from startup")

        # 0. Pre-warm ATR calculators with historical data (async - non-blocking)
        # This avoids 90-minute warm-up delay for regime classification
        self._logger.info("[ATR-WARMUP] Fetching historical klines for ATR initialization...")
        await self._warm_up_atr_calculators(TOP_10_SYMBOLS)

        # 1. Start Clock Driver (Heartbeat)
        asyncio.create_task(self._drive_clock())

        # 2. Start Binance WebSocket FIRST (before heavy node I/O to avoid timeout)
        # Binance WebSocket handshake is sensitive to event loop blocking
        binance_task = asyncio.create_task(self._run_binance_stream())

        # Give Binance time to connect before starting heavy I/O
        await asyncio.sleep(2.0)

        # 3. Start Hyperliquid Integration (Node Adapter or WebSocket Collector)
        if self._hyperliquid_enabled:
            if self._use_node_mode and self._node_bridge:
                # Node Adapter Mode (gRPC to out-of-process adapter)
                try:
                    if self._node_bridge.start():
                        self._logger.info("Node bridge started (streaming prices/liquidations/fills via gRPC)")

                        # Wire HL fills to VWAP, ATR, and Orderflow calculators
                        # This enables regime classification from HL data alone
                        self._node_bridge.on_organic_fill(self._handle_hl_fill)
                        self._logger.info("HL fill callback registered (VWAP + ATR + Orderflow)")

                        # Wire HL liquidations to zscore calculator and burst aggregator
                        # This ensures liq_z and burst_vol reflect HL liquidations in node mode
                        self._node_bridge.on_hl_liquidation(self._handle_hl_liquidation)
                        self._logger.info("HL liquidation callback registered (zscore + burst aggregator)")

                        # Check initial status
                        status = self._node_bridge.get_status()
                        if status:
                            self._logger.info(
                                f"Node adapter status: {status.status.name}, "
                                f"block={status.latest_block_height}, "
                                f"prices={status.prices_emitted}, liqs={status.liquidations_emitted}"
                            )
                    else:
                        self._logger.warning("Node bridge failed to connect, falling back to WebSocket mode")
                        self._use_node_mode = False
                except Exception as e:
                    self._logger.warning(f"Node bridge start failed: {e}")

            # Start WebSocket collector for proximity data (whale position tracking)
            # In node mode: gRPC handles prices/liqs/fills, WebSocket handles proximity
            # In non-node mode: WebSocket handles everything
            if self._hyperliquid_collector:
                try:
                    asyncio.create_task(self._hyperliquid_collector.start())
                    self._logger.info("Hyperliquid WebSocket collector started (proximity tracking)")

                    # Wire up Hyperliquid collector to observation system
                    # This enables M4 cascade primitives to be computed from HL data
                    self._obs.set_hyperliquid_source(self._hyperliquid_collector)
                    self._logger.info("Hyperliquid collector wired to observation system")
                except Exception as e:
                    self._logger.warning(f"Hyperliquid collector start failed: {e}")

        # Wait for Binance task (it runs forever, reconnecting as needed)
        await binance_task

    async def _drive_clock(self):
        """Push Wall Clock time to System every 1s and drive M6 execution cycle.

        CPU Optimization (2026-01-28): Reduced from 10Hz to 5Hz.
        - 200ms cycle provides good balance of responsiveness and CPU usage
        """
        self._logger.info("[CLOCK] Drive clock loop started")
        while self._running:
            # Simple clock source selection:
            # - Node mode: use wall clock (node is synced, data is flowing)
            # - WebSocket mode: use Binance stream time
            if self._use_node_mode:
                current_time = time.time()
            elif self._last_stream_time is not None:
                current_time = self._last_stream_time
            else:
                # Wait for first Binance stream event
                await asyncio.sleep(0.5)
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

            await asyncio.sleep(0.2)  # 5Hz cycle (was 0.1s / 10Hz)

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
            # DIAG: Track why regime classification fails
            _diag_regime = os.environ.get('DIAG_MANDATE', '').lower() in ('1', 'true', 'yes')

            # Get HL node prices as primary source
            # Uses M1's latest_hl_prices cache populated by NodeBridge
            node_prices = self._obs.get_all_hl_prices()

            # Debug: Show HL prices available (first 3 cycles only)
            if _diag_regime and cycle_id and cycle_id <= 3:
                print(f"[HL_DEBUG] cycle={cycle_id} node_prices has {len(node_prices)} symbols: {list(node_prices.keys())[:5]}", flush=True)

            for symbol in snapshot.symbols_active:
                try:
                    # Get current price - prefer HL node, fallback to Binance
                    # Convert symbol format: BTCUSDT -> BTC for HL node
                    hl_symbol = symbol.replace('USDT', '')
                    price = node_prices.get(hl_symbol) or self._current_prices.get(symbol)
                    if price is None:
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            print(f"[REGIME] {symbol}: SKIP - no price", flush=True)
                        continue  # No price data yet

                    # Log when HL oracle price is used (activation proof)
                    # Log first 5 cycles then every 50th to reduce noise
                    if _diag_regime and node_prices.get(hl_symbol) and cycle_id and (cycle_id <= 5 or cycle_id % 50 == 1):
                        print(f"[HL_PRICE] {symbol}: using oracle price {price:.2f} from HL node", flush=True)

                    # Get calculators
                    vwap_calc = self._vwap_calculators.get(symbol)
                    atr_calc = self._atr_calculators.get(symbol)
                    orderflow_calc = self._orderflow_calculators.get(symbol)
                    liquidation_calc = self._liquidation_calculators.get(symbol)

                    if not all([vwap_calc, atr_calc, orderflow_calc, liquidation_calc]):
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            # DATA SOURCE CONTRACT: VWAP, ATR, Orderflow require Binance trades
                            # See runtime/DATA_SOURCE_CONTRACT.py for authority map
                            missing = []
                            if not vwap_calc: missing.append("VWAP (Binance trades required)")
                            if not atr_calc: missing.append("ATR (Binance OHLC required)")
                            if not orderflow_calc: missing.append("Orderflow (Binance direction required)")
                            if not liquidation_calc: missing.append("Liquidation Z-score")
                            print(f"[REGIME] {symbol}: SKIP - Binance-required data missing: {missing}", flush=True)
                        continue  # Binance data not available for this symbol

                    # Compute regime metrics
                    vwap_distance = vwap_calc.get_distance(price)
                    atr_5m = atr_calc.get_atr_5m()
                    atr_30m = atr_calc.get_atr_30m()
                    orderflow_imbalance = orderflow_calc.get_imbalance_30s()
                    liquidation_zscore = liquidation_calc.get_zscore(timestamp)

                    # Check if all metrics available
                    # DATA SOURCE CONTRACT: All metrics except liq_z require Binance trade flow
                    if None in [vwap_distance, atr_5m, atr_30m, orderflow_imbalance, liquidation_zscore]:
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            missing = []
                            if vwap_distance is None: missing.append("VWAP (Binance)")
                            if atr_5m is None: missing.append("ATR_5m (Binance)")
                            if atr_30m is None: missing.append("ATR_30m (Binance warm-up)")
                            if orderflow_imbalance is None: missing.append("Orderflow (Binance)")
                            if liquidation_zscore is None: missing.append("Liq_Z (HL or Binance)")
                            print(f"[REGIME] {symbol}: SKIP - calculator warm-up incomplete: {missing}", flush=True)
                        continue  # Binance calculator warm-up not complete

                    # Create regime metrics object
                    regime_metrics = RegimeMetrics(
                        vwap_distance=vwap_distance,
                        atr_5m=atr_5m,
                        atr_30m=atr_30m,
                        orderflow_imbalance=orderflow_imbalance,
                        liquidation_zscore=liquidation_zscore
                    )

                    # Classify regime
                    regime_state = classify_regime(regime_metrics)

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

            # DIAG: Print cycle summary when DIAG_MANDATE is set
            if os.environ.get('DIAG_MANDATE') and cycle_id and cycle_id % 5 == 0:
                print(f"[DIAG] Cycle {cycle_id}: {len(snapshot.symbols_active)} syms, "
                      f"{len(self._regime_states)} regimes classified", flush=True)

            # DEBUG EXIT: Show all position states once per cycle (P1: gated by env)
            if os.environ.get('DEBUG_EXIT'):
                open_positions = []
                for sym in snapshot.symbols_active:
                    pos = self.executor.state_machine.get_position(sym)
                    if pos and pos.state.name != 'FLAT':
                        open_positions.append(f"{sym}:{pos.state.name}")
                if open_positions:
                    self._logger.debug(f"Open positions: {', '.join(open_positions)}")

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

                    # Phase 6: Get Hyperliquid proximity data (convert symbol to coin)
                    # BTCUSDT -> BTC, ETHUSDT -> ETH
                    hl_proximity = None
                    absorption = None
                    coin = symbol.replace('USDT', '')

                    # Try node mode first (has more complete data)
                    # Note: NodeBridge doesn't have proximity provider (requires ObservationBridge)
                    if self._use_node_mode and self._node_bridge and hasattr(self._node_bridge, 'get_proximity_provider'):
                        proximity_provider = self._node_bridge.get_proximity_provider()
                        if proximity_provider:
                            hl_proximity = proximity_provider.get_proximity(coin)

                    # Fallback to WebSocket collector if no node data
                    if hl_proximity is None and self._hyperliquid_enabled and self._hyperliquid_collector:
                        hl_proximity = self._hyperliquid_collector.get_proximity(coin)

                        # Phase 6: Compute absorption analysis from orderbook + proximity
                        absorption = self._compute_absorption(coin, hl_proximity)

                        # Comprehensive diagnostic logging for ALL coins
                        if self._diag_enabled and hl_proximity:
                            # Get cascade state from strategy
                            from external_policy.ep2_strategy_cascade_sniper import get_cascade_state
                            cascade_state = get_cascade_state(symbol)

                            # Update stop hunt detector with proximity data
                            stop_hunt = self._stop_hunt_detector.update_cluster(
                                symbol=symbol,
                                current_price=current_price or 0,
                                long_positions_count=hl_proximity.long_positions_count,
                                long_positions_value=hl_proximity.long_positions_value,
                                long_closest_liq=hl_proximity.long_closest_liquidation,
                                short_positions_count=hl_proximity.short_positions_count,
                                short_positions_value=hl_proximity.short_positions_value,
                                short_closest_liq=hl_proximity.short_closest_liquidation,
                                timestamp=timestamp
                            )

                            # Check manipulation on orderbook updates
                            if hasattr(self._hyperliquid_collector, '_client'):
                                orderbook = self._hyperliquid_collector._client.get_orderbook(coin)
                                if orderbook:
                                    manipulation_alert = self._manipulation_detector.update_orderbook(symbol, orderbook)
                                    if manipulation_alert:
                                        print(f"[MANIPULATION] {manipulation_alert}")

                            # Log diagnostic every N cycles
                            self._diag_cycle_count += 1
                            if self._diag_cycle_count % self._diag_interval == 0:
                                print(f"\n[DIAG] {coin}:")
                                print(f"  Proximity: {hl_proximity.total_positions_at_risk} pos, ${hl_proximity.total_value_at_risk:,.0f}")
                                if absorption:
                                    print(f"  Absorption: longs={absorption.absorption_ratio_longs:.2f}x, shorts={absorption.absorption_ratio_shorts:.2f}x")
                                print(f"  State: {cascade_state.value}")

                                # Log stop hunt status
                                if stop_hunt:
                                    print(f"  Cluster: {stop_hunt.direction.value} ${stop_hunt.total_value:,.0f} @ {stop_hunt.cluster_price:.2f}")
                                    print(f"    Type: {stop_hunt.liquidity_type.value} (conf={stop_hunt.confidence:.0%})")

                                # Check for active hunt
                                active_hunt = self._stop_hunt_detector.get_active_hunt(symbol)
                                if active_hunt:
                                    print(f"  HUNT: {active_hunt.phase.value} | Reversal: {active_hunt.reversal_pct:.2f}%")
                                    if active_hunt.suggested_entry:
                                        print(f"    Entry: {active_hunt.suggested_entry} @ {active_hunt.price_current:.2f}")
                                        print(f"    Stop: {active_hunt.stop_loss_price:.2f}, Target: {active_hunt.target_price:.2f}")

                                # Check circuit breaker status
                                if self._manipulation_detector.is_circuit_breaker_active(symbol):
                                    remaining = self._manipulation_detector.get_circuit_breaker_remaining(symbol)
                                    print(f"  ⚠️ CIRCUIT BREAKER ACTIVE: {remaining:.0f}s remaining")

                    # Phase 6: Get liquidation burst data
                    # In node mode, use node bridge's aggregator (fed by node_trades liquidations)
                    # Otherwise, use collector's aggregator (fed by Binance forceOrder stream)
                    # Note: NodeBridge doesn't have get_burst (requires ObservationBridge)
                    liquidation_burst = None
                    if self._use_node_mode and self._node_bridge and hasattr(self._node_bridge, 'get_burst'):
                        node_burst = self._node_bridge.get_burst(symbol)
                        if node_burst:
                            # Convert node burst to policy adapter format
                            liquidation_burst = LiquidationBurst(
                                symbol=node_burst.symbol,
                                total_volume=node_burst.total_volume,
                                long_liquidations=node_burst.long_liquidations,
                                short_liquidations=node_burst.short_liquidations,
                                liquidation_count=node_burst.liquidation_count,
                                window_start=node_burst.window_start,
                                window_end=node_burst.window_end,
                            )
                    else:
                        liquidation_burst = self._liquidation_burst_aggregator.get_burst(symbol, timestamp)

                    # Gate B: Get price returns for trend gate
                    # Convert symbol (BTCUSDT) to coin (BTC) for HL price lookup
                    coin_for_returns = symbol.replace('USDT', '').replace('USD', '')
                    price_returns = self._obs.get_hl_price_returns(coin_for_returns)

                    # Invoke PolicyAdapter for this symbol
                    mandates = self.policy_adapter.generate_mandates(
                        observation_snapshot=snapshot,
                        symbol=symbol,
                        timestamp=timestamp,
                        position_state=position_state,
                        regime_state=regime_state,  # Phase 5: Pass regime state
                        regime_metrics=regime_metrics,  # Phase 5: Pass regime metrics
                        current_price=current_price,  # Phase 5: Pass current price
                        hl_proximity=hl_proximity,  # Phase 6: Hyperliquid proximity
                        liquidation_burst=liquidation_burst,  # Phase 6: Liquidation burst
                        absorption=absorption,  # Phase 6: Order book absorption analysis
                        price_returns=price_returns  # Gate B: Short-term price returns
                    )
                    if mandates:
                        print(f"✓ MANDATE GENERATED: {symbol} - {len(mandates)} mandate(s)")
                        for m in mandates:
                            print(f"  Type: {m.type.name}, Authority: {m.authority}")
                            # Track primitives for this mandate
                            mandate_primitives_map[id(m)] = active_primitives
                            # Phase E: Record mandate for stability observation
                            stability_observer.record_mandate(m)
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

            # Phase E: Record actions for stability observation
            for symbol, action in actions_by_symbol.items():
                stability_observer.record_action(action, symbol)

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

    def _compute_absorption(
        self,
        coin: str,
        proximity: ProximityData
    ) -> AbsorptionAnalysis:
        """
        Compute absorption analysis from orderbook + proximity data.

        Compares orderbook depth vs liquidation value at risk to determine
        if cascade can be absorbed.

        Args:
            coin: Asset symbol (e.g., "BTC")
            proximity: Hyperliquid proximity data

        Returns:
            AbsorptionAnalysis for strategy, or None if data insufficient
        """
        if not self._hyperliquid_collector:
            return None

        # Get orderbook from Hyperliquid client
        orderbook = self._hyperliquid_collector._client.get_orderbook(coin)
        if orderbook is None:
            return None

        mid_price = orderbook.get('mid_price', 0)
        total_bid_depth = orderbook.get('total_bid_depth', 0)
        total_ask_depth = orderbook.get('total_ask_depth', 0)

        # Get liquidation values from proximity data
        long_liq_value = 0.0
        short_liq_value = 0.0
        if proximity:
            long_liq_value = proximity.long_positions_value
            short_liq_value = proximity.short_positions_value

        # Compute absorption ratios
        # Long liquidations sell into bids → bid_depth / long_liq_value
        # Short liquidations buy into asks → ask_depth / short_liq_value
        absorption_ratio_longs = total_bid_depth / long_liq_value if long_liq_value > 0 else float('inf')
        absorption_ratio_shorts = total_ask_depth / short_liq_value if short_liq_value > 0 else float('inf')

        return AbsorptionAnalysis(
            coin=coin,
            mid_price=mid_price,
            bid_depth_2pct=total_bid_depth,
            ask_depth_2pct=total_ask_depth,
            long_liq_value=long_liq_value,
            short_liq_value=short_liq_value,
            absorption_ratio_longs=absorption_ratio_longs,
            absorption_ratio_shorts=absorption_ratio_shorts,
            timestamp=time.time()
        )

    def _handle_hl_fill(
        self,
        symbol: str,      # Coin (e.g., "BTC")
        side: str,        # "B" (buy) or "A" (sell)
        price: float,     # Fill price
        size: float,      # Size in base units
        timestamp: float  # Unix timestamp in seconds
    ):
        """Handle HL fill event - feed to VWAP, ATR, and Orderflow calculators.

        Called by NodeBridge when HL fill events are received.
        Only active when USE_HL_NODE=true.

        Mappings applied:
        - Symbol: coin -> f"{coin}USDT" (e.g., "BTC" -> "BTCUSDT")
        - Side for orderflow: "B" -> is_buyer_maker=False, "A" -> is_buyer_maker=True
          (B = buyer is taker = NOT maker, A = seller is taker = buyer IS maker)
        - Price and size used directly
        """
        try:
            # 1. Symbol normalization: HL emits "BTC", calculators use "BTCUSDT"
            normalized_symbol = f"{symbol}USDT"

            # 2. Memory guard: check symbol limit before adding new
            is_new_symbol = normalized_symbol not in self._vwap_calculators
            if is_new_symbol and len(self._vwap_calculators) >= self._calculator_max_symbols:
                self.prune_stale_calculators()

            # 3. Initialize calculators for symbol if needed
            if normalized_symbol not in self._vwap_calculators:
                self._vwap_calculators[normalized_symbol] = VWAPCalculator()
            if normalized_symbol not in self._atr_calculators:
                self._atr_calculators[normalized_symbol] = MultiTimeframeATR(period=3)
            if normalized_symbol not in self._orderflow_calculators:
                self._orderflow_calculators[normalized_symbol] = MultiWindowOrderflow()
            if normalized_symbol not in self._liquidation_calculators:
                self._liquidation_calculators[normalized_symbol] = LiquidationZScoreCalculator()

            # 4. Track last activity for pruning
            self._calculator_last_activity[normalized_symbol] = timestamp

            # 5. Update VWAP (needs price and volume)
            self._vwap_calculators[normalized_symbol].update(price, size, timestamp)

            # 6. Update ATR (needs price)
            self._atr_calculators[normalized_symbol].update_trade(price, timestamp)

            # 7. Update Orderflow (needs is_buyer_maker and volume)
            # HL side: "B" = buyer is taker (lifted asks) = is_buyer_maker=False
            #          "A" = seller is taker (hit bids) = is_buyer_maker=True
            is_buyer_maker = (side == "A")
            self._orderflow_calculators[normalized_symbol].update(is_buyer_maker, size, timestamp)

            # 8. Track current price
            self._current_prices[normalized_symbol] = price

        except Exception as e:
            # Fail silently per constitutional rules - log but don't halt
            self._logger.debug(f"HL fill callback error: {e}")

    def _handle_hl_liquidation(
        self,
        symbol: str,      # Coin (e.g., "BTC")
        side: str,        # Position side: "LONG" or "SHORT"
        price: float,     # Liquidation price
        size: float,      # Size in base units (e.g., BTC quantity)
        timestamp: float  # Unix timestamp in seconds
    ):
        """Handle HL liquidation event - feed to zscore calculator and burst aggregator.

        Called by NodeBridge when HL liquidation events are received.
        Only active when USE_HL_NODE=true.

        Mappings applied:
        - Symbol: coin -> f"{coin}USDT" (e.g., "BTC" -> "BTCUSDT")
        - Side: LONG -> SELL, SHORT -> BUY (position side -> order side)
        - Quantity: size in base units (same as Binance forceOrder)
        - Timestamp: already in seconds from NodeBridge
        """
        try:
            # 1. Symbol normalization: HL emits "BTC", calculators use "BTCUSDT"
            normalized_symbol = f"{symbol}USDT"

            # 2. Initialize calculator for symbol if needed
            if normalized_symbol not in self._liquidation_calculators:
                self._liquidation_calculators[normalized_symbol] = LiquidationZScoreCalculator()

            # 3. Update liquidation Z-score calculator (uses quantity, not value)
            self._liquidation_calculators[normalized_symbol].update(size, timestamp)

            # 4. Side mapping for burst aggregator: LONG -> SELL, SHORT -> BUY
            # (HL side is position side, aggregator expects order side)
            order_side = 'SELL' if side == 'LONG' else 'BUY'

            # 5. Update liquidation burst aggregator
            self._liquidation_burst_aggregator.add_event(
                timestamp=timestamp,
                symbol=normalized_symbol,
                side=order_side,
                price=price,
                quantity=size
            )

            # 6. Track activity for calculator pruning
            self._calculator_last_activity[normalized_symbol] = timestamp

        except Exception as e:
            # Fail silently per constitutional rules - log but don't halt
            self._logger.debug(f"HL liquidation callback error: {e}")

    def _process_ghost_trades(self):
        """Process ghost trades based on new execution results.

        Checks execution log for new successful ENTRY/EXIT actions
        and executes corresponding ghost trades.
        """
        try:
            execution_log = self.executor.get_execution_log()

            # Process new execution results since last check
            new_results = execution_log[self._last_execution_index:]

            for idx, result in enumerate(new_results):
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
                    # Tier B-6: Cascade observation primitives
                    if bundle.liquidation_cascade_proximity is not None:
                        active_primitives.append("liquidation_cascade_proximity")
                    if bundle.cascade_state is not None:
                        active_primitives.append("cascade_state")
                    if bundle.leverage_concentration_ratio is not None:
                        active_primitives.append("leverage_concentration_ratio")
                    if bundle.open_interest_directional_bias is not None:
                        active_primitives.append("open_interest_directional_bias")

                # Try to extract policy name from result (if available)
                if hasattr(result, 'strategy_id') and result.strategy_id:
                    policy_name = result.strategy_id

                # Handle ENTRY actions
                if result.action.name == "ENTRY":
                    # Query position state machine to get actual direction
                    side = "LONG"
                    try:
                        position = self.executor.state_machine.get_position(result.symbol)
                        if position and hasattr(position, 'direction') and position.direction:
                            side = position.direction.value if hasattr(position.direction, 'value') else str(position.direction)
                    except Exception:
                        pass

                    # Get HL orderbook for execution (falls back to Binance if unavailable)
                    hl_orderbook = self._get_hl_orderbook(result.symbol)

                    success, error, trade = self.ghost_tracker.open_position(
                        symbol=result.symbol,
                        side=side,
                        cycle_id=cycle_id,
                        policy_name=policy_name,
                        active_primitives=active_primitives,
                        orderbook=hl_orderbook
                    )

                    if success and trade:
                        print(f"GHOST: ENTRY {result.symbol} {side} {trade.quantity:.4f} @ ${trade.price:,.2f} [{len(active_primitives or [])} primitives]")
                    else:
                        print(f"GHOST: ENTRY_REJECTED {result.symbol} - {error}")
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
                        # Get HL orderbook for execution (falls back to Binance if unavailable)
                        hl_orderbook = self._get_hl_orderbook(result.symbol)

                        success, error, trade = self.ghost_tracker.close_position(
                            symbol=result.symbol,
                            cycle_id=cycle_id,
                            exit_reason="MANDATE_EXIT",
                            orderbook=hl_orderbook
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

                            # Get HL orderbook for execution (falls back to Binance if unavailable)
                            hl_orderbook = self._get_hl_orderbook(result.symbol)

                            success, error, trade = self.ghost_tracker.close_position(
                                symbol=result.symbol,
                                quantity=reduce_qty,
                                cycle_id=cycle_id,
                                exit_reason="PARTIAL_REDUCE",
                                orderbook=hl_orderbook
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
            # Tier B-6: Cascade observation primitives (from Hyperliquid)
            ('liquidation_cascade_proximity', bundle.liquidation_cascade_proximity),
            ('cascade_state', bundle.cascade_state),
            ('leverage_concentration_ratio', bundle.leverage_concentration_ratio),
            ('open_interest_directional_bias', bundle.open_interest_directional_bias),
        ]

        for name, value in primitive_fields:
            if value is not None:
                active_primitives.append(name)

        return active_primitives

    def _get_hl_orderbook(self, symbol: str) -> Optional[NormalizedOrderbook]:
        """Get normalized orderbook from Hyperliquid for ghost execution.

        Args:
            symbol: Full symbol (e.g., "BTCUSDT")

        Returns:
            NormalizedOrderbook if available, None otherwise (falls back to Binance)
        """
        if not self._hyperliquid_collector:
            return None

        try:
            # Convert symbol format: BTCUSDT -> BTC for HL
            coin = symbol.replace('USDT', '').replace('USD', '')

            # Get cached orderbook from HL WebSocket client
            hl_book = self._hyperliquid_collector._client.get_orderbook(coin)
            if hl_book is None:
                return None

            # Convert to normalized format
            return NormalizedOrderbook.from_hl_book(hl_book, coin)

        except Exception:
            return None  # Fallback to Binance

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
                # Tier B-6: Cascade observation primitives
                if bundle.liquidation_cascade_proximity is not None: primitives_computing += 1
                if bundle.cascade_state is not None: primitives_computing += 1
                if bundle.leverage_concentration_ratio is not None: primitives_computing += 1
                if bundle.open_interest_directional_bias is not None: primitives_computing += 1
            
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
        """Connect to Binance WebSocket with dynamic subscription."""
        import websockets

        # Use all TOP_10_SYMBOLS for full liquidation coverage
        test_symbols = TOP_10_SYMBOLS  # All 10 symbols for cascade detection

        # Build stream list for subscription
        streams = [
            f"{s.lower()}@aggTrade" for s in test_symbols
        ] + [
            f"{s.lower()}@forceOrder" for s in test_symbols
        ] + [
            "!forceOrder@arr"  # Global liquidation stream for ALL symbols
        ] + [
            f"{s.lower()}@bookTicker" for s in test_symbols
        ] + [
            f"{s.lower()}@depth20@100ms" for s in test_symbols
        ] + [
            f"{s.lower()}@markPrice@1s" for s in test_symbols
        ]  # 5 streams per symbol + 1 global liquidation

        # Connect to /stream endpoint for combined format (stream/data wrapper)
        base_url = "wss://fstream.binance.com/stream"

        # Exponential backoff parameters
        # WAF ban is typically 5 minutes - start high to let it expire
        reconnect_delay = 30  # Start with 30 seconds
        max_reconnect_delay = 300  # Cap at 5 minutes

        while self._running:
            try:
                import websockets
                self._logger.info(f"Connecting to Binance WebSocket...")
                async with websockets.connect(
                    base_url,
                    open_timeout=30,     # 30s handshake timeout
                    ping_interval=60,    # Send ping every 60 seconds (Binance sends every 3 min)
                    ping_timeout=30,     # Detect dead connection within 30s
                    close_timeout=10     # Clean connection close timeout
                ) as ws:
                    self._logger.info("Connected to Binance, subscribing to streams...")

                    # Subscribe to streams in batches (max 10 messages/sec)
                    # Send all streams in one SUBSCRIBE message (allowed up to 1024)
                    subscribe_msg = {
                        "method": "SUBSCRIBE",
                        "params": streams,
                        "id": 1
                    }
                    await ws.send(json.dumps(subscribe_msg))

                    # Wait for subscription confirmation
                    response = await asyncio.wait_for(ws.recv(), timeout=10)
                    resp_data = json.loads(response)
                    if resp_data.get("result") is None and resp_data.get("id") == 1:
                        self._logger.info(f"Subscribed to {len(streams)} streams")
                    else:
                        self._logger.warning(f"Subscription response: {resp_data}")

                    reconnect_delay = 5  # Reset backoff on successful connection
                    while self._running:
                        try:
                            msg = await ws.recv()
                            data = json.loads(msg)
                            stream = data['stream']
                            payload = data['data']

                            # Parse Symbol & Type
                            symbol = stream.split('@')[0].upper()
                            event_type = "UNKNOWN"

                            # P1: Removed DEBUG_STREAM print from hot path

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
                                # VENUE CONSISTENCY: In node mode (USE_HL_NODE=true), skip Binance
                                # trades for VWAP/ATR/Orderflow. HL fills are wired via
                                # _handle_hl_fill callback to avoid double counting.
                                if not self._use_node_mode:
                                    try:
                                        price = float(payload.get('p', 0))
                                        volume = float(payload.get('q', 0))
                                        timestamp = int(payload.get('T', 0)) / 1000.0 if 'T' in payload else time.time()
                                        is_buyer_maker = payload.get('m', False)

                                        # Memory guard: check symbol limit before adding new
                                        is_new_symbol = symbol not in self._vwap_calculators
                                        if is_new_symbol and len(self._vwap_calculators) >= self._calculator_max_symbols:
                                            self.prune_stale_calculators()

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

                                        # Track last activity for pruning
                                        self._calculator_last_activity[symbol] = timestamp

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
                                # P1: Removed DEBUG_STREAM print from hot path
                                # Log raw liquidation event
                                if 'o' in payload:
                                    order = payload['o']
                                    # For global !forceOrder@arr stream, get symbol from order data
                                    symbol = order.get('s', symbol)
                                    try:
                                        # P1: Removed DEBUG prints from hot path
                                        side_value = order.get('S', 'UNKNOWN')
                                        self._execution_db.log_liquidation_event(
                                            timestamp=ts if 'ts' in locals() else time.time(),
                                            symbol=symbol,
                                            side=side_value,
                                            price=float(order.get('p', 0)),
                                            volume=float(order.get('q', 0))
                                        )
                                    except Exception:
                                        pass  # Fail silently per constitutional rules

                                # Phase 5: Update liquidation Z-score calculator
                                # VENUE CONSISTENCY: In node mode (USE_HL_NODE=true), skip Binance
                                # liquidations for zscore/burst. HL liquidations are wired via
                                # _handle_hl_liquidation callback to avoid double counting.
                                if not self._use_node_mode:
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

                                            # Phase 6: Update liquidation burst aggregator (for cascade sniper)
                                            price = float(order.get('p', 0))
                                            side = order.get('S', 'UNKNOWN')
                                            self._liquidation_burst_aggregator.add_event(
                                                timestamp=timestamp,
                                                symbol=symbol,
                                                side=side,
                                                price=price,
                                                quantity=quantity
                                            )

                                            # Phase 7: Record to entry quality scorer for exhaustion detection
                                            try:
                                                from external_policy.ep2_strategy_cascade_sniper import record_liquidation_event
                                                liq_value = price * quantity
                                                record_liquidation_event(symbol, side, liq_value, timestamp)
                                            except ImportError:
                                                pass  # Module not available
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
                            # Note: 'E' is event time, 'T' varies by stream type
                            # For markPrice, 'T' is next_funding_time (FUTURE!) - must use 'E'
                            ts = time.time()
                            if 'E' in payload:
                                ts = int(payload['E']) / 1000.0
                            elif 'T' in payload and 'markprice' not in stream.lower():
                                # Only use 'T' for non-markPrice streams (trade timestamp)
                                ts = int(payload['T']) / 1000.0

                            # Update authoritative system clock
                            if self._last_stream_time is None or ts > self._last_stream_time:
                                self._last_stream_time = ts

                            # INGEST (P1: removed debug print from hot path)
                            self._obs.ingest_observation(ts, symbol, event_type, payload)

                        except websockets.exceptions.ConnectionClosed:
                            # Let connection errors bubble up to trigger reconnect
                            raise
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

        # Stop Hyperliquid collector if running
        if self._hyperliquid_collector:
            try:
                await self._hyperliquid_collector.stop()
            except Exception:
                pass  # Fail silently per constitutional rules

        # Flush and close buffered database
        if hasattr(self, '_execution_db') and hasattr(self._execution_db, 'close'):
            try:
                self._execution_db.close()
                self._logger.info("Buffered database flushed and closed")
            except Exception:
                pass

    def get_liquidation_proximity(self, coin: str):
        """
        Get current liquidation proximity for a Hyperliquid coin.

        Args:
            coin: Coin symbol (e.g., "BTC", "ETH")

        Returns:
            LiquidationProximity or None if not available
        """
        if self._hyperliquid_collector:
            return self._hyperliquid_collector.get_proximity(coin)
        return None

    def get_all_liquidation_proximity(self):
        """
        Get liquidation proximity for all tracked Hyperliquid coins.

        Returns:
            Dict of coin -> LiquidationProximity
        """
        if self._hyperliquid_collector:
            return self._hyperliquid_collector.get_all_proximity()
        return {}

    def add_hyperliquid_wallet(self, wallet_address: str, wallet_type: str = None, label: str = None):
        """
        Add a wallet to Hyperliquid tracking.

        Args:
            wallet_address: Ethereum address
            wallet_type: Type label (e.g., "WHALE", "LEADERBOARD")
            label: Human-readable label
        """
        if self._hyperliquid_collector:
            self._hyperliquid_collector.add_wallet(wallet_address, wallet_type, label)


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
