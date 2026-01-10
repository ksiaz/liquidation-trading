"""
M2 Historical Evidence Container

Preserves factual history when nodes transition to DORMANT state.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class HistoricalEvidence:
    """
    Compressed historical evidence for dormant nodes.
    
    All fields are COUNTS, SUMS, or STATISTICS - no interpretation.
    """
    
    # Interaction counts
    total_interactions: int
    orderbook_appearances: int
    trade_executions: int
    liquidation_events: int
    
    # Volume evidence
    total_volume: float
    max_single_event_volume: float
    buyer_volume: float
    seller_volume: float
    
    # Liquidation evidence
    long_liquidations: int
    short_liquidations: int
    max_cascade_size: int
    
    # Temporal statistics
    first_seen_ts: float
    last_seen_ts: float
    median_interaction_gap: float
    
    # Topology (at time of dormancy)
    neighbor_count_at_dormancy: int = 0
    
    def to_dict(self) -> dict:
        """Export to dict."""
        return {
            'total_interactions': self.total_interactions,
            'orderbook_appearances': self.orderbook_appearances,
            'trade_executions': self.trade_executions,
            'liquidation_events': self.liquidation_events,
            'total_volume': self.total_volume,
            'max_single_event_volume': self.max_single_event_volume,
            'buyer_volume': self.buyer_volume,
            'seller_volume': self.seller_volume,
            'long_liquidations': self.long_liquidations,
            'short_liquidations': self.short_liquidations,
            'max_cascade_size': self.max_cascade_size,
            'first_seen_ts': self.first_seen_ts,
            'last_seen_ts': self.last_seen_ts,
            'median_interaction_gap': self.median_interaction_gap,
            'neighbor_count_at_dormancy': self.neighbor_count_at_dormancy,
        }


def extract_historical_evidence(node) -> HistoricalEvidence:
    """Extract historical evidence from active node for dormancy."""
    return HistoricalEvidence(
        total_interactions=node.interaction_count,
        orderbook_appearances=node.orderbook_appearance_count,
        trade_executions=node.trade_execution_count,
        liquidation_events=node.liquidation_proximity_count,
        total_volume=node.volume_total,
        max_single_event_volume=node.volume_largest_event,
        buyer_volume=node.buyer_initiated_volume,
        seller_volume=node.seller_initiated_volume,
        long_liquidations=node.long_liquidations,
        short_liquidations=node.short_liquidations,
        max_cascade_size=node.max_liquidation_cascade_size,
        first_seen_ts=node.first_seen_ts,
        last_seen_ts=node.last_interaction_ts,
        median_interaction_gap=node.interaction_gap_median,
    )


def compute_revival_strength(historical: HistoricalEvidence, new_evidence_strength: float) -> float:
    """
    Compute strength when reactivating dormant node.
    
    Combines historical context with new evidence.
    NOT predictive - purely factual accumulation.
    """
    # Historical contribution based on total interactions
    historical_factor = min(0.5, historical.total_interactions * 0.02)
    
    # Volume contribution
    volume_factor = min(0.3, historical.total_volume / 100000.0)
    
    # Combine with new evidence
    revival_strength = min(1.0, historical_factor + volume_factor + new_evidence_strength)
    
    return revival_strength
