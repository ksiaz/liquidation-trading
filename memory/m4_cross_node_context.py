"""
M4 Cross-Node Context Views

Read-only, deterministic view of aggregated context across multiple memory nodes.
Describes spatial relationships, density, and state distribution in price space,
without importance ranking, zone scoring, or strategic clustering.

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
import statistics
from typing import List
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


@dataclass
class CrossNodeContextView:
    """
    Read-only view of cross-node context in a price range.
    
    All fields are factual counts, statistics, or neutral descriptors.
    NO zone importance scores, NO strategic clusters, NO level quality judgments.
    """
    # Price range (factual bounds)
    price_range_start: float
    price_range_end: float
    
    # Node counts (factual)
    node_count: int
    node_density_per_dollar: float
    
    # Spacing statistics (factual)
    avg_node_spacing: float
    min_node_spacing: float
    max_node_spacing: float
    
    # Cluster metrics (factual counts, NOT importance rankings)
    clustered_node_count: int  # Nodes in multi-node clusters
    isolated_node_count: int    # Nodes not in clusters
    cluster_count: int          # Number of distinct clusters
    avg_cluster_size: float     # Mean nodes per cluster
    
    # State distribution (factual counts)
    total_active_nodes: int
    total_dormant_nodes: int
    
    # Motif spread (factual counts)
    shared_motif_count: int           # Number of motifs appearing at multiple nodes
    nodes_with_shared_motifs: int     # Count of nodes sharing motifs


def get_cross_node_context(
    price_range_start: float,
    price_range_end: float,
    all_nodes: List[EnrichedLiquidityMemoryNode],
    current_ts: float
) -> CrossNodeContextView:
    """
    Get cross-node context view for a price range.
    
    Pure function: same inputs → same output.
    Read-only: does not modify nodes.
    Factual: no zone importance scoring, no strategic analysis.
    
    Args:
        price_range_start: Lower price bound (inclusive)
        price_range_end: Upper price bound (inclusive)
        all_nodes: All memory nodes to consider
        current_ts: Reference timestamp
    
    Returns:
        CrossNodeContextView with factual aggregation metrics
    """
    # Filter nodes in price range
    nodes_in_range = [
        node for node in all_nodes
        if price_range_start <= node.price_center <= price_range_end
    ]
    
    node_count = len(nodes_in_range)
    
    if node_count == 0:
        # Empty range
        return CrossNodeContextView(
            price_range_start=price_range_start,
            price_range_end=price_range_end,
            node_count=0,
            node_density_per_dollar=0.0,
            avg_node_spacing=0.0,
            min_node_spacing=0.0,
            max_node_spacing=0.0,
            clustered_node_count=0,
            isolated_node_count=0,
            cluster_count=0,
            avg_cluster_size=0.0,
            total_active_nodes=0,
            total_dormant_nodes=0,
            shared_motif_count=0,
            nodes_with_shared_motifs=0
        )
    
    # Calculate density
    price_range_width = price_range_end - price_range_start
    if price_range_width > 0:
        density = node_count / price_range_width
    else:
        density = 0.0
    
    # Calculate spacing statistics
    if node_count >= 2:
        # Sort by price
        sorted_nodes = sorted(nodes_in_range, key=lambda n: n.price_center)
        prices = [n.price_center for n in sorted_nodes]
        
        # Calculate gaps
        gaps = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        avg_spacing = statistics.mean(gaps)
        min_spacing = min(gaps)
        max_spacing = max(gaps)
    else:
        avg_spacing = 0.0
        min_spacing = 0.0
        max_spacing = 0.0
    
    # Cluster analysis (simple: nodes within threshold distance)
    # Threshold: 2x average spacing (factual metric, not quality judgment)
    cluster_threshold = 2.0 * avg_spacing if avg_spacing > 0 else 0.01
    
    if node_count >= 2:
        sorted_nodes = sorted(nodes_in_range, key=lambda n: n.price_center)
        
        # Build clusters
        clusters = []
        current_cluster = [sorted_nodes[0]]
        
        for i in range(1, len(sorted_nodes)):
            gap = sorted_nodes[i].price_center - sorted_nodes[i-1].price_center
            
            if gap <= cluster_threshold:
                # Part of current cluster
                current_cluster.append(sorted_nodes[i])
            else:
                # Start new cluster
                clusters.append(current_cluster)
                current_cluster = [sorted_nodes[i]]
        
        # Add final cluster
        clusters.append(current_cluster)
        
        # Count clustered vs isolated
        multi_node_clusters = [c for c in clusters if len(c) > 1]
        clustered_node_count = sum(len(c) for c in multi_node_clusters)
        isolated_node_count = node_count - clustered_node_count
        cluster_count = len(multi_node_clusters)
        
        if cluster_count > 0:
            avg_cluster_size = clustered_node_count / cluster_count
        else:
            avg_cluster_size = 0.0
    else:
        # Single node
        clustered_node_count = 0
        isolated_node_count = 1
        cluster_count = 0
        avg_cluster_size = 0.0
    
    # State distribution
    active_count = sum(1 for n in nodes_in_range if n.active)
    dormant_count = node_count - active_count
    
    # Motif analysis (simplified: would need M3 data)
    # For now, return placeholder values
    # Full implementation would analyze motif_counts across nodes
    shared_motif_count = 0
    nodes_with_shared_motifs = 0
    
    return CrossNodeContextView(
        price_range_start=price_range_start,
        price_range_end=price_range_end,
        node_count=node_count,
        node_density_per_dollar=density,
        avg_node_spacing=avg_spacing,
        min_node_spacing=min_spacing,
        max_node_spacing=max_spacing,
        clustered_node_count=clustered_node_count,
        isolated_node_count=isolated_node_count,
        cluster_count=cluster_count,
        avg_cluster_size=avg_cluster_size,
        total_active_nodes=active_count,
        total_dormant_nodes=dormant_count,
        shared_motif_count=shared_motif_count,
        nodes_with_shared_motifs=nodes_with_shared_motifs
    )
