"""
EP-2 Strategy #2: Order Block Pattern Strategy

Pure proposal generator using Tier B-5 pattern primitives (OrderBlockPrimitive).

Authority:
- RAW-DATA PRIMITIVES.md Section 8 (Historical Memory Primitives)
- M4 Structural Primitive Canon v1.0 (Tier B-5)
- STRATEGY_ADMISSION_CRITERIA.md
- EP-3 Arbitration & Risk Gate v1.0

Purpose:
Detects order blocks with CONFIRMATION (interaction pattern + recency).
Only proposes ENTRY when pattern shows CLUSTERED activity (not random).

Pattern Logic:
1. Order block must exist (node with significant interaction history)
2. Interactions must be BURSTY (clustered, not evenly distributed)
3. Activity must be RECENT (not stale)
4. Node must have sufficient STRENGTH (memory persistence)

EXIT Logic:
Only exits when order block is INVALIDATED:
- Order block disappeared (is None)
- Order block went stale (no recent interaction)
- Node ID changed (different node)

This eliminates oscillation because:
- Entry requires clustered interaction pattern (not instantaneous value)
- Exit requires staleness/disappearance (not threshold drop)

CRITICAL: This module makes no decisions. It only proposes.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
from runtime.position.types import PositionState

if TYPE_CHECKING:
    from memory.m4_node_patterns import OrderBlockPrimitive


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass(frozen=True)
class OrderBlockConfig:
    """Configuration for order block pattern detection.

    These are structural thresholds, not predictions or confidence scores.
    """
    # Minimum interaction count for entry
    min_interactions: int = 10

    # Minimum burstiness coefficient (-1=regular, 0=Poisson, 1=bursty)
    # Positive values indicate clustered activity (institutional pattern)
    min_burstiness: float = 0.3

    # Maximum idle time (seconds) for order block to be considered active
    max_idle_sec: float = 300.0

    # Minimum node strength for validity
    min_node_strength: float = 0.4

    # Staleness threshold for exit (seconds)
    staleness_threshold_sec: float = 600.0  # 10 minutes


# Default config
DEFAULT_ORDERBLOCK_CONFIG = OrderBlockConfig()


@dataclass(frozen=True)
class InstantaneousFallbackConfig:
    """Configuration for instantaneous primitive fallback."""
    min_velocity_abs: float = 0.001  # 0.1% per second
    min_compactness_ratio: float = 0.3
    min_acceptance_ratio: float = 0.5


DEFAULT_INSTANTANEOUS_CONFIG = InstantaneousFallbackConfig()


# ==============================================================================
# Input/Output Types
# ==============================================================================

@dataclass(frozen=True)
class StrategyContext:
    """Immutable context for strategy execution."""
    context_id: str
    timestamp: float


@dataclass(frozen=True)
class PermissionOutput:
    """M6 permission result (from M6 scaffolding)."""
    result: str  # "ALLOWED" | "DENIED"
    mandate_id: str
    action_id: str
    reason_code: str
    timestamp: float


@dataclass(frozen=True)
class StrategyProposal:
    """Immutable strategy proposal for EP-3 arbitration."""
    strategy_id: str
    action_type: str  # "ENTRY" | "EXIT"
    confidence: str  # Opaque label (NOT numeric)
    justification_ref: str  # Reference ID only
    timestamp: float
    direction: str = None  # "LONG" | "SHORT" for ENTRY (derived from order block type)


# ==============================================================================
# Stability Tracking (for instantaneous primitive fallback)
# ==============================================================================

_stability_counter: dict = {}
_exit_stability_counter: dict = {}
MIN_STABILITY_CYCLES = 3
MIN_EXIT_STABILITY_CYCLES = 3


def _update_stability(symbol: str, conditions_met: bool) -> int:
    """Update stability counter for symbol."""
    global _stability_counter, _exit_stability_counter
    if conditions_met:
        _stability_counter[symbol] = _stability_counter.get(symbol, 0) + 1
        _exit_stability_counter[symbol] = 0
    else:
        _stability_counter[symbol] = 0
        _exit_stability_counter[symbol] = _exit_stability_counter.get(symbol, 0) + 1
    return _stability_counter.get(symbol, 0)


def _check_stability(symbol: str) -> bool:
    """Check if stability requirement is met."""
    return _stability_counter.get(symbol, 0) >= MIN_STABILITY_CYCLES


def _check_exit_stability(symbol: str) -> bool:
    """Check if exit stability is met."""
    return _exit_stability_counter.get(symbol, 0) >= MIN_EXIT_STABILITY_CYCLES


# ==============================================================================
# Entry Context Tracking (for proper EXIT logic)
# ==============================================================================

# Track which order block triggered entry (per symbol)
_entry_orderblock_context: dict = {}
_entry_method: dict = {}  # symbol -> "PATTERN" or "INSTANTANEOUS"


def _record_entry_orderblock(symbol: str, ob: 'OrderBlockPrimitive'):
    """Record the order block that triggered entry."""
    _entry_orderblock_context[symbol] = {
        "node_id": ob.node_id,
        "price_center": ob.price_center,
        "interaction_count_at_entry": ob.interaction_count,
        "last_interaction_at_entry": ob.last_interaction_ts,
        "timestamp": ob.timestamp
    }


def _get_entry_orderblock(symbol: str) -> Optional[dict]:
    """Get the order block context that triggered entry."""
    return _entry_orderblock_context.get(symbol)


def _clear_entry_orderblock(symbol: str):
    """Clear entry context (on exit)."""
    _entry_orderblock_context.pop(symbol, None)


def reset_entry_context():
    """Reset all entry context (for testing)."""
    global _entry_orderblock_context, _entry_method, _stability_counter, _exit_stability_counter
    _entry_orderblock_context = {}
    _entry_method = {}
    _stability_counter = {}
    _exit_stability_counter = {}


# ==============================================================================
# Instantaneous Primitive Fallback
# ==============================================================================

def _instantaneous_conditions_met(
    velocity,
    compactness,
    acceptance,
    config: InstantaneousFallbackConfig = DEFAULT_INSTANTANEOUS_CONFIG
) -> bool:
    """Check if instantaneous primitive conditions are met."""
    if velocity is None or compactness is None or acceptance is None:
        return False
    if abs(velocity.velocity) < config.min_velocity_abs:
        return False
    if compactness.compactness_ratio < config.min_compactness_ratio:
        return False
    if acceptance.acceptance_ratio < config.min_acceptance_ratio:
        return False
    return True


# ==============================================================================
# Pattern Detection
# ==============================================================================

def _is_orderblock_confirmed(
    ob: 'OrderBlockPrimitive',
    config: OrderBlockConfig = DEFAULT_ORDERBLOCK_CONFIG
) -> bool:
    """
    Check if order block pattern is CONFIRMED.

    Confirmation requires:
    1. Sufficient interactions (activity threshold)
    2. Bursty interaction pattern (clustered, not regular)
    3. Recent activity (not stale)
    4. Strong memory persistence

    Returns:
        True if pattern is confirmed, False otherwise
    """
    # Must have minimum interactions
    if ob.interaction_count < config.min_interactions:
        return False

    # Must have bursty pattern (clustered activity)
    if ob.burstiness_coefficient < config.min_burstiness:
        return False

    # Must be recent (not stale)
    if ob.time_since_interaction_sec > config.max_idle_sec:
        return False

    # Must have strong memory
    if ob.node_strength < config.min_node_strength:
        return False

    return True


def _is_orderblock_invalidated(
    ob: Optional['OrderBlockPrimitive'],
    entry_context: dict,
    current_time: float,
    config: OrderBlockConfig = DEFAULT_ORDERBLOCK_CONFIG
) -> bool:
    """
    Check if the entry order block has been INVALIDATED.

    Invalidation occurs when:
    1. Order block is None (disappeared)
    2. Node ID changed (different node now)
    3. Order block went stale (no activity for staleness_threshold)

    Returns:
        True if order block is invalidated, False otherwise
    """
    # Order block disappeared
    if ob is None:
        return True

    # Node ID changed
    if ob.node_id != entry_context["node_id"]:
        return True

    # Check for staleness
    time_since_entry_interaction = current_time - entry_context["last_interaction_at_entry"]
    if time_since_entry_interaction > config.staleness_threshold_sec:
        # No new interaction since entry for too long -> stale
        if ob.last_interaction_ts <= entry_context["last_interaction_at_entry"]:
            return True

    return False


# ==============================================================================
# EP-2 Strategy #2: Order Block Pattern Strategy
# ==============================================================================

def generate_kinematics_proposal(
    *,
    order_block: Optional['OrderBlockPrimitive'] = None,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    config: OrderBlockConfig = DEFAULT_ORDERBLOCK_CONFIG,
    # Instantaneous primitives for fallback
    velocity=None,
    compactness=None,
    acceptance=None,
    instantaneous_config: InstantaneousFallbackConfig = DEFAULT_INSTANTANEOUS_CONFIG
) -> Optional[StrategyProposal]:
    """
    Generate order block pattern proposal.

    Primary: Uses pattern primitives (order_block) with confirmation.
    Fallback: Uses instantaneous primitives with stability requirement.

    Args:
        order_block: B5 OrderBlockPrimitive or None
        context: Strategy execution context
        permission: M6 permission result
        position_state: Current position state
        config: Pattern configuration thresholds
        velocity: A3 primitive (fallback)
        compactness: A4 primitive (fallback)
        acceptance: A5 primitive (fallback)
        instantaneous_config: Fallback thresholds

    Returns:
        StrategyProposal if conditions warrant action, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None

    # Determine symbol
    if order_block is not None:
        symbol = order_block.symbol
    elif velocity is not None and hasattr(velocity, 'symbol'):
        symbol = velocity.symbol
    else:
        symbol = "UNKNOWN"

    # Check which primitives are available
    has_pattern = order_block is not None
    has_instantaneous = velocity is not None and compactness is not None and acceptance is not None

    # Rule 2: If position exists, check for EXIT
    if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
        entry_method = _entry_method.get(symbol, "PATTERN")
        entry_context = _get_entry_orderblock(symbol)

        if entry_method == "PATTERN" and entry_context is not None:
            if _is_orderblock_invalidated(order_block, entry_context, context.timestamp, config):
                _clear_entry_orderblock(symbol)
                _entry_method.pop(symbol, None)
                return StrategyProposal(
                    strategy_id="EP2-KINEMATICS-V2",
                    action_type="EXIT",
                    confidence="ORDERBLOCK_INVALIDATED",
                    justification_ref=f"B5_OB|INVALIDATED|{entry_context['node_id']}",
                    timestamp=context.timestamp
                )
        elif entry_method == "INSTANTANEOUS":
            conditions_met = _instantaneous_conditions_met(
                velocity, compactness, acceptance, instantaneous_config
            )
            _update_stability(symbol, conditions_met)

            # Exit only after conditions absent for multiple cycles
            if _check_exit_stability(symbol):
                _entry_method.pop(symbol, None)
                _exit_stability_counter[symbol] = 0
                return StrategyProposal(
                    strategy_id="EP2-KINEMATICS-V2",
                    action_type="EXIT",
                    confidence="CONDITIONS_ABSENT",
                    justification_ref=f"A3|A4|A5_ABSENT|STABLE{MIN_EXIT_STABILITY_CYCLES}",
                    timestamp=context.timestamp
                )

        return None

    # Rule 3: Position FLAT -> check for ENTRY
    if position_state == PositionState.FLAT or position_state is None:
        # Priority 1: Pattern-based entry
        if has_pattern and _is_orderblock_confirmed(order_block, config):
            _record_entry_orderblock(symbol, order_block)
            _entry_method[symbol] = "PATTERN"
            # Derive direction from order block side: bid=LONG (buy support), ask=SHORT (sell resistance)
            entry_direction = "LONG" if order_block.side == "bid" else "SHORT"
            return StrategyProposal(
                strategy_id="EP2-KINEMATICS-V2",
                action_type="ENTRY",
                confidence="ORDERBLOCK_CONFIRMED",
                justification_ref=f"B5_OB|{order_block.side.upper()}|INT{order_block.interaction_count}",
                timestamp=context.timestamp,
                direction=entry_direction
            )

        # Priority 2: Instantaneous fallback with stability
        if has_instantaneous:
            # NOTE: Instantaneous path disabled - cannot determine direction without order block
            # F5 requires direction for all ENTRY mandates
            # Re-enable when velocity/compactness includes directional context
            # conditions_met = _instantaneous_conditions_met(...)
            # if conditions_met and _check_stability(symbol):
            #     _entry_method[symbol] = "INSTANTANEOUS"
            #     ...
            pass

    return None
