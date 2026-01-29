"""
M2 Continuity Memory Store

Extends memory store with three-state model and historical continuity.
"""

from typing import List, Dict, Optional, Tuple
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m2_memory_state import MemoryState, MemoryStateThresholds
from memory.m2_historical_evidence import (
    HistoricalEvidence,
    extract_historical_evidence,
    compute_revival_strength
)
from memory.m2_topology import MemoryTopology, TopologyCluster
from memory.m2_pressure import MemoryPressureAnalyzer, PressureMap

# M4 View imports (for type hints and integration)
from memory.m4_evidence_composition import EvidenceCompositionView, get_evidence_composition
from memory.m4_interaction_density import InteractionDensityView, get_interaction_density
from memory.m4_stability_transience import StabilityTransienceView, get_stability_metrics
from memory.m4_temporal_structure import TemporalStructureView, get_temporal_structure
from memory.m4_cross_node_context import CrossNodeContextView, get_cross_node_context


class ContinuityMemoryStore:
    """
    M2 Memory store with three-state model and historical continuity.
    
    States: ACTIVE → DORMANT → ARCHIVED
    Historical evidence preserved across state transitions.
    """
    
    
    def __init__(self, event_logger=None, max_archived_nodes: int = 1000):
        """Initialize store with three collections.

        Args:
            event_logger: Optional database logger for event-level capture
            max_archived_nodes: Maximum archived nodes to retain (memory guard)
        """
        self._active_nodes: Dict[str, EnrichedLiquidityMemoryNode] = {}
        self._dormant_nodes: Dict[str, EnrichedLiquidityMemoryNode] = {}
        self._dormant_evidence: Dict[str, HistoricalEvidence] = {}
        self._archived_nodes: Dict[str, EnrichedLiquidityMemoryNode] = {}

        self._total_nodes_created = 0
        self._total_interactions = 0
        self._last_state_update_ts: Optional[float] = None
        self._archived_nodes_pruned = 0
        self._max_archived_nodes = max_archived_nodes

        # Event logger for research
        self._event_logger = event_logger

        # Topology and pressure analyzers
        self.topology = MemoryTopology()
        self.pressure_analyzer = MemoryPressureAnalyzer()
    
    def add_or_update_node(
        self,
        node_id: str,
        symbol: str,
        price_center: float,
        price_band: float,
        side: str,
        timestamp: float,
        creation_reason: str,
        initial_strength: float = 0.5,
        initial_confidence: float = 0.5,
        volume: float = 0.0
    ) -> EnrichedLiquidityMemoryNode:
        """
        Add new or update existing node (handles revival from dormant).

        Args:
            symbol: Symbol partitioning key (e.g., "BTCUSDT")
        """
        # Check active nodes
        if node_id in self._active_nodes:
            node = self._active_nodes[node_id]
            node.strength = min(1.0, node.strength + 0.1)
            self._total_interactions += 1
            return node

        # Check dormant nodes (REVIVAL)
        if node_id in self._dormant_nodes:
            return self._revive_dormant_node(node_id, timestamp, volume)

        # Check archived (no auto-revival)
        if node_id in self._archived_nodes:
            # Archived nodes do NOT auto-revive
            # Must create new node with new ID
            pass

        # Create new node
        node = EnrichedLiquidityMemoryNode(
            id=node_id,
            symbol=symbol,
            price_center=price_center,
            price_band=price_band,
            side=side,
            first_seen_ts=timestamp,
            last_interaction_ts=timestamp,
            strength=initial_strength,
            confidence=initial_confidence,
            creation_reason=creation_reason,
            decay_rate=MemoryStateThresholds.ACTIVE_DECAY_RATE,
            active=True
        )

        self._active_nodes[node_id] = node
        self._total_nodes_created += 1
        self._total_interactions += 1
        return node
    
    def update_memory_states(self, current_ts: float):
        """
        Update all node states based on thresholds.
        
        ACTIVE → DORMANT: Low strength or timeout
        DORMANT → ARCHIVED: Very low strength or extended timeout
        """
        self._last_state_update_ts = current_ts
        
        # Check ACTIVE → DORMANT
        to_dormant = []
        for node_id, node in self._active_nodes.items():
            time_idle = current_ts - node.last_interaction_ts
            
            if (node.strength < MemoryStateThresholds.DORMANT_STRENGTH_THRESHOLD or
                time_idle > MemoryStateThresholds.DORMANT_TIMEOUT_SEC):
                to_dormant.append(node_id)
        
        for node_id in to_dormant:
            self._transition_to_dormant(node_id)
        
        # Check DORMANT → ARCHIVED
        to_archived = []
        for node_id, node in self._dormant_nodes.items():
            time_idle = current_ts - node.last_interaction_ts
            
            if (node.strength < MemoryStateThresholds.ARCHIVE_STRENGTH_THRESHOLD or
                time_idle > MemoryStateThresholds.ARCHIVE_TIMEOUT_SEC):
                to_archived.append(node_id)
        
        for node_id in to_archived:
            self._transition_to_archived(node_id)

        # Prune old archived nodes to prevent unbounded growth
        pruned = self.prune_archived_nodes()

        return {
            'transitioned_to_dormant': len(to_dormant),
            'transitioned_to_archived': len(to_archived),
            'archived_pruned': pruned
        }
    
    def decay_nodes(self, current_ts: float):
        """Apply state-aware decay."""
        # Decay active nodes (normal rate)
        for node in self._active_nodes.values():
            node.apply_decay(current_ts)
        
        # Decay dormant nodes (reduced rate)
        for node in self._dormant_nodes.values():
            node.apply_decay(current_ts)
    
    def update_with_trade(self, node_id: str, timestamp: float, volume: float, is_buyer_maker: bool):
        """Update active node with trade evidence."""
        if node_id in self._active_nodes:
            self._active_nodes[node_id].record_trade_execution(timestamp, volume, is_buyer_maker)
    
    def update_with_liquidation(self, node_id: str, timestamp: float, side: str):
        """Update active node with liquidation evidence."""
        if node_id in self._active_nodes:
            self._active_nodes[node_id].record_liquidation(timestamp, side)
    
    def ingest_liquidation(
        self,
        symbol: str,
        price: float,
        side: str,
        volume: float,
        timestamp: float
    ) -> Optional[EnrichedLiquidityMemoryNode]:
        """
        Ingest liquidation event and create/update memory node.
        
        Constitutional Rule (Phase 5 Canon):
        - Nodes are created ONLY on liquidation events.
        - Spatial matching: Check overlap with existing nodes.
        - If overlap exists: Reinforce existing node.
        - If no overlap: Create new node.
        
        Args:
            symbol: Symbol partitioning key (e.g., "BTCUSDT")
            price: Liquidation price
            side: "BUY" or "SELL"
            volume: Liquidation volume
            timestamp: Event timestamp
            
        Returns:
            Created or updated node, or None if rejected
        """
        print(f"DEBUG M2 ingest_liquidation: {symbol} @ ${price} {side} vol={volume}")
        
        # Define spatial matching parameters
        PRICE_BAND_DEFAULT = 100.0  # Default band width
        OVERLAP_TOLERANCE = 0.5  # 50% overlap threshold
        
        # Search for overlapping nodes (symbol-partitioned)
        active_candidates = self.get_active_nodes(symbol=symbol)
        
        for candidate in active_candidates:
            # Check spatial overlap
            if candidate.overlaps(price):
                # Reinforce existing node
                was_inactive = not candidate.active
                candidate.record_liquidation(timestamp, side)
                candidate.strength = min(1.0, candidate.strength + 0.15)

                # Reactivate node if it was dormant
                if was_inactive and candidate.strength >= 0.01:
                    candidate.active = True
                    candidate._start_presence_interval(timestamp)

                self._total_interactions += 1
                
                # Log node reinforcement event
                if self._event_logger:
                    try:
                        self._event_logger.log_m2_node_event(
                            timestamp=timestamp,
                            event_type='REINFORCED',
                            node_id=candidate.id,
                            symbol=symbol,
                            price=price,
                            side=side,
                            volume=volume,
                            strength_after=candidate.strength
                        )
                    except:
                        pass
                
                return candidate
        
        # No overlap found - Create new node
        node_id = f"{symbol}_{int(price)}_{int(timestamp)}"
        
        # Determine side from liquidation
        # Liquidation BUY = Long got liquidated (price fell) -> bid zone
        # Liquidation SELL = Short got liquidated (price rose) -> ask zone
        node_side = "bid" if side == "BUY" else "ask"
        
        node = self.add_or_update_node(
            node_id=node_id,
            symbol=symbol,
            price_center=price,
            price_band=PRICE_BAND_DEFAULT,
            side=node_side,
            timestamp=timestamp,
            creation_reason=f"liquidation_{side}",
            initial_strength=0.6,
            initial_confidence=0.7,
            volume=volume
        )
        
        # Record the liquidation evidence
        node.record_liquidation(timestamp, side)
        
        print(f"DEBUG M2: Node CREATED - {symbol} @ ${price:.2f} ({node_side} zone, vol={volume:.2f})")
        
        # Log node creation event
        if self._event_logger:
            try:
                self._event_logger.log_m2_node_event(
                    timestamp=timestamp,
                    event_type='CREATED',
                    node_id=node.id,
                    symbol=symbol,
                    price=price,
                    side=node_side,
                    volume=volume,
                    strength_after=node.strength
                )
            except:
                pass
        
        return node
    
    def ingest_trade(
        self,
        symbol: str,
        price: float,
        side: str,
        volume: float,
        is_buyer_maker: bool,
        timestamp: float
    ) -> Optional[EnrichedLiquidityMemoryNode]:
        """
        Ingest trade event and update existing memory nodes.
        
        Constitutional Rule (Phase 5 Canon):
        - Trades ONLY update existing nodes.
        - Trades DO NOT create new nodes.
        - Spatial matching required.
        
        Args:
            symbol: Symbol partitioning key
            price: Trade execution price
            side: "BUY" or "SELL"
            volume: Trade volume
            is_buyer_maker: True if buyer was maker (seller aggressor)
            timestamp: Event timestamp
            
        Returns:
            Updated node if match found, None otherwise
        """
        # Search for overlapping active nodes (symbol-partitioned)
        active_candidates = self.get_active_nodes(symbol=symbol)
        
        for candidate in active_candidates:
            if candidate.overlaps(price):
                # Update node with trade evidence
                candidate.record_trade_execution(timestamp, volume, is_buyer_maker)
                self._total_interactions += 1
                return candidate
        
        # No match found - Trade is ignored (constitutionally correct)
        return None
    
    def update_mark_price_state(
        self,
        symbol: str,
        mark_price: float,
        index_price: Optional[float],
        timestamp: float
    ):
        """
        Update mark/index price for all nodes of this symbol.

        Constitutional: Factual price update, no interpretation.

        Args:
            symbol: Symbol partitioning key
            mark_price: Mark price
            index_price: Index price (optional)
            timestamp: Update timestamp
        """
        # Update all active nodes for this symbol
        symbol_nodes = self.get_active_nodes(symbol=symbol)

        for node in symbol_nodes:
            node.last_mark_price = mark_price
            node.last_index_price = index_price
            node.last_mark_price_ts = timestamp
            node.mark_price_update_count += 1

    def advance_time(self, current_ts: float):
        """
        Advance system time and apply decay/lifecycle mechanics.

        Should be called periodically (e.g., every 1s or every N events).
        Drives:
        - Decay accumulation
        - State transitions (Active -> Dormant -> Archived)

        Args:
            current_ts: Current system timestamp
        """
        # Apply decay to all nodes
        self.decay_nodes(current_ts)

        # Check and update memory states
        self.update_memory_states(current_ts)

    
    def get_node(self, node_id: str) -> Optional[EnrichedLiquidityMemoryNode]:
        """Get node by ID from any state (Active, Dormant, Archived)."""
        if node_id in self._active_nodes:
            return self._active_nodes[node_id]
        if node_id in self._dormant_nodes:
            return self._dormant_nodes[node_id]
        if node_id in self._archived_nodes:
            return self._archived_nodes[node_id]
        return None

    def get_active_nodes(
        self,
        current_price: Optional[float] = None,
        radius: Optional[float] = None,
        min_strength: float = 0.0,
        symbol: Optional[str] = None
    ) -> List[EnrichedLiquidityMemoryNode]:
        """Query active nodes only. Filter by symbol if provided."""
        results = []
        
        for node in self._active_nodes.values():
            if symbol is not None and node.symbol != symbol:
                continue
                
            if node.strength < min_strength:
                continue
            
            if current_price is not None and radius is not None:
                if abs(node.price_center - current_price) > radius:
                    continue
            
            results.append(node)
        
        results.sort(key=lambda n: n.strength, reverse=True)
        return results
    
    def get_dormant_nodes(
        self,
        current_price: Optional[float] = None,
        radius: Optional[float] = None,
        symbol: Optional[str] = None
    ) -> List[EnrichedLiquidityMemoryNode]:
        """Query dormant nodes (historical context). Filter by symbol if provided."""
        results = []
        
        for node in self._dormant_nodes.values():
            if symbol is not None and node.symbol != symbol:
                continue

            if current_price is not None and radius is not None:
                if abs(node.price_center - current_price) > radius:
                    continue
            
            results.append(node)
        
        return results
    
    def get_node_density(self, price_range: Tuple[float, float], symbol: Optional[str] = None) -> Dict[str, float]:
        """Get node density metrics for price range. Filter by symbol if provided."""
        all_nodes = [n for n in self._active_nodes.values() if symbol is None or n.symbol == symbol] + \
                    [n for n in self._dormant_nodes.values() if symbol is None or n.symbol == symbol]
        
        center_price = (price_range[0] + price_range[1]) / 2
        radius = (price_range[1] - price_range[0]) / 2
        
        return self.topology.compute_neighborhood_density(center_price, radius, all_nodes)
    
    def get_pressure_map(self, price_range: Tuple[float, float], symbol: Optional[str] = None) -> PressureMap:
        """Get memory pressure map for price range. Filter by symbol if provided."""
        all_nodes = [n for n in self._active_nodes.values() if symbol is None or n.symbol == symbol] + \
                    [n for n in self._dormant_nodes.values() if symbol is None or n.symbol == symbol]
        active_nodes = [n for n in self._active_nodes.values() if symbol is None or n.symbol == symbol]
        dormant_nodes = [n for n in self._dormant_nodes.values() if symbol is None or n.symbol == symbol]
        
        return self.pressure_analyzer.compute_local_pressure(
            price_range,
            all_nodes,
            active_nodes,
            dormant_nodes
        )
    
    def get_topological_clusters(
        self,
        price_threshold: float = 0.01,
        min_cluster_size: int = 2,
        symbol: Optional[str] = None
    ) -> List[TopologyCluster]:
        """Get topological clusters (factual grouping only). Filter by symbol if provided."""
        all_nodes = [n for n in self._active_nodes.values() if symbol is None or n.symbol == symbol] + \
                    [n for n in self._dormant_nodes.values() if symbol is None or n.symbol == symbol]
        
        return self.topology.identify_clusters(all_nodes, price_threshold, min_cluster_size)
    
    def update_orderbook_state(
        self,
        symbol: str,
        timestamp: float,
        bid_size: float,
        ask_size: float,
        best_bid_price: Optional[float],
        best_ask_price: Optional[float]
    ):
        """
        Update order book state for nodes near best bid/ask.

        Updates resting size fields for active nodes that overlap with
        observed best bid/ask price levels.

        Args:
            symbol: Trading symbol
            timestamp: Observation timestamp
            bid_size: Total observed bid size
            ask_size: Total observed ask size
            best_bid_price: Best bid price level (or None)
            best_ask_price: Best ask price level (or None)
        """
        # Update active nodes that overlap with best bid/ask (symbol-filtered)
        for node in self._active_nodes.values():
            if node.symbol != symbol:
                continue

            # Determine which prices overlap with this node
            overlaps_bid = best_bid_price is not None and node.overlaps(best_bid_price)
            overlaps_ask = best_ask_price is not None and node.overlaps(best_ask_price)

            if not overlaps_bid and not overlaps_ask:
                continue

            # Determine effective sizes based on overlap and node side
            effective_bid = 0.0
            effective_ask = 0.0

            if overlaps_bid and node.side in ('bid', 'both'):
                effective_bid = bid_size
            if overlaps_ask and node.side in ('ask', 'both'):
                effective_ask = ask_size

            # Update node with both values in single call
            if effective_bid > 0 or effective_ask > 0:
                node.update_orderbook_state(timestamp, effective_bid, effective_ask)

    def get_active_nodes_for_symbol(self, symbol: str) -> List[EnrichedLiquidityMemoryNode]:
        """Get all active nodes for a specific symbol.

        Args:
            symbol: Trading symbol to filter by

        Returns:
            List of active nodes for the symbol
        """
        return [node for node in self._active_nodes.values() if node.symbol == symbol]

    def get_nodes_near_price(
        self,
        symbol: str,
        price: float,
        max_distance: Optional[float] = None
    ) -> List[EnrichedLiquidityMemoryNode]:
        """Get active nodes near a price level (spatial matching).

        Args:
            symbol: Trading symbol
            price: Price level to search near
            max_distance: Maximum distance from price (default: use node price_band)

        Returns:
            List of nodes that overlap with or are near the price
        """
        nearby_nodes = []

        for node in self._active_nodes.values():
            if node.symbol != symbol:
                continue

            # Check if price overlaps with node band
            if node.overlaps(price):
                nearby_nodes.append(node)
            # Check if within max_distance (if specified)
            elif max_distance is not None:
                distance = abs(price - node.price_center)
                if distance <= max_distance:
                    nearby_nodes.append(node)

        return nearby_nodes

    def record_liquidation_at_node(
        self,
        node_id: str,
        timestamp: float,
        side: str
    ):
        """Record liquidation event at a node.

        Args:
            node_id: Node identifier
            timestamp: Liquidation timestamp
            side: Liquidation side ("BUY" or "SELL")
        """
        # Check active nodes first
        if node_id in self._active_nodes:
            node = self._active_nodes[node_id]
            node.record_liquidation(timestamp, side)
            # Boost strength on liquidation
            node.strength = min(1.0, node.strength + 0.15)
            self._total_interactions += 1
        # Check dormant nodes (could trigger revival)
        elif node_id in self._dormant_nodes:
            # Revival handled by add_or_update_node if needed
            pass

    def record_trade_at_node(
        self,
        node_id: str,
        timestamp: float,
        volume: float,
        is_buyer_maker: bool
    ):
        """Record trade execution at a node.

        Args:
            node_id: Node identifier
            timestamp: Trade timestamp
            volume: Trade volume (quote currency)
            is_buyer_maker: Whether buyer was maker (passive)
        """
        # Check active nodes first
        if node_id in self._active_nodes:
            node = self._active_nodes[node_id]
            node.record_trade_execution(timestamp, volume, is_buyer_maker)
            # Boost strength proportional to volume
            volume_boost = min(0.10, volume / 10000.0)  # Cap at 0.10
            node.strength = min(1.0, node.strength + volume_boost)
            self._total_interactions += 1
        # Check dormant nodes (could trigger revival)
        elif node_id in self._dormant_nodes:
            # Revival handled by add_or_update_node if needed
            pass

    def get_node(self, node_id: str) -> Optional[EnrichedLiquidityMemoryNode]:
        """Get node by ID from any state.

        Args:
            node_id: Node identifier

        Returns:
            Node if found, None otherwise
        """
        if node_id in self._active_nodes:
            return self._active_nodes[node_id]
        elif node_id in self._dormant_nodes:
            return self._dormant_nodes[node_id]
        elif node_id in self._archived_nodes:
            return self._archived_nodes[node_id]
        return None

    def _transition_to_dormant(self, node_id: str):
        """Transition node from ACTIVE to DORMANT."""
        node = self._active_nodes.pop(node_id)

        # Extract and preserve historical evidence
        evidence = extract_historical_evidence(node)
        self._dormant_evidence[node_id] = evidence

        # Reduce decay rate
        node.decay_rate = MemoryStateThresholds.DORMANT_DECAY_RATE

        self._dormant_nodes[node_id] = node
    
    def _transition_to_archived(self, node_id: str):
        """Transition node from DORMANT to ARCHIVED."""
        node = self._dormant_nodes.pop(node_id)
        
        # Keep evidence for potential future analysis
        # (does not enable auto-revival)
        
        self._archived_nodes[node_id] = node
    
    def _revive_dormant_node(
        self,
        node_id: str,
        timestamp: float,
        volume: float
    ) -> EnrichedLiquidityMemoryNode:
        """
        Revive dormant node with historical context.
        
        CRITICAL: Revival requires NEW evidence (not automatic).
        Historical evidence contributes to new strength.
        """
        node = self._dormant_nodes.pop(node_id)
        historical = self._dormant_evidence.get(node_id)
        
        # Compute revival strength from historical + new evidence
        new_evidence_strength = min(0.4, volume / 10000.0)
        
        if historical:
            node.strength = compute_revival_strength(historical, new_evidence_strength)
        else:
            node.strength = new_evidence_strength + MemoryStateThresholds.DORMANT_REVIVAL_STRENGTH_BOOST
        
        # Restore active decay rate
        node.decay_rate = MemoryStateThresholds.ACTIVE_DECAY_RATE
        node.last_interaction_ts = timestamp
        
        self._active_nodes[node_id] = node
        self._total_interactions += 1
        
        return node
    
    def get_metrics(self) -> dict:
        """Get store metrics including state distribution."""
        return {
            'total_nodes_created': self._total_nodes_created,
            'active_nodes': len(self._active_nodes),
            'dormant_nodes': len(self._dormant_nodes),
            'archived_nodes': len(self._archived_nodes),
            'archived_nodes_pruned': self._archived_nodes_pruned,
            'max_archived_nodes': self._max_archived_nodes,
            'total_interactions': self._total_interactions,
            'last_state_update_ts': self._last_state_update_ts,
        }

    def prune_archived_nodes(self, max_age_sec: float = 3600.0) -> int:
        """
        Prune old archived nodes to prevent unbounded memory growth.

        Args:
            max_age_sec: Maximum age for archived nodes (default 1 hour)

        Returns:
            Number of nodes pruned
        """
        if not self._archived_nodes:
            return 0

        current_ts = self._last_state_update_ts or 0.0
        cutoff = current_ts - max_age_sec

        # Find nodes to prune (oldest first if over limit, or too old)
        to_prune = []

        for node_id, node in self._archived_nodes.items():
            if node.last_interaction_ts < cutoff:
                to_prune.append(node_id)

        # If still over limit, prune oldest
        if len(self._archived_nodes) - len(to_prune) > self._max_archived_nodes:
            # Sort by last interaction (oldest first)
            remaining = [
                (nid, n.last_interaction_ts)
                for nid, n in self._archived_nodes.items()
                if nid not in to_prune
            ]
            remaining.sort(key=lambda x: x[1])

            # Prune oldest to get under limit
            excess = len(self._archived_nodes) - len(to_prune) - self._max_archived_nodes
            for nid, _ in remaining[:excess]:
                to_prune.append(nid)

        # Actually prune
        for node_id in to_prune:
            del self._archived_nodes[node_id]
            # Also clean up dormant evidence if any
            self._dormant_evidence.pop(node_id, None)
            self._archived_nodes_pruned += 1

        return len(to_prune)
    
    # ==================== M3: TEMPORAL EVIDENCE QUERY INTERFACE ====================
    
    def get_sequence_buffer(self, node_id: str) -> Optional[List[Tuple]]:
        """
        Get complete sequence buffer for a node.
        
        Returns chronologically-ordered list of (token, timestamp) tuples.
        Raw access to temporal event history without interpretation.
        
        Args:
            node_id: Node identifier
        
        Returns:
            List of (EvidenceToken, timestamp) tuples or None if node not found
        """
        node = self._active_nodes.get(node_id)
        if node is None:
            return None
        
        if node.sequence_buffer is None:
            return []
        
        return node.sequence_buffer.get_all()
    
    def get_recent_tokens(self, node_id: str, count: int = 10) -> List[Tuple]:
        """
        Get N most recent tokens from node's sequence buffer.
        
        Returns chronological order (oldest → newest).
        Count is factual limit, NOT importance threshold.
        
        Args:
            node_id: Node identifier
            count: Number of recent tokens to return
        
        Returns:
            List of recent (token, timestamp) tuples (may be < count if buffer smaller)
        """
        node = self._active_nodes.get(node_id)
        if node is None or node.sequence_buffer is None:
            return []
        
        return node.sequence_buffer.get_recent(count)
    
    def get_motifs_for_node(self, node_id: str, min_count: int = 1) -> List[Dict]:
        """
        Get all observed motifs for a node.
        
        Returns motifs filtered by minimum occurrence count.
        NOT sorted by importance - returns in arbitrary order.
        
        Args:
            node_id: Node identifier
            min_count: Minimum occurrence count (factual filter)
        
        Returns:
            List of motif dictionaries with keys: motif, count, last_seen_ts, strength
        """
        node = self._active_nodes.get(node_id)
        if node is None:
            return []
        
        motifs = []
        for motif_tuple, count in node.motif_counts.items():
            if count >= min_count:
                motifs.append({
                    'motif': motif_tuple,
                    'count': count,
                    'last_seen_ts': node.motif_last_seen.get(motif_tuple, 0.0),
                    'strength': node.motif_strength.get(motif_tuple, 0.0)
                })
        
        return motifs
    
    def get_motif_by_pattern(
        self,
        node_id: str,
        pattern: Tuple
    ) -> Optional[Dict]:
        """
        Get metrics for a specific motif pattern if observed.
        
        Factual lookup, NOT prediction.
        
        Args:
            node_id: Node identifier
            pattern: Motif tuple to look up
        
        Returns:
            Dict with motif metrics or None if not observed
        """
        node = self._active_nodes.get(node_id)
        if node is None:
            return None
        
        if pattern not in node.motif_counts:
            return None
        
        return {
            'motif': pattern,
            'count': node.motif_counts[pattern],
            'last_seen_ts': node.motif_last_seen.get(pattern, 0.0),
            'strength': node.motif_strength.get(pattern, 0.0)
        }
    
    def get_nodes_with_motif(
        self,
        motif: Tuple,
        min_count: int = 1
    ) -> List[str]:
        """
        Get node IDs that have observed the specified motif.
        
        Factual list, NOT ranked by importance.
        
        Args:
            motif: Motif tuple to search for
            min_count: Minimum occurrence count
        
        Returns:
            List of node IDs (unordered)
        """
        node_ids = []
        
        for node_id, node in self._active_nodes.items():
            count = node.motif_counts.get(motif, 0)
            if count >= min_count:
                node_ids.append(node_id)
        
        return node_ids
    
    def get_motif_statistics(self, motif: Tuple) -> Dict:
        """
        Get aggregate statistics for motif across all nodes.
        
        Returns factual counts, NOT predictions or importance scores.
        
        Args:
            motif: Motif tuple
        
        Returns:
            Dict with keys: total_count, node_count, avg_count_per_node, most_recent_ts
        """
        total_count = 0
        node_count = 0
        most_recent_ts = 0.0
        
        for node in self._active_nodes.values():
            count = node.motif_counts.get(motif, 0)
            if count > 0:
                total_count += count
                node_count += 1
                node_ts = node.motif_last_seen.get(motif, 0.0)
                most_recent_ts = max(most_recent_ts, node_ts)
        
        avg_count = total_count / node_count if node_count > 0 else 0.0
        
        return {
            'total_count': total_count,
            'node_count': node_count,
            'avg_count_per_node': avg_count,
            'most_recent_ts': most_recent_ts
        }
    
    def get_tokens_in_time_range(
        self,
        node_id: str,
        start_ts: float,
        end_ts: float
    ) -> List[Tuple]:
        """
        Get tokens within specified time range.
        
        Chronological order maintained.
        
        Args:
            node_id: Node identifier
            start_ts: Start timestamp (inclusive)
            end_ts: End timestamp (inclusive)
        
        Returns:
            List of (token, timestamp) tuples within range
        """
        node = self._active_nodes.get(node_id)
        if node is None or node.sequence_buffer is None:
            return []
        
        all_tokens = node.sequence_buffer.get_all()
        
        return [
            (token, ts) for token, ts in all_tokens
            if start_ts <= ts <= end_ts
        ]
    
    def get_motifs_last_seen_since(
        self,
        node_id: str,
        since_ts: float
    ) -> List[Dict]:
        """
        Get motifs observed since specified timestamp.
        
        Factual recency filter, NOT importance ranking.
        
        Args:
            node_id: Node identifier
            since_ts: Timestamp threshold
        
        Returns:
            List of motif dictionaries observed since timestamp
        """
        node = self._active_nodes.get(node_id)
        if node is None:
            return []
        
        motifs = []
        for motif_tuple, last_seen in node.motif_last_seen.items():
            if last_seen >= since_ts:
                motifs.append({
                    'motif': motif_tuple,
                    'count': node.motif_counts.get(motif_tuple, 0),
                    'last_seen_ts': last_seen,
                    'strength': node.motif_strength.get(motif_tuple, 0.0)
                })
        
        return motifs
    
    def get_sequence_diversity(self, node_id: str) -> Dict:
        """
        Get diversity metrics for node's sequence history.
        
        Returns factual counts, NOT quality scores.
        
        Args:
            node_id: Node identifier
        
        Returns:
            Dict with keys: unique_bigrams, unique_trigrams, total_tokens, diversity_ratio
        """
        node = self._active_nodes.get(node_id)
        if node is None:
            return {
                'unique_bigrams': 0,
                'unique_trigrams': 0,
                'total_tokens': 0,
                'diversity_ratio': 0.0
            }
        
        # Count unique motifs by length
        unique_bigrams = sum(1 for m in node.motif_counts.keys() if len(m) == 2)
        unique_trigrams = sum(1 for m in node.motif_counts.keys() if len(m) == 3)
        
        total_tokens = node.sequence_buffer.get_size() if node.sequence_buffer else 0
        
        # Diversity ratio: unique motifs / possible motifs (approx)
        # NOT a quality metric
        total_unique = unique_bigrams + unique_trigrams
        possible_motifs = max(1, total_tokens - 1)  # Avoid division by zero
        diversity_ratio = total_unique / possible_motifs if possible_motifs > 0 else 0.0
        
        return {
            'unique_bigrams': unique_bigrams,
            'unique_trigrams': unique_trigrams,
            'total_tokens': total_tokens,
            'diversity_ratio': diversity_ratio
        }
    
    def get_motif_decay_state(
        self,
        node_id: str,
        motif: Tuple
    ) -> Optional[Dict]:
        """
        Get current decay state for a motif.
        
        Mechanical calculation, NOT relevance prediction.
        
        Args:
            node_id: Node identifier
            motif: Motif tuple
        
        Returns:
            Dict with decay state or None if motif not observed
        """
        node = self._active_nodes.get(node_id)
        if node is None or motif not in node.motif_counts:
            return None
        
        from memory.m2_memory_state import MemoryState, MemoryStateAnalyzer
        
        # Get node's memory state to determine decay rate
        node_state_enum = MemoryStateAnalyzer.classify_node_state(node)
        
        return {
            'current_strength': node.motif_strength.get(motif, 0.0),
            'time_since_seen': 0.0,  # Would need current timestamp
            'decay_rate': node.decay_rate,
            'node_state': node_state_enum.value
        }
    
    def get_buffer_metadata(self, node_id: str) -> Dict:
        """
        Get metadata about node's sequence buffer.
        
        Args:
            node_id: Node identifier
        
        Returns:
            Dict with buffer metadata
        """
        node = self._active_nodes.get(node_id)
        if node is None or node.sequence_buffer is None:
            return {
                'current_size': 0,
                'max_length': 0,
                'time_window_sec': 0.0,
                'oldest_ts': None,
                'newest_ts': None,
                'total_observed': 0
            }
        
        buffer = node.sequence_buffer
        
        return {
            'current_size': buffer.get_size(),
            'max_length': buffer.max_length,
            'time_window_sec': buffer.time_window_sec,
            'oldest_ts': buffer.get_oldest_timestamp(),
            'newest_ts': buffer.get_newest_timestamp(),
            'total_observed': buffer.total_tokens_observed
        }
    
    def get_token_counts(self, node_id: str) -> Dict:
        """
        Get histogram of token types in buffer.
        
        All types counted equally (no importance weighting).
        
        Args:
            node_id: Node identifier
        
        Returns:
            Dict mapping EvidenceToken → count
        """
        node = self._active_nodes.get(node_id)
        if node is None or node.sequence_buffer is None:
            return {}
        
        from memory.m3_evidence_token import EvidenceToken
        
        # Initialize counts for all token types
        counts = {token: 0 for token in EvidenceToken}
        
        # Count occurrences from buffer
        all_tokens = node.sequence_buffer.get_all()
        for token, _ in all_tokens:
            counts[token] += 1
        
        # Return only non-zero counts
        return {token: count for token, count in counts.items() if count > 0}
    
    # ==================== M4: CONTEXTUAL READ MODEL QUERY INTERFACE ====================
    
    def get_evidence_composition_view(self, node_id: str) -> Optional[EvidenceCompositionView]:
        """Get M4 evidence composition view for a node. Thin wrapper - no transformation."""
        node = self.get_node(node_id)
        return get_evidence_composition(node) if node else None
    
    def get_interaction_density_view(self, node_id: str, current_ts: float) -> Optional[InteractionDensityView]:
        """Get M4 interaction density view for a node. Thin wrapper - no transformation."""
        node = self.get_node(node_id)
        return get_interaction_density(node, current_ts) if node else None
    
    def get_stability_metrics_view(self, node_id: str, current_ts: float) -> Optional[StabilityTransienceView]:
        """Get M4 stability/transience view for a node. Thin wrapper - no transformation."""
        node = self.get_node(node_id)
        return get_stability_metrics(node, current_ts) if node else None
    
    def get_temporal_structure_view(self, node_id: str, current_ts: float) -> Optional[TemporalStructureView]:
        """Get M4 temporal structure view for a node. Thin wrapper - no transformation."""
        node = self.get_node(node_id)
        return get_temporal_structure(node, current_ts) if node else None
    
    def get_cross_node_context_view(
        self,
        price_range_start: float,
        price_range_end: float,
        current_ts: float
    ) -> CrossNodeContextView:
        """Get M4 cross-node context view for a price range. Thin wrapper - no transformation."""
        all_nodes = (
            list(self._active_nodes.values()) +
            list(self._dormant_nodes.values()) +
            list(self._archived_nodes.values())
        )
        return get_cross_node_context(price_range_start, price_range_end, all_nodes, current_ts)
