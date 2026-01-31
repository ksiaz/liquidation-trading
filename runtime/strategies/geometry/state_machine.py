"""
HLP10: Geometry Strategy State Machine.

Failed Hunt trading in sideways regime.

The strategy identifies potential liquidation hunts and trades
the reversal when they fail. Named "Geometry" because it trades
the geometric relationships between OI, price, and liquidity.

State Flow:
    DISABLED -> SCANNING: Regime is SIDEWAYS
    SCANNING -> ARMED: Elevated OI + skewed funding + depth asymmetry
    ARMED -> ENTERED: OI drops rapidly + flow flips
    ARMED -> SCANNING: Timeout (2 min) or conditions invalidate
    ENTERED -> EXITED: Target/stop/timeout
    EXITED -> COOLDOWN: Always
    COOLDOWN -> SCANNING: After 5 minutes
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, Set

from ..base import (
    StrategyStateMachine,
    StrategyState,
    StrategyConfig,
    StrategySetup,
    Mandate,
    MandateType,
)


@dataclass
class GeometryConfig(StrategyConfig):
    """Configuration for Geometry strategy."""

    # Setup thresholds
    oi_elevation_zscore: float = 2.0       # Z-score above mean
    funding_skew_threshold: float = 0.0015  # 0.15%
    depth_asymmetry_ratio: float = 1.5     # 1.5:1 imbalance
    liq_band_distance_pct: float = 0.02    # Within 2% of liq band

    # Trigger thresholds
    oi_drop_threshold: float = 0.05        # 5% drop triggers
    oi_drop_window_sec: float = 10.0       # Within 10 seconds
    flow_flip_threshold: float = 0.6       # 60% flow reversal

    # Exit parameters
    target_pct: float = 0.005              # 0.5% profit target
    stop_pct: float = 0.003                # 0.3% stop loss
    max_hold_sec: int = 60                 # 1 minute max hold

    # Timing
    armed_timeout_sec: int = 120           # 2 minute armed timeout
    cooldown_sec: int = 300                # 5 minute cooldown
    entry_grace_sec: int = 5               # 5 second grace period

    # Allowed regimes
    allowed_regimes: Set[str] = field(default_factory=lambda: {'sideways'})


@dataclass
class GeometrySetup(StrategySetup):
    """Setup conditions for Geometry strategy."""

    # OI state
    oi_zscore: float = 0.0
    oi_at_arm: float = 0.0

    # Funding state
    funding_rate: float = 0.0
    funding_skew: float = 0.0

    # Depth state
    bid_depth: float = 0.0
    ask_depth: float = 0.0
    asymmetry_ratio: float = 1.0

    # Flow state
    aggressive_buy_rate: float = 0.0
    aggressive_sell_rate: float = 0.0
    passive_cancel_rate: float = 0.0

    # Derived
    hunt_direction: str = ""  # 'long' or 'short'
    liq_band_price: float = 0.0

    @property
    def is_valid(self) -> bool:
        """All conditions must be met for valid setup."""
        required_conditions = [
            'oi_elevated',
            'funding_skewed',
            'depth_asymmetric',
            'near_liq_band',
        ]
        return all(
            self.conditions_met.get(cond, False)
            for cond in required_conditions
        )


class GeometryStateMachine(StrategyStateMachine):
    """
    State machine for Geometry (Failed Hunt) strategy.

    Trades failed liquidation hunts in sideways markets.
    """

    def __init__(
        self,
        symbol: str,
        config: GeometryConfig = None,
        logger: logging.Logger = None,
    ):
        super().__init__(
            name="geometry",
            symbol=symbol,
            config=config or GeometryConfig(),
            logger=logger,
        )
        self._config: GeometryConfig  # Type hint

        # Geometry-specific tracking
        self._oi_history: list = []  # Recent OI readings for drop detection
        self._flow_history: list = []  # Recent flow readings

    def _check_arm_conditions(self, market_state: Dict[str, Any]) -> Optional[GeometrySetup]:
        """
        Check if conditions for arming are met.

        Requires:
        - Elevated OI (z-score > threshold)
        - Funding skewed in one direction
        - Depth asymmetry
        - Price near liquidation bands
        """
        # Extract market data
        oi = market_state.get('open_interest', 0)
        oi_zscore = market_state.get('oi_zscore', 0)
        funding_rate = market_state.get('funding_rate', 0)
        bid_depth = market_state.get('bid_depth_1pct', 0)
        ask_depth = market_state.get('ask_depth_1pct', 0)
        current_price = market_state.get('mark_price', 0)
        liq_bands = market_state.get('liquidation_bands', {})

        if not current_price or not oi:
            return None

        # Check each condition
        conditions = {}

        # 1. OI elevated
        conditions['oi_elevated'] = oi_zscore >= self._config.oi_elevation_zscore

        # 2. Funding skewed
        funding_skew = abs(funding_rate)
        conditions['funding_skewed'] = funding_skew >= self._config.funding_skew_threshold

        # 3. Depth asymmetric
        if ask_depth > 0:
            asymmetry = bid_depth / ask_depth
        else:
            asymmetry = 1.0
        conditions['depth_asymmetric'] = (
            asymmetry >= self._config.depth_asymmetry_ratio or
            asymmetry <= 1.0 / self._config.depth_asymmetry_ratio
        )

        # 4. Near liquidation bands
        liq_long = liq_bands.get('long_liq_price', 0)
        liq_short = liq_bands.get('short_liq_price', float('inf'))

        near_long_liq = liq_long > 0 and abs(current_price - liq_long) / current_price < self._config.liq_band_distance_pct
        near_short_liq = liq_short < float('inf') and abs(current_price - liq_short) / current_price < self._config.liq_band_distance_pct
        conditions['near_liq_band'] = near_long_liq or near_short_liq

        # Determine hunt direction
        if funding_rate > 0 and asymmetry > 1:
            hunt_direction = 'long'  # Market hunting longs
            liq_band_price = liq_long
        elif funding_rate < 0 and asymmetry < 1:
            hunt_direction = 'short'  # Market hunting shorts
            liq_band_price = liq_short
        else:
            hunt_direction = 'long' if funding_rate > 0 else 'short'
            liq_band_price = liq_long if hunt_direction == 'long' else liq_short

        # Create setup
        setup = GeometrySetup(
            symbol=self._symbol,
            detected_at=datetime.now(),
            conditions_met=conditions,
            metrics={
                'oi_zscore': oi_zscore,
                'funding_skew': funding_skew,
                'asymmetry_ratio': asymmetry,
            },
            oi_zscore=oi_zscore,
            oi_at_arm=oi,
            funding_rate=funding_rate,
            funding_skew=funding_skew,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            asymmetry_ratio=asymmetry,
            hunt_direction=hunt_direction,
            liq_band_price=liq_band_price,
        )

        return setup if setup.is_valid else None

    def _check_trigger_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if trigger conditions for entry are met.

        Trigger when:
        - OI drops >5% within 10 seconds (hunt failed)
        - Order flow flips direction (60% reversal)
        """
        if not self._setup or not isinstance(self._setup, GeometrySetup):
            return None

        oi = market_state.get('open_interest', 0)
        current_price = market_state.get('mark_price', 0)
        buy_flow = market_state.get('aggressive_buy_volume', 0)
        sell_flow = market_state.get('aggressive_sell_volume', 0)

        if not oi or not current_price:
            return None

        # Track OI history
        now = datetime.now()
        self._oi_history.append((now, oi))

        # Clean old history
        cutoff = now.timestamp() - self._config.oi_drop_window_sec
        self._oi_history = [(t, v) for t, v in self._oi_history if t.timestamp() > cutoff]

        # Check OI drop
        if len(self._oi_history) >= 2:
            oldest_oi = self._oi_history[0][1]
            oi_change = (oi - oldest_oi) / oldest_oi if oldest_oi > 0 else 0

            oi_dropped = oi_change <= -self._config.oi_drop_threshold
        else:
            oi_dropped = False

        # Check flow flip
        total_flow = buy_flow + sell_flow
        if total_flow > 0:
            if self._setup.hunt_direction == 'long':
                # Was hunting longs, now should see buying
                flow_ratio = buy_flow / total_flow
                flow_flipped = flow_ratio >= self._config.flow_flip_threshold
            else:
                # Was hunting shorts, now should see selling
                flow_ratio = sell_flow / total_flow
                flow_flipped = flow_ratio >= self._config.flow_flip_threshold
        else:
            flow_flipped = False

        # Trigger if both conditions met
        if oi_dropped and flow_flipped:
            entry_direction = 'short' if self._setup.hunt_direction == 'long' else 'long'

            return {
                'triggered': True,
                'reason': f"Failed {self._setup.hunt_direction} hunt detected",
                'entry_direction': entry_direction,
                'oi_drop_pct': oi_change,
                'flow_ratio': flow_ratio if total_flow > 0 else 0,
                'current_price': current_price,
                'metrics': {
                    'oi_change': oi_change,
                    'flow_ratio': flow_ratio if total_flow > 0 else 0,
                },
            }

        return None

    def _check_exit_conditions(self, market_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Check if position should be exited.

        Exit when:
        - Target reached (0.5% profit)
        - Stop hit (0.3% loss)
        - Max hold time exceeded (60 seconds)
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
            stop_price = current_price * (1 - self._config.stop_pct)
            target_price = current_price * (1 + self._config.target_pct)
        else:
            mandate_type = MandateType.ENTER_SHORT
            stop_price = current_price * (1 + self._config.stop_pct)
            target_price = current_price * (1 - self._config.target_pct)

        return Mandate(
            mandate_type=mandate_type,
            symbol=self._symbol,
            strategy_name=self._name,
            price=current_price,
            stop_price=stop_price,
            take_profit_price=target_price,
            reason=trigger_result.get('reason', 'Geometry trigger'),
            urgency=0.8,
            max_slippage=0.001,
            metadata={
                'hunt_direction': self._setup.hunt_direction if self._setup else 'unknown',
                'oi_drop_pct': trigger_result.get('oi_drop_pct', 0),
                'flow_ratio': trigger_result.get('flow_ratio', 0),
            },
        )

    def _check_arm_invalidation(self, market_state: Dict[str, Any]) -> bool:
        """Check if armed conditions are no longer valid."""
        if not self._setup or not isinstance(self._setup, GeometrySetup):
            return True

        oi_zscore = market_state.get('oi_zscore', 0)
        funding_rate = market_state.get('funding_rate', 0)

        # Invalidate if OI elevation is gone
        if oi_zscore < self._config.oi_elevation_zscore * 0.5:  # Dropped to half threshold
            return True

        # Invalidate if funding flipped direction
        setup_direction = 1 if self._setup.funding_rate > 0 else -1
        current_direction = 1 if funding_rate > 0 else -1
        if setup_direction != current_direction:
            return True

        return False

    def reset(self):
        """Reset strategy state for new trading session."""
        self._state = StrategyState.DISABLED
        self._state_entered_at = datetime.now()
        self._setup = None
        self._clear_position()
        self._oi_history.clear()
        self._flow_history.clear()
        self._logger.info("Strategy reset")
