"""
HLP10: Kinematics Strategy State Machine.

Post-Liquidation Inventory trading.

After a significant OI collapse (liquidation event), the market
often consolidates before a directional move. This strategy
identifies consolidation patterns and trades the breakout.

State Flow:
    DISABLED -> SCANNING: Any regime (works in all)
    SCANNING -> ARMED: Recent OI collapse + consolidation detected
    ARMED -> ENTERED: Range expansion breakout confirmed
    ARMED -> SCANNING: Timeout (10 min) or conditions invalidate
    ENTERED -> EXITED: Target/stop/trailing stop
    EXITED -> COOLDOWN: Always
    COOLDOWN -> SCANNING: After 10 minutes
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
class KinematicsConfig(StrategyConfig):
    """Configuration for Kinematics strategy."""

    # OI collapse detection
    oi_collapse_threshold: float = 0.05    # 5% drop
    oi_collapse_window_sec: int = 3600     # Within 1 hour
    min_oi_collapse_age_sec: int = 600     # At least 10 min ago

    # Consolidation detection
    price_range_threshold: float = 0.01    # <1% range
    consolidation_min_duration_sec: int = 600  # >10 minutes
    volume_elevation_ratio: float = 1.5    # 1.5x normal volume

    # Breakout detection
    breakout_threshold: float = 0.005      # 0.5% move
    breakout_volume_ratio: float = 2.0     # 2x consolidation volume

    # Exit parameters
    initial_target_pct: float = 0.01       # 1% initial target
    trailing_stop_pct: float = 0.004       # 0.4% trailing stop
    max_hold_sec: int = 900                # 15 minute max hold

    # Timing
    armed_timeout_sec: int = 600           # 10 minute armed timeout
    cooldown_sec: int = 600                # 10 minute cooldown
    entry_grace_sec: int = 10              # 10 second grace period

    # Works in all regimes
    allowed_regimes: Set[str] = field(default_factory=lambda: {'sideways', 'expansion', 'trending'})


@dataclass
class KinematicsSetup(StrategySetup):
    """Setup conditions for Kinematics strategy."""

    # OI collapse info
    collapse_start_time: Optional[datetime] = None
    collapse_oi_drop_pct: float = 0.0
    pre_collapse_oi: float = 0.0
    post_collapse_oi: float = 0.0

    # Consolidation info
    consolidation_start_time: Optional[datetime] = None
    consolidation_high: float = 0.0
    consolidation_low: float = 0.0
    consolidation_volume: float = 0.0

    # Book state
    depth_recovery_pct: float = 0.0

    @property
    def consolidation_range_pct(self) -> float:
        """Get consolidation range as percentage."""
        if self.consolidation_low <= 0:
            return float('inf')
        return (self.consolidation_high - self.consolidation_low) / self.consolidation_low

    @property
    def consolidation_midpoint(self) -> float:
        """Get midpoint of consolidation range."""
        return (self.consolidation_high + self.consolidation_low) / 2

    @property
    def is_valid(self) -> bool:
        """All conditions must be met for valid setup."""
        required = ['oi_collapsed', 'consolidated', 'volume_elevated']
        return all(self.conditions_met.get(c, False) for c in required)


class KinematicsStateMachine(StrategyStateMachine):
    """
    State machine for Kinematics (Post-Liq Inventory) strategy.

    Trades range expansion after OI collapse events.
    """

    def __init__(
        self,
        symbol: str,
        config: KinematicsConfig = None,
        logger: logging.Logger = None,
    ):
        super().__init__(
            name="kinematics",
            symbol=symbol,
            config=config or KinematicsConfig(),
            logger=logger,
        )
        self._config: KinematicsConfig  # Type hint

        # Kinematics-specific tracking
        self._oi_collapse_events: List[Tuple[datetime, float]] = []
        self._price_history: List[Tuple[datetime, float]] = []
        self._volume_history: List[Tuple[datetime, float]] = []

        # Trailing stop tracking
        self._highest_price: float = 0.0
        self._lowest_price: float = float('inf')

    def _check_arm_conditions(self, market_state: Dict[str, Any]) -> Optional[KinematicsSetup]:
        """
        Check if conditions for arming are met.

        Requires:
        - Recent OI collapse (>5% in past hour)
        - Price consolidation (<1% range for >10 min)
        - Volume elevated above normal
        """
        current_price = market_state.get('mark_price', 0)
        current_oi = market_state.get('open_interest', 0)
        current_volume = market_state.get('volume_24h', 0)
        avg_volume = market_state.get('avg_volume', current_volume)

        if not current_price or not current_oi:
            return None

        now = datetime.now()

        # Track price and volume
        self._price_history.append((now, current_price))
        self._volume_history.append((now, current_volume))

        # Clean old history (keep 2 hours)
        cutoff = now - timedelta(hours=2)
        self._price_history = [(t, p) for t, p in self._price_history if t > cutoff]
        self._volume_history = [(t, v) for t, v in self._volume_history if t > cutoff]

        # Check OI collapse events
        oi_collapse = market_state.get('recent_oi_collapse', None)
        if oi_collapse:
            collapse_time = oi_collapse.get('time', now)
            collapse_pct = oi_collapse.get('drop_pct', 0)
            if collapse_pct >= self._config.oi_collapse_threshold:
                self._oi_collapse_events.append((collapse_time, collapse_pct))

        # Clean old collapse events
        collapse_cutoff = now - timedelta(seconds=self._config.oi_collapse_window_sec)
        self._oi_collapse_events = [
            (t, p) for t, p in self._oi_collapse_events
            if t > collapse_cutoff
        ]

        # Check conditions
        conditions = {}

        # 1. Recent OI collapse that's at least 10 min old
        valid_collapses = [
            (t, p) for t, p in self._oi_collapse_events
            if (now - t).total_seconds() >= self._config.min_oi_collapse_age_sec
        ]
        conditions['oi_collapsed'] = len(valid_collapses) > 0

        # 2. Price consolidation
        consolidation_cutoff = now - timedelta(seconds=self._config.consolidation_min_duration_sec)
        recent_prices = [p for t, p in self._price_history if t > consolidation_cutoff]

        if len(recent_prices) >= 10:
            price_high = max(recent_prices)
            price_low = min(recent_prices)
            range_pct = (price_high - price_low) / price_low if price_low > 0 else float('inf')
            conditions['consolidated'] = range_pct <= self._config.price_range_threshold
        else:
            conditions['consolidated'] = False
            price_high = current_price
            price_low = current_price
            range_pct = 0

        # 3. Volume elevated
        if avg_volume > 0:
            volume_ratio = current_volume / avg_volume
            conditions['volume_elevated'] = volume_ratio >= self._config.volume_elevation_ratio
        else:
            conditions['volume_elevated'] = False
            volume_ratio = 1.0

        if not all(conditions.values()):
            return None

        # Find most recent valid collapse
        most_recent_collapse = max(valid_collapses, key=lambda x: x[0]) if valid_collapses else (now, 0)

        # Create setup
        setup = KinematicsSetup(
            symbol=self._symbol,
            detected_at=now,
            conditions_met=conditions,
            metrics={
                'oi_collapse_pct': most_recent_collapse[1],
                'consolidation_range_pct': range_pct,
                'volume_ratio': volume_ratio,
            },
            collapse_start_time=most_recent_collapse[0],
            collapse_oi_drop_pct=most_recent_collapse[1],
            consolidation_start_time=consolidation_cutoff,
            consolidation_high=price_high,
            consolidation_low=price_low,
            consolidation_volume=current_volume,
        )

        return setup

    def _check_trigger_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if trigger conditions for entry are met.

        Trigger when:
        - Price breaks above/below consolidation range
        - Volume confirms the breakout (2x consolidation volume)
        """
        if not self._setup or not isinstance(self._setup, KinematicsSetup):
            return None

        current_price = market_state.get('mark_price', 0)
        current_volume = market_state.get('volume_1m', 0)

        if not current_price:
            return None

        # Check for breakout
        breakout_up = current_price > self._setup.consolidation_high * (1 + self._config.breakout_threshold)
        breakout_down = current_price < self._setup.consolidation_low * (1 - self._config.breakout_threshold)

        if not (breakout_up or breakout_down):
            return None

        # Check volume confirmation
        if self._setup.consolidation_volume > 0:
            volume_ratio = current_volume / (self._setup.consolidation_volume / 60)  # Per minute
            volume_confirmed = volume_ratio >= self._config.breakout_volume_ratio
        else:
            volume_confirmed = True  # Default to confirmed if no baseline

        if not volume_confirmed:
            return None

        # Determine direction
        if breakout_up:
            entry_direction = 'long'
            breakout_price = self._setup.consolidation_high
        else:
            entry_direction = 'short'
            breakout_price = self._setup.consolidation_low

        return {
            'triggered': True,
            'reason': f"Range expansion breakout {'up' if breakout_up else 'down'}",
            'entry_direction': entry_direction,
            'breakout_price': breakout_price,
            'current_price': current_price,
            'volume_ratio': volume_ratio if self._setup.consolidation_volume > 0 else 0,
            'metrics': {
                'breakout_pct': abs(current_price - breakout_price) / breakout_price,
                'volume_ratio': volume_ratio if self._setup.consolidation_volume > 0 else 0,
            },
        }

    def _check_exit_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if position should be exited.

        Exit when:
        - Initial target reached (1% profit)
        - Trailing stop hit (0.4% from peak)
        - Max hold time exceeded (15 minutes)
        """
        if not self._entry_price:
            return None

        current_price = market_state.get('mark_price', 0)
        if not current_price:
            return None

        # Track high/low for trailing stop
        if self._position_size and self._position_size > 0:  # Long
            self._highest_price = max(self._highest_price, current_price)
            pnl_pct = (current_price - self._entry_price) / self._entry_price

            # Trailing stop from highest
            trailing_stop_price = self._highest_price * (1 - self._config.trailing_stop_pct)
            trailing_stop_hit = current_price <= trailing_stop_price

        elif self._position_size and self._position_size < 0:  # Short
            self._lowest_price = min(self._lowest_price, current_price)
            pnl_pct = (self._entry_price - current_price) / self._entry_price

            # Trailing stop from lowest
            trailing_stop_price = self._lowest_price * (1 + self._config.trailing_stop_pct)
            trailing_stop_hit = current_price >= trailing_stop_price
        else:
            return None

        # Check initial target
        if pnl_pct >= self._config.initial_target_pct:
            return {
                'reason': 'Initial target reached',
                'exit_type': 'target',
                'pnl_pct': pnl_pct,
                'metrics': {'pnl_pct': pnl_pct},
            }

        # Check trailing stop
        if trailing_stop_hit and pnl_pct > 0:  # Only if in profit
            return {
                'reason': 'Trailing stop hit',
                'exit_type': 'trailing_stop',
                'pnl_pct': pnl_pct,
                'metrics': {'pnl_pct': pnl_pct},
            }

        # Check hard stop (initial stop)
        hard_stop_pct = -self._config.trailing_stop_pct * 2  # 0.8% stop
        if pnl_pct <= hard_stop_pct:
            return {
                'reason': 'Hard stop hit',
                'exit_type': 'stop',
                'pnl_pct': pnl_pct,
                'metrics': {'pnl_pct': pnl_pct},
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
        entry_direction = trigger_result.get('entry_direction', 'long')

        if not current_price:
            return None

        # Calculate stop and target
        if entry_direction == 'long':
            mandate_type = MandateType.ENTER_LONG
            stop_price = current_price * (1 - self._config.trailing_stop_pct * 2)
            target_price = current_price * (1 + self._config.initial_target_pct)
            self._highest_price = current_price
        else:
            mandate_type = MandateType.ENTER_SHORT
            stop_price = current_price * (1 + self._config.trailing_stop_pct * 2)
            target_price = current_price * (1 - self._config.initial_target_pct)
            self._lowest_price = current_price

        return Mandate(
            mandate_type=mandate_type,
            symbol=self._symbol,
            strategy_name=self._name,
            price=current_price,
            stop_price=stop_price,
            take_profit_price=target_price,
            reason=trigger_result.get('reason', 'Kinematics breakout'),
            urgency=0.7,
            max_slippage=0.0015,
            metadata={
                'breakout_price': trigger_result.get('breakout_price', 0),
                'volume_ratio': trigger_result.get('volume_ratio', 0),
                'consolidation_range': self._setup.consolidation_range_pct if self._setup else 0,
            },
        )

    def _check_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Check if armed conditions are no longer valid."""
        if not self._setup or not isinstance(self._setup, KinematicsSetup):
            return True

        current_price = market_state.get('mark_price', 0)
        if not current_price:
            return False

        # Invalidate if consolidation range has expanded too much
        if current_price > self._setup.consolidation_high * 1.02:  # 2% above range
            return True
        if current_price < self._setup.consolidation_low * 0.98:  # 2% below range
            return True

        return False

    def reset(self):
        """Reset strategy state for new trading session."""
        self._state = StrategyState.DISABLED
        self._state_entered_at = datetime.now()
        self._setup = None
        self._clear_position()
        self._oi_collapse_events.clear()
        self._price_history.clear()
        self._volume_history.clear()
        self._highest_price = 0.0
        self._lowest_price = float('inf')
        self._logger.info("Strategy reset")
