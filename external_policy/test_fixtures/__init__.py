"""
Test fixtures for external policy validation.

Provides synthetic M4PrimitiveBundle and individual primitive factories
for testing policy determinism, None-handling, and input immutability.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Task A2.
"""

from .m4_bundles import (
    create_empty_bundle,
    create_minimal_bundle,
    create_full_bundle,
    create_bundle_with_primitives,
)

from .primitive_factories import (
    # Tier A primitives
    create_zone_penetration,
    create_displacement_origin,
    create_price_velocity,
    create_traversal_compactness,
    create_central_tendency_deviation,
    # Tier B-1 primitives
    create_structural_absence,
    # Tier B-2 primitives
    create_structural_persistence,
    # Tier B-2.1 primitives
    create_resting_size,
    create_order_consumption,
    create_refill_event,
    # Tier B-5 primitives
    create_order_block,
    create_supply_demand_zone,
    # Tier B-6 primitives
    create_cascade_proximity,
    create_cascade_state,
    # Context factories
    create_strategy_context,
    create_permission_allowed,
    create_permission_denied,
    create_regime_state_sideways,
    create_regime_state_expansion,
)

__all__ = [
    # Bundle factories
    "create_empty_bundle",
    "create_minimal_bundle",
    "create_full_bundle",
    "create_bundle_with_primitives",
    # Primitive factories
    "create_zone_penetration",
    "create_displacement_origin",
    "create_price_velocity",
    "create_traversal_compactness",
    "create_central_tendency_deviation",
    "create_structural_absence",
    "create_structural_persistence",
    "create_resting_size",
    "create_order_consumption",
    "create_refill_event",
    "create_order_block",
    "create_supply_demand_zone",
    "create_cascade_proximity",
    "create_cascade_state",
    # Context factories
    "create_strategy_context",
    "create_permission_allowed",
    "create_permission_denied",
    "create_regime_state_sideways",
    "create_regime_state_expansion",
]
