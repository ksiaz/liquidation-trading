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
