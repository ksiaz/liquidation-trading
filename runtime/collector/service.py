"""
Runtime Collector Service

The Driver of the Observation System.
Responsibility:
1. IO: Connect to HL node (gRPC adapter) and WebSockets.
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
from runtime.arbitration.types import MandateType
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState
from runtime.logging.pg_buffered_db import PgBufferedResearchDatabase
from runtime.risk.circuit_breaker import DataFreshnessBreaker

# Import Ghost Tracker
from execution.ep4_ghost_tracker import GhostPositionTracker
from execution.ep4_ghost_adapter import NormalizedOrderbook
import os

# Import Trailing Stop Manager for profit protection
from runtime.exchange.trailing_stop_manager import TrailingStopManager, TrailingStopConfig, TrailingMode
from runtime.persistence.execution_state_repository import ExecutionStateRepository

# Import Regime Classification (Phase 5)
from runtime.regime import RegimeState, RegimeMetrics, classify_regime
from runtime.indicators import VWAPCalculator, MultiTimeframeATR
from runtime.orderflow import MultiWindowOrderflow
from runtime.liquidations import LiquidationZScoreCalculator, LiquidationBurstAggregator, LiquidationBurst
from runtime.liquidations.rolling_volume_tracker import RollingVolumeTracker
from runtime.cascade import CapitulationTracker
from runtime.market_state.emitter import MarketStateEmitter
from runtime.market_state.snapshot import SnapshotTrigger

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

# Warmup uses HL candleSnapshot API for ATR/VWAP pre-loading

# Import Validation modules for data integrity and manipulation detection
from runtime.validation import (
    DataValidator,
    ManipulationDetector,
    StopHuntDetector,
    LiquidityType
)

# Constants - Trading symbols (must match run_paper_trade.py)
TOP_10_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "AVAXUSDT", "LINKUSDT", "HYPEUSDT", "SUIUSDT", "NEARUSDT",
    "LTCUSDT", "ATOMUSDT", "AAVEUSDT", "APTUSDT", "ARBUSDT",
    "BNBUSDT", "OPUSDT", "TRXUSDT", "WLDUSDT", "TONUSDT",
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
        # PostgreSQL backend: no _db_lock, prune doesn't block writes (MVCC)
        self._execution_db = PgBufferedResearchDatabase(
            flush_interval_sec=1.0,
            max_buffer_size=1000,
            enable_high_frequency_logs=False,
        )
        
        # Inject event logger into observation system's M2 store
        if not hasattr(self._obs._m2_store, '_event_logger') or self._obs._m2_store._event_logger is None:
            self._obs._m2_store._event_logger = self._execution_db

        # Phase 8: M6 Integration
        self.policy_adapter = PolicyAdapter(AdapterConfig(
            enable_geometry=False,       # DISABLED: 10% win rate, zones from fill-only data lack L2 confirmation
            enable_orderbook_test=False,  # Test policy (disabled)
            # Phase 5: Enable regime-gated strategies
            enable_slbrs=True,           # NEW: SLBRS strategy (SIDEWAYS regime)
            enable_effcs=True,           # NEW: EFFCS strategy (EXPANSION regime)
            # Phase 6: Cascade Sniper (Hyperliquid proximity)
            enable_cascade_sniper=True,  # NEW: Cascade sniper (liquidation proximity)
            cascade_sniper_entry_mode="ROLLING_FADE"  # Fade 30m rolling liq spikes (backtest: 91% WR)
        ))
        self.arbitrator = MandateArbitrator()
        # Fix: Enable position persistence to survive restarts
        # Without this, EXIT signals never trigger (position state lost on restart)
        self.executor = ExecutionController(RiskConfig(), db_path="logs/positions.db")

        # Restore strategy state from persisted positions
        # This enables EXIT signals for positions opened in previous sessions
        self._restore_strategy_state()

        # Track mark prices for execution (updated from HL oracle in regime loop)
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
        # All writes go through PgBufferedResearchDatabase (PostgreSQL, no lock).
        self.ghost_tracker = GhostPositionTracker(
            initial_balance=1000.0,
            position_size_pct=0.05,
            symbols=TOP_10_SYMBOLS,
            buffered_db=self._execution_db
        )

        # Trailing Stop Manager for profit protection
        # Config: ATR_PROGRESSIVE - MFE-based with continuous tightening
        # - Uses 5m ATR for volatility-adaptive stops
        # - Starts at 2.5× ATR, tightens to 1.0× ATR as profit grows
        # - Break-even at 0.5% profit as floor (not override)
        # - Floor at 0.5% distance for low volatility protection
        # Tuning profile: BALANCED (2026-02-07)
        # Wider initial stop, slower tightening, higher BE trigger
        self._trailing_stop_config = TrailingStopConfig(
            mode=TrailingMode.ATR_PROGRESSIVE,
            # Two-phase ATR tightening
            atr_prog_start_mult=2.5,        # Wide at entry
            atr_prog_phase1_end_mult=2.0,   # End of phase 1 (was 1.8 — too aggressive)
            atr_prog_phase1_range=0.02,     # Phase 1: 0-2% MFE (was 1% — tightened too fast)
            atr_prog_end_mult=1.0,          # Tight at target
            atr_prog_profit_range=0.04,     # Full range unchanged
            atr_prog_min_pct=0.005,         # Floor: 0.5% distance
            # Orderflow tightening
            orderflow_tighten_threshold=0.38,  # Adverse flow threshold
            orderflow_tighten_mult=0.6,        # 40% tighter when adverse
            # Break-even settings
            break_even_trigger_pct=0.008,   # Trigger break-even after 0.8% profit (was 0.6%)
            break_even_offset_pct=0.002,    # Lock in 0.2% profit at break-even
            # ATR-relative update gate
            min_move_atr_fraction=0.10,     # Update if move >= 10% of ATR (was 5% — too jittery)
            min_move_to_update_pct=0.002,   # Fallback min move 0.2% (was 0.1%)
            # Lock ratio: retain 35% of unrealized profit (was 45% — too greedy early)
            atr_prog_min_lock_ratio=0.35,
        )
        # Create execution state repository for trailing stop persistence
        self._execution_state_repo = ExecutionStateRepository(db_path="logs/execution_state.db")
        self._trailing_stop_manager = TrailingStopManager(
            logger=self._logger,
            repository=self._execution_state_repo
        )

        # Track execution log index to process new results
        self._last_execution_index = 0

        # Reconcile ghost tracker with positions.db on startup
        self._reconcile_positions_on_startup()

        # Backfill missing exit rows in execution.db from ghost_positions DB
        self._backfill_missing_exits()

        # Store latest cycle context for ghost tracker
        self._latest_cycle_id = None
        self._latest_snapshot = None

        # Phase 5: Regime Classification Infrastructure
        # Initialize regime metric calculators (per-symbol tracking)
        self._vwap_calculators: Dict[str, VWAPCalculator] = {}
        self._atr_calculators: Dict[str, MultiTimeframeATR] = {}
        self._orderflow_calculators: Dict[str, MultiWindowOrderflow] = {}
        self._liquidation_calculators: Dict[str, LiquidationZScoreCalculator] = {}
        # HL fill accumulator: aggregates taker fills per symbol per cycle
        # Each entry: (side_consumed: "bid"|"ask", size: float, price: float, ts: float)
        self._hl_fill_accumulator: Dict[str, list] = {}
        # Governance event buffer: daemon threads append, regime loop drains to _obs.
        # Bridges HL fills/liquidations from gRPC thread to governance (M2 nodes).
        from collections import deque as _deque
        self._governance_event_buffer: _deque = _deque(maxlen=10000)
        # Rolling price high/low tracker (5-min window) for EFFCS impulse detection
        self._price_highs: Dict[str, float] = {}
        self._price_lows: Dict[str, float] = {}
        self._hl_reset_time: Dict[str, float] = {}

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

        # Exhaustion scorer DISABLED — backtest showed anti-predictive at 30s timing.
        # EXHAUSTION_FADE now enters at TRIGGERED (immediate) with counter-trend gate.
        self._exhaustion_scorer = None

        # Rolling volume tracker for ROLLING_FADE entry mode
        self._rolling_volume_tracker = RollingVolumeTracker()

        # Capitulation tracker (detects forced position unwinding from HL fill metadata)
        self._capitulation_tracker = CapitulationTracker(window_sec=60.0)

        # Market state emitter (per-symbol snapshots for trade context + pipeline health)
        self._market_state = MarketStateEmitter(self._execution_db)

        # Track current prices for regime calculation
        self._current_prices: Dict[str, float] = {}

        # Track regime state per symbol
        self._regime_states: Dict[str, RegimeState] = {}

        # Track regime metrics per symbol (Phase 5)
        self._regime_metrics: Dict[str, RegimeMetrics] = {}

        # Track previous regime state for transition logging (Phase 6)
        self._prev_regime_states: Dict[str, RegimeState] = {}
        # Regime debounce: require N consecutive cycles of new state before transitioning
        # Prevents orderflow noise from causing SIDEWAYS↔DISABLED chatter at 5Hz
        self._regime_pending: Dict[str, tuple] = {}  # symbol → (pending_state, count)
        self._REGIME_DEBOUNCE_CYCLES = 50  # 50 cycles × ~200ms = ~10 seconds

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

        # Data freshness circuit breaker — blocks entries when node/adapter stale
        self._data_breaker = DataFreshnessBreaker() if self._node_bridge else None

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
            self._regime_pending.pop(symbol, None)
            self._calculators_pruned += 1

        if to_remove:
            self._logger.debug(f"Pruned {len(to_remove)} stale calculators")

        return len(to_remove)

    def _get_live_price(self, symbol: str) -> Optional[float]:
        """Get the most reliable live price for a symbol.

        Priority:
        1. WebSocket mid price (live from HL API, not from lagging node)
        2. _current_prices fallback (from node oracle or fills)

        The WS allMids subscription provides real-time prices even when the
        HL node is bootstrapping or behind the chain tip.
        """
        coin = symbol.replace('USDT', '')
        if self._hyperliquid_collector and hasattr(self._hyperliquid_collector, '_client'):
            ws_mid = self._hyperliquid_collector._client.get_mid_price(coin)
            if ws_mid and ws_mid > 0:
                return ws_mid
        return self._current_prices.get(symbol)

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

            # Register trailing stops for recovered positions (only if not already loaded from persistence)
            existing_stops = self._trailing_stop_manager.get_all_stops()
            existing_symbols = {s.symbol for s in existing_stops.values()}

            for pos in open_positions.values():
                if pos.state.value == "OPEN" and pos.entry_price and pos.direction:
                    # Skip if trailing stop already exists for this symbol (from persistence)
                    if pos.symbol in existing_symbols:
                        self._logger.info(f"  {pos.symbol}: trailing stop already loaded from persistence")
                        continue

                    entry_price = float(pos.entry_price)
                    direction = pos.direction.value if hasattr(pos.direction, 'value') else str(pos.direction)

                    # Set initial stop at 2% from entry
                    if direction == "LONG":
                        initial_stop = entry_price * 0.98
                    else:
                        initial_stop = entry_price * 1.02

                    # Use symbol as trade_id for recovered positions
                    self._trailing_stop_manager.register_trailing_stop(
                        entry_order_id=f"RECOVERED_{pos.symbol}",
                        symbol=pos.symbol,
                        direction=direction,
                        entry_price=entry_price,
                        initial_stop_price=initial_stop,
                        config=self._trailing_stop_config
                    )
                    self._logger.info(f"  {pos.symbol}: registered trailing stop @ ${initial_stop:,.2f}")

            # Also register trailing stops from ghost_positions (may have additional positions)
            try:
                from runtime.logging.pg_pool import get_conn, put_conn
                pg_conn = get_conn()
                try:
                    cur = pg_conn.cursor()
                    cur.execute("SELECT symbol, side, entry_price FROM ghost_positions WHERE status = 'OPEN'")
                    for row in cur.fetchall():
                        symbol, side, entry_price = row
                        # Skip if already registered
                        if f"RECOVERED_{symbol}" in [s.entry_order_id for s in self._trailing_stop_manager.get_all_stops().values()]:
                            continue

                        direction = side  # ghost_positions uses LONG/SHORT directly
                        entry = float(entry_price) if entry_price else 0
                        if entry <= 0:
                            continue

                        if direction == "LONG":
                            initial_stop = entry * 0.98
                        else:
                            initial_stop = entry * 1.02

                        self._trailing_stop_manager.register_trailing_stop(
                            entry_order_id=f"RECOVERED_{symbol}",
                            symbol=symbol,
                            direction=direction,
                            entry_price=entry,
                            initial_stop_price=initial_stop,
                            config=self._trailing_stop_config
                        )
                        self._logger.info(f"  {symbol}: registered ghost trailing stop @ ${initial_stop:,.2f}")
                finally:
                    put_conn(pg_conn)
            except Exception as ghost_err:
                self._logger.debug(f"Ghost position recovery: {ghost_err}")

        except Exception as e:
            self._logger.warning(f"Position context recovery failed: {e}")

    async def _warm_up_calculators(self, symbols: List[str]):
        """Pre-warm ATR and VWAP from HL candleSnapshot API.

        Fetches 5m candles from Hyperliquid to initialize ATR (needs OHLC)
        and VWAP (needs close*volume). Without this, regime classification
        is blocked for 10+ minutes after restart.

        Also creates Orderflow and LiqZ calculators so they're ready when
        fills arrive (moves from "calculators missing" to "warm-up incomplete").

        Args:
            symbols: USDT-suffixed symbols (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        import aiohttp

        try:
            atr_ready = 0
            vwap_ready = 0
            now_ms = int(time.time() * 1000)
            # Fetch last 2.5h of 5m candles (30 candles)
            start_ms = now_ms - 30 * 5 * 60 * 1000

            async with aiohttp.ClientSession() as session:
                for symbol in symbols:
                    hl_coin = symbol.replace('USDT', '')

                    try:
                        resp = await session.post(
                            'https://api.hyperliquid.xyz/info',
                            json={
                                'type': 'candleSnapshot',
                                'req': {
                                    'coin': hl_coin,
                                    'interval': '5m',
                                    'startTime': start_ms,
                                    'endTime': now_ms,
                                }
                            },
                            timeout=aiohttp.ClientTimeout(total=10)
                        )
                        candles = await resp.json()
                    except Exception as e:
                        self._logger.warning(f"[WARMUP] {symbol}: fetch failed - {e}")
                        continue

                    if not candles or len(candles) < 6:
                        self._logger.warning(
                            f"[WARMUP] {symbol}: insufficient candles "
                            f"({len(candles) if candles else 0})"
                        )
                        continue

                    # Ensure all 4 calculators exist
                    if symbol not in self._atr_calculators:
                        self._atr_calculators[symbol] = MultiTimeframeATR(period=3)
                    if symbol not in self._vwap_calculators:
                        self._vwap_calculators[symbol] = VWAPCalculator()
                    if symbol not in self._orderflow_calculators:
                        self._orderflow_calculators[symbol] = MultiWindowOrderflow()
                    if symbol not in self._liquidation_calculators:
                        self._liquidation_calculators[symbol] = LiquidationZScoreCalculator()

                    # Convert HL candle format to ATR warmup format
                    # HL: {t, T, s, i, o, c, h, l, v, n}
                    klines = []
                    for c in candles:
                        try:
                            klines.append({
                                'high': float(c['h']),
                                'low': float(c['l']),
                                'close': float(c['c']),
                                'open': float(c['o']),
                                'volume': float(c['v']),
                                'close_time': int(c['T']) / 1000.0,
                            })
                        except (KeyError, ValueError):
                            continue

                    if len(klines) < 6:
                        continue

                    # Warm up ATR from OHLC
                    self._atr_calculators[symbol].warm_up_from_klines(klines)

                    # Warm up VWAP from close*volume
                    for k in klines:
                        if k['close'] > 0 and k['volume'] > 0:
                            self._vwap_calculators[symbol].update(
                                k['close'], k['volume'], k['close_time']
                            )

                    atr_5m = self._atr_calculators[symbol].get_atr_5m()
                    atr_30m = self._atr_calculators[symbol].get_atr_30m()
                    vwap = self._vwap_calculators[symbol].get_vwap()

                    if atr_5m and atr_30m:
                        atr_ready += 1
                    if vwap:
                        vwap_ready += 1

                    if atr_5m and atr_30m and vwap:
                        self._logger.info(
                            f"[WARMUP] {symbol}: ATR_5m={atr_5m:.4f}, "
                            f"ATR_30m={atr_30m:.4f}, VWAP={vwap:.2f}"
                        )

            self._logger.info(
                f"[WARMUP] Complete: ATR={atr_ready}/{len(symbols)}, "
                f"VWAP={vwap_ready}/{len(symbols)}"
            )

        except Exception as e:
            self._logger.warning(f"[WARMUP] Failed: {e}")

    async def start(self):
        """Start all collectors."""
        self._running = True
        # Don't set _startup_time here - will be set on first stream data
        # self._startup_time = time.time()  # REMOVED: causes clock skew

        # 0a. Recover persisted positions and strategy contexts (for restart recovery)
        await self._recover_position_contexts()

        # self._logger.info(f"Warmup period duration: {self._warmup_duration_sec}s from startup")

        # 1. Start Clock Driver (Heartbeat)
        asyncio.create_task(self._drive_clock())

        # Give WS time to connect before starting heavy I/O
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

                        # Wire ALL fills (including liquidation) for capitulation tracking
                        # CapitulationTracker needs dir/startPosition/closedPnl from extended fill data
                        self._node_bridge.on_fill_extended(self._handle_hl_fill_extended)
                        self._logger.info("HL extended fill callback registered (capitulation tracker)")

                        # Wire HL oracle prices to _mark_prices and ATR calculators
                        # Breaks the staleness chain: oracle prices arrive every ~1s vs sparse fills
                        # Ensures _mark_prices is always fresh (no Decimal("0") defaults)
                        # and ATR reflects true price range (not just moments of fills)
                        self._node_bridge.on_price_update(self._handle_hl_price)
                        self._logger.info("HL price callback registered (mark prices + ATR)")

                        # Inject capitulation tracker into cascade sniper for absorption confidence
                        try:
                            from external_policy.ep2_strategy_cascade_sniper import set_capitulation_tracker
                            set_capitulation_tracker(self._capitulation_tracker)
                            self._logger.info("Capitulation tracker injected into cascade sniper")
                        except ImportError:
                            pass

                        # Exhaustion scorer DISABLED — anti-predictive per backtest.
                        # EXHAUSTION_FADE uses counter-trend + liq count gates instead.

                        # Verify adapter is responding (STALE is OK during warmup)
                        await asyncio.sleep(2)  # Give adapter time to send status
                        status = self._node_bridge.get_status()
                        if status:
                            self._logger.info(
                                f"Node adapter status: {status.status.name}, "
                                f"block={status.latest_block_height}, "
                                f"prices={status.prices_emitted}, liqs={status.liquidations_emitted}"
                            )
                            if status.status.name == 'ERROR':
                                raise RuntimeError(
                                    f"HL adapter ERROR: {status.last_error}. "
                                    "Start adapter with: cd hl-adapter && python server.py"
                                )
                        else:
                            raise RuntimeError(
                                "HL adapter not responding (no status received). "
                                "Start adapter with: cd hl-adapter && python server.py"
                            )

                        # Start periodic health check
                        asyncio.create_task(self._monitor_node_bridge_health())

                        # Pre-warm ATR + VWAP from HL candles (avoids 10+ min warmup delay)
                        # Also creates Orderflow/LiqZ calculators so they're ready for fills
                        await self._warm_up_calculators(TOP_10_SYMBOLS)
                    else:
                        raise RuntimeError(
                            "Node bridge failed to connect. "
                            "Start adapter with: cd hl-adapter && python server.py"
                        )
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

                    # Wire HL orderbook to observation layer for depth primitives
                    # (resting_size, order_consumption, absorption)
                    if hasattr(self._hyperliquid_collector, '_client'):
                        self._hyperliquid_collector._client.set_orderbook_callback(
                            self._handle_hl_orderbook
                        )
                        self._logger.info("HL orderbook callback registered (depth primitives)")
                except Exception as e:
                    self._logger.warning(f"Hyperliquid collector start failed: {e}")

        # Keep service alive (block forever until shutdown)
        self._shutdown_event = asyncio.Event()
        await self._shutdown_event.wait()

    async def _monitor_node_bridge_health(self):
        """Periodic health check for HL adapter connection.

        Logs ERROR loudly if adapter becomes unhealthy or disconnected.
        This prevents silent failures where fills/liqs stop flowing.
        """
        check_interval = 30  # Check every 30 seconds
        last_fills = 0
        stale_count = 0

        while self._running and self._node_bridge:
            await asyncio.sleep(check_interval)

            try:
                if not self._node_bridge.is_connected:
                    self._logger.error(
                        "🚨 HL ADAPTER DISCONNECTED - fills/liqs NOT flowing! "
                        "Restart adapter: cd hl-adapter && python server.py"
                    )
                    print(
                        "\n🚨🚨🚨 HL ADAPTER DISCONNECTED 🚨🚨🚨\n"
                        "Fills and liquidations are NOT being received!\n"
                        "Restart adapter: cd hl-adapter && python server.py\n",
                        flush=True
                    )
                    continue

                if not self._node_bridge.is_healthy:
                    status = self._node_bridge.get_status()
                    self._logger.error(
                        f"🚨 HL ADAPTER UNHEALTHY: {status.status.name if status else 'unknown'}"
                    )
                    continue

                # Check if fills are flowing (should increase over time)
                metrics = self._node_bridge.get_metrics()
                current_fills = metrics.get('fills_ingested', 0)
                if current_fills == last_fills:
                    stale_count += 1
                    if stale_count >= 3:  # 3 checks = 90 seconds of no fills
                        self._logger.warning(
                            f"⚠️ HL adapter stale: no new fills in {stale_count * check_interval}s"
                        )
                else:
                    stale_count = 0
                last_fills = current_fills

            except Exception as e:
                self._logger.error(f"Health check failed: {e}")

    async def _drive_clock(self):
        """Push Wall Clock time to System every 1s and drive M6 execution cycle.

        CPU Optimization (2026-01-28): Reduced from 10Hz to 5Hz.
        - 200ms cycle provides good balance of responsiveness and CPU usage
        """
        self._logger.info("[CLOCK] Drive clock loop started")
        while self._running:
            # Simple clock source selection:
            # - Node mode: use wall clock (node is synced, data is flowing)
            # - WebSocket mode: use WS stream time
            if self._use_node_mode:
                current_time = time.time()
            elif self._last_stream_time is not None:
                current_time = self._last_stream_time
            else:
                # Wait for first WS stream event
                await asyncio.sleep(0.5)
                continue

            try:
                # 0. Drain governance event buffer (fills + liquidations from gRPC thread)
                # This feeds M2 node creation so structural_persistence is available.
                _gov_drained = 0
                while self._governance_event_buffer:
                    try:
                        event_type, symbol, payload = self._governance_event_buffer.popleft()
                        self._obs.ingest_observation(
                            timestamp=payload.get('timestamp', current_time),
                            symbol=symbol,
                            event_type=event_type,
                            payload=payload,
                        )
                        _gov_drained += 1
                    except Exception as e:
                        self._logger.warning(f"Governance drain error ({event_type}/{symbol}): {e}")
                        continue  # Skip bad event, process remaining

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
                self._logger.warning(f"Clock/Execution cycle exception: {e}")
                import traceback
                traceback.print_exc()

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
                # Skip HL-format duplicates (e.g., "BTC") - only process USDT symbols
                # run_paper_trade.py adds both "BTCUSDT" and "BTC" to allowed_symbols;
                # calculators are keyed by USDT format from HL fill handler.
                if not symbol.endswith('USDT'):
                    continue

                try:
                    # Get current price — prefer live WS mid over node oracle
                    hl_symbol = symbol.replace('USDT', '')
                    price = self._get_live_price(symbol) or node_prices.get(symbol)
                    if price is None:
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            print(f"[REGIME] {symbol}: SKIP - no price", flush=True)
                        continue  # No price data yet

                    # Update price dicts so all paths use the best available price
                    self._mark_prices[symbol] = Decimal(str(price))
                    self._current_prices[symbol] = price

                    # Update trailing stops with oracle price every cycle
                    # (HL fills are sparse — oracle price ensures stops trail on moves)
                    self._update_trailing_stops(symbol, price)

                    # Log when HL oracle price is used (activation proof)
                    # Log first 5 cycles then every 50th to reduce noise
                    if _diag_regime and node_prices.get(symbol) and cycle_id and (cycle_id <= 5 or cycle_id % 50 == 1):
                        print(f"[HL_PRICE] {symbol}: using oracle price {price:.2f} from HL node", flush=True)

                    # Get calculators
                    vwap_calc = self._vwap_calculators.get(symbol)
                    atr_calc = self._atr_calculators.get(symbol)
                    orderflow_calc = self._orderflow_calculators.get(symbol)
                    liquidation_calc = self._liquidation_calculators.get(symbol)

                    if not all([vwap_calc, atr_calc, orderflow_calc, liquidation_calc]):
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            missing = []
                            if not vwap_calc: missing.append("VWAP")
                            if not atr_calc: missing.append("ATR")
                            if not orderflow_calc: missing.append("Orderflow")
                            if not liquidation_calc: missing.append("Liquidation Z-score")
                            print(f"[REGIME] {symbol}: SKIP - calculators missing: {missing}", flush=True)
                        continue  # Calculator not initialized for this symbol

                    # Compute regime metrics
                    vwap_distance = vwap_calc.get_distance(price)
                    atr_5m = atr_calc.get_atr_5m()
                    atr_30m = atr_calc.get_atr_30m()
                    # Use 60s window in node mode (HL fills are sparser)
                    orderflow_imbalance = (
                        orderflow_calc.get_imbalance_60s()
                        if self._use_node_mode
                        else orderflow_calc.get_imbalance_30s()
                    )
                    liquidation_zscore = liquidation_calc.get_zscore(timestamp)
                    orderflow_fill_count = (
                        orderflow_calc.get_trade_count_60s()
                        if self._use_node_mode
                        else orderflow_calc.get_trade_count_30s()
                    )

                    # Check if all metrics available
                    if None in [vwap_distance, atr_5m, atr_30m, orderflow_imbalance, liquidation_zscore]:
                        if _diag_regime and cycle_id and cycle_id % 10 == 1:
                            missing = []
                            if vwap_distance is None: missing.append("VWAP")
                            if atr_5m is None: missing.append("ATR_5m")
                            if atr_30m is None: missing.append("ATR_30m")
                            if orderflow_imbalance is None: missing.append("Orderflow")
                            if liquidation_zscore is None: missing.append("Liq_Z")
                            print(f"[REGIME] {symbol}: SKIP - calculator warm-up incomplete: {missing}", flush=True)
                        continue  # Calculator warm-up not complete

                    # Compute VWAP z-score (signed deviation from VWAP in σ units)
                    vwap_z = vwap_calc.get_z(price) or 0.0

                    # Create regime metrics object
                    regime_metrics = RegimeMetrics(
                        vwap_distance=vwap_distance,
                        atr_5m=atr_5m,
                        atr_30m=atr_30m,
                        orderflow_imbalance=orderflow_imbalance,
                        liquidation_zscore=liquidation_zscore,
                        orderflow_fill_count=orderflow_fill_count,
                        vwap_z=vwap_z
                    )

                    # Classify regime (pass current state for hysteresis)
                    prev_regime = self._prev_regime_states.get(symbol)
                    regime_state = classify_regime(regime_metrics, prev_regime)

                    # Diagnostic: show why DISABLED (temporary)
                    if _diag_regime and regime_state.name == "DISABLED" and cycle_id and cycle_id % 50 == 1:
                        atr_ratio = atr_5m / atr_30m if atr_30m else 0
                        atr5_pct = (atr_5m / price * 100) if price else 0
                        atr30_pct = (atr_30m / price * 100) if price else 0
                        print(f"[REGIME] {symbol}: DISABLED - vwap_d={vwap_distance:.4f} "
                              f"atr5={atr5_pct:.2f}% atr30={atr30_pct:.2f}% "
                              f"ratio={atr_ratio:.2f} of={orderflow_imbalance:.3f} "
                              f"liq_z={liquidation_zscore:.2f}", flush=True)

                    # Phase 6: Debounced regime transitions
                    # Require N consecutive cycles of the new state before applying
                    # (prev_regime already read above for classifier hysteresis)
                    if prev_regime is not None and prev_regime != regime_state:
                        pending = self._regime_pending.get(symbol)
                        if pending and pending[0] == regime_state:
                            count = pending[1] + 1
                        else:
                            count = 1
                        self._regime_pending[symbol] = (regime_state, count)

                        if count >= self._REGIME_DEBOUNCE_CYCLES:
                            # Confirmed transition
                            atr5_pct = (atr_5m / price * 100) if price else 0
                            atr30_pct = (atr_30m / price * 100) if price else 0
                            atr_r = atr_5m / atr_30m if atr_30m else 0
                            self._logger.info(
                                f"Regime transition: {symbol} {prev_regime.name} → {regime_state.name} "
                                f"(VWAP dist={vwap_distance:.4f}, ATR 5m={atr5_pct:.2f}% 30m={atr30_pct:.2f}% "
                                f"ratio={atr_r:.2f}, orderflow={orderflow_imbalance:.3f}, liq_z={liquidation_zscore:.2f})"
                            )
                            self._prev_regime_states[symbol] = regime_state
                            self._regime_pending.pop(symbol, None)
                        else:
                            # Not confirmed yet — keep previous regime
                            regime_state = prev_regime
                    else:
                        # Same state as before or first classification — reset pending
                        self._regime_pending.pop(symbol, None)
                        self._prev_regime_states[symbol] = regime_state

                    # Store regime state and metrics for this symbol
                    self._regime_states[symbol] = regime_state
                    self._regime_metrics[symbol] = regime_metrics

                except Exception as e:
                    # Don't fail cycle if regime classification fails
                    self._logger.warning(f"Regime classification error for {symbol}: {e}")
                    continue

            # Data freshness gate — block new entries when node/adapter stale
            # Trailing stops already updated in regime loop above (~line 951)
            _data_breaker_open = False
            if self._data_breaker:
                self._data_breaker.evaluate(self._node_bridge)
                _data_breaker_open = self._data_breaker.is_open

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
                    current_price = self._get_live_price(symbol)

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
                    # Otherwise, use collector's aggregator (fed by WS forceOrder stream)
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

                    # Trend context for cascade sniper kill-switch
                    trend_context = self._obs.get_trend_context(symbol)

                    # Capitulation confidence for SLBRS entry quality gate
                    cap_confidence = 0.0
                    if self._capitulation_tracker:
                        cap_metrics = self._capitulation_tracker.get_metrics(
                            coin_for_returns, timestamp
                        )
                        cap_confidence = cap_metrics.confidence

                    # Check for rolling fade signal (30m rolling liq spike)
                    rolling_fade_signal = self._rolling_volume_tracker.check_for_signal(
                        symbol, timestamp
                    )

                    # Feed freshness gate: block ROLLING_FADE when regime can't be computed.
                    # Regime requires VWAP + ATR + orderflow + liq_z all non-None.
                    # When the node is lagging or adapter is disconnected, these are None,
                    # meaning the system has no context for stop sizing or direction.
                    if rolling_fade_signal and regime_metrics is None:
                        self._logger.debug(
                            f"ROLLING_FADE blocked for {symbol}: regime_metrics unavailable"
                        )
                        rolling_fade_signal = None

                    # ── Market State Snapshot (periodic) ──
                    # Emit per-symbol snapshot with derived values + raw input counters.
                    # All data is already computed at this point in the loop.
                    try:
                        from external_policy.ep2_strategy_cascade_sniper import get_cascade_state
                        _cascade_st = get_cascade_state(symbol)
                        _cascade_str = _cascade_st.value if _cascade_st else None
                    except Exception:
                        _cascade_str = None

                    # Proximity fields
                    _prox_count = None
                    _prox_usd = None
                    _closest_pct = None
                    if hl_proximity:
                        _prox_count = hl_proximity.total_positions_at_risk
                        _prox_usd = hl_proximity.total_value_at_risk
                        if current_price and current_price > 0:
                            # Closest liq distance as % of price
                            closest = min(
                                abs(hl_proximity.long_closest_liquidation - current_price) if hl_proximity.long_closest_liquidation else float('inf'),
                                abs(hl_proximity.short_closest_liquidation - current_price) if hl_proximity.short_closest_liquidation else float('inf'),
                            )
                            if closest < float('inf'):
                                _closest_pct = closest / current_price * 100

                    # Absorption fields
                    _bid_depth = None
                    _ask_depth = None
                    _abs_longs = None
                    _abs_shorts = None
                    if absorption:
                        _bid_depth = absorption.bid_depth_2pct
                        _ask_depth = absorption.ask_depth_2pct
                        _abs_longs = absorption.absorption_ratio_longs if absorption.absorption_ratio_longs != float('inf') else None
                        _abs_shorts = absorption.absorption_ratio_shorts if absorption.absorption_ratio_shorts != float('inf') else None

                    # Raw input counters
                    _feed_age = None
                    _last_activity = self._calculator_last_activity.get(symbol)
                    if _last_activity:
                        _feed_age = int((timestamp - _last_activity) * 1000)

                    _raw_of = regime_metrics.orderflow_fill_count if regime_metrics else None

                    _raw_liq_baseline = None
                    _raw_liq_rate = None
                    _liq_calc = self._liquidation_calculators.get(symbol)
                    if _liq_calc:
                        _raw_liq_baseline = _liq_calc.get_event_count()
                        _raw_liq_rate = _liq_calc.get_current_rate(timestamp)

                    _raw_burst_count = None
                    _raw_burst_vol = None
                    if liquidation_burst:
                        _raw_burst_count = liquidation_burst.liquidation_count
                        _raw_burst_vol = liquidation_burst.total_volume

                    _rolling_hist = self._rolling_volume_tracker.get_history_count(symbol)
                    _rolling_warm = self._rolling_volume_tracker.is_warmed_up(symbol)

                    _l2_age = None
                    if self._hyperliquid_enabled and self._hyperliquid_collector and hasattr(self._hyperliquid_collector, '_client'):
                        _l2_book = self._hyperliquid_collector._client.get_orderbook(coin)
                        if _l2_book and 'timestamp' in _l2_book:
                            _l2_age = int((timestamp - _l2_book['timestamp']) * 1000)

                    _cap_fills = None
                    if self._capitulation_tracker:
                        _cm = self._capitulation_tracker.get_metrics(coin_for_returns, timestamp)
                        _cap_fills = _cm.total_fills if hasattr(_cm, 'total_fills') else None

                    # Position info
                    _has_pos = self.ghost_tracker.has_open_position(symbol)
                    _pos_side = None
                    if _has_pos:
                        _gp = self.ghost_tracker.get_open_position(symbol)
                        _pos_side = _gp.side if _gp else None

                    # Rolling liq volume/z
                    _rolling_vol = self._rolling_volume_tracker.get_window_volume(symbol, timestamp)
                    _rolling_z = self._rolling_volume_tracker.get_current_z(symbol, timestamp)

                    self._market_state.emit(
                        symbol=symbol,
                        trigger=SnapshotTrigger.PERIODIC.value,
                        timestamp=timestamp,
                        price=current_price or 0,
                        vwap=self._vwap_calculators[symbol].get_vwap() if symbol in self._vwap_calculators else None,
                        vwap_distance=regime_metrics.vwap_distance if regime_metrics else None,
                        vwap_z=regime_metrics.vwap_z if regime_metrics else None,
                        atr_5m=regime_metrics.atr_5m if regime_metrics else None,
                        atr_30m=regime_metrics.atr_30m if regime_metrics else None,
                        orderflow_ratio=regime_metrics.orderflow_imbalance if regime_metrics else None,
                        orderflow_fill_count=regime_metrics.orderflow_fill_count if regime_metrics else None,
                        orderflow_neutralized=(regime_metrics.orderflow_fill_count or 0) < 15 if regime_metrics else False,
                        liq_z=regime_metrics.liquidation_zscore if regime_metrics else None,
                        rolling_liq_volume=_rolling_vol if _rolling_vol > 0 else None,
                        rolling_liq_z=_rolling_z if _rolling_z != 0 else None,
                        regime=regime_state.name if regime_state else None,
                        cascade_state=_cascade_str,
                        proximity_count=_prox_count,
                        proximity_usd_at_risk=_prox_usd,
                        closest_liq_pct=_closest_pct,
                        bid_depth_2pct=_bid_depth,
                        ask_depth_2pct=_ask_depth,
                        absorption_ratio_longs=_abs_longs,
                        absorption_ratio_shorts=_abs_shorts,
                        cap_confidence=cap_confidence,
                        has_position=_has_pos,
                        position_side=_pos_side,
                        feed_age_ms=_feed_age,
                        raw_of_fills_60s=_raw_of,
                        raw_liq_events_baseline=_raw_liq_baseline,
                        raw_liq_rate_1m=_raw_liq_rate,
                        raw_burst_count=_raw_burst_count,
                        raw_burst_volume=_raw_burst_vol,
                        raw_rolling_history_count=_rolling_hist,
                        raw_rolling_warmed_up=_rolling_warm,
                        raw_l2_age_ms=_l2_age,
                        raw_cap_fills=_cap_fills,
                    )

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
                        trend_context=trend_context,  # Trend kill-switch for cascade sniper
                        price_returns=price_returns,  # Gate B: Short-term price returns
                        hl_order_consumption=None,  # Canonical OC now has initial_size
                        price_high=self._price_highs.get(symbol, current_price),
                        price_low=self._price_lows.get(symbol, current_price),
                        capitulation_confidence=cap_confidence,
                        rolling_fade_signal=rolling_fade_signal
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
                    self._logger.warning(f"Policy generation exception for {symbol}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue to next symbol

            # Data freshness gate: drop ENTRY mandates when breaker open
            if _data_breaker_open and all_mandates:
                before = len(all_mandates)
                all_mandates = [m for m in all_mandates if m.type != MandateType.ENTRY]
                dropped = before - len(all_mandates)
                if dropped:
                    self._logger.warning(
                        f"Data breaker open: dropped {dropped} ENTRY mandate(s), "
                        f"kept {len(all_mandates)} EXIT/REDUCE"
                    )

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

            # Process new execution results: register entries with ghost tracker,
            # handle exits and reduces. Single unified path.
            existing_stop_symbols = set(
                s.symbol for s in self._trailing_stop_manager._stops.values()
            )
            for result in self.executor.get_execution_log()[self._last_execution_index:]:
                if not result.success:
                    continue

                # --- ENTRY: register with ghost tracker + trailing stop ---
                if (result.action.name == "ENTRY"
                        and result.state_after.name == "OPEN"
                        and result.symbol not in existing_stop_symbols):
                    pos = self.executor.state_machine.get_position(result.symbol)
                    if pos and pos.direction and pos.entry_price:
                        side = pos.direction.value
                        entry_px = float(pos.entry_price)
                        qty = float(pos.quantity) if pos.quantity else 0.0

                        success, error, trade = self.ghost_tracker.open_position(
                            symbol=result.symbol,
                            side=side,
                            quantity=qty,
                            entry_price=entry_px,
                            timestamp=result.timestamp,
                            cycle_id=getattr(result, 'cycle_id', None),
                            policy_name=result.strategy_id
                        )
                        if success and trade:
                            # Use custom trailing config for fade entries
                            stop_config = self._trailing_stop_config
                            cascade_mode = self.policy_adapter.config.cascade_sniper_entry_mode
                            is_cascade = result.strategy_id == "EP2-CASCADE-SNIPER-V1"
                            is_exhaust_fade = is_cascade and cascade_mode == "EXHAUSTION_FADE"
                            is_rolling_fade = is_cascade and cascade_mode == "ROLLING_FADE"
                            if is_exhaust_fade:
                                stop_config, initial_stop = self._get_exhaust_fade_stop_config(
                                    result.symbol, entry_px, side
                                )
                            elif is_rolling_fade:
                                stop_config, initial_stop = self._get_rolling_fade_stop_config(
                                    result.symbol, entry_px, side
                                )
                            else:
                                initial_stop = entry_px * (0.975 if side == "LONG" else 1.025)
                            self._trailing_stop_manager.register_trailing_stop(
                                entry_order_id=trade.trade_id,
                                symbol=result.symbol,
                                direction=side,
                                entry_price=entry_px,
                                initial_stop_price=initial_stop,
                                config=stop_config
                            )
                            existing_stop_symbols.add(result.symbol)
                            print(f"ENTRY: {result.symbol} {side} qty={qty:.4f} @ ${entry_px:,.2f} id={trade.trade_id}")
                            # Emit ENTRY snapshot from latest ring buffer state
                            _ms_cur = self._market_state.get_current(result.symbol)
                            if _ms_cur:
                                self._market_state.emit(
                                    symbol=result.symbol,
                                    trigger=SnapshotTrigger.ENTRY.value,
                                    timestamp=result.timestamp,
                                    price=entry_px,
                                    vwap=_ms_cur.vwap, vwap_distance=_ms_cur.vwap_distance, vwap_z=_ms_cur.vwap_z,
                                    atr_5m=_ms_cur.atr_5m, atr_30m=_ms_cur.atr_30m,
                                    orderflow_ratio=_ms_cur.orderflow_ratio, orderflow_fill_count=_ms_cur.orderflow_fill_count,
                                    orderflow_neutralized=_ms_cur.orderflow_neutralized,
                                    liq_z=_ms_cur.liq_z, rolling_liq_volume=_ms_cur.rolling_liq_volume, rolling_liq_z=_ms_cur.rolling_liq_z,
                                    regime=_ms_cur.regime, cascade_state=_ms_cur.cascade_state,
                                    proximity_count=_ms_cur.proximity_count, proximity_usd_at_risk=_ms_cur.proximity_usd_at_risk,
                                    closest_liq_pct=_ms_cur.closest_liq_pct,
                                    bid_depth_2pct=_ms_cur.bid_depth_2pct, ask_depth_2pct=_ms_cur.ask_depth_2pct,
                                    absorption_ratio_longs=_ms_cur.absorption_ratio_longs, absorption_ratio_shorts=_ms_cur.absorption_ratio_shorts,
                                    cap_confidence=_ms_cur.cap_confidence,
                                    has_position=True, position_side=side,
                                    feed_age_ms=_ms_cur.feed_age_ms, raw_of_fills_60s=_ms_cur.raw_of_fills_60s,
                                    raw_liq_events_baseline=_ms_cur.raw_liq_events_baseline, raw_liq_rate_1m=_ms_cur.raw_liq_rate_1m,
                                    raw_burst_count=_ms_cur.raw_burst_count, raw_burst_volume=_ms_cur.raw_burst_volume,
                                    raw_rolling_history_count=_ms_cur.raw_rolling_history_count, raw_rolling_warmed_up=_ms_cur.raw_rolling_warmed_up,
                                    raw_l2_age_ms=_ms_cur.raw_l2_age_ms, raw_cap_fills=_ms_cur.raw_cap_fills,
                                )
                        else:
                            print(f"ENTRY_REJECTED: {result.symbol} - {error}")

                # --- EXIT: close ghost position (must stay in sync with controller) ---
                elif result.action.name == "EXIT":
                    if self.ghost_tracker.has_open_position(result.symbol):
                        current_price = self._get_live_price(result.symbol)
                        ok, err, trade = self.ghost_tracker.close_position(
                            symbol=result.symbol,
                            cycle_id=getattr(result, 'cycle_id', None),
                            exit_reason="MANDATE_EXIT",
                            exit_price=current_price,
                            timestamp=time.time()
                        )
                        if ok and trade:
                            hold = f"{trade.holding_duration_sec:.0f}s" if trade.holding_duration_sec else "?"
                            print(f"EXIT: MANDATE {result.symbol} @ ${trade.price:,.2f} PNL=${trade.pnl:+.2f} Hold={hold}")
                            # Emit EXIT snapshot
                            _ms_cur = self._market_state.get_current(result.symbol)
                            if _ms_cur:
                                self._market_state.emit(
                                    symbol=result.symbol,
                                    trigger=SnapshotTrigger.EXIT.value,
                                    timestamp=time.time(),
                                    price=trade.price,
                                    vwap=_ms_cur.vwap, vwap_distance=_ms_cur.vwap_distance, vwap_z=_ms_cur.vwap_z,
                                    atr_5m=_ms_cur.atr_5m, atr_30m=_ms_cur.atr_30m,
                                    orderflow_ratio=_ms_cur.orderflow_ratio, orderflow_fill_count=_ms_cur.orderflow_fill_count,
                                    orderflow_neutralized=_ms_cur.orderflow_neutralized,
                                    liq_z=_ms_cur.liq_z, rolling_liq_volume=_ms_cur.rolling_liq_volume, rolling_liq_z=_ms_cur.rolling_liq_z,
                                    regime=_ms_cur.regime, cascade_state=_ms_cur.cascade_state,
                                    proximity_count=_ms_cur.proximity_count, proximity_usd_at_risk=_ms_cur.proximity_usd_at_risk,
                                    closest_liq_pct=_ms_cur.closest_liq_pct,
                                    bid_depth_2pct=_ms_cur.bid_depth_2pct, ask_depth_2pct=_ms_cur.ask_depth_2pct,
                                    absorption_ratio_longs=_ms_cur.absorption_ratio_longs, absorption_ratio_shorts=_ms_cur.absorption_ratio_shorts,
                                    cap_confidence=_ms_cur.cap_confidence,
                                    has_position=False, position_side=None,
                                    feed_age_ms=_ms_cur.feed_age_ms, raw_of_fills_60s=_ms_cur.raw_of_fills_60s,
                                    raw_liq_events_baseline=_ms_cur.raw_liq_events_baseline, raw_liq_rate_1m=_ms_cur.raw_liq_rate_1m,
                                    raw_burst_count=_ms_cur.raw_burst_count, raw_burst_volume=_ms_cur.raw_burst_volume,
                                    raw_rolling_history_count=_ms_cur.raw_rolling_history_count, raw_rolling_warmed_up=_ms_cur.raw_rolling_warmed_up,
                                    raw_l2_age_ms=_ms_cur.raw_l2_age_ms, raw_cap_fills=_ms_cur.raw_cap_fills,
                                )
                            self._force_position_flat(result.symbol)
                            for stop_id, stop_state in list(self._trailing_stop_manager.get_all_stops().items()):
                                if stop_state.symbol == result.symbol:
                                    self._trailing_stop_manager.unregister_stop(stop_id)
                        elif not ok:
                            # Fallback: force position flat even if ghost tracker write failed
                            print(f"EXIT_FAILED: {result.symbol} ghost close error: {err}")
                            self._force_position_flat(result.symbol)
                            for stop_id, stop_state in list(self._trailing_stop_manager.get_all_stops().items()):
                                if stop_state.symbol == result.symbol:
                                    self._trailing_stop_manager.unregister_stop(stop_id)

                # --- REDUCE: partial close ---
                elif result.action.name == "REDUCE":
                    if self.ghost_tracker.has_open_position(result.symbol):
                        position = self.ghost_tracker.get_open_position(result.symbol)
                        if position:
                            reduce_qty = position.quantity * 0.5
                            hl_orderbook = self._get_hl_orderbook(result.symbol)
                            ok, err, trade = self.ghost_tracker.close_position(
                                symbol=result.symbol,
                                quantity=reduce_qty,
                                cycle_id=getattr(result, 'cycle_id', None),
                                exit_reason="PARTIAL_REDUCE",
                                orderbook=hl_orderbook
                            )
                            if ok and trade:
                                print(f"REDUCE: {result.symbol} {trade.quantity:.4f} @ ${trade.price:,.2f} PNL=${trade.pnl:+.2f}")

            # Advance execution log index (was in _process_ghost_trades)
            self._last_execution_index = len(self.executor.get_execution_log())

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
                            timestamp=mandate.timestamp,
                            source_policy=mandate.strategy_id
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

    def _handle_hl_price(
        self,
        hl_symbol: str,   # Coin (e.g., "BTC")
        price: float,     # Oracle price
        timestamp: float  # Unix timestamp in seconds
    ):
        """Handle HL oracle price — keep _mark_prices and ATR fresh.

        Oracle prices arrive every ~1s per symbol. This breaks the staleness
        chain where _mark_prices was only updated in the regime loop (every 2s,
        and only for symbols past the calculator warmup gate).

        Also feeds ATR with continuous price data so it reflects true volatility
        even when HL fills are sparse. ATR aggregates prices into 5m/30m candles
        internally, so frequent updates just give more accurate high/low/close.
        """
        symbol = hl_symbol + 'USDT'

        # Do NOT write to _current_prices here. This callback runs on a gRPC
        # daemon thread — writing to _current_prices races with the asyncio
        # event loop (regime loop + mandate processing). When the node is
        # bootstrapping old blocks, the oracle price can be stale/wrong,
        # overwriting the correct WS mid that _get_live_price() provides.
        # The regime loop updates _current_prices every 2s from _get_live_price().
        self._mark_prices[symbol] = Decimal(str(price))

        # Feed ATR calculator with oracle prices (keeps ATR fresh between sparse fills).
        # Create ATR if it doesn't exist yet — symbols with zero fills would never
        # get an ATR calculator from _handle_hl_fill alone.
        atr_calc = self._atr_calculators.get(symbol)
        if not atr_calc:
            atr_calc = MultiTimeframeATR(period=3)
            self._atr_calculators[symbol] = atr_calc
        atr_calc.update_trade(price, timestamp)

        # Feed M1 observation system so latest_hl_prices is populated.
        # Without this, get_all_hl_prices() returns {} (symbols=0 bug).
        # Throttle to 1 per symbol per 5s (oracle arrives ~1/s × 20 symbols).
        if not hasattr(self, '_last_hl_price_buffered'):
            self._last_hl_price_buffered = {}
        if timestamp - self._last_hl_price_buffered.get(symbol, 0) >= 5.0:
            self._last_hl_price_buffered[symbol] = timestamp
            self._governance_event_buffer.append(('HL_PRICE', symbol, {
                'oracle_price': price, 'mark_price': None, 'timestamp': timestamp,
            }))

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

            # 4. Track last activity for pruning (wall clock, not fill timestamp)
            # Using time.time() so feed_age_ms reflects data flow health, not node lag.
            # Previously used fill's block timestamp which conflated node lag (fills
            # flowing with old timestamps) with adapter disconnect (no fills at all).
            self._calculator_last_activity[normalized_symbol] = time.time()

            # 5. Update VWAP (needs price and volume)
            self._vwap_calculators[normalized_symbol].update(price, size, timestamp)

            # 6. Update ATR (needs price)
            self._atr_calculators[normalized_symbol].update_trade(price, timestamp)

            # 7. Update Orderflow (needs is_buyer_maker and volume)
            # HL side: "B" = buyer is taker (lifted asks) = is_buyer_maker=False
            #          "A" = seller is taker (hit bids) = is_buyer_maker=True
            is_buyer_maker = (side == "A")
            self._orderflow_calculators[normalized_symbol].update(is_buyer_maker, size, timestamp)

            # 8. Track rolling high/low (5-min window)
            # Do NOT write to _current_prices here — this runs on a gRPC daemon
            # thread and races with the asyncio event loop. The regime loop
            # updates _current_prices every 2s from _get_live_price() (WS mid).
            now = time.time()
            if normalized_symbol not in self._hl_reset_time or now - self._hl_reset_time[normalized_symbol] >= 300:
                self._hl_reset_time[normalized_symbol] = now
                self._price_highs[normalized_symbol] = price
                self._price_lows[normalized_symbol] = price
            else:
                self._price_highs[normalized_symbol] = max(self._price_highs.get(normalized_symbol, price), price)
                self._price_lows[normalized_symbol] = min(self._price_lows.get(normalized_symbol, price), price)

            # 9. Accumulate fill for order consumption primitive
            # HL side: "B" = buyer is taker (consumed asks), "A" = seller is taker (consumed bids)
            side_consumed = "ask" if side == "B" else "bid"
            if normalized_symbol not in self._hl_fill_accumulator:
                self._hl_fill_accumulator[normalized_symbol] = []
            self._hl_fill_accumulator[normalized_symbol].append((side_consumed, size, price, timestamp))

            # 9b. Buffer for governance M2 node creation (drained in regime loop)
            self._governance_event_buffer.append(('HL_FILL', normalized_symbol, {
                'side': side, 'price': price, 'size': size,
                'value_usd': price * size, 'timestamp': timestamp,
                'timestamp_ms': int(timestamp * 1000),
            }))

            # 10. Update trailing stops and check for triggers
            self._update_trailing_stops(normalized_symbol, price)

            # 11. Feed cascade sniper organic flow detector (non-liquidation fills)
            try:
                from external_policy.ep2_strategy_cascade_sniper import record_organic_trade
                trade_side = "BUY" if side == "B" else "SELL"
                trade_value = price * size  # USD value
                record_organic_trade(normalized_symbol, trade_side, trade_value, timestamp,
                                     price=price, size=size)
            except ImportError:
                pass

        except Exception as e:
            # Fail silently per constitutional rules - log but don't halt
            import traceback
            print(f"HL_FILL_ERROR: {e}", flush=True)
            traceback.print_exc()

    def _handle_hl_fill_extended(self, event):
        """Handle extended fill event with capitulation data.

        Called for ALL fills (organic + liquidation) via on_fill_extended callback.
        Feeds CapitulationTracker with dir/startPosition/closedPnl from HL node.
        """
        try:
            if not event.dir:
                return  # No direction data — skip

            timestamp = event.timestamp_ms / 1000.0
            self._capitulation_tracker.on_fill(
                symbol=event.symbol,
                dir_type=event.dir,
                closed_pnl=event.closed_pnl_float,
                start_position=event.start_position_float,
                size=event.size_float,
                timestamp=timestamp,
            )
        except Exception as e:
            print(f"HL_FILL_EXTENDED_ERROR: {e}", flush=True)

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
        - Quantity: size in base units
        - Timestamp: already in seconds from NodeBridge
        """
        try:
            # 1. Symbol normalization: HL emits "BTC", calculators use "BTCUSDT"
            normalized_symbol = f"{symbol}USDT"

            # Log liquidations for visibility
            if not hasattr(self, '_hl_liq_count'):
                self._hl_liq_count = 0
            self._hl_liq_count += 1
            liq_value = price * size
            if self._hl_liq_count <= 5 or self._hl_liq_count % 100 == 0:
                self._logger.info(f'[HL_LIQ #{self._hl_liq_count}] {symbol} {side} ${liq_value:.0f}')

            # 2. Initialize calculator for symbol if needed
            if normalized_symbol not in self._liquidation_calculators:
                self._liquidation_calculators[normalized_symbol] = LiquidationZScoreCalculator()

            # 3. Update liquidation Z-score calculator (USD value, not base units)
            # Base units (0.005 BTC) produce near-zero variance; USD ($480) gives
            # meaningful magnitude differences between assets and time windows.
            liq_usd = price * size
            self._liquidation_calculators[normalized_symbol].update(liq_usd, timestamp)

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

            # 5b. Feed rolling volume tracker (30m window for ROLLING_FADE)
            self._rolling_volume_tracker.add_event(
                normalized_symbol, side, price, size, timestamp
            )

            # 6. Track activity for calculator pruning (wall clock, not fill timestamp)
            self._calculator_last_activity[normalized_symbol] = time.time()

            # 6b. Buffer for governance M2 node creation (drained in regime loop)
            self._governance_event_buffer.append(('HL_LIQUIDATION', normalized_symbol, {
                'side': side, 'price': price,
                'liquidated_size': size, 'value': price * size,
                'timestamp': timestamp,
            }))

            # 7. Feed cascade sniper organic flow detector
            try:
                from external_policy.ep2_strategy_cascade_sniper import record_liquidation_event
                liq_value = price * size
                record_liquidation_event(normalized_symbol, order_side, liq_value, timestamp)
            except ImportError:
                pass

        except Exception as e:
            # Fail silently per constitutional rules - log but don't halt
            self._logger.debug(f"HL liquidation callback error: {e}")

    _hl_depth_logged_coins: set = set()  # Track which coins we've logged

    async def _handle_hl_orderbook(self, orderbook: Dict):
        """Feed HL L2 orderbook to observation layer as DEPTH event.

        Called by HyperliquidClient on every l2Book WebSocket update.
        Converts HL format to M1 depth array format for primitive computation
        (resting_size, order_consumption, absorption).
        """
        try:
            coin = orderbook.get('coin')
            if not coin:
                return
            symbol = f"{coin}USDT"

            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            if not bids or not asks:
                return

            # Convert to M1 depth array format: [["price", "qty"], ...]
            bid_levels = [[str(b['price']), str(b['size'])] for b in bids[:20]]
            ask_levels = [[str(a['price']), str(a['size'])] for a in asks[:20]]

            ts = orderbook.get('timestamp', time.time())
            payload = {
                'E': int(ts * 1000),
                'b': bid_levels,
                'a': ask_levels
            }

            self._obs.ingest_observation(
                timestamp=ts,
                symbol=symbol,
                event_type='DEPTH',
                payload=payload
            )

            # Feed cascade sniper for structural absorption detection
            try:
                from external_policy.ep2_strategy_cascade_sniper import record_orderbook_update
                record_orderbook_update(symbol, bids, asks, ts)
            except ImportError:
                pass
        except Exception as e:
            self._logger.warning(f"HL orderbook ingestion error for {orderbook.get('coin', '?')}: {e}")

    def _process_ghost_trades(self):
        """Deprecated: entry/exit now handled in unified path after process_cycle().
        Kept as empty method to avoid changing main loop call sites."""
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

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price — delegates to _get_live_price for WS mid priority.

        Kept for backward compatibility. All new code should use _get_live_price().
        """
        return self._get_live_price(symbol)

    def _reconcile_positions_on_startup(self):
        """Reconcile ghost tracker with positions.db on startup.

        Handles two mismatch cases:
        1. Ghost OPEN + Controller FLAT → force-close stale ghost position
        2. Controller OPEN + Ghost empty → register in ghost tracker + trailing stop
        """
        try:
            import psycopg2.extras
            from runtime.logging.pg_pool import get_conn, put_conn
            pg_conn = get_conn()
            try:
                cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(
                    "SELECT symbol, state, direction, quantity, entry_price, strategy_id "
                    "FROM positions"
                )
                rows = cur.fetchall()
            finally:
                put_conn(pg_conn)

            controller_open = {}
            for row in rows:
                if row['state'] == 'OPEN' and row['entry_price']:
                    controller_open[row['symbol']] = row

            ghost_open = self.ghost_tracker.get_open_positions()

            # Case 1: Ghost has position but controller is FLAT → stale ghost, close it
            for symbol in list(ghost_open.keys()):
                if symbol not in controller_open:
                    print(f"RECONCILE: Ghost position for {symbol} but controller is FLAT — closing stale ghost")
                    self.ghost_tracker.close_position(
                        symbol=symbol,
                        exit_reason="RECONCILE_STALE",
                        exit_price=ghost_open[symbol].entry_price,  # flat PnL
                        timestamp=time.time()
                    )

            # Case 2: Controller has OPEN position but ghost tracker empty → register
            for symbol, row in controller_open.items():
                if symbol not in ghost_open:
                    side = row['direction']
                    qty = float(row['quantity']) if row['quantity'] else 0.0
                    entry_px = float(row['entry_price'])
                    if qty <= 0 or not side:
                        continue

                    # Price sanity check: entry must be within 20% of current market
                    live_price = self._get_live_price(symbol)
                    if live_price and entry_px > 0:
                        deviation = abs(entry_px - live_price) / live_price
                        if deviation > 0.20:
                            print(f"RECONCILE: STALE {symbol} entry=${entry_px:,.2f} vs market=${live_price:,.2f} "
                                  f"(dev={deviation:.1%}) — forcing FLAT")
                            # Force controller to FLAT instead of creating bogus ghost trade
                            try:
                                pg2 = get_conn()
                                try:
                                    c2 = pg2.cursor()
                                    c2.execute(
                                        "UPDATE positions SET state='FLAT', direction=NULL, "
                                        "quantity='0', entry_price=NULL, updated_at=%s WHERE symbol=%s",
                                        (time.time(), symbol)
                                    )
                                    pg2.commit()
                                finally:
                                    put_conn(pg2)
                            except Exception as e2:
                                print(f"RECONCILE: Failed to clear stale {symbol}: {e2}")
                            continue

                    print(f"RECONCILE: Controller OPEN for {symbol} but ghost empty — registering")
                    success, error, trade = self.ghost_tracker.open_position(
                        symbol=symbol,
                        side=side,
                        quantity=qty,
                        entry_price=entry_px,
                        timestamp=time.time(),  # Use current time since we don't know original
                        policy_name=row['strategy_id']
                    )
                    if success and trade:
                        # Register trailing stop (2.5% initial stop matching balanced config)
                        initial_stop = entry_px * (0.975 if side == "LONG" else 1.025)
                        self._trailing_stop_manager.register_trailing_stop(
                            entry_order_id=trade.trade_id,
                            symbol=symbol,
                            direction=side,
                            entry_price=entry_px,
                            initial_stop_price=initial_stop,
                            config=self._trailing_stop_config
                        )
                        print(f"RECONCILE: Registered {symbol} {side} @ ${entry_px:,.2f} id={trade.trade_id}")
                    else:
                        print(f"RECONCILE: Failed to register {symbol}: {error}")

            # Case 3: Stale trailing stops for positions that no longer exist
            all_open_symbols = set(controller_open.keys()) | set(ghost_open.keys())
            stale_stops = []
            for entry_id, state in self._trailing_stop_manager.get_all_stops().items():
                if state.symbol not in all_open_symbols:
                    stale_stops.append(entry_id)
            for entry_id in stale_stops:
                print(f"RECONCILE: Removing stale trailing stop {entry_id}")
                self._trailing_stop_manager.unregister_stop(entry_id)

        except Exception as e:
            print(f"RECONCILE: Error during startup reconciliation: {e}")

    def _backfill_missing_exits(self):
        """Backfill missing exit rows in ghost_trades from ghost_positions.

        When the process is killed (kill -9), BRD buffer is lost. The position
        table (ghost_positions) gets updated immediately (direct write), but
        ghost_trades exit rows are lost. This method detects the mismatch and
        writes the missing exit rows on startup.
        """
        try:
            from runtime.logging.pg_pool import get_conn, put_conn
            pg_conn = get_conn()
            try:
                cur = pg_conn.cursor()
                cur.execute('''
                    SELECT trade_id, symbol, side, qty, entry_price, exit_price,
                           entry_time, exit_time, pnl, strategy_id
                    FROM ghost_positions
                    WHERE status = 'CLOSED' AND exit_price IS NOT NULL
                ''')
                closed_positions = cur.fetchall()
            finally:
                put_conn(pg_conn)

            if not closed_positions:
                return

            # Flush BRD so reads reflect latest state
            self._execution_db.flush()

            # Get all entry trade_ids that have matching exit rows
            exit_rows = self._execution_db.read_sql(
                'SELECT entry_trade_id FROM ghost_trades WHERE is_entry = 0 AND entry_trade_id IS NOT NULL'
            )
            exited_entry_ids = {r[0] for r in exit_rows if r[0]}

            # Also check for recovered exits by trade_id pattern
            recovered_rows = self._execution_db.read_sql(
                "SELECT trade_id FROM ghost_trades WHERE trade_id LIKE 'recovered_exit_%'"
            )
            recovered_symbols_ts = set()
            for r in recovered_rows:
                # recovered_exit_BTCUSDT_1770706169 format
                parts = r[0].split('_')
                if len(parts) >= 3:
                    recovered_symbols_ts.add(parts[2])  # symbol

            backfilled = 0
            for row in closed_positions:
                tid, sym, side, qty, entry_px, exit_px, entry_t, exit_t, pnl, strat = row

                # Skip if exit already exists
                if tid in exited_entry_ids:
                    continue

                # Skip if already recovered
                # Check for exact exit row by looking for entry in execution.db
                entry_exists = self._execution_db.read_sql(
                    'SELECT 1 FROM ghost_trades WHERE trade_id = ? AND is_entry = 1',
                    (tid,)
                )
                if not entry_exists:
                    continue  # Entry not in execution.db either — very old position

                # Check if ANY exit row already exists for this entry
                has_exit = self._execution_db.read_sql(
                    'SELECT 1 FROM ghost_trades WHERE entry_trade_id = ? AND is_entry = 0',
                    (tid,)
                )
                if has_exit:
                    continue

                # Missing exit — backfill it
                exit_side = "BUY" if side == "SHORT" else "SELL"
                hold_dur = (exit_t - entry_t) if exit_t and entry_t else None

                # Determine exit reason from PnL
                if pnl and pnl > 0:
                    exit_reason = "TRAILING_STOP_PROFIT"
                elif pnl and pnl < 0:
                    exit_reason = "TRAILING_STOP_LOSS"
                else:
                    exit_reason = "UNKNOWN_RECOVERED"

                # Get latest balance for running total
                bal_rows = self._execution_db.read_sql(
                    'SELECT account_balance_after FROM ghost_trades ORDER BY id DESC LIMIT 1'
                )
                last_bal = float(bal_rows[0][0]) if bal_rows and bal_rows[0][0] else 1000.0
                new_bal = last_bal + (pnl or 0)

                self._execution_db.execute_sql('''
                    INSERT INTO ghost_trades
                    (trade_id, symbol, side, quantity, price, timestamp,
                     position_side, is_entry, pnl, account_balance_after,
                     exit_reason, holding_duration_sec, entry_trade_id,
                     winning_policy_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                ''', (
                    f"backfill_{tid}",
                    sym, exit_side, qty, exit_px, exit_t or time.time(),
                    side, pnl, new_bal, exit_reason,
                    hold_dur, tid, strat
                ))
                backfilled += 1
                pnl_str = f"${pnl:+.2f}" if pnl else "$0.00"
                print(f"BACKFILL: {tid} {sym} {side} exit@{exit_px:,.2f} pnl={pnl_str} hold={hold_dur:.0f}s")

            if backfilled > 0:
                self._execution_db.flush()
                print(f"BACKFILL: Recovered {backfilled} missing exit rows in execution.db")

        except Exception as e:
            print(f"BACKFILL: Error during exit backfill: {e}")
            import traceback
            traceback.print_exc()

    def _force_position_flat(self, symbol: str):
        """Set position to FLAT in positions table."""
        try:
            from runtime.logging.pg_pool import get_conn, put_conn
            pg_conn = get_conn()
            try:
                pg_conn.cursor().execute(
                    "UPDATE positions SET state = 'FLAT', direction = NULL, quantity = '0', "
                    "entry_price = NULL, strategy_id = NULL, entry_context = NULL "
                    "WHERE symbol = %s",
                    (symbol,)
                )
                pg_conn.commit()
            finally:
                put_conn(pg_conn)
        except Exception as e:
            print(f"WARN: _force_position_flat({symbol}) failed: {e}")

    def _recovered_exit(self, symbol: str, price: float, entry_id: str,
                        direction: str, entry_price: float, exit_reason: str):
        """Crash-recovery exit for positions in positions.db but not in ghost tracker.

        Used when ghost_tracker.close_position() fails because position was
        opened before the unified path (or after a restart without reconciliation).
        """
        try:
            from runtime.logging.pg_pool import get_conn, put_conn
            pg_conn = get_conn()
            try:
                cur = pg_conn.cursor()
                cur.execute(
                    "SELECT quantity FROM positions WHERE symbol = %s",
                    (symbol,)
                )
                row = cur.fetchone()
                qty = float(row[0]) if row and row[0] else 0.0
            finally:
                put_conn(pg_conn)

            # Set FLAT
            self._force_position_flat(symbol)

            # Calculate PnL
            if direction == "LONG":
                pnl = (price - entry_price) * qty
            else:
                pnl = (entry_price - price) * qty

            # Record exit to ghost_trades via BufferedResearchDatabase
            try:
                exit_side = "SELL" if direction == "LONG" else "BUY"
                now = time.time()

                # Flush pending writes so reads reflect latest state
                self._execution_db.flush()

                # Look up entry timestamp for holding duration
                holding_dur = None
                entry_rows = self._execution_db.read_sql(
                    'SELECT timestamp FROM ghost_trades WHERE trade_id = ? AND is_entry = 1',
                    (entry_id,)
                )
                if entry_rows:
                    holding_dur = now - float(entry_rows[0][0])

                # Get latest balance
                bal_rows = self._execution_db.read_sql(
                    'SELECT account_balance_after FROM ghost_trades ORDER BY id DESC LIMIT 1'
                )
                last_bal = float(bal_rows[0][0]) if bal_rows and bal_rows[0][0] else 1000.0
                new_bal = last_bal + pnl

                # Write exit row via BRD buffer
                self._execution_db.execute_sql('''
                    INSERT INTO ghost_trades
                    (trade_id, symbol, side, quantity, price, timestamp,
                     position_side, is_entry, pnl, account_balance_after,
                     exit_reason, holding_duration_sec, entry_trade_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                ''', (
                    f"recovered_exit_{symbol}_{now:.0f}",
                    symbol, exit_side, qty, price, now,
                    direction, pnl, new_bal, exit_reason,
                    holding_dur, entry_id
                ))
            except Exception as db_err:
                print(f"TRAILING: DB_WRITE_FAILED {symbol} - {db_err}")

            print(f"RECOVERED: EXIT {symbol} qty={qty:.4f} @ ${price:,.2f}, PNL: ${pnl:+.2f}, Reason: {exit_reason}")
            return True
        except Exception as e:
            print(f"TRAILING: RECOVERED_EXIT_FAILED {symbol} - {e}")
            return False

    def _get_hl_order_consumption(self, symbol: str, window_sec: float = 30.0):
        """Build OrderConsumption from accumulated HL taker fills.

        Each taker fill = size consumed from the resting book.
        Aggregates fills within window into a single OrderConsumption primitive.

        Returns:
            OrderConsumption-compatible object or None if no fills
        """
        fills = self._hl_fill_accumulator.get(symbol)
        if not fills:
            return None

        now = time.time()
        # Filter to window and trim old fills to prevent unbounded growth
        recent = [(s, sz, px, ts) for s, sz, px, ts in fills if now - ts <= window_sec]
        self._hl_fill_accumulator[symbol] = recent
        if not recent:
            return None

        # Aggregate by dominant side
        bid_consumed = sum(sz for s, sz, px, ts in recent if s == "bid")
        ask_consumed = sum(sz for s, sz, px, ts in recent if s == "ask")

        # Use the side with more consumption
        if bid_consumed >= ask_consumed:
            consumed_size = bid_consumed
            side = "bid"
        else:
            consumed_size = ask_consumed
            side = "ask"

        total_consumed = bid_consumed + ask_consumed
        latest_price = recent[-1][2]
        latest_ts = recent[-1][3]

        # Return object compatible with OrderConsumption interface
        # consumed_size = dominant side consumption, initial_size = total both sides
        # (initial_size approximation: total volume gives SLBRS the ratio denominator)
        from memory.m4_orderbook_primitives import OrderConsumption
        # OrderConsumption is frozen and only has: consumed_size, side, price_level, timestamp
        # SLBRS also checks initial_size via getattr — use a simple namespace
        class _HLOrderConsumption:
            __slots__ = ('consumed_size', 'initial_size', 'side', 'price_level', 'timestamp')
            def __init__(self, consumed_size, initial_size, side, price_level, timestamp):
                self.consumed_size = consumed_size
                self.initial_size = initial_size
                self.side = side
                self.price_level = price_level
                self.timestamp = timestamp

        return _HLOrderConsumption(
            consumed_size=consumed_size,
            initial_size=total_consumed,
            side=side,
            price_level=latest_price,
            timestamp=latest_ts
        )

    def _get_exhaust_fade_stop_config(self, symbol: str, entry_px: float, side: str):
        """Get per-coin trailing stop config for EXHAUSTION_FADE entries.

        Returns (TrailingStopConfig, initial_stop_price).
        Uses FIXED_DISTANCE mode with per-coin trail distance and hard SL.
        Calibrated from TP/SL grid backtest (11 days, 3889 cascades).
        """
        from external_policy.ep2_strategy_cascade_sniper import (
            EXHAUSTION_FADE_TRAIL_CONFIG, EXHAUSTION_FADE_DEFAULT_TRAIL
        )
        coin = symbol.replace('USDT', '').replace('USD', '')
        trail_cfg = EXHAUSTION_FADE_TRAIL_CONFIG.get(coin, EXHAUSTION_FADE_DEFAULT_TRAIL)

        sl_pct = trail_cfg['sl_bps'] / 10000.0    # e.g., 30bp = 0.003
        trail_pct = trail_cfg['trail_bps'] / 10000.0  # e.g., 8bp = 0.0008

        # Hard stop loss from entry
        if side == "LONG":
            initial_stop = entry_px * (1 - sl_pct)
        else:
            initial_stop = entry_px * (1 + sl_pct)

        activation_pct = trail_cfg['activation_bps'] / 10000.0  # e.g., 15bp = 0.0015

        config = TrailingStopConfig(
            mode=TrailingMode.FIXED_DISTANCE,
            trail_distance_pct=trail_pct,
            # Activation: trail only starts once MFE exceeds this
            # Before activation, the initial stop (hard SL at sl_bps) is the only protection
            trail_activation_pct=activation_pct,
            # Break-even: not used for exhaustion fade (activation handles it)
            break_even_trigger_pct=1.0,  # Effectively disabled (100% profit never reached)
            break_even_offset_pct=0.0,
            # Minimal update gate for tight trailing
            min_move_to_update_pct=0.0002,  # 0.02% = 2bp
            min_move_atr_fraction=0.05,
        )

        print(f"EXHAUST_FADE STOP: {symbol} {side} @ ${entry_px:,.2f} "
              f"SL={trail_cfg['sl_bps']}bp trail={trail_cfg['trail_bps']}bp "
              f"act={trail_cfg['activation_bps']}bp initial_stop=${initial_stop:,.2f}")

        return config, initial_stop

    def _get_rolling_fade_stop_config(self, symbol: str, entry_px: float, side: str):
        """Get trailing stop config for ROLLING_FADE entries.

        Returns (TrailingStopConfig, initial_stop_price).
        Uses FIXED_DISTANCE mode: 0.5% activation, 0.20% trail, 0.50% hard SL.
        Calibrated from backtest (11 days, 91% WR, +0.56% mean).
        """
        from external_policy.ep2_strategy_cascade_sniper import ROLLING_FADE_TRAIL_CONFIG
        cfg = ROLLING_FADE_TRAIL_CONFIG
        sl_pct = cfg['sl_pct']
        trail_pct = cfg['trail_pct']
        activation_pct = cfg['activation_pct']

        # Hard stop loss from entry
        if side == "LONG":
            initial_stop = entry_px * (1 - sl_pct)
        else:
            initial_stop = entry_px * (1 + sl_pct)

        config = TrailingStopConfig(
            mode=TrailingMode.FIXED_DISTANCE,
            trail_distance_pct=trail_pct,
            trail_activation_pct=activation_pct,
            break_even_trigger_pct=1.0,  # Disabled
            break_even_offset_pct=0.0,
            min_move_to_update_pct=0.0002,
            min_move_atr_fraction=0.05,
        )

        print(f"ROLLING_FADE STOP: {symbol} {side} @ ${entry_px:,.2f} "
              f"SL={sl_pct*100:.1f}% trail={trail_pct*100:.2f}% "
              f"act={activation_pct*100:.1f}% initial_stop=${initial_stop:,.2f}")

        return config, initial_stop

    def _update_trailing_stops(self, symbol: str, price: float):
        """Update trailing stops for symbol and check for triggers.

        Called on each price update. If a trailing stop is hit, closes the ghost position.
        """
        try:
            # Get 5m ATR for this symbol (used by ATR_PROGRESSIVE mode)
            atr_value = None
            atr_calc = self._atr_calculators.get(symbol)
            if atr_calc:
                atr_value = atr_calc.get_atr_5m()

            # Orderflow for stop tightening (adverse flow = tighter stop)
            orderflow = None
            orderflow_calc = self._orderflow_calculators.get(symbol)
            if orderflow_calc:
                orderflow = (
                    orderflow_calc.get_imbalance_60s()
                    if self._use_node_mode
                    else orderflow_calc.get_imbalance_30s()
                )

            # Update trailing stop manager with new price, ATR, and orderflow
            self._trailing_stop_manager.update_price(
                symbol, price, atr=atr_value, orderflow_imbalance=orderflow
            )

            # Check if any stops are triggered (price crossed stop level)
            # Use list() snapshot — we may unregister during iteration
            for entry_id, state in self._trailing_stop_manager.get_all_stops().items():
                if state.symbol != symbol:
                    continue

                # Guard: if position already closed (by a prior stop for same symbol), skip
                if not self.ghost_tracker.has_open_position(symbol):
                    # Stale stop — unregister and move on
                    self._trailing_stop_manager.unregister_stop(entry_id)
                    continue

                # Check if stop is triggered
                stop_triggered = False
                if state.direction == "LONG" and price <= state.current_stop_price:
                    stop_triggered = True
                elif state.direction == "SHORT" and price >= state.current_stop_price:
                    stop_triggered = True

                if stop_triggered:
                    # Determine exit reason from actual PnL
                    if state.direction == "LONG":
                        pnl_pct = (price - state.entry_price) / state.entry_price
                    else:
                        pnl_pct = (state.entry_price - price) / state.entry_price

                    if pnl_pct > 0.0005:
                        exit_reason = "TRAILING_STOP_PROFIT"
                    elif pnl_pct >= -0.0005:
                        exit_reason = "TRAILING_STOP_BE"
                    else:
                        exit_reason = "TRAILING_STOP_LOSS"

                    print(f"TRAILING: STOP HIT {symbol} @ ${price:,.2f} (stop was ${state.current_stop_price:,.2f})")

                    success, error, trade = self.ghost_tracker.close_position(
                        symbol=symbol,
                        exit_reason=exit_reason,
                        exit_price=price,
                        timestamp=time.time()
                    )

                    if success and trade:
                        pnl_str = f"${trade.pnl:+.2f}" if trade.pnl else "$0.00"
                        hold_str = f"{trade.holding_duration_sec:.0f}s" if trade.holding_duration_sec else "?"
                        print(f"EXIT: {symbol} {trade.quantity:.4f} @ ${trade.price:,.2f}, PNL: {pnl_str}, Hold: {hold_str}, Reason: {exit_reason}")
                        self._force_position_flat(symbol)
                    else:
                        recovered = self._recovered_exit(
                            symbol=symbol,
                            price=price,
                            entry_id=entry_id,
                            direction=state.direction,
                            entry_price=state.entry_price,
                            exit_reason=exit_reason
                        )
                        if not recovered:
                            print(f"TRAILING: EXIT_FAILED {symbol} - {error} (entry_id={entry_id})")

                    # Unregister ALL stops for this symbol after exit (prevents duplicate exits)
                    for sid, sstate in self._trailing_stop_manager.get_all_stops().items():
                        if sstate.symbol == symbol:
                            self._trailing_stop_manager.unregister_stop(sid)
                    break  # Only one exit per symbol per call

        except Exception as e:
            import traceback
            print(f"TRAILING: EXCEPTION in _update_trailing_stops: {e}")
            traceback.print_exc()

    def _get_hl_orderbook(self, symbol: str) -> Optional[NormalizedOrderbook]:
        """Get normalized orderbook from Hyperliquid for ghost execution.

        Args:
            symbol: Full symbol (e.g., "BTCUSDT")

        Returns:
            NormalizedOrderbook if available, None otherwise
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
            return None

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
    print("[COLLECTOR] Connecting to HL node + WebSocket streams...")
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
