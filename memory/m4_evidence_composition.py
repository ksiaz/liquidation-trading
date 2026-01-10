"""
M4 Evidence Composition Views

Read-only, deterministic view of evidence composition at memory nodes.
Describes what types of evidence have been observed (orderbook/trade/liquidation)
and their proportions, without interpretation or importance ranking.

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
from typing import List
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m3_evidence_token import EvidenceToken


@dataclass
class EvidenceCompositionView:
    """
    Read-only view of evidence type composition at a node.
    
    All fields are factual counts, ratios, or neutral labels.
    NO importance scores, NO quality judgments.
    """
    node_id: str
    
    # Factual counts
    orderbook_count: int
    trade_count: int
    liquidation_count: int
    
    # Factual ratios (proportions only, NOT importance weights)
    orderbook_ratio: float  # 0.0-1.0
    trade_ratio: float      # 0.0-1.0
    liquidation_ratio: float  # 0.0-1.0
    
    # Volume breakdowns (factual USD amounts, execution-side attribution)
    buyer_volume_usd: float  # Buyer-initiated volume (factual)
    seller_volume_usd: float  # Seller-initiated volume (factual)
    total_volume_usd: float
    
    # Fill type ratios (factual proportions)
    passive_fill_ratio: float   # 0.0-1.0
    aggressive_fill_ratio: float  # 0.0-1.0
    
    # Neutral descriptor (NOT evaluative)
    dominant_evidence_type: str  # 'orderbook', 'trade', or 'liquidation'


def get_evidence_composition(node: EnrichedLiquidityMemoryNode) -> EvidenceCompositionView:
    """
    Get evidence composition view for a single node.
    
    Pure function: same node → same output.
    Read-only: does not modify node.
    Factual: no ranking, no importance, no prediction.
    
    Args:
        node: Memory node to analyze
    
    Returns:
        EvidenceCompositionView with factual composition metrics
    """
    # Read M2 fields (read-only)
    orderbook_count = node.orderbook_appearance_count
    trade_count = node.trade_execution_count
    liquidation_count = node.liquidation_proximity_count
    
    total_interactions = orderbook_count + trade_count + liquidation_count
    
    # Calculate ratios (if total > 0, else all zeros)
    if total_interactions > 0:
        orderbook_ratio = orderbook_count / total_interactions
        trade_ratio = trade_count / total_interactions
        liquidation_ratio = liquidation_count / total_interactions
    else:
        orderbook_ratio = 0.0
        trade_ratio = 0.0
        liquidation_ratio = 0.0
    
    # Read volume fields (factual execution-side data)
    buyer_volume = node.buyer_initiated_volume
    seller_volume = node.seller_initiated_volume
    total_volume = node.volume_total
    
    # Calculate fill ratios
    passive_volume = node.passive_fill_volume
    aggressive_volume = node.aggressive_fill_volume
    total_fill_volume = passive_volume + aggressive_volume
    
    if total_fill_volume > 0:
        passive_ratio = passive_volume / total_fill_volume
        aggressive_ratio = aggressive_volume / total_fill_volume
    else:
        passive_ratio = 0.0
        aggressive_ratio = 0.0
    
    # Determine dominant type (neutral descriptor, NOT importance ranking)
    if orderbook_count >= trade_count and orderbook_count >= liquidation_count:
        dominant = 'orderbook'
    elif trade_count >= liquidation_count:
        dominant = 'trade'
    else:
        dominant = 'liquidation'
    
    return EvidenceCompositionView(
        node_id=node.id,
        orderbook_count=orderbook_count,
        trade_count=trade_count,
        liquidation_count=liquidation_count,
        orderbook_ratio=orderbook_ratio,
        trade_ratio=trade_ratio,
        liquidation_ratio=liquidation_ratio,
        buyer_volume_usd=buyer_volume,
        seller_volume_usd=seller_volume,
        total_volume_usd=total_volume,
        passive_fill_ratio=passive_ratio,
        aggressive_fill_ratio=aggressive_ratio,
        dominant_evidence_type=dominant
    )


def get_evidence_composition_by_token_type(
    node: EnrichedLiquidityMemoryNode,
    token_types: List[EvidenceToken]
) -> EvidenceCompositionView:
    """
    Get evidence composition view filtered by specific token types.
    
    Returns composition considering only the specified evidence token types.
    Factual filter - NOT an importance or relevance filter.
    
    Args:
        node: Memory node to analyze
        token_types: List of token types to include in composition
    
    Returns:
        EvidenceCompositionView with filtered composition
    """
    # Read sequence buffer from M3
    if node.sequence_buffer is None:
        # No M3 data, return standard composition
        return get_evidence_composition(node)
    
    all_tokens = node.sequence_buffer.get_all()
    
    # Count tokens by type (factual counting only)
    orderbook_tokens = {EvidenceToken.OB_APPEAR, EvidenceToken.OB_PERSIST, EvidenceToken.OB_VANISH}
    trade_tokens = {EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_VOLUME_HIGH}
    liquidation_tokens = {EvidenceToken.LIQ_OCCUR, EvidenceToken.LIQ_CASCADE}
    
    # Filter to requested types
    filtered_tokens = [token for token, _ in all_tokens if token in token_types]
    
    # Count by category
    orderbook_count = sum(1 for t in filtered_tokens if t in orderbook_tokens)
    trade_count = sum(1 for t in filtered_tokens if t in trade_tokens)
    liquidation_count = sum(1 for t in filtered_tokens if t in liquidation_tokens)
    
    total = orderbook_count + trade_count + liquidation_count
    
    # Calculate ratios
    if total > 0:
        orderbook_ratio = orderbook_count / total
        trade_ratio = trade_count / total
        liquidation_ratio = liquidation_count / total
    else:
        orderbook_ratio = 0.0
        trade_ratio = 0.0
        liquidation_ratio = 0.0
    
    # Volume data still from M2 (not filtered)
    buyer_volume = node.buyer_initiated_volume
    seller_volume = node.seller_initiated_volume
    total_volume = node.volume_total
    
    passive_volume = node.passive_fill_volume
    aggressive_volume = node.aggressive_fill_volume
    total_fill_volume = passive_volume + aggressive_volume
    
    if total_fill_volume > 0:
        passive_ratio = passive_volume / total_fill_volume
        aggressive_ratio = aggressive_volume / total_fill_volume
    else:
        passive_ratio = 0.0
        aggressive_ratio = 0.0
    
    # Dominant type from filtered tokens
    if orderbook_count >= trade_count and orderbook_count >= liquidation_count:
        dominant = 'orderbook'
    elif trade_count >= liquidation_count:
        dominant = 'trade'
    else:
        dominant = 'liquidation'
    
    return EvidenceCompositionView(
        node_id=node.id,
        orderbook_count=orderbook_count,
        trade_count=trade_count,
        liquidation_count=liquidation_count,
        orderbook_ratio=orderbook_ratio,
        trade_ratio=trade_ratio,
        liquidation_ratio=liquidation_ratio,
        buyer_volume_usd=buyer_volume,
        seller_volume_usd=seller_volume,
        total_volume_usd=total_volume,
        passive_fill_ratio=passive_ratio,
        aggressive_fill_ratio=aggressive_ratio,
        dominant_evidence_type=dominant
    )
