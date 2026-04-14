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

    # Activation threshold for FIXED_DISTANCE mode (optional).
    # Trail only starts once MFE exceeds this percentage.
    # Before activation, the initial stop (hard SL) is the only protection.
    # 0.0 = trail from entry (default behavior)
    trail_activation_pct: float = 0.0

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

    # Context-aware trailing (X4-A CONTEXT) — transient, repopulated from live data
    entry_timestamp: float = 0.0              # time.time() at registration
    last_liq_z: Optional[float] = None        # latest liq_z
    last_cascade_state: Optional[str] = None  # CascadeState.value string
    last_vwap_distance: Optional[float] = None
    last_fill_count: Optional[int] = None
    last_atr_30m: Optional[float] = None
    cascade_quiet_since: Optional[float] = None  # when liq_z first dropped < 1.0
    peak_liq_z: float = 0.0                   # highest liq_z seen during trade
    last_adverse_l2: Optional[float] = None   # Adverse L2 gravity near price
    last_rolling_z: Optional[float] = None    # Rolling burst rate ratio

    # Orderflow momentum exit (OME) — tracks OF shift for smart profit-taking
    best_of: float = 0.5                       # Most favorable OF since entry
    of_was_favorable: bool = False             # Has OF been clearly in our direction?

    # Time-delayed watermark ratchet — prevents wicks from permanently ratcheting stop.
    # A new high must persist for RATCHET_DELAY_SEC before becoming the official watermark.
    _candidate_high: Optional[float] = None   # Candidate new high (LONG)
    _candidate_high_ts: float = 0.0           # When candidate was first seen
    _candidate_low: Optional[float] = None    # Candidate new low (SHORT)
    _candidate_low_ts: float = 0.0            # When candidate was first seen

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

    # Context-aware trailing stop constants
    _CASCADE_ACTIVE_STATES = {"TRIGGERED", "ABSORBING"}
    _LIQ_Z_ACTIVE = 1.0
    _VWAP_CLOSE_ATR_MULT = 0.5  # within 0.5 × ATR_5m of VWAP = "approaching"
    _THIN_BOOK_FILLS = 8
    _CASCADE_QUIET_GRACE_SEC = 120
    _PHASE2_WINDOW_SEC = 300
    _BE_FORCE_SEC = 7200  # Force break-even after 2h regardless
    _CASCADE_CONTINUE_Z = 20.0      # Rolling z threshold for "cascade continuing"
    _CASCADE_CONTINUE_GRACE = 120   # 2-min grace before circuit breaker active
    _RATCHET_DELAY_SEC = 5          # New high must persist 5s before becoming watermark

    def __init__(
        self,
        logger: logging.Logger = None,
        repository: Optional["ExecutionStateRepository"] = None
    ):
        self._logger = logger or logging.getLogger(__name__)
        self._stops: Dict[str, TrailingStopState] = {}  # entry_order_id -> state
        self._lock = RLock()
        self._context_log_times: Dict[str, float] = {}  # symbol -> last log time

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
                    # Activation gate
                    trail_activation_pct=config_dict.get('trail_activation_pct', 0.0),
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
                    entry_timestamp=p.created_at,  # Approximate from persistence
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
                # Activation gate
                'trail_activation_pct': state.config.trail_activation_pct,
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
        config: TrailingStopConfig = None,
        entry_timestamp: float = None
    ):
        """Register a new trailing stop for a position.

        Args:
            entry_order_id: Order ID of the entry
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            entry_price: Entry fill price
            initial_stop_price: Initial stop loss price
            config: Trailing stop configuration
            entry_timestamp: Time of entry (defaults to now)
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
            entry_timestamp=entry_timestamp or time.time(),
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

    def update_entry_price(self, symbol: str, new_entry_price: float,
                           current_price: float, new_initial_stop: float = None):
        """Update entry price after DCA add. Resets MFE tracking.

        Prevents stale MFE from immediately triggering trail after avg-down.

        Args:
            symbol: Trading symbol
            new_entry_price: New weighted average entry price
            current_price: Current market price
            new_initial_stop: Optional new initial stop price
        """
        with self._lock:
            for entry_id, state in self._stops.items():
                if state.symbol != symbol:
                    continue

                old_entry = state.entry_price
                state.entry_price = new_entry_price

                if new_initial_stop is not None:
                    state.initial_stop_price = new_initial_stop
                    # Reset stop to new initial — DCA avg-down means old trail may be
                    # above new entry price which would cause immediate stop-out
                    state.current_stop_price = new_initial_stop

                # Reset MFE tracking to new entry price (not current price).
                # DCA adds happen at adverse prices — resetting MFE to current
                # (adverse) price prevents the stop from ever seeing favorable MFE.
                # Using new_entry_price means MFE tracks from the averaged entry.
                if state.direction == "LONG":
                    state.highest_price = new_entry_price
                    state._candidate_high = None
                else:
                    state.lowest_price = new_entry_price
                    state._candidate_low = None

                # Reset break-even (new avg entry changes the BE level)
                state.break_even_triggered = False

                self._logger.info(
                    f"X4-A DCA: {symbol} entry {old_entry:.2f} -> {new_entry_price:.2f} "
                    f"MFE reset to {current_price:.2f} stop={state.current_stop_price:.2f}"
                )

                # Persist updated state
                self._persist_state(state)

    def update_price(self, symbol: str, price: float, atr: Optional[float] = None,
                     orderflow_imbalance: Optional[float] = None,
                     liq_z: Optional[float] = None,
                     cascade_state: Optional[str] = None,
                     vwap_distance: Optional[float] = None,
                     fill_count: Optional[int] = None,
                     atr_30m: Optional[float] = None,
                     adverse_l2_gravity: Optional[float] = None,
                     rolling_z: Optional[float] = None):
        """Update price and potentially trail stops.

        Args:
            symbol: Trading symbol
            price: Current market price
            atr: Current ATR value (for ATR_MULTIPLE mode)
            orderflow_imbalance: Buy/sell imbalance (0-1, <0.5 = selling pressure)
            liq_z: Current liquidation z-score
            cascade_state: Current CascadeState value string
            vwap_distance: VWAP distance ratio
            fill_count: Orderflow fill count
            atr_30m: 30-minute ATR value
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
                    # Track best OF for momentum exit
                    if state.direction == "SHORT":
                        if orderflow_imbalance < state.best_of:
                            state.best_of = orderflow_imbalance
                        if orderflow_imbalance < 0.45:
                            state.of_was_favorable = True
                    else:  # LONG
                        if orderflow_imbalance > state.best_of:
                            state.best_of = orderflow_imbalance
                        if orderflow_imbalance > 0.55:
                            state.of_was_favorable = True

                # Update context fields if provided
                if liq_z is not None:
                    state.last_liq_z = liq_z
                    state.peak_liq_z = max(state.peak_liq_z, liq_z)
                    # Track cascade quiet transition
                    if liq_z < self._LIQ_Z_ACTIVE:
                        if state.cascade_quiet_since is None:
                            state.cascade_quiet_since = time.time()
                    else:
                        state.cascade_quiet_since = None
                if cascade_state is not None:
                    state.last_cascade_state = cascade_state
                if vwap_distance is not None:
                    state.last_vwap_distance = vwap_distance
                if fill_count is not None:
                    state.last_fill_count = fill_count
                if atr_30m is not None:
                    state.last_atr_30m = atr_30m
                if adverse_l2_gravity is not None:
                    state.last_adverse_l2 = adverse_l2_gravity
                if rolling_z is not None:
                    state.last_rolling_z = rolling_z

                # Update high/low watermark with time-delayed ratchet.
                # A new extreme must persist for _RATCHET_DELAY_SEC before
                # becoming the official watermark. Prevents wicks from
                # permanently ratcheting the trailing stop.
                _now_wm = time.time()
                if state.direction == "LONG":
                    if price > state.highest_price:
                        if state._candidate_high is None or price > state._candidate_high:
                            state._candidate_high = price
                            state._candidate_high_ts = _now_wm
                        elif _now_wm - state._candidate_high_ts >= self._RATCHET_DELAY_SEC:
                            state.highest_price = state._candidate_high
                            state._candidate_high = None
                    else:
                        # Price retreated below current high — keep candidate alive
                        # (it may still be confirmed if delay hasn't elapsed)
                        if (state._candidate_high is not None and
                                _now_wm - state._candidate_high_ts >= self._RATCHET_DELAY_SEC):
                            state.highest_price = state._candidate_high
                            state._candidate_high = None
                else:
                    if price < state.lowest_price:
                        if state._candidate_low is None or price < state._candidate_low:
                            state._candidate_low = price
                            state._candidate_low_ts = _now_wm
                        elif _now_wm - state._candidate_low_ts >= self._RATCHET_DELAY_SEC:
                            state.lowest_price = state._candidate_low
                            state._candidate_low = None
                    else:
                        if (state._candidate_low is not None and
                                _now_wm - state._candidate_low_ts >= self._RATCHET_DELAY_SEC):
                            state.lowest_price = state._candidate_low
                            state._candidate_low = None

                # Context logging (throttled 30s/symbol)
                if (state.config.mode == TrailingMode.ATR_PROGRESSIVE and
                        state.last_liq_z is not None):
                    _now = time.time()
                    _last_log = self._context_log_times.get(symbol, 0)
                    _cascade_active = (
                        (state.last_liq_z is not None and state.last_liq_z >= self._LIQ_Z_ACTIVE) or
                        (state.last_cascade_state in self._CASCADE_ACTIVE_STATES)
                    )
                    _hold = _now - state.entry_timestamp if state.entry_timestamp > 0 else 0
                    _be_suppressed = (
                        _cascade_active and
                        _hold < self._PHASE2_WINDOW_SEC and
                        not state.break_even_triggered
                    )
                    _vwap_close = (
                        state.last_vwap_distance is not None and
                        state.current_atr is not None and state.current_atr > 0 and
                        abs(state.last_vwap_distance) < self._VWAP_CLOSE_ATR_MULT * state.current_atr
                    )
                    if (_now - _last_log >= 30) and (_cascade_active or _be_suppressed or _vwap_close):
                        self._context_log_times[symbol] = _now
                        _vwap_str = f"{state.last_vwap_distance:.4f}" if state.last_vwap_distance is not None else "N/A"
                        _l2_str = f"{state.last_adverse_l2:,.0f}" if state.last_adverse_l2 is not None else "N/A"
                        _rz_str = f"{state.last_rolling_z:.1f}" if state.last_rolling_z is not None else "N/A"
                        self._logger.info(
                            f"X4-A CONTEXT: {symbol} liq_z={state.last_liq_z:.2f} "
                            f"cascade={state.last_cascade_state} "
                            f"vwap_d={_vwap_str} "
                            f"fills={state.last_fill_count} hold={_hold:.0f}s "
                            f"l2_adv={_l2_str} rolling_z={_rz_str} "
                            f"be_suppressed={_be_suppressed}"
                        )

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

        # Context: determine if cascade is active (used for BE suppression + stop widening)
        now = time.time()
        hold_seconds = now - state.entry_timestamp if state.entry_timestamp > 0 else 0
        _cascade_active = (
            (state.last_liq_z is not None and state.last_liq_z >= self._LIQ_Z_ACTIVE) or
            (state.last_cascade_state in self._CASCADE_ACTIVE_STATES)
        )

        # Cascade continuation: rolling_z still elevated after grace period
        # = cascade didn't exhaust, it's a trend step not mean-reversion
        _cascade_continuing = (
            state.last_rolling_z is not None and
            state.last_rolling_z >= self._CASCADE_CONTINUE_Z and
            hold_seconds >= self._CASCADE_CONTINUE_GRACE
        )

        # Check break-even trigger first (applies to all modes)
        if not state.break_even_triggered:
            if state.direction == "LONG":
                profit_pct = (current_price - entry) / entry
            else:
                profit_pct = (entry - current_price) / entry

            if profit_pct >= config.break_even_trigger_pct:
                # Suppress BE during active cascade in early trade (Phase 1/2 bounce-retrace)
                be_suppressed = (
                    _cascade_active and
                    hold_seconds < self._PHASE2_WINDOW_SEC and
                    config.mode == TrailingMode.ATR_PROGRESSIVE
                )
                # Safety: force BE after 2h regardless
                if hold_seconds > self._BE_FORCE_SEC and profit_pct > 0:
                    be_suppressed = False
                # Cascade continuation → force BE (override suppression)
                if _cascade_continuing:
                    be_suppressed = False

                if not be_suppressed:
                    state.break_even_triggered = True
                    if state.direction == "LONG":
                        be_stop = entry * (1 + config.break_even_offset_pct)
                        if be_stop > current_stop:
                            return be_stop
                    else:  # SHORT
                        be_stop = entry * (1 - config.break_even_offset_pct)
                        if be_stop < current_stop:
                            return be_stop

        # Mode-specific trailing
        if config.mode == TrailingMode.BREAK_EVEN_ONLY:
            # Only move to break-even (handled above)
            return None

        elif config.mode == TrailingMode.FIXED_DISTANCE:
            # Activation gate: don't start trailing until MFE exceeds threshold
            if config.trail_activation_pct > 0:
                if state.direction == "LONG":
                    mfe_pct = (state.highest_price - entry) / entry
                else:
                    mfe_pct = (entry - state.lowest_price) / entry
                if mfe_pct < config.trail_activation_pct:
                    return None  # Not activated yet — keep initial stop (hard SL)

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
            base_mult = max(config.atr_prog_end_mult, min(config.atr_prog_start_mult, raw_mult))

            # Context-aware multiplier: widen/tighten based on live market state
            context_mult = 1.0

            if _cascade_active:
                # Rule 1: Cascade active → widen stop (give bounce room)
                context_mult = max(context_mult, 1.3)
            elif (state.cascade_quiet_since is not None and
                  hold_seconds < self._PHASE2_WINDOW_SEC):
                # Rule 2: Cascade just quieted → linear ramp 1.3→1.0 over grace period
                quiet_elapsed = now - state.cascade_quiet_since
                if quiet_elapsed < self._CASCADE_QUIET_GRACE_SEC:
                    ramp = 1.0 + 0.3 * (1.0 - quiet_elapsed / self._CASCADE_QUIET_GRACE_SEC)
                    context_mult = max(context_mult, ramp)

            # Rule 3: Favorable orderflow → widen slightly
            if state.last_orderflow is not None:
                of = state.last_orderflow
                favorable = (
                    (state.direction == "LONG" and of > 0.6) or
                    (state.direction == "SHORT" and of < 0.4)
                )
                if favorable:
                    context_mult = max(context_mult, 1.15)

            # Rule 4: Thin book → widen (few fills = volatile gaps)
            if (state.last_fill_count is not None and
                    state.last_fill_count < self._THIN_BOOK_FILLS):
                context_mult = max(context_mult, 1.2)

            # Rule 5: Approaching VWAP (only when NOT cascade active) → tighten to lock
            # Uses ATR-normalized distance: vwap_distance < 0.5 × ATR_5m = "close"
            # (was comparing raw dollar distance vs 0.003 — never fired for any coin)
            if (not _cascade_active and
                    state.last_vwap_distance is not None and
                    state.current_atr is not None and state.current_atr > 0 and
                    abs(state.last_vwap_distance) < self._VWAP_CLOSE_ATR_MULT * state.current_atr and
                    mfe_profit_pct > config.break_even_trigger_pct):
                context_mult = min(context_mult, 0.8)

            atr_mult = base_mult * context_mult
            # Clamp to [end_mult, start_mult]
            atr_mult = max(config.atr_prog_end_mult, min(config.atr_prog_start_mult, atr_mult))

            # Cascade continuation → slam to minimum ATR distance
            if _cascade_continuing:
                atr_mult = config.atr_prog_end_mult

            # Orderflow-aware tightening: adverse flow reduces multiplier (existing logic)
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

            # Rule: Adverse trade volume near price → tighten stop
            # Concentrated sell (for LONG) or buy (for SHORT) volume within 30bps
            # signals institutional conviction against the position.
            if state.last_adverse_l2 is not None and state.last_adverse_l2 > 500_000:
                atr_mult *= 0.7
                atr_mult = max(config.atr_prog_end_mult, atr_mult)

            # Calculate ATR-based distance with floor protection
            atr_distance = state.current_atr * atr_mult
            min_distance = entry * config.atr_prog_min_pct
            distance = max(atr_distance, min_distance)

            # Profit lock ratio: reduce during active cascade to avoid locking in too early
            lock_ratio = config.atr_prog_min_lock_ratio
            if _cascade_active and hold_seconds < self._PHASE2_WINDOW_SEC:
                lock_ratio = 0.20

            # Calculate stop from MFE (highest/lowest), not current price
            if state.direction == "LONG":
                atr_stop = state.highest_price - distance

                # Only engage profit-lock after meaningful MFE
                # Without this, profit_lock at MFE=0 equals entry price, killing the position
                new_stop = atr_stop
                if mfe_profit_pct >= config.break_even_trigger_pct:
                    locked_profit = mfe_profit_abs * lock_ratio
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
                    locked_profit = mfe_profit_abs * lock_ratio
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
