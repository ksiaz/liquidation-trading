"""
Enriched Liquidity Memory Store

Manages collection of enriched memory nodes with evidence accumulation.
"""

from typing import List, Dict, Optional
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode


class EnrichedLiquidityMemoryStore:
    """
    Central store for enriched liquidity memory nodes.
    Maintains active and archived nodes with full evidence tracking.
    """
    
    def __init__(self):
        """Initialize empty store."""
        self._active_nodes: Dict[str, EnrichedLiquidityMemoryNode] = {}
        self._archived_nodes: Dict[str, EnrichedLiquidityMemoryNode] = {}
        
        self._total_nodes_created = 0
        self._total_interactions = 0
        self._last_decay_ts: Optional[float] = None
    
    def add_or_update_node(
        self,
        node_id: str,
        price_center: float,
        price_band: float,
        side: str,
        timestamp: float,
        creation_reason: str,
        initial_strength: float = 0.5,
        initial_confidence: float = 0.5,
        decay_rate: float = 0.0001
    ) -> EnrichedLiquidityMemoryNode:
        """Add new or update existing node."""
        
        if node_id in self._active_nodes:
            node = self._active_nodes[node_id]
            node.strength = min(1.0, node.strength + 0.1)
            self._total_interactions += 1
            return node
        
        elif node_id in self._archived_nodes:
            node = self._archived_nodes.pop(node_id)
            node.strength = min(1.0, node.strength + 0.2)
            node.active = True
            node.last_interaction_ts = timestamp
            self._active_nodes[node_id] = node
            self._total_interactions += 1
            return node
        
        else:
            node = EnrichedLiquidityMemoryNode(
                id=node_id,
                price_center=price_center,
                price_band=price_band,
                side=side,
                first_seen_ts=timestamp,
                last_interaction_ts=timestamp,
                strength=initial_strength,
                confidence=initial_confidence,
                creation_reason=creation_reason,
                decay_rate=decay_rate,
                active=True
            )
            self._active_nodes[node_id] = node
            self._total_nodes_created += 1
            self._total_interactions += 1
            return node
    
    def update_with_orderbook(self, node_id: str, timestamp: float):
        """Update node with orderbook appearance evidence."""
        if node_id in self._active_nodes:
            self._active_nodes[node_id].record_orderbook_appearance(timestamp)
            self._total_interactions += 1
    
    def update_with_trade(
        self,
        node_id: str,
        timestamp: float,
        volume: float,
        is_buyer_maker: bool
    ):
        """Update node with trade execution evidence."""
        if node_id in self._active_nodes:
            self._active_nodes[node_id].record_trade_execution(timestamp, volume, is_buyer_maker)
            self._total_interactions += 1
    
    def update_with_liquidation(self, node_id: str, timestamp: float, side: str):
        """Update node with liquidation evidence."""
        if node_id in self._active_nodes:
            self._active_nodes[node_id].record_liquidation(timestamp, side)
            self._total_interactions += 1
    
    def decay_nodes(self, current_ts: float, current_price: float = None) -> int:
        """Apply decay to all active nodes."""
        self._last_decay_ts = current_ts
        archived_count = 0
        
        nodes_to_archive = []
        
        for node_id, node in self._active_nodes.items():
            if current_price is not None:
                node.apply_enhanced_decay(current_ts, current_price)
            else:
                node.apply_decay(current_ts)
            
            node.checkpoint_strength()
            
            if not node.active or node.strength < 0.01:
                nodes_to_archive.append(node_id)
        
        for node_id in nodes_to_archive:
            node = self._active_nodes.pop(node_id)
            self._archived_nodes[node_id] = node
            archived_count += 1
        
        return archived_count
    
    def get_active_nodes(
        self,
        current_price: Optional[float] = None,
        radius: Optional[float] = None,
        min_strength: float = 0.0,
        side_filter: Optional[str] = None
    ) -> List[EnrichedLiquidityMemoryNode]:
        """Query active memory nodes."""
        results = []
        
        for node in self._active_nodes.values():
            if node.strength < min_strength:
                continue
            
            if side_filter and node.side != side_filter and node.side != "both":
                continue
            
            if current_price is not None and radius is not None:
                distance = abs(node.price_center - current_price)
                if distance > radius:
                    continue
            
            results.append(node)
        
        results.sort(key=lambda n: n.strength, reverse=True)
        return results
    
    def get_metrics(self) -> dict:
        """Get store metrics."""
        active_strengths = [n.strength for n in self._active_nodes.values()]
        active_confidences = [n.confidence for n in self._active_nodes.values()]
        
        total_volume = sum(n.volume_total for n in self._active_nodes.values())
        total_liquidations = sum(n.liquidations_within_band for n in self._active_nodes.values())
        
        return {
            'total_nodes_created': self._total_nodes_created,
            'active_nodes': len(self._active_nodes),
            'archived_nodes': len(self._archived_nodes),
            'total_interactions': self._total_interactions,
            'avg_strength': sum(active_strengths) / len(active_strengths) if active_strengths else 0.0,
            'max_strength': max(active_strengths) if active_strengths else 0.0,
            'min_strength': min(active_strengths) if active_strengths else 0.0,
            'avg_confidence': sum(active_confidences) / len(active_confidences) if active_confidences else 0.0,
            'total_volume_tracked': total_volume,
            'total_liquidations_tracked': total_liquidations,
            'last_decay_ts': self._last_decay_ts,
        }
    
    def clear(self):
        """Clear all nodes."""
        self._active_nodes.clear()
        self._archived_nodes.clear()
        self._total_nodes_created = 0
        self._total_interactions = 0
        self._last_decay_ts = None
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"EnrichedLiquidityMemoryStore("
            f"active={len(self._active_nodes)}, "
            f"archived={len(self._archived_nodes)}, "
            f"created={self._total_nodes_created})"
        )
