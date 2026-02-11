"""
Primitive factory functions for test fixtures.

Creates synthetic M4 primitives with configurable values.
Supports None, minimal, and full tier configurations.

Per DOWNSTREAM_ACTIVATION_SPEC.md Phase A, Task A2.
"""

from dataclasses import dataclass
from typing import Optional


# ==============================================================================
# Tier A: Zone Geometry
# ==============================================================================

def create_zone_penetration(
    zone_id: str = "ZONE_TEST",
    penetration_depth: float = 5.0,
    symbol: str = "BTCUSDT"
):
    """Create ZonePenetrationDepth primitive."""
    from memory.m4_zone_geometry import ZonePenetrationDepth
    return ZonePenetrationDepth(
        zone_id=zone_id,
        penetration_depth=penetration_depth
    )


def create_displacement_origin(
    traversal_id: str = "TRAV_TEST",
    anchor_low: float = 64000.0,
    anchor_high: float = 64100.0,
    anchor_dwell_time: float = 30.0
):
    """Create DisplacementOriginAnchor primitive."""
    from memory.m4_zone_geometry import DisplacementOriginAnchor
    return DisplacementOriginAnchor(
        traversal_id=traversal_id,
        anchor_low=anchor_low,
        anchor_high=anchor_high,
        anchor_dwell_time=anchor_dwell_time
    )


# ==============================================================================
# Tier A: Traversal Kinematics
# ==============================================================================

def create_price_velocity(
    traversal_id: str = "TRAV_TEST",
    price_delta: float = 100.0,
    time_delta: float = 60.0,
    velocity: float = 1.67,
    symbol: str = "BTCUSDT"
):
    """Create PriceTraversalVelocity primitive."""
    from memory.m4_traversal_kinematics import PriceTraversalVelocity
    return PriceTraversalVelocity(
        traversal_id=traversal_id,
        price_delta=price_delta,
        time_delta=time_delta,
        velocity=velocity
    )


def create_traversal_compactness(
    traversal_id: str = "TRAV_TEST",
    net_displacement: float = 100.0,
    total_path_length: float = 150.0,
    compactness_ratio: float = 0.667,
    symbol: str = "BTCUSDT"
):
    """Create TraversalCompactness primitive."""
    from memory.m4_traversal_kinematics import TraversalCompactness
    return TraversalCompactness(
        traversal_id=traversal_id,
        net_displacement=net_displacement,
        total_path_length=total_path_length,
        compactness_ratio=compactness_ratio
    )


# ==============================================================================
# Tier A: Central Tendency
# ==============================================================================

def create_central_tendency_deviation(
    deviation_value: float = 0.003
):
    """Create CentralTendencyDeviation primitive."""
    from memory.m4_price_distribution import CentralTendencyDeviation
    return CentralTendencyDeviation(
        deviation_value=deviation_value
    )


# ==============================================================================
# Tier B-1: Structural Absence
# ==============================================================================

def create_structural_absence(
    absence_duration: float = 120.0,
    observation_window: float = 300.0,
    absence_ratio: float = 0.4
):
    """Create StructuralAbsenceDuration primitive."""
    from memory.m4_structural_absence import StructuralAbsenceDuration
    return StructuralAbsenceDuration(
        absence_duration=absence_duration,
        observation_window=observation_window,
        absence_ratio=absence_ratio
    )


# ==============================================================================
# Tier B-2: Structural Persistence
# ==============================================================================

def create_structural_persistence(
    total_persistence_duration: float = 600.0,
    observation_window: float = 1000.0,
    persistence_ratio: float = 0.6
):
    """Create StructuralPersistenceDuration primitive."""
    from memory.m4_structural_persistence import StructuralPersistenceDuration
    return StructuralPersistenceDuration(
        total_persistence_duration=total_persistence_duration,
        observation_window=observation_window,
        persistence_ratio=persistence_ratio
    )


# ==============================================================================
# Tier B-2.1: Order Book Primitives
# ==============================================================================

@dataclass(frozen=True)
class RestingSizeAtPrice:
    """Stub for resting size primitive (test fixture)."""
    bid_size: float
    ask_size: float
    mid_price: float
    timestamp: float


@dataclass(frozen=True)
class OrderConsumption:
    """Stub for order consumption primitive (test fixture)."""
    consumed_size: float
    side: str  # "bid" or "ask"
    price_level: float
    timestamp: float
    initial_size: float = 0.0  # Size before consumption (previous snapshot)


@dataclass(frozen=True)
class RefillEvent:
    """Stub for refill event primitive (test fixture)."""
    refill_size: float
    side: str  # "bid" or "ask"
    price_level: float
    timestamp: float


def create_resting_size(
    bid_size: float = 100.0,
    ask_size: float = 80.0,
    mid_price: float = 64000.0,
    timestamp: float = 1000.0
):
    """Create RestingSizeAtPrice primitive."""
    return RestingSizeAtPrice(
        bid_size=bid_size,
        ask_size=ask_size,
        mid_price=mid_price,
        timestamp=timestamp
    )


def create_order_consumption(
    consumed_size: float = 50.0,
    side: str = "bid",
    price_level: float = 63900.0,
    timestamp: float = 1000.0,
    initial_size: float = 100.0
):
    """Create OrderConsumption primitive."""
    return OrderConsumption(
        consumed_size=consumed_size,
        side=side,
        price_level=price_level,
        timestamp=timestamp,
        initial_size=initial_size
    )


def create_refill_event(
    refill_size: float = 30.0,
    side: str = "bid",
    price_level: float = 63900.0,
    timestamp: float = 1000.0
):
    """Create RefillEvent primitive."""
    return RefillEvent(
        refill_size=refill_size,
        side=side,
        price_level=price_level,
        timestamp=timestamp
    )


# ==============================================================================
# Tier B-5: Node Pattern Primitives
# ==============================================================================

def create_order_block(
    node_id: str = "OB_TEST",
    symbol: str = "BTCUSDT",
    price_center: float = 64000.0,
    price_band: float = 50.0,
    side: str = "bid",
    interaction_count: int = 20,
    interactions_per_hour: float = 120.0,
    burstiness_coefficient: float = 0.5,
    last_interaction_ts: float = 950.0,
    time_since_interaction_sec: float = 50.0,
    longest_idle_period_sec: float = 30.0,
    total_volume: float = 50000.0,
    buyer_initiated_volume: float = 30000.0,
    seller_initiated_volume: float = 20000.0,
    node_strength: float = 0.7,
    liquidations_within_band: int = 2,
    timestamp: float = 1000.0
):
    """Create OrderBlockPrimitive."""
    from memory.m4_node_patterns import OrderBlockPrimitive
    return OrderBlockPrimitive(
        node_id=node_id,
        symbol=symbol,
        price_center=price_center,
        price_band=price_band,
        side=side,
        interaction_count=interaction_count,
        interactions_per_hour=interactions_per_hour,
        burstiness_coefficient=burstiness_coefficient,
        last_interaction_ts=last_interaction_ts,
        time_since_interaction_sec=time_since_interaction_sec,
        longest_idle_period_sec=longest_idle_period_sec,
        total_volume=total_volume,
        buyer_initiated_volume=buyer_initiated_volume,
        seller_initiated_volume=seller_initiated_volume,
        node_strength=node_strength,
        liquidations_within_band=liquidations_within_band,
        timestamp=timestamp
    )


def create_supply_demand_zone(
    zone_id: str = "SDZ_TEST",
    symbol: str = "BTCUSDT",
    zone_type: str = "demand",
    zone_low: float = 63800.0,
    zone_high: float = 64000.0,
    zone_center: float = 63900.0,
    zone_width: float = 200.0,
    node_count: int = 5,
    total_interactions: int = 100,
    total_volume: float = 200000.0,
    avg_node_strength: float = 0.6,
    displacement_detected: bool = True,
    displacement_direction: str = "up",
    displacement_magnitude: float = 500.0,
    retest_detected: bool = True,
    retest_count: int = 2,
    timestamp: float = 1000.0
):
    """Create SupplyDemandZonePrimitive."""
    from memory.m4_node_patterns import SupplyDemandZonePrimitive
    return SupplyDemandZonePrimitive(
        zone_id=zone_id,
        symbol=symbol,
        zone_type=zone_type,
        zone_low=zone_low,
        zone_high=zone_high,
        zone_center=zone_center,
        zone_width=zone_width,
        node_count=node_count,
        total_interactions=total_interactions,
        total_volume=total_volume,
        avg_node_strength=avg_node_strength,
        displacement_detected=displacement_detected,
        displacement_direction=displacement_direction,
        displacement_magnitude=displacement_magnitude,
        retest_detected=retest_detected,
        retest_count=retest_count,
        timestamp=timestamp
    )


# ==============================================================================
# Tier B-6: Cascade Observation Primitives
# ==============================================================================

def create_cascade_proximity(
    symbol: str = "BTC",
    price_level: float = 64000.0,
    threshold_pct: float = 0.005,
    long_positions_count: int = 10,
    long_positions_value: float = 500000.0,
    long_closest_price: Optional[float] = 63700.0,
    long_avg_distance_pct: float = 0.003,
    short_positions_count: int = 5,
    short_positions_value: float = 200000.0,
    short_closest_price: Optional[float] = 64300.0,
    short_avg_distance_pct: float = 0.004,
    positions_at_risk_count: int = 15,
    aggregate_position_value: float = 700000.0,
    timestamp: float = 1000.0
):
    """Create LiquidationCascadeProximity primitive."""
    from memory.m4_cascade_proximity import LiquidationCascadeProximity
    return LiquidationCascadeProximity(
        symbol=symbol,
        price_level=price_level,
        threshold_pct=threshold_pct,
        positions_at_risk_count=positions_at_risk_count,
        aggregate_position_value=aggregate_position_value,
        long_positions_count=long_positions_count,
        long_positions_value=long_positions_value,
        long_closest_price=long_closest_price,
        long_avg_distance_pct=long_avg_distance_pct,
        short_positions_count=short_positions_count,
        short_positions_value=short_positions_value,
        short_closest_price=short_closest_price,
        short_avg_distance_pct=short_avg_distance_pct,
        timestamp=timestamp
    )


def create_cascade_state(
    symbol: str = "BTC",
    phase: str = "LIQUIDATING",
    has_confirmed_liquidation: bool = True,
    liquidations_5s: int = 2,
    liquidations_30s: int = 5,
    liquidations_60s: int = 8,
    confirmed_liquidation_value: float = 80000.0,
    positions_remaining_at_risk: int = 5,
    cascade_value_liquidated: float = 100000.0,
    cascade_duration_sec: float = 15.0,
    cascade_start_ts: Optional[float] = 985.0,
    observation_confidence: str = "CONFIRMED",
    timestamp: float = 1000.0
):
    """Create CascadeStateObservation primitive."""
    from memory.m4_cascade_state import CascadeStateObservation, CascadePhase
    phase_enum = CascadePhase[phase] if isinstance(phase, str) else phase
    return CascadeStateObservation(
        symbol=symbol,
        phase=phase_enum,
        has_confirmed_liquidation=has_confirmed_liquidation,
        liquidations_5s=liquidations_5s,
        liquidations_30s=liquidations_30s,
        liquidations_60s=liquidations_60s,
        confirmed_liquidation_value=confirmed_liquidation_value,
        positions_remaining_at_risk=positions_remaining_at_risk,
        cascade_value_liquidated=cascade_value_liquidated,
        cascade_duration_sec=cascade_duration_sec,
        cascade_start_ts=cascade_start_ts,
        observation_confidence=observation_confidence,
        timestamp=timestamp
    )


# ==============================================================================
# Strategy Context and Permission Factories
# ==============================================================================

def create_strategy_context(
    context_id: str = "TEST_CTX",
    timestamp: float = 1000.0,
    current_price: Optional[float] = None
):
    """Create StrategyContext for testing."""
    # Import from geometry as canonical source
    from external_policy.ep2_strategy_geometry import StrategyContext
    if current_price is not None:
        return StrategyContext(
            context_id=context_id,
            timestamp=timestamp,
            current_price=current_price
        )
    return StrategyContext(
        context_id=context_id,
        timestamp=timestamp
    )


def create_permission_allowed(
    mandate_id: str = "M_TEST",
    action_id: str = "A_TEST",
    reason_code: str = "APPROVED",
    timestamp: float = 1000.0
):
    """Create PermissionOutput with ALLOWED result."""
    from external_policy.ep2_strategy_geometry import PermissionOutput
    return PermissionOutput(
        result="ALLOWED",
        mandate_id=mandate_id,
        action_id=action_id,
        reason_code=reason_code,
        timestamp=timestamp
    )


def create_permission_denied(
    mandate_id: str = "M_TEST",
    action_id: str = "A_TEST",
    reason_code: str = "REJECTED",
    timestamp: float = 1000.0
):
    """Create PermissionOutput with DENIED result."""
    from external_policy.ep2_strategy_geometry import PermissionOutput
    return PermissionOutput(
        result="DENIED",
        mandate_id=mandate_id,
        action_id=action_id,
        reason_code=reason_code,
        timestamp=timestamp
    )


# ==============================================================================
# Regime State Factories (for SLBRS/EFFCS)
# ==============================================================================

def create_regime_state_sideways(
    vwap_distance: float = 0.001,
    atr_5m: float = 50.0,
    atr_30m: float = 100.0
):
    """Create RegimeState for SIDEWAYS_ACTIVE regime."""
    from external_policy.ep2_slbrs_strategy import RegimeState
    return RegimeState(
        regime="SIDEWAYS_ACTIVE",
        vwap_distance=vwap_distance,
        atr_5m=atr_5m,
        atr_30m=atr_30m
    )


def create_regime_state_expansion(
    vwap_distance: float = 0.01,
    atr_5m: float = 150.0,
    atr_30m: float = 100.0
):
    """Create RegimeState for EXPANSION_ACTIVE regime."""
    from external_policy.ep2_effcs_strategy import RegimeState
    return RegimeState(
        regime="EXPANSION_ACTIVE",
        vwap_distance=vwap_distance,
        atr_5m=atr_5m,
        atr_30m=atr_30m
    )
