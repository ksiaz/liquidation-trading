"""
Liquidity Memory Store — Phase M1.2

Manages collection of LiquidityMemoryNodes.

PUBLIC API ONLY:
- add_or_update_node(...)
- decay_nodes(current_ts)
- get_active_nodes(current_price, radius)
- get_metrics()

CONSTRAINTS:
- Deterministic (reproducible on replay)
- No strategy logic
- No signal generation
"""

from typing import List, Dict, Optional
from memory.liquidity_memory_node import LiquidityMemoryNode, CreationReason


class LiquidityMemoryStore:
    """
    Central store for all liquidity memory nodes.
    
    Maintains both active and archived nodes.
    Provides query interface and metrics.
    """
    
    def __init__(self):
        """Initialize empty memory store."""
        # Active nodes (strength > 0.01, active=True)
        self._active_nodes: Dict[str, LiquidityMemoryNode] = {}
        
        # Archived nodes (strength <= 0.01 or active=False)
        self._archived_nodes: Dict[str, LiquidityMemoryNode] = {}
        
        # Metrics
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
        creation_reason: CreationReason,
        initial_strength: float = 0.5,
        initial_confidence: float = 0.5,
        decay_rate: float = 0.0001,  # Default: 0.01% decay per second
        volume: float = 0.0
    ) -> LiquidityMemoryNode:
        """
        Add new node or update existing node.
        
        If node exists:
            - Update interaction timestamp
            - Increase strength (capped at 1.0)
            - Add volume
        
        If node is new:
            - Create with specified parameters
        
        Args:
            node_id: Unique identifier
            price_center: Center of price band
            price_band: Width of band (absolute)
            side: "bid", "ask", or "both"
            timestamp: Current timestamp
            creation_reason: Why this node is being created
            initial_strength: Starting strength [0,1]
            initial_confidence: Starting confidence [0,1]
            decay_rate: Decay per second
            volume: Associated volume
        
        Returns:
            The node (new or updated)
        """
        # Check if node exists (active or archived)
        if node_id in self._active_nodes:
            node = self._active_nodes[node_id]
            node.update_interaction(timestamp, volume)
            # Boost strength on interaction (capped at 1.0)
            node.strength = min(1.0, node.strength + 0.1)
            self._total_interactions += 1
            return node
        
        elif node_id in self._archived_nodes:
            # Resurrect archived node
            node = self._archived_nodes.pop(node_id)
            node.update_interaction(timestamp, volume)
            node.strength = min(1.0, node.strength + 0.2)  # Larger boost for resurrection
            node.active = True
            self._active_nodes[node_id] = node
            self._total_interactions += 1
            return node
        
        else:
            # Create new node
            node = LiquidityMemoryNode(
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
                active=True,
                interaction_count=1,
                volume_observed=volume
            )
            self._active_nodes[node_id] = node
            self._total_nodes_created += 1
            self._total_interactions += 1
            return node
    
    def decay_nodes(self, current_ts: float) -> int:
        """
        Apply time-based decay to all active nodes.
        Archive nodes that fall below strength threshold.
        
        Args:
            current_ts: Current timestamp for decay calculation
        
        Returns:
            Number of nodes archived during this decay
        """
        self._last_decay_ts = current_ts
        archived_count = 0
        
        # Apply decay to all active nodes
        nodes_to_archive = []
        
        for node_id, node in self._active_nodes.items():
            node.apply_decay(current_ts)
            
            # Check if node should be archived
            if not node.active or node.strength < 0.01:
                nodes_to_archive.append(node_id)
        
        # Archive inactive nodes
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
    ) -> List[LiquidityMemoryNode]:
        """
        Query active memory nodes.
        
        Args:
            current_price: Optional price to search around
            radius: Optional radius around current_price
            min_strength: Minimum strength threshold
            side_filter: Optional "bid", "ask", or "both"
        
        Returns:
            List of matching active nodes
        """
        results = []
        
        for node in self._active_nodes.values():
            # Strength filter
            if node.strength < min_strength:
                continue
            
            # Side filter
            if side_filter and node.side != side_filter and node.side != "both":
                continue
            
            # Price radius filter
            if current_price is not None and radius is not None:
                distance = abs(node.price_center - current_price)
                if distance > radius:
                    continue
            
            results.append(node)
        
        # Sort by strength (strongest first)
        results.sort(key=lambda n: n.strength, reverse=True)
        
        return results
    
    def get_metrics(self) -> dict:
        """
        Get store metrics for monitoring.
        
        Returns:
            Dictionary of metrics
        """
        active_strengths = [n.strength for n in self._active_nodes.values()]
        active_confidences = [n.confidence for n in self._active_nodes.values()]
        
        return {
            # Counts
            'total_nodes_created': self._total_nodes_created,
            'active_nodes': len(self._active_nodes),
            'archived_nodes': len(self._archived_nodes),
            'total_interactions': self._total_interactions,
            
            # Strength stats
            'avg_strength': sum(active_strengths) / len(active_strengths) if active_strengths else 0.0,
            'max_strength': max(active_strengths) if active_strengths else 0.0,
            'min_strength': min(active_strengths) if active_strengths else 0.0,
            
            # Confidence stats
            'avg_confidence': sum(active_confidences) / len(active_confidences) if active_confidences else 0.0,
            
            # Metadata
            'last_decay_ts': self._last_decay_ts,
        }
    
    def get_node_by_id(self, node_id: str) -> Optional[LiquidityMemoryNode]:
        """Get specific node by ID (active or archived)."""
        if node_id in self._active_nodes:
            return self._active_nodes[node_id]
        elif node_id in self._archived_nodes:
            return self._archived_nodes[node_id]
        return None
    
    def clear(self):
        """Clear all nodes (for testing/reset)."""
        self._active_nodes.clear()
        self._archived_nodes.clear()
        self._total_nodes_created = 0
        self._total_interactions = 0
        self._last_decay_ts = None
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"LiquidityMemoryStore("
            f"active={len(self._active_nodes)}, "
            f"archived={len(self._archived_nodes)}, "
            f"total_created={self._total_nodes_created})"
        )
