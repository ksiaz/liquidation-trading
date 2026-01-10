"""
EFFCS State Machine

Implements momentum continuation strategy for EXPANSION regimes.

RULES:
- Active ONLY in EXPANSION regime
- Never fade price (only trade WITH impulse)
- Pullback ≤ 30% of impulse
- Volume decreases during pullback
- Single entry per impulse
"""

from typing import Optional, List
from collections import deque
from enum import Enum
from dataclasses import dataclass
import sys
sys.path.append('d:/liquidation-trading')

# LOCAL: RegimeType enum (copied to avoid masterframe import cascade)
class RegimeType(Enum):
    """Regime classification types (local copy for C9 isolation)."""
    DISABLED = "DISABLED"
    SIDEWAYS = "SIDEWAYS"
    EXPANSION = "EXPANSION"

# LOCAL: DerivedMetrics stub (minimal interface for C9 isolation)
@dataclass
class DerivedMetrics:
    """Minimal metrics interface (local copy for C9 isolation)."""
    atr_5m: Optional[float] = None
    taker_buy_volume_30s: Optional[float] = None
    taker_sell_volume_30s: Optional[float] = None
    liquidation_zscore: Optional[float] = None
    oi_delta: Optional[float] = None

from .types import (
    EFFCSState,
    ImpulseDirection,
    Impulse,
    Pullback,
    EFFCSSetup,
    Position,
)


class EFFCSStateMachine:
    """
    EFFCS strategy state machine.
    
    INVARIANT: Active ONLY in EXPANSION regime.
    INVARIANT: Never fade price direction.
    INVARIANT: Single entry per impulse.
    """
    
    # Impulse detection
    MIN_DISPLACEMENT_ATR_MULTIPLIER = 0.5
    MIN_LIQ_ZSCORE = 2.5
    MIN_OI_CONTRACTION = -1000.0
    
    # Pullback thresholds
    MAX_PULLBACK_DEPTH_PERCENT = 30.0
    
    # Risk management
    STOP_LOSS_ATR_MULTIPLIER = 1.0
    TAKE_PROFIT_ATR_MULTIPLIER = 2.0
    
    # Price tracking
    PRICE_HISTORY_SIZE = 50
    
    def __init__(self):
        """Initialize state machine."""
        self.state = EFFCSState.DISABLED
        self.current_impulse: Optional[Impulse] = None
        self.current_pullback: Optional[Pullback] = None
        self.current_setup: Optional[EFFCSSetup] = None
        self.current_position: Optional[Position] = None
        
        # Track recent prices for impulse detection
        self.price_history: deque = deque(maxlen=self.PRICE_HISTORY_SIZE)
        self.time_history: deque = deque(maxlen=self.PRICE_HISTORY_SIZE)
        self.volume_history: deque = deque(maxlen=self.PRICE_HISTORY_SIZE)
        
        # Impulse tracking
        self.impulse_start_idx: Optional[int] = None
        self.pullback_start_time: Optional[float] = None
    
    def update(
        self,
        regime: RegimeType,
        current_price: float,
        metrics: DerivedMetrics,
        current_time: float
    ) -> Optional[str]:
        """
        Update state machine.
        
        Args:
            regime: Current regime
            current_price: Current mid-price
            metrics: Derived metrics
            current_time: Current timestamp
        
        Returns:
            Trade signal ('ENTER', 'EXIT', or None)
        
        RULE: Check regime first - abort if not EXPANSION.
        RULE: Never fade price direction.
        """
        # Update price history
        self.price_history.append(current_price)
        self.time_history.append(current_time)
        
        # Get current volume (30s taker buy + sell)
        if metrics.taker_buy_volume_30s and metrics.taker_sell_volume_30s:
            total_volume = metrics.taker_buy_volume_30s + metrics.taker_sell_volume_30s
            self.volume_history.append(total_volume)
        
        # HARD REGIME GATE
        if regime != RegimeType.EXPANSION:
            if self.state != EFFCSState.DISABLED:
                return self._force_exit("Regime changed", current_price, current_time)
            return None
        
        # State-specific logic
        if self.state == EFFCSState.DISABLED:
            return self._handle_disabled(current_price, metrics, current_time)
        
        elif self.state == EFFCSState.IMPULSE_DETECTED:
            return self._handle_impulse_detected(current_price, metrics, current_time)
        
        elif self.state == EFFCSState.PULLBACK_MONITORING:
            return self._handle_pullback_monitoring(current_price, current_time)
        
        elif self.state == EFFCSState.ENTRY_ARMED:
            return self._handle_entry_armed(current_price, current_time)
        
        elif self.state == EFFCSState.IN_POSITION:
            return self._handle_in_position(current_price, current_time)
        
        return None
    
    def _handle_disabled(
        self,
        current_price: float,
        metrics: DerivedMetrics,
        current_time: float
    ) -> Optional[str]:
        """
        DISABLED: Look for impulse.
        
        Transition: DISABLED → IMPULSE_DETECTED
        """
        # Need enough price history
        if len(self.price_history) < 10:
            return None
        
        # Need ATR
        if not metrics.atr_5m:
            return None
        
        # Detect impulse
        impulse = self._detect_impulse(metrics)
        
        if impulse:
            self.current_impulse = impulse
            self.state = EFFCSState.IMPULSE_DETECTED
        
        return None
    
    def _handle_impulse_detected(
        self,
        current_price: float,
        metrics: DerivedMetrics,
        current_time: float
    ) -> Optional[str]:
        """
        IMPULSE_DETECTED: Wait for pullback to begin.
        
        Transition: IMPULSE_DETECTED → PULLBACK_MONITORING
        """
        if not self.current_impulse:
            return self._reset(current_price, current_time)
        
        # Check if price started pulling back
        if self._pullback_started(current_price):
            self.pullback_start_time = current_time
            self.state = EFFCSState.PULLBACK_MONITORING
        
        return None
    
    def _handle_pullback_monitoring(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        PULLBACK_MONITORING: Monitor pullback depth and volume.
        
        Transition: PULLBACK_MONITORING → ENTRY_ARMED or DISABLED
        """
        if not self.current_impulse or not self.pullback_start_time:
            return self._reset(current_price, current_time)
        
        # Calculate pullback state
        pullback = self._calculate_pullback(current_price)
        
        if not pullback:
            return self._reset(current_price, current_time)
        
        # Check if pullback too deep (>30%)
        if pullback.depth_percent > self.MAX_PULLBACK_DEPTH_PERCENT:
            return self._reset(current_price, current_time)
        
        # Check if pullback ended (price resuming impulse direction)
        if self._pullback_ended(current_price):
            # Verify volume decreased
            if pullback.is_volume_decreasing():
                self.current_pullback = pullback
                self.current_setup = self._create_setup(pullback, current_time)
                self.state = EFFCSState.ENTRY_ARMED
            else:
                # Volume increased - possible reversal
                return self._reset(current_price, current_time)
        
        return None
    
    def _handle_entry_armed(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        ENTRY_ARMED: Price resumed, enter on continuation.
        
        Transition: ENTRY_ARMED → IN_POSITION
        
        RULE: Entry WITH impulse direction.
        """
        if not self.current_setup:
            return self._reset(current_price, current_time)
        
        # Check if price continuing in impulse direction
        if self._price_continuing(current_price):
            # ENTRY
            self.current_position = Position(
                setup=self.current_setup,
                entry_time=current_time,
                entry_price=current_price,
                current_pnl=0.0,
                is_active=True
            )
            self.state = EFFCSState.IN_POSITION
            return "ENTER"
        
        return None
    
    def _handle_in_position(
        self,
        current_price: float,
        current_time: float
    ) -> Optional[str]:
        """
        IN_POSITION: Monitor stop/target.
        
        Transition: IN_POSITION → DISABLED
        """
        if not self.current_position or not self.current_setup:
            return self._reset(current_price, current_time)
        
        # Update P&L
        self.current_position.update_pnl(current_price)
        
        # Check stop loss
        if self._stop_hit(current_price):
            return self._exit_position("Stop loss hit", current_price, current_time)
        
        # Check take profit
        if self._target_hit(current_price):
            return self._exit_position("Take profit hit", current_price, current_time)
        
        return None
    
    def _detect_impulse(self, metrics: DerivedMetrics) -> Optional[Impulse]:
        """
        Detect impulse from recent price action.
        
        Returns:
            Impulse if detected, None otherwise
        
        RULE: Displacement ≥ 0.5 × ATR.
        RULE: Liq spike ≥ 2.5 OR OI contraction < -1000.
        """
        if len(self.price_history) < 10:
            return None
        
        prices = list(self.price_history)
        times = list(self.time_history)
        
        # Find swing low and high in recent history
        swing_low_idx = prices.index(min(prices[-20:]))
        swing_high_idx = prices.index(max(prices[-20:]))
        
        # Determine direction
        if swing_high_idx > swing_low_idx:
            # Bullish impulse (low to high)
            direction = ImpulseDirection.BULLISH
            start_price = prices[swing_low_idx]
            end_price = prices[swing_high_idx]
            start_time = times[swing_low_idx]
            end_time = times[swing_high_idx]
        else:
            # Bearish impulse (high to low)
            direction = ImpulseDirection.BEARISH
            start_price = prices[swing_high_idx]
            end_price = prices[swing_low_idx]
            start_time = times[swing_high_idx]
            end_time = times[swing_low_idx]
        
        displacement = abs(end_price - start_price)
        
        # Check displacement threshold
        if displacement < self.MIN_DISPLACEMENT_ATR_MULTIPLIER * metrics.atr_5m:
            return None
        
        # Check liquidation/OI confirmation
        liq_confirmed = (metrics.liquidation_zscore is not None and 
                        metrics.liquidation_zscore >= self.MIN_LIQ_ZSCORE)
        oi_confirmed = (metrics.oi_delta is not None and 
                       metrics.oi_delta < self.MIN_OI_CONTRACTION)
        
        if not (liq_confirmed or oi_confirmed):
            return None
        
        return Impulse(
            direction=direction,
            start_price=start_price,
            end_price=end_price,
            displacement=displacement,
            start_time=start_time,
            end_time=end_time,
            liquidation_zscore=metrics.liquidation_zscore,
            oi_delta=metrics.oi_delta,
            atr=metrics.atr_5m
        )
    
    def _pullback_started(self, current_price: float) -> bool:
        """Check if pullback started from impulse."""
        if not self.current_impulse:
            return False
        
        if self.current_impulse.direction == ImpulseDirection.BULLISH:
            # Pullback = price going down from high
            return current_price < self.current_impulse.end_price
        else:  # BEARISH
            # Pullback = price going up from low
            return current_price > self.current_impulse.end_price
    
    def _calculate_pullback(self, current_price: float) -> Optional[Pullback]:
        """Calculate pullback state."""
        if not self.current_impulse:
            return None
        
        impulse_range = self.current_impulse.get_impulse_range()
        
        if self.current_impulse.direction == ImpulseDirection.BULLISH:
            retracement = self.current_impulse.end_price - current_price
        else:  # BEARISH
            retracement = current_price - self.current_impulse.end_price
        
        depth_percent = (retracement / impulse_range) * 100.0 if impulse_range > 0 else 0.0
        
        # Calculate average volumes
        impulse_volume = self._calculate_average_volume(self.impulse_start_idx or 0, len(self.volume_history))
        pullback_volume = self._calculate_average_volume(max(0, len(self.volume_history) - 5), len(self.volume_history))
        
        return Pullback(
            impulse=self.current_impulse,
            start_price=self.current_impulse.end_price,
            current_price=current_price,
            depth_percent=depth_percent,
            avg_volume=pullback_volume,
            impulse_avg_volume=impulse_volume
        )
    
    def _calculate_average_volume(self, start_idx: int, end_idx: int) -> float:
        """Calculate average volume in range."""
        if len(self.volume_history) == 0 or start_idx >= end_idx:
            return 0.0
        
        volumes = list(self.volume_history)
        if end_idx > len(volumes):
            end_idx = len(volumes)
        
        relevant_volumes = volumes[start_idx:end_idx]
        if not relevant_volumes:
            return 0.0
        
        return sum(relevant_volumes) / len(relevant_volumes)
    
    def _pullback_ended(self, current_price: float) -> bool:
        """Check if pullback ended (price resuming)."""
        if not self.current_impulse or len(self.price_history) < 3:
            return False
        
        # Check if price moving in impulse direction again
        recent_prices = list(self.price_history)[-3:]
        
        if self.current_impulse.direction == ImpulseDirection.BULLISH:
            # Price increasing again
            return recent_prices[-1] > recent_prices[-2] > recent_prices[-3]
        else:  # BEARISH
            # Price decreasing again
            return recent_prices[-1] < recent_prices[-2] < recent_prices[-3]
    
    def _price_continuing(self, current_price: float) -> bool:
        """Check if price continuing in impulse direction."""
        if not self.current_impulse or not self.current_pullback:
            return False
        
        if self.current_impulse.direction == ImpulseDirection.BULLISH:
            # Price above pullback low
            return current_price > self.current_pullback.current_price
        else:  # BEARISH
            # Price below pullback high
            return current_price < self.current_pullback.current_price
    
    def _create_setup(self, pullback: Pullback, current_time: float) -> EFFCSSetup:
        """Create trade setup."""
        impulse = pullback.impulse
        
        # Determine side
        side = 'long' if impulse.direction == ImpulseDirection.BULLISH else 'short'
        
        # Entry at current price
        entry_price = pullback.current_price
        
        # Calculate stop and target
        if side == 'long':
            stop_loss = entry_price - (self.STOP_LOSS_ATR_MULTIPLIER * impulse.atr)
            risk = entry_price - stop_loss
            take_profit = entry_price + (self.TAKE_PROFIT_ATR_MULTIPLIER * risk)
        else:  # short
            stop_loss = entry_price + (self.STOP_LOSS_ATR_MULTIPLIER * impulse.atr)
            risk = stop_loss - entry_price
            take_profit = entry_price - (self.TAKE_PROFIT_ATR_MULTIPLIER * risk)
        
        return EFFCSSetup(
            impulse=impulse,
            pullback=pullback,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            side=side,
            setup_time=current_time
        )
    
    def _stop_hit(self, price: float) -> bool:
        """Check if stop loss hit."""
        if not self.current_setup:
            return False
        
        if self.current_setup.side == 'long':
            return price <= self.current_setup.stop_loss
        else:
            return price >= self.current_setup.stop_loss
    
    def _target_hit(self, price: float) -> bool:
        """Check if take profit hit."""
        if not self.current_setup:
            return False
        
        if self.current_setup.side == 'long':
            return price >= self.current_setup.take_profit
        else:
            return price <= self.current_setup.take_profit
    
    def _exit_position(self, reason: str, price: float, timestamp: float) -> str:
        """Exit position and reset."""
        self.current_position = None
        self.state = EFFCSState.DISABLED
        self._clear_setup()
        return "EXIT"
    
    def _force_exit(self, reason: str, price: float, timestamp: float) -> Optional[str]:
        """Force exit (regime change)."""
        if self.current_position:
            return self._exit_position(reason, price, timestamp)
        
        self.state = EFFCSState.DISABLED
        self._clear_setup()
        return None
    
    def _reset(self, price: float, timestamp: float) -> None:
        """Reset state machine."""
        self.state = EFFCSState.DISABLED
        self._clear_setup()
        return None
    
    def _clear_setup(self) -> None:
        """Clear all setup state."""
        self.current_impulse = None
        self.current_pullback = None
        self.current_setup = None
        self.impulse_start_idx = None
        self.pullback_start_time = None
    
    def get_state(self) -> EFFCSState:
        """Get current state."""
        return self.state
    
    def get_position(self) -> Optional[Position]:
        """Get current position."""
        return self.current_position
    
    def get_setup(self) -> Optional[EFFCSSetup]:
        """Get current setup."""
        return self.current_setup
    
    def reset(self) -> None:
        """Hard reset state machine."""
        self.state = EFFCSState.DISABLED
        self._clear_setup()
        self.current_position = None
        self.price_history.clear()
        self.time_history.clear()
        self.volume_history.clear()
