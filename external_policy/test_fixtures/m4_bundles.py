"""
M4PrimitiveBundle factory functions for test fixtures.

Creates synthetic M4PrimitiveBundle instances at different tiers:
- Empty: All primitives None
- Minimal: Only required primitives for specific policies
- Full: All primitives populated

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Task A2.
"""

from typing import Dict, Any, Optional
from observation.types import M4PrimitiveBundle

from .primitive_factories import (
    create_zone_penetration,
    create_displacement_origin,
    create_price_velocity,
    create_traversal_compactness,
    create_central_tendency_deviation,
    create_structural_absence,
    create_structural_persistence,
    create_resting_size,
    create_order_consumption,
    create_refill_event,
    create_order_block,
    create_supply_demand_zone,
    create_cascade_proximity,
    create_cascade_state,
)


def create_empty_bundle(symbol: str = "BTCUSDT") -> M4PrimitiveBundle:
    """
    Create M4PrimitiveBundle with all primitives set to None.

    Use for testing None-handling behavior.
    """
    return M4PrimitiveBundle.empty(symbol)


def create_minimal_bundle(
    symbol: str = "BTCUSDT",
    policy: str = "geometry"
) -> M4PrimitiveBundle:
    """
    Create M4PrimitiveBundle with minimal primitives for a specific policy.

    Args:
        symbol: Symbol for the bundle
        policy: Policy name to create minimal primitives for:
            - "geometry": zone_penetration, traversal_compactness, central_tendency_deviation
            - "kinematics": order_block, velocity, compactness, acceptance
            - "absence": structural_absence, structural_persistence
            - "orderbook": resting_size, order_consumption, refill_event
            - "slbrs": zone_penetration, resting_size, order_consumption, structural_persistence
            - "effcs": price_velocity, displacement
            - "cascade": cascade_proximity, cascade_state

    Returns:
        M4PrimitiveBundle with specified primitives populated
    """
    base = M4PrimitiveBundle.empty(symbol)

    if policy == "geometry":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=create_zone_penetration(),
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=create_traversal_compactness(),
            central_tendency_deviation=create_central_tendency_deviation(),
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=create_supply_demand_zone(symbol=symbol),
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "kinematics":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=create_price_velocity(),
            traversal_compactness=create_traversal_compactness(),
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=create_order_block(symbol=symbol),
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "absence":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=create_structural_absence(),
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=create_structural_persistence(),
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "orderbook":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=create_resting_size(),
            order_consumption=create_order_consumption(),
            absorption_event=None,
            refill_event=create_refill_event(),
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "slbrs":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=create_zone_penetration(),
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=create_structural_persistence(),
            resting_size=create_resting_size(),
            order_consumption=create_order_consumption(),
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "effcs":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=create_displacement_origin(),
            price_traversal_velocity=create_price_velocity(),
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=None,
            cascade_state=None,
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    elif policy == "cascade":
        return M4PrimitiveBundle(
            symbol=symbol,
            zone_penetration=None,
            displacement_origin_anchor=None,
            price_traversal_velocity=None,
            traversal_compactness=None,
            central_tendency_deviation=None,
            structural_absence_duration=None,
            traversal_void_span=None,
            event_non_occurrence_counter=None,
            structural_persistence_duration=None,
            resting_size=None,
            order_consumption=None,
            absorption_event=None,
            refill_event=None,
            price_acceptance_ratio=None,
            liquidation_density=None,
            directional_continuity=None,
            trade_burst=None,
            order_block=None,
            supply_demand_zone=None,
            liquidation_cascade_proximity=create_cascade_proximity(symbol=symbol.replace("USDT", "")),
            cascade_state=create_cascade_state(symbol=symbol.replace("USDT", "")),
            leverage_concentration_ratio=None,
            open_interest_directional_bias=None,
        )

    else:
        raise ValueError(f"Unknown policy: {policy}")


def create_full_bundle(symbol: str = "BTCUSDT") -> M4PrimitiveBundle:
    """
    Create M4PrimitiveBundle with all primitives populated.

    Use for comprehensive testing.
    """
    return M4PrimitiveBundle(
        symbol=symbol,
        zone_penetration=create_zone_penetration(),
        displacement_origin_anchor=create_displacement_origin(),
        price_traversal_velocity=create_price_velocity(),
        traversal_compactness=create_traversal_compactness(),
        central_tendency_deviation=create_central_tendency_deviation(),
        structural_absence_duration=create_structural_absence(),
        traversal_void_span=None,  # Not implemented
        event_non_occurrence_counter=None,  # Not implemented
        structural_persistence_duration=create_structural_persistence(),
        resting_size=create_resting_size(),
        order_consumption=create_order_consumption(),
        absorption_event=None,  # Complex type
        refill_event=create_refill_event(),
        price_acceptance_ratio=None,  # Complex type
        liquidation_density=None,  # Complex type
        directional_continuity=None,  # Complex type
        trade_burst=None,  # Complex type
        order_block=create_order_block(symbol=symbol),
        supply_demand_zone=create_supply_demand_zone(symbol=symbol),
        liquidation_cascade_proximity=create_cascade_proximity(symbol=symbol.replace("USDT", "")),
        cascade_state=create_cascade_state(symbol=symbol.replace("USDT", "")),
        leverage_concentration_ratio=None,  # Complex type
        open_interest_directional_bias=None,  # Complex type
    )


def create_bundle_with_primitives(
    symbol: str = "BTCUSDT",
    **kwargs
) -> M4PrimitiveBundle:
    """
    Create M4PrimitiveBundle with specific primitives.

    Pass primitive instances as keyword arguments matching bundle field names.
    Unspecified primitives are set to None.

    Example:
        bundle = create_bundle_with_primitives(
            symbol="BTCUSDT",
            zone_penetration=create_zone_penetration(penetration_depth=10.0),
            order_block=create_order_block(interaction_count=50)
        )
    """
    # Start with empty bundle
    base_fields = {
        "symbol": symbol,
        "zone_penetration": None,
        "displacement_origin_anchor": None,
        "price_traversal_velocity": None,
        "traversal_compactness": None,
        "central_tendency_deviation": None,
        "structural_absence_duration": None,
        "traversal_void_span": None,
        "event_non_occurrence_counter": None,
        "structural_persistence_duration": None,
        "resting_size": None,
        "order_consumption": None,
        "absorption_event": None,
        "refill_event": None,
        "price_acceptance_ratio": None,
        "liquidation_density": None,
        "directional_continuity": None,
        "trade_burst": None,
        "order_block": None,
        "supply_demand_zone": None,
        "liquidation_cascade_proximity": None,
        "cascade_state": None,
        "leverage_concentration_ratio": None,
        "open_interest_directional_bias": None,
    }

    # Override with provided primitives
    for key, value in kwargs.items():
        if key in base_fields:
            base_fields[key] = value
        else:
            raise ValueError(f"Unknown primitive field: {key}")

    return M4PrimitiveBundle(**base_fields)
