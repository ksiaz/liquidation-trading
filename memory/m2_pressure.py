"""
M2 Memory Pressure Metrics

Quantifies historical attention concentration.
NOT trade pressure - purely factual density measurements.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class PressureMap:
    """
    Factual density metrics for a price range.
    
    Pressure = concentration of historical activity.
    NOT directional bias or trade pressure.
    """
    price_start: float
    price_end: float
    price_width: float
    
    # Event density
    events_per_unit: float
    interactions_per_unit: float
    
    # Volume density
    volume_per_unit: float
    
    # Liquidation density
    liquidations_per_unit: float
    
    # Node density
    nodes_per_unit: float
    active_nodes_per_unit: float
    dormant_nodes_per_unit: float


class MemoryPressureAnalyzer:
    """
    Computes factual pressure metrics.
    All outputs are COUNTS or RATIOS - no interpretation.
    """
    
    @staticmethod
    def compute_global_pressure(nodes: list) -> Dict[str, float]:
        """
        Global memory pressure across all nodes.
        
        Returns factual aggregates.
        """
        if not nodes:
            return {
                'total_interactions': 0,
                'total_volume': 0.0,
                'total_liquidations': 0,
                'total_nodes': 0,
            }
        
        return {
            'total_interactions': sum(n.interaction_count for n in nodes),
            'total_volume': sum(n.volume_total for n in nodes),
            'total_liquidations': sum(n.liquidations_within_band for n in nodes),
            'total_nodes': len(nodes),
        }
    
    @staticmethod
    def compute_local_pressure(
        price_range: Tuple[float, float],
        nodes: list,
        active_nodes: list,
        dormant_nodes: list
    ) -> PressureMap:
        """
        Local pressure within price range.
        
        Returns density metrics - NOT trade signals.
        """
        price_start, price_end = price_range
        price_width = price_end - price_start
        
        # Filter nodes in range
        range_nodes = [n for n in nodes if price_start <= n.price_center <= price_end]
        range_active = [n for n in active_nodes if price_start <= n.price_center <= price_end]
        range_dormant = [n for n in dormant_nodes if price_start <= n.price_center <= price_end]
        
        if not range_nodes or price_width == 0:
            return PressureMap(
                price_start=price_start,
                price_end=price_end,
                price_width=price_width,
                events_per_unit=0.0,
                interactions_per_unit=0.0,
                volume_per_unit=0.0,
                liquidations_per_unit=0.0,
                nodes_per_unit=0.0,
                active_nodes_per_unit=0.0,
                dormant_nodes_per_unit=0.0
            )
        
        # Compute densities
        total_interactions = sum(n.interaction_count for n in range_nodes)
        total_volume = sum(n.volume_total for n in range_nodes)
        total_liquidations = sum(n.liquidations_within_band for n in range_nodes)
        
        # Count events (approximation: interactions include all event types)
        total_events = total_interactions
        
        return PressureMap(
            price_start=price_start,
            price_end=price_end,
            price_width=price_width,
            events_per_unit=total_events / price_width,
            interactions_per_unit=total_interactions / price_width,
            volume_per_unit=total_volume / price_width,
            liquidations_per_unit=total_liquidations / price_width,
            nodes_per_unit=len(range_nodes) / price_width,
            active_nodes_per_unit=len(range_active) / price_width,
            dormant_nodes_per_unit=len(range_dormant) / price_width
        )
    
    @staticmethod
    def compute_pressure_distribution(
        nodes: list,
        price_min: float,
        price_max: float,
        num_buckets: int = 10
    ) -> List[PressureMap]:
        """
        Divide price range into buckets and compute pressure for each.
        
        Returns list of pressure maps.
        """
        bucket_width = (price_max - price_min) / num_buckets
        pressure_maps = []
        
        for i in range(num_buckets):
            bucket_start = price_min + (i * bucket_width)
            bucket_end = bucket_start + bucket_width
            
            # Separate by state
            bucket_nodes = [n for n in nodes if bucket_start <= n.price_center < bucket_end]
            active = [n for n in bucket_nodes if n.active]
            dormant = [n for n in bucket_nodes if not n.active]
            
            pressure_map = MemoryPressureAnalyzer.compute_local_pressure(
                (bucket_start, bucket_end),
                bucket_nodes,
                active,
                dormant
            )
            pressure_maps.append(pressure_map)
        
        return pressure_maps
