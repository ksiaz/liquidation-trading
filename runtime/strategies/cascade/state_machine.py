"""
HLP10: Cascade Strategy State Machine.

Liquidation Cascade Sniper.

This strategy identifies imminent liquidation cascades and
enters to profit from the rapid price movement. Uses a
two-stage arming process (PRE_ARMED -> ARMED) for better
timing.

State Flow:
    DISABLED -> SCANNING: Any regime except DISABLED
    SCANNING -> PRE_ARMED: Liquidation bands detected
    PRE_ARMED -> ARMED: Liquidity thinning confirmed
    PRE_ARMED -> SCANNING: Bands move away or conditions fail
    ARMED -> ENTERED: Cascade begins
    ARMED -> SCANNING: Timeout (2 min) or conditions invalidate
    ENTERED -> EXITED: Target/stop/cascade exhaustion
    EXITED -> COOLDOWN: Always
    COOLDOWN -> SCANNING: After 3 minutes (shorter cooldown)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set, List, Tuple

from ..base import (
    StrategyStateMachine,
    StrategyState,
    StrategyConfig,
    StrategySetup,
    Mandate,
    MandateType,
)


@dataclass
class CascadeConfig(StrategyConfig):
    """Configuration for Cascade strategy."""

    # Liquidation band detection
    liq_band_distance_pct: float = 0.02    # Within 2% of current price
    oi_concentration_threshold: float = 0.3  # 30% of OI near band

    # Pre-arm to arm (liquidity thinning)
    depth_thinning_threshold: float = 0.50  # 50% depth reduction
    thinning_window_sec: int = 60          # Within 1 minute

    # Trigger (cascade beginning)
    price_velocity_threshold: float = 0.001  # 0.1% per second toward band
    volume_spike_ratio: float = 3.0        # 3x normal volume

    # Exit parameters
    target_pct: float = 0.008              # 0.8% profit target
    stop_pct: float = 0.003                # 0.3% stop loss
    cascade_exhaustion_threshold: float = 0.5  # 50% velocity drop = exhausted
    max_hold_sec: int = 60                 # 1 minute max hold

    # Timing
    armed_timeout_sec: int = 120           # 2 minute armed timeout
    cooldown_sec: int = 180                # 3 minute cooldown (shorter for cascade)
    entry_grace_sec: int = 3               # 3 second grace period

    # Works in expansion regime
    allowed_regimes: Set[str] = field(default_factory=lambda: {'expansion', 'sideways'})


@dataclass
class CascadeSetup(StrategySetup):
    """Setup conditions for Cascade strategy."""

    # Liquidation band info
    target_liq_price: float = 0.0
    cascade_direction: str = ""  # 'long' = price falling to longs, 'short' = price rising to shorts
    oi_at_band: float = 0.0
    oi_concentration: float = 0.0

    # Liquidity state
    initial_depth: float = 0.0
    current_depth: float = 0.0
    depth_thinning_pct: float = 0.0

    # Velocity tracking
    price_velocity: float = 0.0  # Price change per second toward band

    @property
    def is_valid(self) -> bool:
        """All conditions must be met for valid setup."""
        # PRE_ARMED requires: liq_band_near, oi_concentrated
        # ARMED adds: depth_thinned
        required = ['liq_band_near', 'oi_concentrated']
        return all(self.conditions_met.get(c, False) for c in required)

    @property
    def is_fully_armed(self) -> bool:
        """Check if ready for full ARMED state."""
        return self.is_valid and self.conditions_met.get('depth_thinned', False)


class CascadeStateMachine(StrategyStateMachine):
    """
    State machine for Cascade (Sniper) strategy.

    Trades liquidation cascades with two-stage arming.
    """

    def __init__(
        self,
        symbol: str,
        config: CascadeConfig = None,
        logger: logging.Logger = None,
    ):
        super().__init__(
            name="cascade",
            symbol=symbol,
            config=config or CascadeConfig(),
            logger=logger,
        )
        self._config: CascadeConfig  # Type hint

        # Cascade-specific tracking
        self._depth_history: List[Tuple[datetime, float]] = []
        self._price_history: List[Tuple[datetime, float]] = []
        self._peak_velocity: float = 0.0

    def _use_pre_armed(self) -> bool:
        """Cascade uses PRE_ARMED state."""
        return True

    def _check_arm_conditions(self, market_state: Dict[str, Any]) -> Optional[CascadeSetup]:
        """
        Check if conditions for pre-arming are met.

        Requires:
        - Liquidation bands detected within threshold
        - OI concentrated near those bands
        """
        current_price = market_state.get('mark_price', 0)
        liq_bands = market_state.get('liquidation_bands', {})
        oi = market_state.get('open_interest', 0)

        if not current_price or not liq_bands:
            return None

        # Check liquidation bands
        long_liq = liq_bands.get('long_liq_price', 0)
        short_liq = liq_bands.get('short_liq_price', float('inf'))
        oi_at_long = liq_bands.get('oi_at_long_liq', 0)
        oi_at_short = liq_bands.get('oi_at_short_liq', 0)

        conditions = {}
        cascade_direction = ""
        target_liq_price = 0
        oi_at_band = 0
        oi_concentration = 0

        # Check if near long liquidation band (price falling toward longs)
        if long_liq > 0:
            distance_to_long = (current_price - long_liq) / current_price
            near_long = distance_to_long <= self._config.liq_band_distance_pct

            if near_long and oi > 0:
                oi_concentration = oi_at_long / oi
                if oi_concentration >= self._config.oi_concentration_threshold:
                    cascade_direction = 'long'
                    target_liq_price = long_liq
                    oi_at_band = oi_at_long
                    conditions['liq_band_near'] = True
                    conditions['oi_concentrated'] = True

        # Check if near short liquidation band (price rising toward shorts)
        if short_liq < float('inf') and not conditions.get('liq_band_near'):
            distance_to_short = (short_liq - current_price) / current_price
            near_short = distance_to_short <= self._config.liq_band_distance_pct

            if near_short and oi > 0:
                oi_concentration = oi_at_short / oi
                if oi_concentration >= self._config.oi_concentration_threshold:
                    cascade_direction = 'short'
                    target_liq_price = short_liq
                    oi_at_band = oi_at_short
                    conditions['liq_band_near'] = True
                    conditions['oi_concentrated'] = True

        if not conditions.get('liq_band_near') or not conditions.get('oi_concentrated'):
            return None

        # Get depth for tracking
        if cascade_direction == 'long':
            current_depth = market_state.get('bid_depth_1pct', 0)
        else:
            current_depth = market_state.get('ask_depth_1pct', 0)

        setup = CascadeSetup(
            symbol=self._symbol,
            detected_at=datetime.now(),
            conditions_met=conditions,
            metrics={
                'oi_concentration': oi_concentration,
                'distance_to_band': abs(current_price - target_liq_price) / current_price,
            },
            target_liq_price=target_liq_price,
            cascade_direction=cascade_direction,
            oi_at_band=oi_at_band,
            oi_concentration=oi_concentration,
            initial_depth=current_depth,
            current_depth=current_depth,
        )

        return setup

    def _check_pre_arm_to_arm(self, market_state: Dict[str, Any]) -> bool:
        """Check if should advance from PRE_ARMED to ARMED (liquidity thinning)."""
        if not self._setup or not isinstance(self._setup, CascadeSetup):
            return False

        # Get current depth on relevant side
        if self._setup.cascade_direction == 'long':
            current_depth = market_state.get('bid_depth_1pct', 0)
        else:
            current_depth = market_state.get('ask_depth_1pct', 0)

        # Track depth history
        now = datetime.now()
        self._depth_history.append((now, current_depth))

        # Clean old history
        cutoff = now - timedelta(seconds=self._config.thinning_window_sec)
        self._depth_history = [(t, d) for t, d in self._depth_history if t > cutoff]

        # Check for thinning
        if len(self._depth_history) >= 2 and self._setup.initial_depth > 0:
            thinning_pct = 1 - (current_depth / self._setup.initial_depth)
            self._setup.current_depth = current_depth
            self._setup.depth_thinning_pct = thinning_pct

            if thinning_pct >= self._config.depth_thinning_threshold:
                self._setup.conditions_met['depth_thinned'] = True
                return True

        return False

    def _check_pre_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Check if PRE_ARMED conditions are invalidated."""
        if not self._setup or not isinstance(self._setup, CascadeSetup):
            return True

        current_price = market_state.get('mark_price', 0)
        if not current_price:
            return False

        # Invalidate if price moved away from liq band
        distance = abs(current_price - self._setup.target_liq_price) / current_price
        if distance > self._config.liq_band_distance_pct * 2:  # Moved 2x threshold away
            return True

        return False

    def _check_trigger_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if trigger conditions for entry are met.

        Trigger when:
        - Price velocity toward liq band exceeds threshold
        - Volume spikes confirming cascade beginning
        """
        if not self._setup or not isinstance(self._setup, CascadeSetup):
            return None

        current_price = market_state.get('mark_price', 0)
        current_volume = market_state.get('volume_1m', 0)
        avg_volume = market_state.get('avg_volume_1m', current_volume)

        if not current_price:
            return None

        # Track price for velocity
        now = datetime.now()
        self._price_history.append((now, current_price))

        # Clean old history (keep 10 seconds)
        cutoff = now - timedelta(seconds=10)
        self._price_history = [(t, p) for t, p in self._price_history if t > cutoff]

        # Calculate velocity toward liq band
        if len(self._price_history) >= 2:
            oldest_time, oldest_price = self._price_history[0]
            time_delta = (now - oldest_time).total_seconds()

            if time_delta > 0:
                if self._setup.cascade_direction == 'long':
                    # Price should be falling toward long liquidations
                    velocity = (oldest_price - current_price) / oldest_price / time_delta
                else:
                    # Price should be rising toward short liquidations
                    velocity = (current_price - oldest_price) / oldest_price / time_delta

                self._setup.price_velocity = velocity
            else:
                velocity = 0
        else:
            velocity = 0

        # Check velocity threshold
        velocity_triggered = velocity >= self._config.price_velocity_threshold

        # Check volume spike
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            volume_triggered = volume_ratio >= self._config.volume_spike_ratio
        else:
            volume_triggered = True
            volume_ratio = 1.0

        if velocity_triggered and volume_triggered:
            # Determine entry direction (same as cascade direction)
            if self._setup.cascade_direction == 'long':
                entry_direction = 'short'  # Cascade is liquidating longs, we go short
            else:
                entry_direction = 'long'  # Cascade is liquidating shorts, we go long

            return {
                'triggered': True,
                'reason': f"Cascade toward {self._setup.cascade_direction} liquidations",
                'entry_direction': entry_direction,
                'current_price': current_price,
                'velocity': velocity,
                'volume_ratio': volume_ratio,
                'metrics': {
                    'velocity': velocity,
                    'volume_ratio': volume_ratio,
                    'distance_to_liq': abs(current_price - self._setup.target_liq_price) / current_price,
                },
            }

        return None

    def _check_exit_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if position should be exited.

        Exit when:
        - Target reached (0.8% profit)
        - Stop hit (0.3% loss)
        - Cascade exhaustion (velocity drops 50%)
        - Max hold time exceeded (1 minute)
        """
        if not self._entry_price:
            return None

        current_price = market_state.get('mark_price', 0)
        if not current_price:
            return None

        # Calculate P&L
        if self._position_size and self._position_size > 0:  # Long
            pnl_pct = (current_price - self._entry_price) / self._entry_price
        elif self._position_size and self._position_size < 0:  # Short
            pnl_pct = (self._entry_price - current_price) / self._entry_price
        else:
            return None

        # Check target
        if pnl_pct >= self._config.target_pct:
            return {
                'reason': 'Target reached',
                'exit_type': 'target',
                'pnl_pct': pnl_pct,
                'metrics': {'pnl_pct': pnl_pct},
            }

        # Check stop
        if pnl_pct <= -self._config.stop_pct:
            return {
                'reason': 'Stop hit',
                'exit_type': 'stop',
                'pnl_pct': pnl_pct,
                'metrics': {'pnl_pct': pnl_pct},
            }

        # Check cascade exhaustion (velocity dropped significantly)
        if self._setup and isinstance(self._setup, CascadeSetup):
            current_velocity = self._setup.price_velocity
            self._peak_velocity = max(self._peak_velocity, current_velocity)

            if self._peak_velocity > 0:
                velocity_ratio = current_velocity / self._peak_velocity
                if velocity_ratio < self._config.cascade_exhaustion_threshold:
                    return {
                        'reason': 'Cascade exhaustion',
                        'exit_type': 'exhaustion',
                        'pnl_pct': pnl_pct,
                        'velocity_ratio': velocity_ratio,
                        'metrics': {'pnl_pct': pnl_pct, 'velocity_ratio': velocity_ratio},
                    }

        # Check max hold time
        if self._entry_time:
            hold_time = (datetime.now() - self._entry_time).total_seconds()
            if hold_time >= self._config.max_hold_sec:
                return {
                    'reason': 'Max hold time exceeded',
                    'exit_type': 'timeout',
                    'pnl_pct': pnl_pct,
                    'hold_time': hold_time,
                    'metrics': {'pnl_pct': pnl_pct, 'hold_time': hold_time},
                }

        return None

    def _calculate_mandate(
        self,
        market_state: Dict[str, Any],
        trigger_result: Dict[str, Any],
    ) -> Optional[Mandate]:
        """Generate entry mandate based on trigger."""
        current_price = trigger_result.get('current_price', market_state.get('mark_price', 0))
        entry_direction = trigger_result.get('entry_direction', 'short')

        if not current_price:
            return None

        # Calculate stop and target
        if entry_direction == 'long':
            mandate_type = MandateType.ENTER_LONG
            stop_price = current_price * (1 - self._config.stop_pct)
            target_price = current_price * (1 + self._config.target_pct)
        else:
            mandate_type = MandateType.ENTER_SHORT
            stop_price = current_price * (1 + self._config.stop_pct)
            target_price = current_price * (1 - self._config.target_pct)

        # Reset peak velocity for exhaustion tracking
        self._peak_velocity = trigger_result.get('velocity', 0)

        return Mandate(
            mandate_type=mandate_type,
            symbol=self._symbol,
            strategy_name=self._name,
            price=current_price,
            stop_price=stop_price,
            take_profit_price=target_price,
            reason=trigger_result.get('reason', 'Cascade trigger'),
            urgency=0.95,  # High urgency for cascade trades
            max_slippage=0.002,  # Allow more slippage for cascade
            metadata={
                'cascade_direction': self._setup.cascade_direction if self._setup else 'unknown',
                'velocity': trigger_result.get('velocity', 0),
                'volume_ratio': trigger_result.get('volume_ratio', 0),
                'target_liq_price': self._setup.target_liq_price if self._setup else 0,
            },
        )

    def _check_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Check if armed conditions are no longer valid."""
        if not self._setup or not isinstance(self._setup, CascadeSetup):
            return True

        current_price = market_state.get('mark_price', 0)
        if not current_price:
            return False

        # Invalidate if price moved away from liq band
        distance = abs(current_price - self._setup.target_liq_price) / current_price
        if distance > self._config.liq_band_distance_pct * 1.5:
            return True

        # Invalidate if depth recovered
        if self._setup.cascade_direction == 'long':
            current_depth = market_state.get('bid_depth_1pct', 0)
        else:
            current_depth = market_state.get('ask_depth_1pct', 0)

        if self._setup.initial_depth > 0:
            depth_ratio = current_depth / self._setup.initial_depth
            if depth_ratio > 0.8:  # Depth recovered to 80%
                return True

        return False

    def reset(self):
        """Reset strategy state for new trading session."""
        self._state = StrategyState.DISABLED
        self._state_entered_at = datetime.now()
        self._setup = None
        self._clear_position()
        self._depth_history.clear()
        self._price_history.clear()
        self._peak_velocity = 0.0
        self._logger.info("Strategy reset")
