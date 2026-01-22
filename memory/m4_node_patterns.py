"""
M4 Node Pattern Primitives

Pattern detection from M2 memory nodes.
Implements order block and supply/demand zone detection based on:
- Interaction density
- Visit history
- Absence intervals
- Node clustering

Per research decomposition:
- Orderblocks = interaction density + absence + visit history
- Supply/Demand = consolidation → displacement → retest geometry

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
from typing import List, Optional
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m4_interaction_density import get_interaction_density


@dataclass(frozen=True)
class OrderBlockPrimitive:
    """
    Detected order block at a price level.

    An order block is a price level showing:
    - High interaction density (clustered activity)
    - Recent activity (not stale)
    - Strong memory persistence

    Records structural fact. Cannot imply: future reaction, quality, edge.
    """
    node_id: str
    symbol: str
    price_center: float
    price_band: float
    side: str  # "bid", "ask", or "both"

    # Interaction metrics
    interaction_count: int
    interactions_per_hour: float
    burstiness_coefficient: float  # [-1, 1]: -1=regular, 0=Poisson, 1=bursty

    # Temporal metrics
    last_interaction_ts: float
    time_since_interaction_sec: float
    longest_idle_period_sec: float

    # Volume metrics
    total_volume: float
    buyer_initiated_volume: float
    seller_initiated_volume: float

    # Memory strength
    node_strength: float  # [0, 1]

    # Liquidation proximity
    liquidations_within_band: int

    timestamp: float  # Detection timestamp


@dataclass(frozen=True)
class SupplyDemandZonePrimitive:
    """
    Detected supply or demand zone from node cluster.

    A supply/demand zone shows:
    - Multiple nodes clustered in price range (consolidation)
    - Price displacement from cluster
    - Retest behavior (if applicable)

    Records structural fact. Cannot imply: future reaction, zone quality.
    """
    zone_id: str
    symbol: str
    zone_type: str  # "supply" (resistance cluster) or "demand" (support cluster)

    # Zone geometry
    zone_low: float
    zone_high: float
    zone_center: float
    zone_width: float

    # Cluster properties
    node_count: int
    total_interactions: int
    total_volume: float
    avg_node_strength: float

    # Displacement geometry (if detected)
    displacement_detected: bool
    displacement_direction: Optional[str]  # "up" or "down"
    displacement_magnitude: Optional[float]

    # Retest geometry (if detected)
    retest_detected: bool
    retest_count: Optional[int]

    timestamp: float  # Detection timestamp


def detect_order_block(
    node: EnrichedLiquidityMemoryNode,
    current_time: float,
    min_interactions: int = 10,
    min_burstiness: float = 0.3,
    max_idle_sec: float = 300.0,
    min_strength: float = 0.4
) -> Optional[OrderBlockPrimitive]:
    """
    Detect order block pattern from a single node.

    Criteria (all must be met):
    - Sufficient interactions (activity threshold)
    - Bursty interaction pattern (clustered, not regular)
    - Recent activity (not stale)
    - Strong memory persistence

    Args:
        node: Memory node to analyze
        current_time: Current timestamp
        min_interactions: Minimum interaction count
        min_burstiness: Minimum burstiness coefficient
        max_idle_sec: Maximum idle time to qualify
        min_strength: Minimum node strength

    Returns:
        OrderBlockPrimitive if pattern detected, None otherwise
    """
    # Check basic criteria
    if node.interaction_count < min_interactions:
        return None

    time_since_interaction = current_time - node.last_interaction_ts
    if time_since_interaction > max_idle_sec:
        return None

    if node.strength < min_strength:
        return None

    # Compute interaction density
    density = get_interaction_density(node, current_time)

    # Check burstiness (clustered activity pattern)
    if density.burstiness_coefficient < min_burstiness:
        return None

    # Pattern detected - construct primitive
    return OrderBlockPrimitive(
        node_id=node.id,
        symbol=node.symbol,
        price_center=node.price_center,
        price_band=node.price_band,
        side=node.side,
        interaction_count=node.interaction_count,
        interactions_per_hour=density.interactions_per_hour,
        burstiness_coefficient=density.burstiness_coefficient,
        last_interaction_ts=node.last_interaction_ts,
        time_since_interaction_sec=time_since_interaction,
        longest_idle_period_sec=density.longest_idle_period_sec,
        total_volume=node.volume_total,
        buyer_initiated_volume=node.buyer_initiated_volume,
        seller_initiated_volume=node.seller_initiated_volume,
        node_strength=node.strength,
        liquidations_within_band=node.liquidations_within_band,
        timestamp=current_time
    )


def detect_supply_demand_zone(
    nodes: List[EnrichedLiquidityMemoryNode],
    current_price: float,
    current_time: float,
    min_cluster_nodes: int = 3,
    max_cluster_width_pct: float = 0.5,
    min_displacement_pct: float = 0.3,
    min_avg_strength: float = 0.3
) -> Optional[SupplyDemandZonePrimitive]:
    """
    Detect supply or demand zone from node cluster.

    Process:
    1. Find nodes clustered in price range
    2. Classify as supply (above price) or demand (below price)
    3. Detect displacement from cluster
    4. Detect retest behavior (if applicable)

    Args:
        nodes: List of memory nodes to analyze
        current_price: Current market price
        current_time: Current timestamp
        min_cluster_nodes: Minimum nodes to form cluster
        max_cluster_width_pct: Maximum cluster width (% of center price)
        min_displacement_pct: Minimum displacement to qualify
        min_avg_strength: Minimum average node strength

    Returns:
        SupplyDemandZonePrimitive if pattern detected, None otherwise
    """
    if len(nodes) < min_cluster_nodes:
        return None

    # Sort nodes by price
    sorted_nodes = sorted(nodes, key=lambda n: n.price_center)

    # Compute cluster bounds
    zone_low = sorted_nodes[0].price_center
    zone_high = sorted_nodes[-1].price_center
    zone_center = (zone_low + zone_high) / 2.0
    zone_width = zone_high - zone_low

    # Check cluster width constraint
    max_width = zone_center * (max_cluster_width_pct / 100.0)
    if zone_width > max_width:
        return None

    # Compute cluster properties
    total_interactions = sum(n.interaction_count for n in nodes)
    total_volume = sum(n.volume_total for n in nodes)
    avg_strength = sum(n.strength for n in nodes) / len(nodes)

    # Check average strength
    if avg_strength < min_avg_strength:
        return None

    # Classify as supply or demand based on position relative to current price
    if zone_center > current_price:
        zone_type = "supply"  # Resistance cluster above price
    else:
        zone_type = "demand"  # Support cluster below price

    # Detect displacement
    displacement_detected = False
    displacement_direction = None
    displacement_magnitude = None

    distance_from_zone = abs(current_price - zone_center)
    displacement_pct = (distance_from_zone / zone_center) * 100.0

    if displacement_pct >= min_displacement_pct:
        displacement_detected = True
        if current_price > zone_high:
            displacement_direction = "up"
        elif current_price < zone_low:
            displacement_direction = "down"
        displacement_magnitude = distance_from_zone

    # Detect retest (price returning to cluster after displacement)
    retest_detected = False
    retest_count = None

    # Count nodes with recent interactions (potential retests)
    if displacement_detected:
        recent_interaction_threshold = 60.0  # Within last 60 seconds
        recent_nodes = [n for n in nodes
                       if current_time - n.last_interaction_ts <= recent_interaction_threshold]
        if recent_nodes:
            retest_detected = True
            retest_count = len(recent_nodes)

    # Generate zone ID
    zone_id = f"{nodes[0].symbol}_{zone_type}_{int(zone_center)}"

    return SupplyDemandZonePrimitive(
        zone_id=zone_id,
        symbol=nodes[0].symbol,
        zone_type=zone_type,
        zone_low=zone_low,
        zone_high=zone_high,
        zone_center=zone_center,
        zone_width=zone_width,
        node_count=len(nodes),
        total_interactions=total_interactions,
        total_volume=total_volume,
        avg_node_strength=avg_strength,
        displacement_detected=displacement_detected,
        displacement_direction=displacement_direction,
        displacement_magnitude=displacement_magnitude,
        retest_detected=retest_detected,
        retest_count=retest_count,
        timestamp=current_time
    )


def find_node_clusters(
    nodes: List[EnrichedLiquidityMemoryNode],
    max_gap_pct: float = 0.2
) -> List[List[EnrichedLiquidityMemoryNode]]:
    """
    Find clusters of nearby nodes.

    Nodes are clustered if price gap between consecutive nodes
    is less than max_gap_pct of the lower node's price.

    Args:
        nodes: List of memory nodes
        max_gap_pct: Maximum gap percentage to cluster

    Returns:
        List of node clusters
    """
    if not nodes:
        return []

    # Sort by price
    sorted_nodes = sorted(nodes, key=lambda n: n.price_center)

    clusters = []
    current_cluster = [sorted_nodes[0]]

    for i in range(1, len(sorted_nodes)):
        prev_node = sorted_nodes[i-1]
        curr_node = sorted_nodes[i]

        # Calculate gap percentage
        gap = curr_node.price_center - prev_node.price_center
        gap_pct = (gap / prev_node.price_center) * 100.0

        if gap_pct <= max_gap_pct:
            # Within cluster
            current_cluster.append(curr_node)
        else:
            # Start new cluster
            if len(current_cluster) >= 1:
                clusters.append(current_cluster)
            current_cluster = [curr_node]

    # Add final cluster
    if len(current_cluster) >= 1:
        clusters.append(current_cluster)

    return clusters
