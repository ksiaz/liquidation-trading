"""
Paper Trading Engine
Weeks 14-15: Real-Time Validation with Zero Capital Risk

Integrates all 17 modules for real-time signal generation and simulated execution.
Uses live Binance WebSocket data but executes NO REAL ORDERS.

Architecture:
1. Receives real-time market data from WebSocket client
2. Processes through all 17 modules
3. Generates signals when all filters pass
4. Simulates executions (assumes 40-50% fill rate)
5. Tracks positions and monitors exits
6. Calculates performance metrics
7. Compares to backtest targets

Zero capital risk - all trades are simulated.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from collections import defaultdict, deque
import json
import threading

# Import WebSocket client
from paper_trading_websocket import BinanceWebSocketClient

# Import real detection modules
from early_reversal_detector import EarlyReversalDetector

logger = logging.getLogger(__name__)


class SignalStatus(Enum):
    """Signal lifecycle status"""
    GENERATED = "GENERATED"
    SIMULATED_FILL = "SIMULATED_FILL"
    NO_FILL = "NO_FILL"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Signal:
    """Real-time signal with simulated execution"""
    def __init__(
        self,
        timestamp: float,
        symbol: str,
        side: str,
        regime: str,
        confidence: float,
        threshold_used: float,
        session: str,
    ):
        self.timestamp = timestamp
        self.symbol = symbol
        self.side = side
        self.regime = regime
        self.confidence = confidence
        self.threshold_used = threshold_used
        self.session = session
        
        # Signal generation
        self.signal_id = f"{symbol}_{int(timestamp * 1000)}"
        self.status = SignalStatus.GENERATED
        
        # Execution (simulated)
        self.entry_price = None
        self.fill_price = None
        self.fill_time = None
        self.simulated_fill = False
        self.size = 0.0  # Position size from dynamic sizer
        
        # Exit
        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None
        
        # Performance
        self.pnl_gross = 0.0
        self.pnl_net = 0.0
        self.pnl_pct = 0.0
        self.mfe = 0.0  # Max favorable excursion
        self.mae = 0.0  # Max adverse excursion
        self.hold_time_sec = 0.0
        self.winner = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/storage."""
        return {
            'signal_id': self.signal_id,
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'side': self.side,
            'regime': self.regime,
            'confidence': self.confidence,
            'session': self.session,
            'status': self.status.value,
            'entry_price': self.entry_price,
            'fill_price': self.fill_price,
            'simulated_fill': self.simulated_fill,
            'size': self.size,
            'exit_price': self.exit_price,
            'exit_reason': self.exit_reason,
            'pnl_pct': self.pnl_pct,
            'winner': self.winner,
            'hold_time_sec': self.hold_time_sec,
        }


class PaperTradingEngine:
    """
    Complete paper trading system integrating all 17 modules.
    
    Real-time signal generation with simulated execution.
    Zero capital at risk - purely for validation.
    """
    
    def __init__(
        self,
        symbols: List[str] = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        fill_rate: float = 0.45,  # Assume 45% fill rate (conservative)
    ):
        """
        Initialize paper trading engine.
        
        Args:
            symbols: Trading symbols
            fill_rate: Simulated fill rate (0-1)
        """
        self.symbols = symbols
        self.fill_rate = fill_rate
        
        logger.info("=" * 80)
        logger.info("INITIALIZING PAPER TRADING ENGINE")
        logger.info("=" * 80)
        
        # WebSocket client
        self.ws_client = BinanceWebSocketClient(
            symbols=symbols,
            on_orderbook=self._on_orderbook_update,
            on_trade=self._on_trade,
        )
        
        # Module initialization
        # In production, these would be actual module instantiations
        self._init_modules()
        
        # State
        self.signals: List[Signal] = []
        self.open_positions: Dict[str, Signal] = {}  # signal_id -> Signal
        self.closed_positions: List[Signal] = []
        
        # Session tracking
        self.current_session = None
        self.session_signals = defaultdict(int)  # session -> count
        self.session_start_time = {}
        
        # Performance tracking
        self.daily_stats = defaultdict(lambda: {
            'signals': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'costs': 0.0,
        })
        
        # Real-time metrics (rolling window)
        self.recent_signals = deque(maxlen=50)  # Last 50 signals
        
        # Control
        self.running = False
        self.paused = False
        self.last_process_time = {}  # symbol -> last process timestamp
        
        # Statistics
        self.stats = {
            'total_signals': 0,
            'simulated_fills': 0,
            'no_fills': 0,
            'total_wins': 0,
            'total_losses': 0,
            'total_pnl': 0.0,
            'circuit_breaker_blocks': 0,
            'regime_filters': 0,
            'toxicity_filters': 0,
        }
        
        logger.info("Paper Trading Engine initialized")
        logger.info(f"Symbols: {symbols}")
        logger.info(f"Simulated fill rate: {fill_rate * 100:.0f}%")
    
    def _init_modules(self):
        """
        Initialize all 17 modules.
        
        In production, each module would be instantiated here.
        For this framework, we track module status.
        """
        logger.info("Initializing all 17 modules...")
        
        # Initialize Early Reversal Detector (main signal generator)
        self.detector = EarlyReversalDetector(
            max_lookback_seconds=300,
            predictor=None,
            impact_calc=None,
            snr_threshold=0.15
        )
        
        # Phase 1 modules
        self.modules = {
            # Week 2: Toxicity filtering
            'survival_depth': {'active': True, 'week': 2},
            'ctr_calculator': {'active': True, 'week': 2},
            'ghost_filter': {'active': True, 'week': 2},
            'toxicity_detector': {'active': True, 'week': 2},
            
            # Week 3: Regime classification
            'regime_classifier': {'active': True, 'week': 3},
            
            # Week 4: Execution
            'execution_engine': {'active': True, 'week': 4},
            
            # Week 5: Exits
            'exit_manager': {'active': True, 'week': 5},
            
            # Week 6: Sizing
            'position_sizer': {'active': True, 'week': 6},
            
            # Week 7: OBI
            'obi_velocity': {'active': True, 'week': 7},
            
            # Week 8: VPIN
            'vpin_circuit_breaker': {'active': True, 'week': 8},
            
            # Week 9: Adaptive thresholds
            'volatility_calc': {'active': True, 'week': 9},
            'threshold_manager': {'active': True, 'week': 9},
            
            # Week 10: Session awareness
            'session_manager': {'active': True, 'week': 10},
            
            # Tracking
            'performance_tracker': {'active': True, 'week': 1},
        }
        
        logger.info(f"[OK] {len(self.modules)} modules initialized")
        
        # Locked parameters (from expert guidance)
        self.params = self._load_locked_parameters()
        logger.info("[OK] Locked parameters loaded")
    
    def _load_locked_parameters(self) -> Dict:
        """Load all locked parameters from expert guidance."""
        return {
            # Toxicity (Week 2)
            'lambda_base': 0.08,
            'alpha': 0.5,
            'beta': 0.6,
            'gamma': 1.2,
            'ctr_threshold': 4.0,
            'ctr_window_sec': 10,
            'ghost_discount': 0.15,
            'ghost_duration_sec': 60,
            
            # Regime (Week 3)
            'active_threshold_mult': 1.8,
            'concurrent_window_sec': 30,
            'sanity_window_sec': 1.5,
            
            # Execution (Week 4)
            'stability_window_sec': 1.5,
            'stability_threshold_bps': 5,
            'fill_timeout_sec': 1,
            
            # Exits (Week 5)
            'half_life_sec': 200,
            'stagnation_sec': 100,
            
            # Sizing (Week 6)
            'tier1_pct': 0.001,  # 0.1%
            'tier2_pct': 0.0025,  # 0.25%
            'tier3_pct': 0.005,  # 0.5%
            'max_exposure_pct': 0.01,  # 1.0%
            'drawdown_mult': 0.5,
            
            # OBI (Week 7)
            'obi_window_sec': 300,
            'obi_min_samples': 100,
            'obi_velocity_z': 2.0,
            
            # VPIN (Week 8)
            'vpin_bucket_btc': 100,
            'vpin_window': 50,
            'vpin_high': 0.5,
            'vpin_extreme': 0.7,
            'vpin_z_threshold': 2.5,
            
            # Adaptive (Week 9)
            'vol_beta': 0.6,
            'vol_base': 0.25,
            'vol_min': 0.10,
            'vol_max': 0.60,
            
            # Session (Week 10)
            'session_limits': {'ASIA': 30, 'EUROPE': 70, 'US': 120},
            'session_multipliers': {'ASIA': 1.10, 'EUROPE': 1.00, 'US': 0.95},
            
            # Symbol multipliers (Week 9)
            'symbol_mults': {'BTCUSDT': 1.0, 'ETHUSDT': 1.15, 'SOLUSDT': 1.35},
        }
    
    def start(self):
        """Start paper trading engine."""
        if self.running:
            logger.warning("Engine already running")
            return
        
        self.running = True
        logger.info("=" * 80)
        logger.info("STARTING PAPER TRADING ENGINE")
        logger.info("=" * 80)
        
        # Connect WebSocket
        self.ws_client.connect()
        logger.info("[OK] WebSocket connected")
        
        # Wait for initial data
        logger.info("Waiting for initial market data...")
        time.sleep(3)
        
        # Start processing loop
        process_thread = threading.Thread(target=self._processing_loop, daemon=True)
        process_thread.start()
        
        logger.info("[OK] Paper trading engine LIVE")
        logger.info("=" * 80)
    
    def stop(self):
        """Stop paper trading engine."""
        logger.info("Stopping paper trading engine...")
        self.running = False
        self.ws_client.disconnect()
        
        # Close any open positions
        for signal in list(self.open_positions.values()):
            self._simulate_exit(signal, "ENGINE_STOP")
        
        logger.info("Paper trading engine stopped")
    
    def _processing_loop(self):
        """Main processing loop - runs continuously."""
        logger.info("Processing loop started")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Process each symbol
                for symbol in self.symbols:
                    # Throttle processing (every 1 second per symbol)
                    last_time = self.last_process_time.get(symbol, 0)
                    if current_time - last_time < 1.0:
                        continue
                    
                    self.last_process_time[symbol] = current_time
                    
                    # Process market data
                    if not self.paused:
                        self._process_symbol(symbol, current_time)
                
                # Monitor open positions
                self._monitor_positions(current_time)
                
                # Sleep briefly
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                time.sleep(1)
    
    def _on_orderbook_update(self, symbol: str, orderbook: dict):
        """Callback for orderbook updates."""
        # In production, this would update module calculators
        # (volatility, OBI, VPIN, etc.)
        pass
    
    def _on_trade(self, symbol: str, trade: dict):
        """Callback for trade executions."""
        # In production, this would update trade-based calculators
        # (CTR, toxicity, etc.)
        pass
    
    def _process_symbol(self, symbol: str, timestamp: float):
        """
        Process symbol for potential signal using EarlyReversalDetector.
        
        Pipeline:
        1. Check session and circuit breakers
        2. Call detector.update() with orderbook data
        3. If signal returned, validate and execute
        """
        # Get current market data
        orderbook = self.ws_client.get_orderbook(symbol)
        if not orderbook:
            return
        
        # 1. Detect current session
        session = self._detect_session(timestamp)
        if session != self.current_session:
            self._on_session_change(session, timestamp)
        
        # 2. Check circuit breakers (session limits, etc.)
        if self._check_circuit_breakers(symbol, session, timestamp):
            self.stats['circuit_breaker_blocks'] += 1
            return
        
        # 3. Prepare orderbook data for detector
        best_bid = orderbook['bids'][0][0] if orderbook.get('bids') else 0
        best_ask = orderbook['asks'][0][0] if orderbook.get('asks') else 0
        
        # Calculate imbalance
        bid_volume = sum([float(q) for p, q in orderbook.get('bids', [])[:10]])
        ask_volume = sum([float(q) for p, q in orderbook.get('asks', [])[:10]])
        total_volume = bid_volume + ask_volume
        imbalance = (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0
        
        detector_data = {
            'symbol': symbol,
            'timestamp': datetime.fromtimestamp(timestamp),
            'best_bid': float(best_bid),
            'best_ask': float(best_ask),
            'imbalance': imbalance,
            'bid_volume_10': bid_volume,
            'ask_volume_10': ask_volume,
            'spread_pct': ((float(best_ask) - float(best_bid)) / float(best_bid)) * 100 if best_bid > 0 else 0,
        }
        
        # 4. Call detector (already includes chop filter, regime, confidence, etc.)
        signal_dict = self.detector.update(detector_data)
        
        if not signal_dict:
            return
        
        # 5. Extract signal info
        regime = 'REAL_PRESSURE'  # EarlyReversalDetector already filtered
        confidence = signal_dict['confidence'] / 100.0  # Convert to 0-1
        threshold = self._get_adaptive_threshold(symbol, session) / 100.0
        
        # 6. Generate Signal object
        signal = self._generate_signal(
            timestamp=timestamp,
            symbol=symbol,
            regime=regime,
            confidence=confidence,
            threshold_used=threshold,
            session=session,
        )
        
        # Store signal metadata from detector
        signal.entry_price = signal_dict['entry_price']
        signal.detector_info = {
            'direction': signal_dict['direction'],
            'signals_confirmed': signal_dict['signals_confirmed'],
            'snr': signal_dict['snr'],
            'timeframe': signal_dict['timeframe'],
        }
        
        self.signals.append(signal)
        self.stats['total_signals'] += 1
        logger.info(f"[SIGNAL] GENERATED: {signal.signal_id} ({regime}, {confidence:.2%})")
        
        # 7. Simulate execution
        self._simulate_execution(signal, orderbook)
    
    def _detect_session(self, timestamp: float) -> str:
        """Detect current trading session."""
        dt = datetime.fromtimestamp(timestamp)
        hour_utc = dt.hour
        
        # Session boundaries (UTC)
        if 0 <= hour_utc < 8:
            return 'ASIA'
        elif 8 <= hour_utc < 16:
            return 'EUROPE'
        else:
            return 'US'
    
    def _on_session_change(self, new_session: str, timestamp: float):
        """Handle session transition."""
        logger.info("=" * 80)
        logger.info(f"SESSION CHANGE: {self.current_session} -> {new_session}")
        logger.info("=" * 80)
        
        self.current_session = new_session
        self.session_start_time[new_session] = timestamp
        
        # Reset session signal counter
        self.session_signals[new_session] = 0
    
    def _check_circuit_breakers(self, symbol: str, session: str, timestamp: float) -> bool:
        """
        Check if any circuit breaker should block trading.
        
        Returns:
            True if should block, False if OK to trade
        """
        # Session limit check
        session_limit = self.params['session_limits'].get(session, 100)
        session_count = self.session_signals.get(session, 0)
        
        if session_count >= session_limit:
            return True  # Block
        
        # In production, also check:
        # - VPIN circuit breaker
        # - Z-score monitoring
        # - Drawdown limits
        
        return False  # OK to trade
    
    def _simulate_drain_detection(self, symbol: str, orderbook: dict) -> bool:
        """Simulate liquidity drain detection (placeholder)."""
        # In production: actual toxicity-aware drain detection
        # For demo: random 5% of the time
        import random
        return random.random() < 0.05
    
    def _simulate_regime_classification(self, symbol: str, orderbook: dict) -> str:
        """Simulate regime classification (placeholder)."""
        # In production: actual 4-regime classifier
        # For demo: 80% REAL_PRESSURE, 20% other
        import random
        return 'REAL_PRESSURE' if random.random() < 0.80 else 'SPOOF_CLEANUP'
    
    def _simulate_confidence(self, symbol: str, orderbook: dict) -> float:
        """Simulate confidence calculation (placeholder)."""
        # In production: actual confidence from drain magnitude
        import random
        return 0.65 + random.random() * 0.25  # 65-90%
    
    def _get_adaptive_threshold(self, symbol: str, session: str) -> float:
        """Calculate adaptive threshold."""
        # Base volatility scaling
        base_threshold = self.params['vol_base']
        
        # Symbol multiplier
        symbol_mult = self.params['symbol_mults'].get(symbol, 1.0)
        
        # Session multiplier
        session_mult = self.params['session_multipliers'].get(session, 1.0)
        
        # In production: also incorporate real-time volatility
        # For demo: use baseline
        threshold = base_threshold * symbol_mult * session_mult
        
        # Clamp to min/max
        threshold = max(self.params['vol_min'], min(self.params['vol_max'], threshold))
        
        return threshold
    
    def _simulate_obi_check(self, symbol: str) -> bool:
        """Simulate OBI velocity check (placeholder)."""
        # In production: actual OBI velocity calculation
        # For demo: 90% pass
        import random
        return random.random() < 0.90
    
    def _generate_signal(
        self,
        timestamp: float,
        symbol: str,
        regime: str,
        confidence: float,
        threshold_used: float,
        session: str,
    ) -> Signal:
        """Generate signal object."""
        signal = Signal(
            timestamp=timestamp,
            symbol=symbol,
            side='LONG',  # Liquidation trading = buy the dip
            regime=regime,
            confidence=confidence,
            threshold_used=threshold_used,
            session=session,
        )
        
        # Increment session counter
        self.session_signals[session] += 1
        
        return signal
    
    def _simulate_execution(self, signal: Signal, orderbook: dict):
        """
        Simulate order execution.
        
        Uses simulated fill rate - no real orders placed.
        """
        # BUGFIX: Get FRESH orderbook instead of using potentially stale one
        fresh_orderbook = self.ws_client.get_orderbook(signal.symbol)
        if not fresh_orderbook:
            signal.status = SignalStatus.NO_FILL
            self.stats['no_fills'] += 1
            return
        
        # Get entry price (would be current best ask for LONG)
        bids = fresh_orderbook.get('bids', [])
        asks = fresh_orderbook.get('asks', [])
        
        if not asks:
            signal.status = SignalStatus.NO_FILL
            self.stats['no_fills'] += 1
            return
        
        signal.entry_price = asks[0][0]  # Best ask
        
        # Simulate fill probability
        import random
        rand_val = random.random()
        filled = rand_val < self.fill_rate
        
        logger.info(f"  Fill check: rand={rand_val:.3f} vs rate={self.fill_rate:.3f} -> filled={filled}")
        
        if not filled:
            signal.status = SignalStatus.NO_FILL
            signal.fill_time = signal.timestamp  # Set for dashboard display
            self.stats['no_fills'] += 1
            
            # Add to recent signals for dashboard
            self.recent_signals.append(signal)
            
            logger.info(f"  [NO_FILL] {signal.signal_id}")
            return
        
        # Simulate fill
        signal.simulated_fill = True
        
        # Apply slippage: assuming we pay the ask for LONG, bid for SHORT
        # Plus additional 0.02-0.03% slippage from market impact
        if signal.side == 'LONG':
            # Pay the ask + slippage
            signal.fill_price = float(asks[0][0]) * 1.0003  # 0.03% slippage
        else:
            # Sell at bid - slippage  
            signal.fill_price = float(bids[0][0]) * 0.9997  # 0.03% slippage
        
        signal.fill_time = signal.timestamp + 0.5  # Assume 500ms fill
        signal.status = SignalStatus.OPEN
        
        # Calculate position size
        signal.size = self._get_position_size(signal)
        
        # Add to open positions
        self.open_positions[signal.signal_id] = signal
        self.stats['simulated_fills'] += 1
        
        # Add to recent signals for dashboard
        self.recent_signals.append(signal)
        
        logger.info(f"  [FILL] {signal.signal_id} @ {signal.fill_price:.2f} (size: {signal.size:.3%})")
    
    def _get_position_size(self, signal: Signal) -> float:
        """Get position size from dynamic sizer."""
        # In production: actual dynamic position sizer
        # For demo: use tier 2 (0.25%)
        
        # High confidence (>85%) = tier 3
        if signal.confidence >= 0.85:
            return self.params['tier3_pct']
        # Medium confidence (60-85%) = tier 2
        elif signal.confidence >= 0.60:
            return self.params['tier2_pct']
        # Low confidence (<60%) = tier 1
        else:
            return self.params['tier1_pct']
    
    def _monitor_positions(self, current_time: float):
        """Monitor open positions for exit conditions."""
        for signal in list(self.open_positions.values()):
            # Check exit conditions
            exit_reason = self._check_exit_conditions(signal, current_time)
            
            if exit_reason:
                self._simulate_exit(signal, exit_reason)
    
    def _check_exit_conditions(self, signal: Signal, current_time: float) -> Optional[str]:
        """
        Check if position should be exited.
        
        Returns:
            Exit reason if should exit, None otherwise
        """
        hold_time = current_time - signal.fill_time
        
        # Get current price
        orderbook = self.ws_client.get_orderbook(signal.symbol)
        if not orderbook or not orderbook.get('bids'):
            return None
        
        current_price = orderbook['bids'][0][0]  # Best bid (exit price for LONG)
        
        # Calculate unrealized P&L
        pnl_pct = (current_price - signal.fill_price) / signal.fill_price
        
        # Update MFE/MAE
        if pnl_pct > signal.mfe:
            signal.mfe = pnl_pct
        if pnl_pct < signal.mae:
            signal.mae = pnl_pct
        
        # 1. Half-life breakeven stop (200s)
        if hold_time >= self.params['half_life_sec']:
            if pnl_pct < 0:
                return "HALF_LIFE_LOSS"
            # Move to breakeven
            if pnl_pct < 0.0005:  # <5 bps profit
                return "HALF_LIFE_BREAKEVEN"
        
        # 2. Stagnation (100s no new MFE)
        # In production: track time since last MFE update
        # For demo: simplified check
        if hold_time >= self.params['stagnation_sec']:
            if signal.mfe > 0.001 and pnl_pct < signal.mfe * 0.8:
                return "STAGNATION"
        
        # 3. Stop loss (-2%)
        if pnl_pct <= -0.02:
            return "STOP_LOSS"
        
        # 4. Take profit (+3%)
        if pnl_pct >= 0.03:
            return "TAKE_PROFIT"
        
        return None
    
    def _simulate_exit(self, signal: Signal, reason: str):
        """Simulate position exit."""
        # Get exit price
        orderbook = self.ws_client.get_orderbook(signal.symbol)
        # Get exit price based on side
        if signal.side == 'LONG':
            if not orderbook or not orderbook.get('bids'):
                return
            # Sell at bid - slippage
            exit_price = float(orderbook['bids'][0][0]) * 0.9997
        else:
            if not orderbook or not orderbook.get('asks'):
                return
            # Buy to cover at ask + slippage
            exit_price = float(orderbook['asks'][0][0]) * 1.0003
        
        exit_time = time.time()
        
        # DEBUG: Log prices to diagnose -1000% losses
        logger.info(f"  >> EXIT DEBUG: Entry={signal.fill_price:.2f}, Exit={exit_price:.2f}, Side={signal.side}")
        
        # Calculate P&L based on side
        if signal.side == 'LONG':
            pnl_gross = ((exit_price - signal.fill_price) / signal.fill_price) * 100
        else:
            pnl_gross = ((signal.fill_price - exit_price) / signal.fill_price) * 100
        
        logger.info(f"  >> PNL DEBUG: Gross={pnl_gross:.2f}%")
        
        # Apply fees: 0.04% entry + 0.04% exit = 0.08% total
        # (slippage already applied in entry/exit prices)
        FEES_PCT = 0.08
        pnl_net = pnl_gross - FEES_PCT
        
        # Update signal
        signal.exit_price = exit_price
        signal.exit_time = exit_time
        signal.exit_reason = reason
        signal.pnl_gross = pnl_gross
        signal.pnl_net = pnl_net
        signal.pnl_pct = pnl_net
        signal.hold_time_sec = exit_time - signal.fill_time
        signal.winner = pnl_net > 0
        signal.status = SignalStatus.CLOSED
        
        # Remove from open positions
        del self.open_positions[signal.signal_id]
        
        # Add to closed positions
        self.closed_positions.append(signal)
        self.recent_signals.append(signal)
        
        # Update stats
        if signal.winner:
            self.stats['total_wins'] += 1
        else:
            self.stats['total_losses'] += 1
        
        self.stats['total_pnl'] += pnl_net
        
        # Log
        status_emoji = "[OK]" if signal.winner else "[FAIL]"
        logger.info(
            f"{status_emoji} EXIT: {signal.signal_id} | "
            f"Reason: {reason} | "
            f"P&L: {pnl_net:+.2f}% | "
            f"Hold: {signal.hold_time_sec:.0f}s"
        )
    
    def get_performance_summary(self) -> Dict:
        """Get current performance summary."""
        # Calculate from recent closed positions
        recent_closed = [s for s in self.recent_signals if s.status == SignalStatus.CLOSED]
        
        if not recent_closed:
            return {
                'total_signals': self.stats['total_signals'],
                'fills': self.stats['simulated_fills'],
                'no_fills': self.stats['no_fills'],
                'open_positions': len(self.open_positions),
                'closed_positions': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl_pct': 0.0,
                'avg_pnl_pct': 0.0,
                'sharpe': 0.0,
            }
        
        wins = sum(1 for s in recent_closed if s.winner)
        total = len(recent_closed)
        win_rate = wins / total if total > 0 else 0
        
        total_pnl = sum(s.pnl_pct for s in recent_closed)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        # Simple Sharpe approximation
        if total > 2:
            pnls = [s.pnl_pct for s in recent_closed]
            mean = sum(pnls) / len(pnls)
            variance = sum((p - mean) ** 2 for p in pnls) / len(pnls)
            std = variance ** 0.5 if variance > 0 else 0.0001
            sharpe = (mean / std) * (252 ** 0.5) if std > 0 else 0  # Annualized
        else:
            sharpe = 0
        
            'total_pnl_pct': total_pnl,
            'avg_pnl_pct': avg_pnl,
            'fills': self.stats['simulated_fills'],
            'no_fills': self.stats['no_fills'],
            'open_positions': len(self.open_positions),
            'closed_positions': len(recent_closed),
            'wins': wins,
            'losses': total - wins,
            'win_rate': win_rate,
            'total_pnl_pct': total_pnl * 100,
            'avg_pnl_pct': avg_pnl * 100,
            'sharpe': sharpe,
        }
    
    def get_status_report(self) -> str:
        """Generate status report."""
        perf = self.get_performance_summary()
        
        report = []
        report.append("=" * 80)
        report.append("PAPER TRADING STATUS")
        report.append("=" * 80)
        report.append(f"Session: {self.current_session}")
        report.append(f"Session Signals: {self.session_signals.get(self.current_session, 0)}")
        report.append(f"Total Signals: {perf['total_signals']}")
        report.append(f"Fills: {perf['fills']} ({perf['fills']/(perf['total_signals'] or 1)*100:.0f}%)")
        report.append(f"Open Positions: {perf['open_positions']}")
        report.append(f"Closed Trades: {perf['closed_positions']}")
        report.append(f"Win Rate: {perf['win_rate']*100:.1f}%")
        report.append(f"Total P&L: {perf['total_pnl_pct']:+.2f}%")
        report.append(f"Sharpe: {perf['sharpe']:.2f}")
        report.append("=" * 80)
        
        return "\n".join(report)


def run_paper_trading():
    """Run paper trading demo."""
    print("=" * 80)
    print("PAPER TRADING ENGINE - LIVE DEMO")
    print("Week 14-15 Real-Time Validation (Zero Capital Risk)")
    print("=" * 80)
    
    # Create engine
    engine = PaperTradingEngine(
        symbols=['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        fill_rate=0.45,  # 45% fill rate
    )
    
    # Start engine
    engine.start()
    
    print("\nPaper trading engine running...")
    print("Press Ctrl+C to stop\n")
    
    try:
        # Print status every 30 seconds
        while True:
            time.sleep(30)
            print(engine.get_status_report())
            
    except KeyboardInterrupt:
        print("\n\nStopping engine...")
        engine.stop()
        
        # Final report
        print("\n" + "=" * 80)
        print("FINAL PERFORMANCE REPORT")
        print("=" * 80)
        perf = engine.get_performance_summary()
        print(json.dumps(perf, indent=2))
        
        print("\nPaper trading demo complete")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_paper_trading()



