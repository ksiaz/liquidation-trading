"""
EP-2 Strategy #1: Supply/Demand Zone Pattern Strategy

Pure proposal generator using Tier B-5 pattern primitives (SupplyDemandZonePrimitive).

Authority:
- RAW-DATA PRIMITIVES.md Section 8 (Historical Memory Primitives)
- M4 Structural Primitive Canon v1.0 (Tier B-5)
- STRATEGY_ADMISSION_CRITERIA.md
- EP-3 Arbitration & Risk Gate v1.0

Purpose:
Detects supply/demand zones with CONFIRMATION (retest pattern).
Only proposes ENTRY when pattern is CONFIRMED (not on first touch).

Pattern Logic:
1. Zone must exist (cluster of nodes with activity)
2. Displacement must have occurred (price moved away from zone)
3. Retest must be detected (price returned to zone)
4. Retest count >= 1 (CONFIRMATION - price returned to zone)

EXIT Logic:
Only exits when zone is INVALIDATED:
- Zone disappeared (is None)
- Zone broken through (price closes beyond zone bounds)

This eliminates oscillation because:
- Entry requires CONFIRMATION (not instantaneous threshold)
- Exit requires INVALIDATION (not threshold drop)

CRITICAL: This module makes no decisions. It only proposes.
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
from runtime.position.types import PositionState

if TYPE_CHECKING:
    from memory.m4_node_patterns import SupplyDemandZonePrimitive


# ==============================================================================
# Configuration
# ==============================================================================

@dataclass(frozen=True)
class SupplyDemandZoneConfig:
    """Configuration for supply/demand zone pattern detection.

    These are structural thresholds, not predictions or confidence scores.
    """
    # Minimum retest count for CONFIRMATION (first retest = 1)
    min_retest_count: int = 1

    # Minimum node count to consider zone valid
    min_node_count: int = 3

    # Minimum average node strength for zone validity
    min_avg_node_strength: float = 0.3

    # Zone break threshold - if price moves this far beyond zone, it's invalidated
    # (as fraction of zone width, e.g., 1.0 = one zone width beyond)
    zone_break_threshold: float = 1.0


# Default config - can be overridden per-instance
DEFAULT_ZONE_CONFIG = SupplyDemandZoneConfig()


@dataclass(frozen=True)
class InstantaneousFallbackConfig:
    """Configuration for instantaneous primitive fallback.

    Used when pattern primitives (supply_demand_zone) are not available.
    These thresholds require stability (N consecutive cycles) to prevent oscillation.
    """
    # Zone penetration: minimum depth as fraction of price
    min_penetration_depth: float = 0.005  # 0.5%

    # Traversal compactness: minimum ratio (0-1)
    min_compactness_ratio: float = 0.3

    # Central tendency deviation: minimum absolute deviation
    min_deviation_value: float = 0.002  # 0.2%


DEFAULT_INSTANTANEOUS_CONFIG = InstantaneousFallbackConfig()


# ==============================================================================
# Input/Output Types
# ==============================================================================

@dataclass(frozen=True)
class StrategyContext:
    """Immutable context for strategy execution."""
    context_id: str
    timestamp: float
    current_price: Optional[float] = None  # For zone break detection


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


# ==============================================================================
# Stability Tracking (for instantaneous primitive fallback)
# ==============================================================================

# Track consecutive cycles where conditions are met (per symbol)
# This prevents oscillation when using instantaneous primitives
_stability_counter: dict = {}

# Track consecutive cycles where conditions are NOT met (for exit stability)
_exit_stability_counter: dict = {}

# Minimum consecutive cycles required for entry (stability requirement)
# Keep low to allow trades while preventing rapid oscillation
MIN_STABILITY_CYCLES = 3

# Minimum consecutive cycles conditions must be absent before exit
MIN_EXIT_STABILITY_CYCLES = 3


def _update_stability(symbol: str, conditions_met: bool) -> int:
    """Update stability counter for symbol.

    Returns current count of consecutive cycles where conditions were met.
    """
    global _stability_counter, _exit_stability_counter
    if conditions_met:
        _stability_counter[symbol] = _stability_counter.get(symbol, 0) + 1
        _exit_stability_counter[symbol] = 0  # Reset exit counter when conditions met
    else:
        _stability_counter[symbol] = 0
        _exit_stability_counter[symbol] = _exit_stability_counter.get(symbol, 0) + 1
    return _stability_counter.get(symbol, 0)


def _check_stability(symbol: str) -> bool:
    """Check if stability requirement is met (N consecutive cycles)."""
    return _stability_counter.get(symbol, 0) >= MIN_STABILITY_CYCLES


def _check_exit_stability(symbol: str) -> bool:
    """Check if exit stability is met (conditions absent for N cycles)."""
    return _exit_stability_counter.get(symbol, 0) >= MIN_EXIT_STABILITY_CYCLES


# ==============================================================================
# Entry Context Tracking (for proper EXIT logic)
# ==============================================================================

# Track which zone triggered entry (per symbol)
# This enables exit only when THAT zone is invalidated
_entry_zone_context: dict = {}

# Track entry method for proper exit logic
_entry_method: dict = {}  # symbol -> "PATTERN" or "INSTANTANEOUS"


def _record_entry_zone(symbol: str, zone: 'SupplyDemandZonePrimitive'):
    """Record the zone that triggered entry."""
    _entry_zone_context[symbol] = {
        "zone_id": zone.zone_id,
        "zone_low": zone.zone_low,
        "zone_high": zone.zone_high,
        "zone_center": zone.zone_center,
        "retest_count_at_entry": zone.retest_count,
        "timestamp": zone.timestamp
    }


def _get_entry_zone(symbol: str) -> Optional[dict]:
    """Get the zone context that triggered entry."""
    return _entry_zone_context.get(symbol)


def _clear_entry_zone(symbol: str):
    """Clear entry zone context (on exit)."""
    _entry_zone_context.pop(symbol, None)


def reset_entry_context():
    """Reset all entry context (for testing)."""
    global _entry_zone_context, _entry_method, _stability_counter, _exit_stability_counter
    _entry_zone_context = {}
    _entry_method = {}
    _stability_counter = {}
    _exit_stability_counter = {}


# ==============================================================================
# Instantaneous Primitive Fallback (with stability)
# ==============================================================================

def _instantaneous_conditions_met(
    zone_penetration,
    traversal_compactness,
    central_tendency_deviation,
    config: InstantaneousFallbackConfig = DEFAULT_INSTANTANEOUS_CONFIG
) -> bool:
    """Check if instantaneous primitive conditions are met.

    Used as fallback when pattern primitives aren't available.
    """
    if zone_penetration is None:
        return False
    if traversal_compactness is None:
        return False
    if central_tendency_deviation is None:
        return False

    if zone_penetration.penetration_depth < config.min_penetration_depth:
        return False
    if traversal_compactness.compactness_ratio < config.min_compactness_ratio:
        return False
    if abs(central_tendency_deviation.deviation_value) < config.min_deviation_value:
        return False

    return True


# ==============================================================================
# Pattern Detection
# ==============================================================================

def _is_zone_confirmed(
    zone: 'SupplyDemandZonePrimitive',
    config: SupplyDemandZoneConfig = DEFAULT_ZONE_CONFIG
) -> bool:
    """
    Check if zone pattern is CONFIRMED.

    Confirmation requires:
    1. Displacement detected (price moved away from zone)
    2. Retest detected (price returned to zone)
    3. Retest count >= min_retest_count (price returned = confirmation)
    4. Zone has sufficient structure (node count, strength)

    Returns:
        True if pattern is confirmed, False otherwise
    """
    # Zone must have displacement (price moved away)
    if not zone.displacement_detected:
        return False

    # Zone must have retest (price returned)
    if not zone.retest_detected:
        return False

    # Retest count must meet minimum (confirmation threshold)
    if zone.retest_count is None or zone.retest_count < config.min_retest_count:
        return False

    # Zone must have sufficient structure
    if zone.node_count < config.min_node_count:
        return False

    if zone.avg_node_strength < config.min_avg_node_strength:
        return False

    return True


def _is_zone_invalidated(
    zone: Optional['SupplyDemandZonePrimitive'],
    entry_context: dict,
    current_price: Optional[float],
    config: SupplyDemandZoneConfig = DEFAULT_ZONE_CONFIG
) -> bool:
    """
    Check if the entry zone has been INVALIDATED.

    Invalidation occurs when:
    1. Zone is None (disappeared completely)
    2. Zone ID changed (different zone now)
    3. Price broke through zone (closed beyond bounds)

    Returns:
        True if zone is invalidated, False otherwise
    """
    # Zone disappeared
    if zone is None:
        return True

    # Zone ID changed (different zone now in same region)
    if zone.zone_id != entry_context["zone_id"]:
        return True

    # Check for zone break (price closed beyond bounds)
    if current_price is not None:
        zone_width = zone.zone_high - zone.zone_low
        break_distance = zone_width * config.zone_break_threshold

        # Demand zone (below price): invalidated if price closes far below
        if zone.zone_type == "demand":
            if current_price < zone.zone_low - break_distance:
                return True

        # Supply zone (above price): invalidated if price closes far above
        elif zone.zone_type == "supply":
            if current_price > zone.zone_high + break_distance:
                return True

    return False


# ==============================================================================
# EP-2 Strategy #1: Supply/Demand Zone Pattern Strategy
# ==============================================================================

def generate_geometry_proposal(
    *,
    supply_demand_zone: Optional['SupplyDemandZonePrimitive'] = None,
    context: StrategyContext,
    permission: PermissionOutput,
    position_state: Optional[PositionState] = None,
    config: SupplyDemandZoneConfig = DEFAULT_ZONE_CONFIG,
    # Instantaneous primitives for fallback when pattern primitives unavailable
    zone_penetration=None,
    traversal_compactness=None,
    central_tendency_deviation=None,
    instantaneous_config: InstantaneousFallbackConfig = DEFAULT_INSTANTANEOUS_CONFIG
) -> Optional[StrategyProposal]:
    """
    Generate supply/demand zone pattern proposal.

    Primary: Uses pattern primitives (supply_demand_zone) with confirmation.
    Fallback: Uses instantaneous primitives with stability requirement (3 cycles).

    Pattern ENTRY requires:
    - Zone exists with displacement + retest
    - Retest count >= 1 (confirmation)
    - Zone has sufficient structure

    Fallback ENTRY requires:
    - All instantaneous thresholds met
    - Conditions stable for MIN_STABILITY_CYCLES consecutive cycles

    EXIT requires:
    - Pattern: Zone invalidated (disappeared, ID changed, price broke through)
    - Fallback: Conditions not met for MIN_STABILITY_CYCLES cycles

    Args:
        supply_demand_zone: B5 SupplyDemandZonePrimitive or None
        context: Strategy execution context (includes current_price)
        permission: M6 permission result
        position_state: Current position state
        config: Pattern configuration thresholds
        zone_penetration: A6 primitive (fallback)
        traversal_compactness: A4 primitive (fallback)
        central_tendency_deviation: A8 primitive (fallback)
        instantaneous_config: Fallback thresholds

    Returns:
        StrategyProposal if conditions warrant action, None otherwise
    """
    # Rule 1: M6 DENIED -> no proposal
    if permission.result == "DENIED":
        return None

    # Determine symbol
    if supply_demand_zone is not None:
        symbol = supply_demand_zone.symbol
    elif zone_penetration is not None and hasattr(zone_penetration, 'symbol'):
        symbol = zone_penetration.symbol
    else:
        symbol = "UNKNOWN"

    # Check which primitives are available
    has_pattern_primitive = supply_demand_zone is not None
    has_instantaneous = (zone_penetration is not None and
                         traversal_compactness is not None and
                         central_tendency_deviation is not None)

    # Rule 2: If position exists, check for EXIT
    if position_state in (PositionState.ENTERING, PositionState.OPEN, PositionState.REDUCING):
        entry_method = _entry_method.get(symbol, "PATTERN")
        entry_context = _get_entry_zone(symbol)

        if entry_method == "PATTERN" and entry_context is not None:
            # Pattern-based exit: check zone invalidation
            if _is_zone_invalidated(supply_demand_zone, entry_context, context.current_price, config):
                _clear_entry_zone(symbol)
                _entry_method.pop(symbol, None)
                return StrategyProposal(
                    strategy_id="EP2-GEOMETRY-V2",
                    action_type="EXIT",
                    confidence="ZONE_INVALIDATED",
                    justification_ref=f"B5_SDZ|INVALIDATED|{entry_context['zone_id']}",
                    timestamp=context.timestamp
                )
        elif entry_method == "INSTANTANEOUS":
            # Instantaneous-based exit: require conditions to be absent for multiple cycles
            conditions_met = _instantaneous_conditions_met(
                zone_penetration, traversal_compactness, central_tendency_deviation, instantaneous_config
            )
            _update_stability(symbol, conditions_met)

            # Exit only if conditions have been NOT met for MIN_EXIT_STABILITY_CYCLES
            if _check_exit_stability(symbol):
                _entry_method.pop(symbol, None)
                _exit_stability_counter[symbol] = 0  # Reset after exit
                return StrategyProposal(
                    strategy_id="EP2-GEOMETRY-V2",
                    action_type="EXIT",
                    confidence="CONDITIONS_ABSENT",
                    justification_ref=f"A6|A4|A8_ABSENT|STABLE{MIN_EXIT_STABILITY_CYCLES}",
                    timestamp=context.timestamp
                )

        # Conditions still valid -> HOLD
        return None

    # Rule 3: Position FLAT -> check for ENTRY
    if position_state == PositionState.FLAT or position_state is None:
        # Priority 1: Pattern-based entry (preferred, no oscillation risk)
        if has_pattern_primitive and _is_zone_confirmed(supply_demand_zone, config):
            _record_entry_zone(symbol, supply_demand_zone)
            _entry_method[symbol] = "PATTERN"
            return StrategyProposal(
                strategy_id="EP2-GEOMETRY-V2",
                action_type="ENTRY",
                confidence="ZONE_CONFIRMED",
                justification_ref=f"B5_SDZ|{supply_demand_zone.zone_type.upper()}|RT{supply_demand_zone.retest_count}",
                timestamp=context.timestamp
            )

        # Priority 2: Instantaneous fallback with stability requirement
        if has_instantaneous:
            conditions_met = _instantaneous_conditions_met(
                zone_penetration, traversal_compactness, central_tendency_deviation, instantaneous_config
            )
            stability = _update_stability(symbol, conditions_met)

            # Entry only if conditions stable for MIN_STABILITY_CYCLES
            if conditions_met and _check_stability(symbol):
                _entry_method[symbol] = "INSTANTANEOUS"
                # Reset stability counter after entry
                _stability_counter[symbol] = 0
                return StrategyProposal(
                    strategy_id="EP2-GEOMETRY-V2",
                    action_type="ENTRY",
                    confidence="STABLE_CONDITIONS",
                    justification_ref=f"A6|A4|A8|STABLE{MIN_STABILITY_CYCLES}",
                    timestamp=context.timestamp
                )

    # No action warranted
    return None
