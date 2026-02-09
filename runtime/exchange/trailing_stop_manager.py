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
    ATR_PROGRESSIVE = "ATR_PROGRESSIVE"    # ATR-based with MFE-progressive tightening


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

    # ATR_PROGRESSIVE settings - MFE-based continuous tightening
    # Two-phase piecewise linear: fast initial tightening, gradual for runners
    atr_prog_start_mult: float = 2.5       # Wide at entry (2.5× ATR)
    atr_prog_phase1_end_mult: float = 1.8  # End of phase 1 multiplier
    atr_prog_phase1_range: float = 0.01    # Phase 1 covers 0-1% MFE (fast tightening)
    atr_prog_end_mult: float = 1.0         # Tight at max profit (1.0× ATR)
    atr_prog_profit_range: float = 0.03    # Full tightening over 3% MFE profit
    atr_prog_min_pct: float = 0.005        # Floor: at least 0.5% distance (low vol protection)
    atr_prog_min_lock_ratio: float = 0.4   # Profit floor: lock at least 40% of MFE profit

    # Orderflow-aware tightening
    orderflow_tighten_threshold: float = 0.38  # Adverse flow threshold (< this for LONG)
    orderflow_tighten_mult: float = 0.6        # Multiply ATR distance by this when adverse

    # Update settings
    min_move_to_update_pct: float = 0.002  # Only update stop if new level is 0.2% better
    min_move_atr_fraction: float = 0.05    # Update if move >= 5% of ATR (dynamic gate)


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

    # Orderflow imbalance (0-1, where 0.5 = balanced, <0.5 = selling, >0.5 = buying)
    last_orderflow: Optional[float] = None

    # AUDIT-P0-9: Track confirmed exchange state separately from intended state
    # This allows detecting divergence when exchange ACK fails
    last_confirmed_stop_price: Optional[float] = None
    pending_stop_price: Optional[float] = None  # Price awaiting exchange ACK
    pending_update_ns: Optional[int] = None  # When pending update was requested

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
                    # ATR_PROGRESSIVE settings (two-phase)
                    atr_prog_start_mult=config_dict.get('atr_prog_start_mult', 2.5),
                    atr_prog_phase1_end_mult=config_dict.get('atr_prog_phase1_end_mult', 1.8),
                    atr_prog_phase1_range=config_dict.get('atr_prog_phase1_range', 0.01),
                    atr_prog_end_mult=config_dict.get('atr_prog_end_mult', 1.0),
                    atr_prog_profit_range=config_dict.get('atr_prog_profit_range', 0.03),
                    atr_prog_min_pct=config_dict.get('atr_prog_min_pct', 0.005),
                    atr_prog_min_lock_ratio=config_dict.get('atr_prog_min_lock_ratio', 0.4),
                    # Orderflow tightening
                    orderflow_tighten_threshold=config_dict.get('orderflow_tighten_threshold', 0.38),
                    orderflow_tighten_mult=config_dict.get('orderflow_tighten_mult', 0.6),
                    # Update settings
                    min_move_to_update_pct=config_dict.get('min_move_to_update_pct', 0.002),
                    min_move_atr_fraction=config_dict.get('min_move_atr_fraction', 0.05),
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
                # ATR_PROGRESSIVE settings (two-phase)
                'atr_prog_start_mult': state.config.atr_prog_start_mult,
                'atr_prog_phase1_end_mult': state.config.atr_prog_phase1_end_mult,
                'atr_prog_phase1_range': state.config.atr_prog_phase1_range,
                'atr_prog_end_mult': state.config.atr_prog_end_mult,
                'atr_prog_profit_range': state.config.atr_prog_profit_range,
                'atr_prog_min_pct': state.config.atr_prog_min_pct,
                'atr_prog_min_lock_ratio': state.config.atr_prog_min_lock_ratio,
                # Orderflow tightening
                'orderflow_tighten_threshold': state.config.orderflow_tighten_threshold,
                'orderflow_tighten_mult': state.config.orderflow_tighten_mult,
                # Update settings
                'min_move_to_update_pct': state.config.min_move_to_update_pct,
                'min_move_atr_fraction': state.config.min_move_atr_fraction,
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
            highest_price=entry_price,  # Always start at entry for MFE tracking
            lowest_price=entry_price,   # Always start at entry for MFE tracking
            last_update_ns=self._now_ns(),
            config=config
        )

        with self._lock:
            # Remove any existing stop for the same symbol (enforce 1 stop per symbol)
            existing_ids = [
                eid for eid, s in self._stops.items()
                if s.symbol == symbol and eid != entry_order_id
            ]
            for eid in existing_ids:
                self._logger.info(f"X4-A: Replacing existing stop {eid} for {symbol} with {entry_order_id}")
                del self._stops[eid]
                # Clean up persistence for old stop
                if self._repository:
                    try:
                        self._repository.delete_trailing_stop(eid)
                    except Exception:
                        pass

            self._stops[entry_order_id] = state

        # P2: Persist new trailing stop
        self._persist_state(state)

        self._logger.info(
            f"X4-A: Registered trailing stop for {entry_order_id}: "
            f"{symbol} {direction} entry={entry_price} stop={initial_stop_price} "
            f"mode={config.mode.value}"
        )

    def update_price(self, symbol: str, price: float, atr: Optional[float] = None,
                     orderflow_imbalance: Optional[float] = None):
        """Update price and potentially trail stops.

        Args:
            symbol: Trading symbol
            price: Current market price
            atr: Current ATR value (for ATR_MULTIPLE mode)
            orderflow_imbalance: Buy/sell imbalance (0-1, <0.5 = selling pressure)
        """
        with self._lock:
            for entry_id, state in list(self._stops.items()):
                if state.symbol != symbol:
                    continue

                # Update ATR if provided
                if atr is not None:
                    state.current_atr = atr

                # Update orderflow if provided
                if orderflow_imbalance is not None:
                    state.last_orderflow = orderflow_imbalance

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
                    # Dynamic update gate: use ATR-relative threshold when ATR available
                    config = state.config
                    if state.current_atr and state.current_atr > 0:
                        min_move = state.current_atr * config.min_move_atr_fraction
                        min_move_pct = min_move / state.entry_price
                    else:
                        min_move_pct = config.min_move_to_update_pct

                    if state.direction == "LONG":
                        improvement = (new_stop - old_stop) / state.entry_price
                    else:
                        improvement = (old_stop - new_stop) / state.entry_price

                    if improvement >= min_move_pct:
                        # Update stop immediately (ghost mode - no exchange ACK needed)
                        state.current_stop_price = new_stop
                        state.last_update_ns = self._now_ns()
                        state.updates_count += 1

                        # Format with appropriate precision for small values
                        def fmt(v): return f"{v:.5f}" if v < 1 else f"{v:.2f}"
                        self._logger.info(
                            f"X4-A: Trailing stop updated for {entry_id}: "
                            f"{fmt(old_stop)} -> {fmt(new_stop)} "
                            f"(price={fmt(price)}, high/low={fmt(state.highest_price)}/{fmt(state.lowest_price)})"
                        )

                        # Persist updated state
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

        elif config.mode == TrailingMode.ATR_PROGRESSIVE:
            # MFE-based ATR trailing with continuous tightening + profit-locking floor
            # Uses highest/lowest price (MFE), not current price
            # Avoids oscillation and step discontinuities

            # Calculate MFE profit % (based on best price, not current)
            if state.direction == "LONG":
                mfe_profit_pct = (state.highest_price - entry) / entry
                mfe_profit_abs = state.highest_price - entry
            else:  # SHORT
                mfe_profit_pct = (entry - state.lowest_price) / entry
                mfe_profit_abs = entry - state.lowest_price

            if state.current_atr is None:
                # Fallback: use profit-locking only (no ATR data)
                # Only lock profit after meaningful MFE (prevents stop at entry)
                if mfe_profit_pct < config.break_even_trigger_pct:
                    return None  # No ATR data and no meaningful profit — keep current stop
                locked_profit = mfe_profit_abs * config.atr_prog_min_lock_ratio
                if state.direction == "LONG":
                    new_stop = entry + locked_profit
                    return new_stop if new_stop > current_stop else None
                else:
                    new_stop = entry - locked_profit
                    return new_stop if new_stop < current_stop else None

            # Two-phase piecewise linear multiplier:
            # Phase 1 (0 → phase1_range): fast tightening to protect new profit
            # Phase 2 (phase1_range → profit_range): gradual tightening for runners
            if mfe_profit_pct <= config.atr_prog_phase1_range:
                # Phase 1: Fast tightening (entry protection)
                if config.atr_prog_phase1_range > 0:
                    k1 = (config.atr_prog_start_mult - config.atr_prog_phase1_end_mult) / config.atr_prog_phase1_range
                    raw_mult = config.atr_prog_start_mult - (k1 * mfe_profit_pct)
                else:
                    raw_mult = config.atr_prog_start_mult
            else:
                # Phase 2: Gradual tightening (let winners run)
                remaining_range = config.atr_prog_profit_range - config.atr_prog_phase1_range
                if remaining_range > 0:
                    progress = mfe_profit_pct - config.atr_prog_phase1_range
                    k2 = (config.atr_prog_phase1_end_mult - config.atr_prog_end_mult) / remaining_range
                    raw_mult = config.atr_prog_phase1_end_mult - (k2 * progress)
                else:
                    raw_mult = config.atr_prog_end_mult
            atr_mult = max(config.atr_prog_end_mult, min(config.atr_prog_start_mult, raw_mult))

            # Orderflow-aware tightening: adverse flow reduces multiplier
            if state.last_orderflow is not None:
                of = state.last_orderflow
                if state.direction == "LONG" and of < config.orderflow_tighten_threshold:
                    # Selling pressure against LONG — tighten stop
                    atr_mult *= config.orderflow_tighten_mult
                elif state.direction == "SHORT" and of > (1.0 - config.orderflow_tighten_threshold):
                    # Buying pressure against SHORT — tighten stop
                    atr_mult *= config.orderflow_tighten_mult
                # Re-clamp after orderflow adjustment
                atr_mult = max(config.atr_prog_end_mult, atr_mult)

            # Calculate ATR-based distance with floor protection
            atr_distance = state.current_atr * atr_mult
            min_distance = entry * config.atr_prog_min_pct
            distance = max(atr_distance, min_distance)

            # Calculate stop from MFE (highest/lowest), not current price
            if state.direction == "LONG":
                atr_stop = state.highest_price - distance

                # Only engage profit-lock after meaningful MFE
                # Without this, profit_lock at MFE=0 equals entry price, killing the position
                new_stop = atr_stop
                if mfe_profit_pct >= config.break_even_trigger_pct:
                    locked_profit = mfe_profit_abs * config.atr_prog_min_lock_ratio
                    profit_lock_stop = entry + locked_profit
                    new_stop = max(atr_stop, profit_lock_stop)

                # Break-even as additional floor
                if state.break_even_triggered:
                    be_stop = entry * (1 + config.break_even_offset_pct)
                    new_stop = max(new_stop, be_stop)

                return new_stop if new_stop > current_stop else None
            else:  # SHORT
                atr_stop = state.lowest_price + distance

                # Only engage profit-lock after meaningful MFE
                new_stop = atr_stop
                if mfe_profit_pct >= config.break_even_trigger_pct:
                    locked_profit = mfe_profit_abs * config.atr_prog_min_lock_ratio
                    profit_lock_stop = entry - locked_profit
                    new_stop = min(atr_stop, profit_lock_stop)

                # Break-even as additional floor
                if state.break_even_triggered:
                    be_stop = entry * (1 - config.break_even_offset_pct)
                    new_stop = min(new_stop, be_stop)

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

    def confirm_stop_update(self, entry_order_id: str, confirmed_price: float) -> bool:
        """AUDIT-P0-9: Confirm that exchange has updated the stop price.

        Call this AFTER receiving exchange ACK for stop modification.
        Only persists state after exchange confirms the update.

        Args:
            entry_order_id: Entry order ID
            confirmed_price: The stop price confirmed by exchange

        Returns:
            True if update confirmed, False if no pending update or mismatch
        """
        with self._lock:
            state = self._stops.get(entry_order_id)
            if not state:
                self._logger.warning(f"P0-9: confirm_stop_update for unknown order {entry_order_id}")
                return False

            if state.pending_stop_price is None:
                self._logger.warning(
                    f"P0-9: confirm_stop_update called but no pending update for {entry_order_id}"
                )
                return False

            # Verify the confirmed price matches what we requested
            if abs(confirmed_price - state.pending_stop_price) > 0.0001:
                self._logger.warning(
                    f"P0-9: Exchange confirmed different price for {entry_order_id}: "
                    f"requested={state.pending_stop_price:.2f}, confirmed={confirmed_price:.2f}"
                )

            # Update confirmed state
            old_confirmed = state.last_confirmed_stop_price or state.initial_stop_price
            state.current_stop_price = confirmed_price
            state.last_confirmed_stop_price = confirmed_price
            state.last_update_ns = self._now_ns()
            state.updates_count += 1
            state.pending_stop_price = None
            state.pending_update_ns = None

            self._logger.info(
                f"P0-9: Trailing stop confirmed for {entry_order_id}: "
                f"{old_confirmed:.2f} -> {confirmed_price:.2f}"
            )

            # P2: Only persist after exchange ACK
            self._persist_state(state)
            return True

    def fail_stop_update(self, entry_order_id: str, error: str):
        """AUDIT-P0-9: Handle failed stop update (exchange rejected/timeout).

        Clears pending state so divergence can be detected and retried.
        """
        with self._lock:
            state = self._stops.get(entry_order_id)
            if not state:
                return

            self._logger.warning(
                f"P0-9: Stop update failed for {entry_order_id}: {error}. "
                f"Pending: {state.pending_stop_price}, Confirmed: {state.last_confirmed_stop_price}"
            )

            # Clear pending but don't update confirmed
            state.pending_stop_price = None
            state.pending_update_ns = None

    def get_divergent_stops(self) -> List[Dict]:
        """AUDIT-P0-9: Find stops with unconfirmed updates (potential divergence).

        Returns list of stops where intended != confirmed state.
        """
        with self._lock:
            divergent = []
            now = self._now_ns()

            for entry_id, state in self._stops.items():
                # Check for old pending updates (>30 seconds)
                if state.pending_stop_price is not None and state.pending_update_ns is not None:
                    elapsed_sec = (now - state.pending_update_ns) / 1_000_000_000
                    if elapsed_sec > 30.0:
                        divergent.append({
                            "entry_order_id": entry_id,
                            "symbol": state.symbol,
                            "pending_price": state.pending_stop_price,
                            "confirmed_price": state.last_confirmed_stop_price,
                            "elapsed_sec": elapsed_sec,
                            "issue": "pending_timeout"
                        })

            return divergent

    def reconcile_with_exchange(
        self,
        exchange_stops: Dict[str, float],
        logger=None
    ) -> List[Dict]:
        """AUDIT-P0-9: Reconcile local state with exchange reality.

        Args:
            exchange_stops: Dict mapping entry_order_id -> actual stop price on exchange
            logger: Optional logger

        Returns:
            List of discrepancies found
        """
        import logging
        log = logger or logging.getLogger(__name__)

        discrepancies = []
        with self._lock:
            for entry_id, state in self._stops.items():
                if entry_id not in exchange_stops:
                    # Stop exists locally but not on exchange
                    discrepancies.append({
                        "entry_order_id": entry_id,
                        "symbol": state.symbol,
                        "local_price": state.current_stop_price,
                        "exchange_price": None,
                        "issue": "missing_on_exchange"
                    })
                    log.warning(
                        f"P0-9: Trailing stop {entry_id} not found on exchange "
                        f"(local={state.current_stop_price:.2f})"
                    )
                else:
                    exchange_price = exchange_stops[entry_id]
                    # Check for price mismatch (>0.1% difference)
                    diff_pct = abs(exchange_price - state.current_stop_price) / state.current_stop_price
                    if diff_pct > 0.001:
                        discrepancies.append({
                            "entry_order_id": entry_id,
                            "symbol": state.symbol,
                            "local_price": state.current_stop_price,
                            "exchange_price": exchange_price,
                            "diff_pct": diff_pct * 100,
                            "issue": "price_mismatch"
                        })
                        log.warning(
                            f"P0-9: Trailing stop {entry_id} price mismatch: "
                            f"local={state.current_stop_price:.2f}, "
                            f"exchange={exchange_price:.2f} ({diff_pct*100:.2f}%)"
                        )

                        # Update local to match exchange (exchange is truth)
                        state.current_stop_price = exchange_price
                        state.last_confirmed_stop_price = exchange_price
                        self._persist_state(state)

            # Check for stops on exchange that we don't track
            for entry_id, exchange_price in exchange_stops.items():
                if entry_id not in self._stops:
                    discrepancies.append({
                        "entry_order_id": entry_id,
                        "local_price": None,
                        "exchange_price": exchange_price,
                        "issue": "unknown_stop_on_exchange"
                    })
                    log.warning(
                        f"P0-9: Unknown stop order on exchange: {entry_id} @ {exchange_price:.2f}"
                    )

        return discrepancies
