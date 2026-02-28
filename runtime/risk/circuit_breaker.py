"""
HLP16: Circuit Breakers.

Automatic safety mechanisms that halt trading when dangerous conditions detected.

Circuit breakers:
1. Rapid Loss Detection - Lose too much too fast
2. Abnormal Price Movement - Flash crash detection
3. Strategy Malfunction - Strategy performing poorly
4. Resource Exhaustion - System overloaded

Hardenings:
- H7-A: Sample size guard for consecutive loss breaker
- H7-B: Larger window for strategy malfunction detection
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum, auto
from threading import Lock


class CircuitBreakerState(Enum):
    """State of a circuit breaker."""
    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Tripped, blocking trading
    HALF_OPEN = auto()  # Testing if safe to resume


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    # Rapid loss
    single_trade_loss_pct: float = 0.05  # 5% loss triggers
    session_loss_pct: float = 0.10  # 10% session loss triggers
    consecutive_losses: int = 5
    min_trades_for_streak: int = 10  # H7-A: Minimum trades before streak check

    # Abnormal price
    price_move_threshold_pct: float = 0.20  # 20% in 1 minute
    depth_drop_threshold_pct: float = 0.95  # 95% depth drop
    funding_spike_multiplier: float = 10.0

    # Strategy malfunction
    win_rate_drop_pct: float = 0.30  # 30% below baseline
    avg_loss_multiplier: float = 2.0  # Loss 2x avg win
    sharpe_threshold: float = 0.0
    malfunction_window_size: int = 30  # H7-B: Trades for malfunction detection (was 20)

    # Resource exhaustion
    cpu_threshold_pct: float = 95.0
    memory_threshold_pct: float = 90.0
    latency_multiplier: float = 10.0

    # Cooldown
    cooldown_seconds: float = 60.0
    manual_reset_required: bool = True


@dataclass
class CircuitBreakerEvent:
    """Record of circuit breaker trip."""
    breaker_name: str
    timestamp: int  # nanoseconds
    reason: str
    details: Dict
    state: CircuitBreakerState


class CircuitBreaker:
    """
    Base circuit breaker class.

    When tripped:
    1. Trading halts immediately
    2. Open positions can be managed (stops active)
    3. No new positions allowed
    4. May require manual reset
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig = None,
        logger: logging.Logger = None
    ):
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._state = CircuitBreakerState.CLOSED
        self._trip_time: Optional[int] = None
        self._trip_reason: Optional[str] = None
        self._events: List[CircuitBreakerEvent] = []
        self._lock = Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitBreakerState:
        return self._state

    @property
    def is_open(self) -> bool:
        """True if breaker is tripped (blocking trading)."""
        return self._state == CircuitBreakerState.OPEN

    @property
    def is_closed(self) -> bool:
        """True if breaker allows trading."""
        return self._state == CircuitBreakerState.CLOSED

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def trip(self, reason: str, details: Dict = None):
        """Trip the circuit breaker."""
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                return  # Already tripped

            self._state = CircuitBreakerState.OPEN
            self._trip_time = self._now_ns()
            self._trip_reason = reason

            event = CircuitBreakerEvent(
                breaker_name=self._name,
                timestamp=self._trip_time,
                reason=reason,
                details=details or {},
                state=CircuitBreakerState.OPEN
            )
            self._events.append(event)

            self._logger.error(
                f"CIRCUIT BREAKER TRIPPED: {self._name} - {reason}"
            )

    def reset(self, manual: bool = False):
        """Reset the circuit breaker."""
        with self._lock:
            if self._config.manual_reset_required and not manual:
                self._logger.warning(
                    f"Circuit breaker {self._name} requires manual reset"
                )
                return False

            self._state = CircuitBreakerState.CLOSED
            self._trip_time = None
            self._trip_reason = None

            self._logger.info(f"Circuit breaker {self._name} reset")
            return True

    def check(self) -> bool:
        """Check if trading is allowed. Override in subclasses."""
        return self.is_closed

    def get_events(self) -> List[CircuitBreakerEvent]:
        """Get list of breaker events."""
        return list(self._events)


class DataFreshnessBreaker(CircuitBreaker):
    """
    Trips when node data actually stops flowing. Auto-resets when data resumes.

    Staleness checks (evaluated every regime cycle ~2s):
    1. gRPC disconnected: bridge.is_connected == False
    2. Fill stale: no fills for 300s
    3. Price stale: no prices for 60s

    Adapter's STALE status is intentionally NOT checked — it uses block
    timestamps which lag behind wall clock on non-validator nodes even when
    data is flowing normally (false trips every ~5 min).

    When tripped: blocks new entries, exits always permitted.
    Anti-flap: requires N consecutive healthy evaluations to close.
    Startup grace: skips evaluation for first 30s.
    """

    _RESET_THRESHOLD = 3       # consecutive healthy checks to close
    _STARTUP_GRACE_SEC = 30.0  # skip checks for first 30s
    _PRICE_STALE_SEC = 60.0    # no prices for 60s → trip
    _FILL_STALE_SEC = 300.0    # no fills for 5 min → trip

    def __init__(self, name: str = "data-freshness", logger: logging.Logger = None):
        config = CircuitBreakerConfig(manual_reset_required=False)
        super().__init__(name, config, logger)
        self._created_at = time.time()
        self._consecutive_healthy = 0

    def evaluate(self, bridge) -> None:
        """Evaluate data freshness from node bridge. Call every regime cycle."""
        now = time.time()

        # Startup grace — don't trip before first data arrives
        if now - self._created_at < self._STARTUP_GRACE_SEC:
            return

        reason = self._check_staleness(bridge, now)
        if reason:
            self._consecutive_healthy = 0
            if not self.is_open:
                self.trip(reason)
        else:
            self._consecutive_healthy += 1
            if self.is_open and self._consecutive_healthy >= self._RESET_THRESHOLD:
                self._logger.info(
                    f"Data freshness restored after {self._RESET_THRESHOLD} healthy checks"
                )
                self.reset(manual=True)  # manual=True bypasses the flag check
                self._consecutive_healthy = 0

    def _check_staleness(self, bridge, now: float) -> Optional[str]:
        """Return trip reason string, or None if healthy.

        Trust actual data flow over adapter status. The adapter reports STALE
        based on block timestamps which lag behind wall clock on non-validator
        nodes even when data is flowing normally. If fills arrived recently,
        the node is working regardless of what the adapter thinks.
        """
        if not bridge.is_connected:
            return "gRPC disconnected"

        metrics = bridge.get_metrics()
        last_price = metrics.get('last_price_time', 0)
        last_fill = metrics.get('last_fill_time', 0)

        # Data flow checks — these prove the node is actually producing data
        if last_fill > 0 and (now - last_fill) > self._FILL_STALE_SEC:
            return f"no fills for {now - last_fill:.0f}s"
        elif last_fill == 0 and (now - self._created_at) > self._FILL_STALE_SEC:
            # Never received any fills after startup grace — fill stream may be dead
            return "no fills ever received"

        # Only check price staleness if fills are also stale.
        # Prices come from replica_cmds (oracle) which may not exist on all nodes.
        # Fills prove the node is alive — if fills flow, price absence is not fatal
        # (WS allMids provides prices independently).
        fills_healthy = last_fill > 0 and (now - last_fill) <= self._FILL_STALE_SEC
        if not fills_healthy:
            if last_price > 0 and (now - last_price) > self._PRICE_STALE_SEC:
                return f"no prices for {now - last_price:.0f}s"
            elif last_price == 0 and (now - self._created_at) > self._PRICE_STALE_SEC:
                return "no prices ever received"

        return None

    def allows_entry(self) -> bool:
        return self.is_closed

    def allows_exit(self) -> bool:
        return True


class RapidLossBreaker(CircuitBreaker):
    """
    Triggers when losses accumulate too quickly.

    Conditions:
    - Single trade loss > 5% of capital
    - Session loss > 10% of capital
    - 5 consecutive losses
    """

    def __init__(self, config: CircuitBreakerConfig = None, logger: logging.Logger = None):
        super().__init__("rapid_loss", config, logger)
        self._session_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._capital: float = 0.0
        self._total_trades: int = 0  # H7-A: Track total trades for sample guard

    def set_capital(self, capital: float):
        """Set current capital for threshold calculations."""
        self._capital = capital

    def record_trade(self, pnl: float):
        """Record a trade result."""
        if self._capital <= 0:
            return

        self._session_pnl += pnl
        self._total_trades += 1  # H7-A: Track total trades

        # Check single trade loss
        loss_pct = abs(pnl) / self._capital if pnl < 0 else 0
        if loss_pct > self._config.single_trade_loss_pct:
            self.trip(
                f"Single trade loss {loss_pct*100:.1f}% exceeds {self._config.single_trade_loss_pct*100:.1f}%",
                {'pnl': pnl, 'loss_pct': loss_pct}
            )
            return

        # Check session loss
        session_loss_pct = abs(self._session_pnl) / self._capital if self._session_pnl < 0 else 0
        if session_loss_pct > self._config.session_loss_pct:
            self.trip(
                f"Session loss {session_loss_pct*100:.1f}% exceeds {self._config.session_loss_pct*100:.1f}%",
                {'session_pnl': self._session_pnl, 'loss_pct': session_loss_pct}
            )
            return

        # Track consecutive losses
        if pnl < 0:
            self._consecutive_losses += 1
            # H7-A: Only check streak after minimum trades (prevents false trips)
            if (self._consecutive_losses >= self._config.consecutive_losses and
                    self._total_trades >= self._config.min_trades_for_streak):
                self.trip(
                    f"{self._consecutive_losses} consecutive losses",
                    {'consecutive_losses': self._consecutive_losses, 'total_trades': self._total_trades}
                )
        else:
            self._consecutive_losses = 0

    def reset_session(self):
        """Reset session tracking (call at start of new session)."""
        self._session_pnl = 0.0
        self._consecutive_losses = 0
        self._total_trades = 0  # H7-A: Reset trade count


class AbnormalPriceBreaker(CircuitBreaker):
    """
    Triggers on abnormal price movements (flash crash detection).

    Conditions:
    - Price moves > 20% in < 1 minute
    - Orderbook depth drops > 95%
    - Funding rate spikes > 10x normal
    """

    def __init__(self, config: CircuitBreakerConfig = None, logger: logging.Logger = None):
        super().__init__("abnormal_price", config, logger)
        self._price_history: Dict[str, List[tuple]] = {}  # symbol -> [(ts, price)]
        self._normal_funding: Dict[str, float] = {}  # symbol -> baseline funding

    def record_price(self, symbol: str, price: float, timestamp: int = None):
        """Record a price update."""
        ts = timestamp or self._now_ns()

        if symbol not in self._price_history:
            self._price_history[symbol] = []

        self._price_history[symbol].append((ts, price))

        # Keep only last 2 minutes
        cutoff = ts - 120_000_000_000
        self._price_history[symbol] = [
            (t, p) for t, p in self._price_history[symbol] if t > cutoff
        ]

        # Check for rapid movement
        if len(self._price_history[symbol]) >= 2:
            oldest_ts, oldest_price = self._price_history[symbol][0]
            time_diff_ns = ts - oldest_ts

            if time_diff_ns <= 60_000_000_000:  # Within 1 minute
                if oldest_price > 0:
                    move_pct = abs(price - oldest_price) / oldest_price
                    if move_pct > self._config.price_move_threshold_pct:
                        self.trip(
                            f"{symbol} moved {move_pct*100:.1f}% in {time_diff_ns/1e9:.1f}s",
                            {'symbol': symbol, 'move_pct': move_pct, 'price': price}
                        )

    def check_depth(self, symbol: str, current_depth: float, normal_depth: float):
        """Check if depth dropped abnormally."""
        if normal_depth <= 0:
            return

        drop_pct = 1 - (current_depth / normal_depth)
        if drop_pct > self._config.depth_drop_threshold_pct:
            self.trip(
                f"{symbol} depth dropped {drop_pct*100:.1f}%",
                {'symbol': symbol, 'current_depth': current_depth, 'normal_depth': normal_depth}
            )

    def check_funding(self, symbol: str, funding_rate: float):
        """Check if funding rate is abnormal."""
        if symbol not in self._normal_funding:
            self._normal_funding[symbol] = abs(funding_rate) if funding_rate != 0 else 0.0001
            return

        normal = self._normal_funding[symbol]
        if normal > 0:
            spike = abs(funding_rate) / normal
            if spike > self._config.funding_spike_multiplier:
                self.trip(
                    f"{symbol} funding {spike:.1f}x normal",
                    {'symbol': symbol, 'funding_rate': funding_rate, 'normal': normal}
                )


class StrategyMalfunctionBreaker(CircuitBreaker):
    """
    Triggers when a strategy performs poorly.

    Conditions:
    - Win rate drops > 30% below baseline
    - Average loss > 2x average win
    - Sharpe ratio < 0 over 20 trades
    """

    def __init__(self, config: CircuitBreakerConfig = None, logger: logging.Logger = None):
        super().__init__("strategy_malfunction", config, logger)
        self._baseline_win_rate: Dict[str, float] = {}
        self._recent_trades: Dict[str, List[float]] = {}  # strategy -> [pnl...]
        # H7-B: Use config window size (default 30, was hardcoded 20)
        self._window_size = self._config.malfunction_window_size

    def set_baseline(self, strategy_name: str, win_rate: float):
        """Set baseline win rate for a strategy."""
        self._baseline_win_rate[strategy_name] = win_rate

    def record_trade(self, strategy_name: str, pnl: float):
        """Record a trade for a strategy."""
        if strategy_name not in self._recent_trades:
            self._recent_trades[strategy_name] = []

        self._recent_trades[strategy_name].append(pnl)

        # Keep window size
        if len(self._recent_trades[strategy_name]) > self._window_size:
            self._recent_trades[strategy_name] = self._recent_trades[strategy_name][-self._window_size:]

        # Check metrics
        self._check_strategy(strategy_name)

    def _check_strategy(self, strategy_name: str):
        """Check if strategy is malfunctioning."""
        trades = self._recent_trades.get(strategy_name, [])
        if len(trades) < self._window_size:
            return

        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t < 0]

        # Win rate check
        current_win_rate = len(wins) / len(trades)
        baseline = self._baseline_win_rate.get(strategy_name, 0.5)

        if baseline > 0:
            drop = (baseline - current_win_rate) / baseline
            if drop > self._config.win_rate_drop_pct:
                self.trip(
                    f"{strategy_name} win rate dropped {drop*100:.1f}%",
                    {'strategy': strategy_name, 'current': current_win_rate, 'baseline': baseline}
                )
                return

        # Average loss vs win check
        if wins and losses:
            avg_win = sum(wins) / len(wins)
            avg_loss = abs(sum(losses) / len(losses))

            if avg_win > 0 and avg_loss > avg_win * self._config.avg_loss_multiplier:
                self.trip(
                    f"{strategy_name} avg loss {avg_loss/avg_win:.1f}x avg win",
                    {'strategy': strategy_name, 'avg_win': avg_win, 'avg_loss': avg_loss}
                )
                return

        # Sharpe check
        if len(trades) >= self._window_size:
            import statistics
            mean_pnl = statistics.mean(trades)
            std_pnl = statistics.stdev(trades) if len(trades) > 1 else 1
            sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0

            if sharpe < self._config.sharpe_threshold:
                self.trip(
                    f"{strategy_name} Sharpe {sharpe:.2f} below threshold",
                    {'strategy': strategy_name, 'sharpe': sharpe}
                )


class ResourceExhaustionBreaker(CircuitBreaker):
    """
    Triggers when system resources are exhausted.

    Conditions:
    - CPU > 95% for 30 seconds
    - Memory > 90%
    - Latency p99 > 10x baseline
    """

    def __init__(self, config: CircuitBreakerConfig = None, logger: logging.Logger = None):
        super().__init__("resource_exhaustion", config, logger)
        self._cpu_samples: List[tuple] = []  # [(ts, pct)]
        self._baseline_latency: float = 0.0

    def record_cpu(self, cpu_pct: float, timestamp: int = None):
        """Record CPU usage."""
        ts = timestamp or self._now_ns()
        self._cpu_samples.append((ts, cpu_pct))

        # Keep last 60 seconds
        cutoff = ts - 60_000_000_000
        self._cpu_samples = [(t, p) for t, p in self._cpu_samples if t > cutoff]

        # Check if CPU high for 30+ seconds
        recent = [(t, p) for t, p in self._cpu_samples if t > ts - 30_000_000_000]
        if len(recent) >= 3:  # At least 3 samples
            avg_cpu = sum(p for _, p in recent) / len(recent)
            if avg_cpu > self._config.cpu_threshold_pct:
                self.trip(
                    f"CPU {avg_cpu:.1f}% for 30s",
                    {'avg_cpu': avg_cpu}
                )

    def check_memory(self, memory_pct: float):
        """Check memory usage."""
        if memory_pct > self._config.memory_threshold_pct:
            self.trip(
                f"Memory {memory_pct:.1f}% exceeds threshold",
                {'memory_pct': memory_pct}
            )

    def set_baseline_latency(self, latency_ms: float):
        """Set baseline latency."""
        self._baseline_latency = latency_ms

    def check_latency(self, latency_ms: float):
        """Check latency against baseline."""
        if self._baseline_latency > 0:
            multiplier = latency_ms / self._baseline_latency
            if multiplier > self._config.latency_multiplier:
                self.trip(
                    f"Latency {latency_ms:.1f}ms ({multiplier:.1f}x baseline)",
                    {'latency_ms': latency_ms, 'baseline': self._baseline_latency}
                )


@dataclass
class KillSwitchState:
    """
    Persistent kill switch state.

    Survives restarts via database storage.
    """
    triggered: bool
    trigger_ts_ns: Optional[int]
    trigger_reason: Optional[str]
    manual_override_required: bool


class PersistentKillSwitch:
    """
    Kill switch that survives restarts.

    Uses database for state persistence.
    Requires explicit operator confirmation to reset.
    """

    CONFIRMATION_PHRASE = "CONFIRM KILL SWITCH RESET"

    def __init__(
        self,
        db=None,  # ResearchDatabase
        logger: logging.Logger = None,
    ):
        """
        Initialize persistent kill switch.

        Args:
            db: ResearchDatabase instance for persistence
            logger: Logger instance
        """
        self._db = db
        self._logger = logger or logging.getLogger(__name__)
        self._lock = Lock()

        # In-memory state (loaded from DB)
        self._state = self._load_state()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _load_state(self) -> KillSwitchState:
        """Load state from database."""
        if self._db is None:
            return KillSwitchState(
                triggered=False,
                trigger_ts_ns=None,
                trigger_reason=None,
                manual_override_required=True,
            )

        try:
            row = self._db.get_kill_switch_state()
            if row is None:
                return KillSwitchState(
                    triggered=False,
                    trigger_ts_ns=None,
                    trigger_reason=None,
                    manual_override_required=True,
                )

            return KillSwitchState(
                triggered=bool(row.get('triggered', 0)),
                trigger_ts_ns=row.get('trigger_ts_ns'),
                trigger_reason=row.get('trigger_reason'),
                manual_override_required=bool(row.get('manual_override_required', 1)),
            )
        except Exception as e:
            self._logger.error(f"Failed to load kill switch state: {e}")
            return KillSwitchState(
                triggered=False,
                trigger_ts_ns=None,
                trigger_reason=None,
                manual_override_required=True,
            )

    def _save_state(self) -> None:
        """Save state to database."""
        if self._db is None:
            return

        try:
            self._db.set_kill_switch_state(
                triggered=self._state.triggered,
                trigger_ts_ns=self._state.trigger_ts_ns,
                trigger_reason=self._state.trigger_reason,
                manual_override_required=self._state.manual_override_required,
            )
        except Exception as e:
            self._logger.error(f"Failed to save kill switch state: {e}")

    @property
    def is_triggered(self) -> bool:
        """Check if kill switch is triggered."""
        with self._lock:
            return self._state.triggered

    @property
    def state(self) -> KillSwitchState:
        """Get current state."""
        with self._lock:
            return self._state

    def trigger(self, reason: str, ts_ns: int = None) -> None:
        """
        Trigger the kill switch.

        Args:
            reason: Reason for trigger
            ts_ns: Timestamp (uses current if None)
        """
        if ts_ns is None:
            ts_ns = self._now_ns()

        with self._lock:
            if self._state.triggered:
                self._logger.warning(f"Kill switch already triggered: {self._state.trigger_reason}")
                return

            self._state = KillSwitchState(
                triggered=True,
                trigger_ts_ns=ts_ns,
                trigger_reason=reason,
                manual_override_required=True,
            )
            self._save_state()

            self._logger.error(f"KILL SWITCH TRIGGERED: {reason}")

    def reset(self, operator_confirmation: str) -> bool:
        """
        Reset the kill switch.

        Requires exact confirmation phrase.

        Args:
            operator_confirmation: Must be CONFIRM_PHRASE

        Returns:
            True if reset successful
        """
        if operator_confirmation != self.CONFIRMATION_PHRASE:
            self._logger.warning(
                f"Invalid kill switch reset confirmation. "
                f"Expected: '{self.CONFIRMATION_PHRASE}'"
            )
            return False

        with self._lock:
            if not self._state.triggered:
                self._logger.info("Kill switch not triggered, nothing to reset")
                return True

            previous_reason = self._state.trigger_reason

            self._state = KillSwitchState(
                triggered=False,
                trigger_ts_ns=None,
                trigger_reason=None,
                manual_override_required=True,
            )
            self._save_state()

            self._logger.warning(
                f"KILL SWITCH RESET by operator. Previous reason: {previous_reason}"
            )
            return True

    def allows_trading(self) -> bool:
        """Check if trading is allowed (not triggered)."""
        return not self.is_triggered

    def allows_entry(self) -> bool:
        """Check if new position entry is allowed."""
        return not self.is_triggered

    def allows_exit(self) -> bool:
        """
        Check if position exit is allowed.

        Exits are always allowed, even when triggered.
        """
        return True

    def get_summary(self) -> Dict:
        """Get kill switch summary."""
        with self._lock:
            return {
                "triggered": self._state.triggered,
                "trigger_ts_ns": self._state.trigger_ts_ns,
                "trigger_reason": self._state.trigger_reason,
                "manual_override_required": self._state.manual_override_required,
            }


class CircuitBreakerManager:
    """
    Unified manager for all circuit breakers.

    Provides:
    - Single check_all_triggers() method
    - Integration with DegradationManager
    - Integration with failure handling modules
    - Unified reset and status
    """

    def __init__(
        self,
        config: CircuitBreakerConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or CircuitBreakerConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Initialize all breakers
        self._rapid_loss = RapidLossBreaker(self._config, self._logger)
        self._abnormal_price = AbnormalPriceBreaker(self._config, self._logger)
        self._strategy_malfunction = StrategyMalfunctionBreaker(self._config, self._logger)
        self._resource_exhaustion = ResourceExhaustionBreaker(self._config, self._logger)

        self._all_breakers = [
            self._rapid_loss,
            self._abnormal_price,
            self._strategy_malfunction,
            self._resource_exhaustion,
        ]

        # Callbacks
        self._on_trip: Optional[Callable] = None
        self._on_reset: Optional[Callable] = None

        self._lock = Lock()

    @property
    def rapid_loss(self) -> RapidLossBreaker:
        return self._rapid_loss

    @property
    def abnormal_price(self) -> AbnormalPriceBreaker:
        return self._abnormal_price

    @property
    def strategy_malfunction(self) -> StrategyMalfunctionBreaker:
        return self._strategy_malfunction

    @property
    def resource_exhaustion(self) -> ResourceExhaustionBreaker:
        return self._resource_exhaustion

    def set_trip_callback(self, callback: Callable):
        """Set callback for any breaker trip."""
        self._on_trip = callback

    def set_reset_callback(self, callback: Callable):
        """Set callback for breaker reset."""
        self._on_reset = callback

    def check_all_triggers(self) -> Optional[str]:
        """
        Check all circuit breakers.

        Returns:
            First triggered breaker name, or None if all clear
        """
        for breaker in self._all_breakers:
            if breaker.is_open:
                return breaker.name
        return None

    def is_any_tripped(self) -> bool:
        """Check if any breaker is tripped."""
        return any(b.is_open for b in self._all_breakers)

    def is_trading_allowed(self) -> bool:
        """Check if trading is allowed (no breakers tripped)."""
        return not self.is_any_tripped()

    def get_tripped_breakers(self) -> List[str]:
        """Get list of tripped breaker names."""
        return [b.name for b in self._all_breakers if b.is_open]

    def reset_all(self, manual: bool = False) -> bool:
        """
        Reset all breakers.

        Args:
            manual: Whether this is a manual reset

        Returns:
            True if all breakers reset successfully
        """
        success = True
        for breaker in self._all_breakers:
            if breaker.is_open:
                if not breaker.reset(manual):
                    success = False

        if success and self._on_reset:
            try:
                self._on_reset()
            except Exception as e:
                self._logger.error(f"Reset callback error: {e}")

        return success

    def get_summary(self) -> Dict:
        """Get summary of all breakers."""
        return {
            'any_tripped': self.is_any_tripped(),
            'trading_allowed': self.is_trading_allowed(),
            'tripped_breakers': self.get_tripped_breakers(),
            'breakers': {
                b.name: {
                    'state': b.state.name,
                    'is_open': b.is_open,
                }
                for b in self._all_breakers
            }
        }

    def get_all_events(self) -> List[CircuitBreakerEvent]:
        """Get events from all breakers."""
        events = []
        for breaker in self._all_breakers:
            events.extend(breaker.get_events())
        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp)
        return events
