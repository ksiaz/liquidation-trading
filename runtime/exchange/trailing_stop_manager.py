"""
X4-A: Trailing Stop Manager.

Manages trailing stop logic for open positions.

Features:
- Trail stop as profit increases
- Break-even stop after X profit
- ATR-based trailing distance
- Multiple trailing modes
- P2: State persistence across restarts

This is EXTERNAL to the core state machine - operates on placed stop orders.
"""

import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Callable, List, TYPE_CHECKING
from enum import Enum
from threading import RLock

if TYPE_CHECKING:
    from runtime.persistence import ExecutionStateRepository, PersistedTrailingStop


class TrailingMode(Enum):
    """Trailing stop behavior modes."""
    FIXED_DISTANCE = "FIXED_DISTANCE"      # Fixed % below high
    ATR_MULTIPLE = "ATR_MULTIPLE"          # ATR-based distance
    BREAK_EVEN_ONLY = "BREAK_EVEN_ONLY"    # Move to break-even, then fixed
    STEPPED = "STEPPED"                     # Step-based trailing (e.g., every 1%)


@dataclass
class TrailingStopConfig:
    """Configuration for a trailing stop."""
    # Basic settings
    mode: TrailingMode = TrailingMode.FIXED_DISTANCE
    trail_distance_pct: float = 0.02       # 2% trailing distance (FIXED_DISTANCE mode)
    atr_multiplier: float = 2.0            # 2x ATR (ATR_MULTIPLE mode)

    # Break-even settings
    break_even_trigger_pct: float = 0.01   # Move to BE after 1% profit
    break_even_offset_pct: float = 0.001   # Place stop 0.1% above entry (small profit lock)

    # Step settings (STEPPED mode)
    step_size_pct: float = 0.01            # Trail every 1% move
    step_trail_pct: float = 0.005          # Trail stop by 0.5% each step

    # Update settings
    min_move_to_update_pct: float = 0.002  # Only update stop if new level is 0.2% better


@dataclass
class TrailingStopState:
    """State for a single trailing stop."""
    entry_order_id: str
    symbol: str
    direction: str                          # "LONG" or "SHORT"
    entry_price: float
    current_stop_price: float
    initial_stop_price: float

    # Tracking
    highest_price: float = 0.0              # Highest since entry (for LONG)
    lowest_price: float = float('inf')      # Lowest since entry (for SHORT)
    break_even_triggered: bool = False
    last_update_ns: int = 0
    updates_count: int = 0

    # ATR (if using ATR mode)
    current_atr: Optional[float] = None

    # Config
    config: TrailingStopConfig = field(default_factory=TrailingStopConfig)


class TrailingStopManager:
    """
    X4-A: Manages trailing stop logic for multiple positions.

    Does NOT place orders directly - emits update requests to caller.

    Usage:
    1. register_trailing_stop() when entry fills
    2. update_price() on each price tick
    3. Handle on_stop_update callback to modify stop order

    P2: State persistence across restarts via ExecutionStateRepository.

    Thread-safe.
    """

    def __init__(
        self,
        logger: logging.Logger = None,
        repository: Optional["ExecutionStateRepository"] = None
    ):
        self._logger = logger or logging.getLogger(__name__)
        self._stops: Dict[str, TrailingStopState] = {}  # entry_order_id -> state
        self._lock = RLock()

        # P2: Persistence layer
        self._repository = repository

        # Callback for stop updates (caller should modify stop order)
        self._on_stop_update: Optional[Callable[[str, float, float], None]] = None

        # P2: Load persisted state on init
        if self._repository:
            self._load_persisted_state()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _load_persisted_state(self):
        """P2: Load persisted trailing stop state on startup."""
        if not self._repository:
            return

        try:
            persisted = self._repository.load_all_trailing_stops()
            for entry_id, p in persisted.items():
                # Reconstruct config from JSON
                config_dict = json.loads(p.config_json)
                config = TrailingStopConfig(
                    mode=TrailingMode(config_dict.get('mode', 'FIXED_DISTANCE')),
                    trail_distance_pct=config_dict.get('trail_distance_pct', 0.02),
                    atr_multiplier=config_dict.get('atr_multiplier', 2.0),
                    break_even_trigger_pct=config_dict.get('break_even_trigger_pct', 0.01),
                    break_even_offset_pct=config_dict.get('break_even_offset_pct', 0.001),
                    step_size_pct=config_dict.get('step_size_pct', 0.01),
                    step_trail_pct=config_dict.get('step_trail_pct', 0.005),
                    min_move_to_update_pct=config_dict.get('min_move_to_update_pct', 0.002),
                )

                state = TrailingStopState(
                    entry_order_id=p.entry_order_id,
                    symbol=p.symbol,
                    direction=p.direction,
                    entry_price=p.entry_price,
                    current_stop_price=p.current_stop_price,
                    initial_stop_price=p.initial_stop_price,
                    highest_price=p.highest_price,
                    lowest_price=p.lowest_price,
                    break_even_triggered=p.break_even_triggered,
                    updates_count=p.updates_count,
                    current_atr=p.current_atr,
                    config=config
                )
                self._stops[entry_id] = state

            self._logger.info(f"P2: Loaded {len(persisted)} trailing stops from persistence")
        except Exception as e:
            self._logger.error(f"P2: Failed to load persisted trailing stops: {e}")

    def _persist_state(self, state: TrailingStopState):
        """P2: Persist trailing stop state."""
        if not self._repository:
            return

        try:
            from runtime.persistence import PersistedTrailingStop

            # Serialize config to JSON
            config_dict = {
                'mode': state.config.mode.value,
                'trail_distance_pct': state.config.trail_distance_pct,
                'atr_multiplier': state.config.atr_multiplier,
                'break_even_trigger_pct': state.config.break_even_trigger_pct,
                'break_even_offset_pct': state.config.break_even_offset_pct,
                'step_size_pct': state.config.step_size_pct,
                'step_trail_pct': state.config.step_trail_pct,
                'min_move_to_update_pct': state.config.min_move_to_update_pct,
            }

            persisted = PersistedTrailingStop(
                entry_order_id=state.entry_order_id,
                symbol=state.symbol,
                direction=state.direction,
                entry_price=state.entry_price,
                current_stop_price=state.current_stop_price,
                initial_stop_price=state.initial_stop_price,
                highest_price=state.highest_price,
                lowest_price=state.lowest_price,
                break_even_triggered=state.break_even_triggered,
                updates_count=state.updates_count,
                current_atr=state.current_atr,
                config_json=json.dumps(config_dict),
                created_at=time.time(),
                updated_at=time.time()
            )
            self._repository.save_trailing_stop(persisted)
        except Exception as e:
            self._logger.error(f"P2: Failed to persist trailing stop: {e}")

    def set_stop_update_callback(self, callback: Callable[[str, float, float], None]):
        """Set callback for stop price updates.

        Callback receives: (entry_order_id, old_stop_price, new_stop_price)
        Caller should modify the stop order on exchange.
        """
        self._on_stop_update = callback

    def register_trailing_stop(
        self,
        entry_order_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        initial_stop_price: float,
        config: TrailingStopConfig = None
    ):
        """Register a new trailing stop for a position.

        Args:
            entry_order_id: Order ID of the entry
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            entry_price: Entry fill price
            initial_stop_price: Initial stop loss price
            config: Trailing stop configuration
        """
        config = config or TrailingStopConfig()

        state = TrailingStopState(
            entry_order_id=entry_order_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            current_stop_price=initial_stop_price,
            initial_stop_price=initial_stop_price,
            highest_price=entry_price if direction == "LONG" else 0.0,
            lowest_price=entry_price if direction == "SHORT" else float('inf'),
            last_update_ns=self._now_ns(),
            config=config
        )

        with self._lock:
            self._stops[entry_order_id] = state

        # P2: Persist new trailing stop
        self._persist_state(state)

        self._logger.info(
            f"X4-A: Registered trailing stop for {entry_order_id}: "
            f"{symbol} {direction} entry={entry_price} stop={initial_stop_price} "
            f"mode={config.mode.value}"
        )

    def update_price(self, symbol: str, price: float, atr: Optional[float] = None):
        """Update price and potentially trail stops.

        Args:
            symbol: Trading symbol
            price: Current market price
            atr: Current ATR value (for ATR_MULTIPLE mode)
        """
        with self._lock:
            for entry_id, state in list(self._stops.items()):
                if state.symbol != symbol:
                    continue

                # Update ATR if provided
                if atr is not None:
                    state.current_atr = atr

                # Update high/low watermark
                if state.direction == "LONG":
                    state.highest_price = max(state.highest_price, price)
                else:
                    state.lowest_price = min(state.lowest_price, price)

                # Calculate new stop price
                new_stop = self._calculate_new_stop(state, price)

                if new_stop is not None:
                    old_stop = state.current_stop_price

                    # Check if move is significant enough
                    if state.direction == "LONG":
                        improvement = (new_stop - old_stop) / state.entry_price
                    else:
                        improvement = (old_stop - new_stop) / state.entry_price

                    if improvement >= state.config.min_move_to_update_pct:
                        state.current_stop_price = new_stop
                        state.last_update_ns = self._now_ns()
                        state.updates_count += 1

                        self._logger.info(
                            f"X4-A: Trailing stop updated for {entry_id}: "
                            f"{old_stop:.2f} -> {new_stop:.2f} "
                            f"(price={price:.2f}, high/low={state.highest_price:.2f}/{state.lowest_price:.2f})"
                        )

                        # P2: Persist updated state
                        self._persist_state(state)

                        # Notify callback
                        if self._on_stop_update:
                            self._on_stop_update(entry_id, old_stop, new_stop)

    def _calculate_new_stop(self, state: TrailingStopState, current_price: float) -> Optional[float]:
        """Calculate new stop price based on trailing mode.

        Returns:
            New stop price, or None if no update needed
        """
        config = state.config
        entry = state.entry_price
        current_stop = state.current_stop_price

        # Check break-even trigger first (applies to all modes)
        if not state.break_even_triggered:
            if state.direction == "LONG":
                profit_pct = (current_price - entry) / entry
                if profit_pct >= config.break_even_trigger_pct:
                    state.break_even_triggered = True
                    be_stop = entry * (1 + config.break_even_offset_pct)
                    if be_stop > current_stop:
                        return be_stop
            else:  # SHORT
                profit_pct = (entry - current_price) / entry
                if profit_pct >= config.break_even_trigger_pct:
                    state.break_even_triggered = True
                    be_stop = entry * (1 - config.break_even_offset_pct)
                    if be_stop < current_stop:
                        return be_stop

        # Mode-specific trailing
        if config.mode == TrailingMode.BREAK_EVEN_ONLY:
            # Only move to break-even (handled above)
            return None

        elif config.mode == TrailingMode.FIXED_DISTANCE:
            if state.direction == "LONG":
                # Trail below highest price
                new_stop = state.highest_price * (1 - config.trail_distance_pct)
                return new_stop if new_stop > current_stop else None
            else:  # SHORT
                # Trail above lowest price
                new_stop = state.lowest_price * (1 + config.trail_distance_pct)
                return new_stop if new_stop < current_stop else None

        elif config.mode == TrailingMode.ATR_MULTIPLE:
            if state.current_atr is None:
                return None  # Need ATR data

            atr_distance = state.current_atr * config.atr_multiplier

            if state.direction == "LONG":
                new_stop = state.highest_price - atr_distance
                return new_stop if new_stop > current_stop else None
            else:  # SHORT
                new_stop = state.lowest_price + atr_distance
                return new_stop if new_stop < current_stop else None

        elif config.mode == TrailingMode.STEPPED:
            if state.direction == "LONG":
                # Calculate how many steps above entry
                gain_pct = (state.highest_price - entry) / entry
                steps = int(gain_pct / config.step_size_pct)
                if steps > 0:
                    new_stop = entry * (1 + (steps * config.step_trail_pct))
                    return new_stop if new_stop > current_stop else None
            else:  # SHORT
                gain_pct = (entry - state.lowest_price) / entry
                steps = int(gain_pct / config.step_size_pct)
                if steps > 0:
                    new_stop = entry * (1 - (steps * config.step_trail_pct))
                    return new_stop if new_stop < current_stop else None

        return None

    def unregister_stop(self, entry_order_id: str):
        """Remove trailing stop tracking (position closed)."""
        with self._lock:
            if entry_order_id in self._stops:
                del self._stops[entry_order_id]
                self._logger.info(f"X4-A: Unregistered trailing stop for {entry_order_id}")

        # P2: Remove from persistence
        if self._repository:
            try:
                self._repository.delete_trailing_stop(entry_order_id)
            except Exception as e:
                self._logger.error(f"P2: Failed to delete persisted trailing stop: {e}")

    def get_stop_state(self, entry_order_id: str) -> Optional[TrailingStopState]:
        """Get current trailing stop state."""
        with self._lock:
            return self._stops.get(entry_order_id)

    def get_all_stops(self) -> Dict[str, TrailingStopState]:
        """Get all active trailing stops."""
        with self._lock:
            return dict(self._stops)

    def get_stats(self) -> Dict:
        """Get trailing stop statistics."""
        with self._lock:
            total_updates = sum(s.updates_count for s in self._stops.values())
            be_triggered = sum(1 for s in self._stops.values() if s.break_even_triggered)

            return {
                "active_stops": len(self._stops),
                "total_updates": total_updates,
                "break_even_triggered": be_triggered,
                "symbols": list(set(s.symbol for s in self._stops.values()))
            }
