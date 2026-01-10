"""
M4 Temporal Structure Views

Read-only, deterministic view of temporal evidence sequence structure from M3.
Describes how evidence tokens unfold chronologically, their diversity, and motif patterns,
without interpretation, quality scoring, or predictive pattern analysis.

NO prediction, NO ranking, NO scoring.
"""

from dataclasses import dataclass
import statistics
from typing import Tuple, Dict, List
from collections import Counter
from memory.enriched_memory_node import EnrichedLiquidityMemoryNode
from memory.m3_evidence_token import EvidenceToken


@dataclass
class TemporalStructureView:
    """
    Read-only view of temporal sequence structure at a node.
    
    All fields are factual counts, ratios, or neutral descriptors.
    NO pattern strength scores, NO sequence quality judgments, NO predictions.
    """
    node_id: str
    
    # Sequence metrics (factual)
    avg_sequence_length: float
    token_type_count: int  # Number of distinct token types
    token_diversity_ratio: float  # unique types / total tokens (0.0-1.0)
    
    # Timing metrics (factual)
    median_token_gap_sec: float
    
    # Motif metrics (factual counts only, NOT importance rankings)
    most_common_bigram: Tuple[EvidenceToken, EvidenceToken]  # Most frequent, NOT most important
    most_common_bigram_count: int
    
    # Distribution (factual proportions)
    token_type_distribution: Dict[EvidenceToken, float]  # Proportions, NOT weights
    
    # Factual counts
    total_sequences_observed: int
    current_buffer_size: int


def get_temporal_structure(
    node: EnrichedLiquidityMemoryNode,
    current_ts: float
) -> TemporalStructureView:
    """
    Get temporal structure view for a single node.
    
    Pure function: same node + same current_ts → same output.
    Read-only: does not modify node.
    Factual: no pattern strength scoring, no predictive analysis.
    
    Args:
        node: Memory node to analyze
        current_ts: Reference timestamp (used for future extensions)
    
    Returns:
        TemporalStructureView with factual temporal metrics
    """
    node_id = node.id
    
    # Check if M3 data exists
    if node.sequence_buffer is None:
        # No M3 data, return empty metrics
        return TemporalStructureView(
            node_id=node_id,
            avg_sequence_length=0.0,
            token_type_count=0,
            token_diversity_ratio=0.0,
            median_token_gap_sec=0.0,
            most_common_bigram=(EvidenceToken.OB_APPEAR, EvidenceToken.OB_APPEAR),  # Placeholder
            most_common_bigram_count=0,
            token_type_distribution={},
            total_sequences_observed=0,
            current_buffer_size=0
        )
    
    # Read M3 sequence buffer (read-only)
    all_tokens = node.sequence_buffer.get_all()
    total_observed = node.total_sequences_observed if hasattr(node, 'total_sequences_observed') else len(all_tokens)
    
    current_buffer_size = len(all_tokens)
    
    if current_buffer_size == 0:
        return TemporalStructureView(
            node_id=node_id,
            avg_sequence_length=0.0,
            token_type_count=0,
            token_diversity_ratio=0.0,
            median_token_gap_sec=0.0,
            most_common_bigram=(EvidenceToken.OB_APPEAR, EvidenceToken.OB_APPEAR),
            most_common_bigram_count=0,
            token_type_distribution={},
            total_sequences_observed=total_observed,
            current_buffer_size=0
        )
    
    # Extract tokens and timestamps
    tokens = [token for token, _ in all_tokens]
    timestamps = [ts for _, ts in all_tokens]
    
    # Token diversity
    unique_tokens = set(tokens)
    token_type_count = len(unique_tokens)
    token_diversity_ratio = token_type_count / len(tokens) if len(tokens) > 0 else 0.0
    
    # Average sequence length (current buffer size is our measure)
    avg_sequence_length = float(current_buffer_size)
    
    # Token gaps
    if len(timestamps) >= 2:
        gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        median_gap = statistics.median(gaps)
    else:
        median_gap = 0.0
    
    # Token type distribution (proportions)
    token_counts = Counter(tokens)
    total_tokens = len(tokens)
    token_distribution = {
        token: count / total_tokens
        for token, count in token_counts.items()
    }
    
    # Most common bigram (factual count, NOT importance ranking)
    if len(tokens) >= 2:
        bigrams = [(tokens[i], tokens[i+1]) for i in range(len(tokens) - 1)]
        bigram_counts = Counter(bigrams)
        most_common_bigram, most_common_count = bigram_counts.most_common(1)[0]
    else:
        most_common_bigram = (EvidenceToken.OB_APPEAR, EvidenceToken.OB_APPEAR)
        most_common_count = 0
    
    return TemporalStructureView(
        node_id=node_id,
        avg_sequence_length=avg_sequence_length,
        token_type_count=token_type_count,
        token_diversity_ratio=token_diversity_ratio,
        median_token_gap_sec=median_gap,
        most_common_bigram=most_common_bigram,
        most_common_bigram_count=most_common_count,
        token_type_distribution=token_distribution,
        total_sequences_observed=total_observed,
        current_buffer_size=current_buffer_size
    )


def get_temporal_structure_batch(
    nodes: List[EnrichedLiquidityMemoryNode],
    current_ts: float
) -> Dict[str, TemporalStructureView]:
    """
    Get temporal structure view for multiple nodes.
    
    Returns dict mapping node_id → TemporalStructureView.
    Output order is arbitrary (dict, not sorted by any metric).
    
    Args:
        nodes: List of memory nodes to analyze
        current_ts: Reference timestamp
    
    Returns:
        Dict mapping node_id to temporal structure (unordered)
    """
    return {
        node.id: get_temporal_structure(node, current_ts)
        for node in nodes
    }
