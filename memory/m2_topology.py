"""
M2 Memory Topology

Structural relationships between memory nodes.
NO interpretation - pure geometric/statistical facts.
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
from collections import defaultdict
import statistics


@dataclass
class TopologyCluster:
    """
    Group of nodes with structural similarity.
    NOT support/resistance - purely factual grouping.
    """
    cluster_id: str
    price_center: float
    price_range: float
    node_count: int
    total_interactions: int
    total_volume: float
    avg_strength: float


class MemoryTopology:
    """
    Topological analysis of memory structure.
    All methods return FACTS about geometric relationships.
    """
    
    @staticmethod
    def compute_neighborhood_density(
        center_price: float,
        radius: float,
        nodes: list
    ) -> Dict[str, float]:
        """
        Count nodes within radius and compute density metrics.
        
        Returns factual counts and weighted measures.
        """
        neighbors = []
        for node in nodes:
            distance = abs(node.price_center - center_price)
            if distance <= radius:
                neighbors.append(node)
        
        if not neighbors:
            return {
                'neighbor_count': 0,
                'density': 0.0,
                'strength_weighted_density': 0.0,
                'avg_neighbor_strength': 0.0
            }
        
        total_strength = sum(n.strength for n in neighbors)
        
        return {
            'neighbor_count': len(neighbors),
            'density': len(neighbors) / (2 * radius),  # Nodes per price unit
            'strength_weighted_density': total_strength / (2 * radius),
            'avg_neighbor_strength': total_strength / len(neighbors)
        }
    
    @staticmethod
    def identify_clusters(
        nodes: list,
        price_threshold: float = 0.01,
        min_cluster_size: int = 2
    ) -> List[TopologyCluster]:
        """
        Group nodes by price proximity.
        
        NOT support/resistance levels - purely spatial clustering.
        """
        if not nodes:
            return []
        
        # Sort by price
        sorted_nodes = sorted(nodes, key=lambda n: n.price_center)
        
        clusters = []
        current_cluster = [sorted_nodes[0]]
        
        for node in sorted_nodes[1:]:
            # Check if node belongs to current cluster
            if node.price_center - current_cluster[-1].price_center <= price_threshold:
                current_cluster.append(node)
            else:
                # Finalize current cluster if meets size requirement
                if len(current_cluster) >= min_cluster_size:
                    clusters.append(_create_cluster(current_cluster, len(clusters)))
                current_cluster = [node]
        
        # Final cluster
        if len(current_cluster) >= min_cluster_size:
            clusters.append(_create_cluster(current_cluster, len(clusters)))
        
        return clusters
    
    @staticmethod
    def identify_gaps(
        nodes: list,
        price_range: Tuple[float, float],
        gap_threshold: float = 0.02
    ) -> List[Dict[str, float]]:
        """
        Identify price regions with no memory nodes.
        
        Returns factual gap measurements - no interpretation.
        """
        if not nodes:
            return [{
                'gap_start': price_range[0],
                'gap_end': price_range[1],
                'gap_width': price_range[1] - price_range[0]
            }]
        
        sorted_nodes = sorted(nodes, key=lambda n: n.price_center)
        gaps = []
        
        # Check gap before first node
        if sorted_nodes[0].price_center - price_range[0] > gap_threshold:
            gaps.append({
                'gap_start': price_range[0],
                'gap_end': sorted_nodes[0].price_center,
                'gap_width': sorted_nodes[0].price_center - price_range[0]
            })
        
        # Check gaps between nodes
        for i in range(len(sorted_nodes) - 1):
            gap_width = sorted_nodes[i+1].price_center - sorted_nodes[i].price_center
            if gap_width > gap_threshold:
                gaps.append({
                    'gap_start': sorted_nodes[i].price_center,
                    'gap_end': sorted_nodes[i+1].price_center,
                    'gap_width': gap_width
                })
        
        # Check gap after last node
        if price_range[1] - sorted_nodes[-1].price_center > gap_threshold:
            gaps.append({
                'gap_start': sorted_nodes[-1].price_center,
                'gap_end': price_range[1],
                'gap_width': price_range[1] - sorted_nodes[-1].price_center
            })
        
        return gaps


def _create_cluster(nodes: list, cluster_id: int) -> TopologyCluster:
    """Create cluster from node group."""
    prices = [n.price_center for n in nodes]
    
    return TopologyCluster(
        cluster_id=f"cluster_{cluster_id}",
        price_center=statistics.mean(prices),
        price_range=max(prices) - min(prices),
        node_count=len(nodes),
        total_interactions=sum(n.interaction_count for n in nodes),
        total_volume=sum(n.volume_total for n in nodes),
        avg_strength=statistics.mean(n.strength for n in nodes)
    )
