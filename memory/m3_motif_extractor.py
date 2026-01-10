"""
M3 Motif Extractor

Extracts bigrams and trigrams from token sequences.
Pure sliding window - NO ranking, scoring, or prediction.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
from memory.m3_evidence_token import EvidenceToken


@dataclass
class MotifMetrics:
    """
    Metrics for a single observed motif (bigram or trigram).
    
    Stores factual counts and decay-weighted strength.
    NO predictions, probabilities, or importance scores.
    """
    
    motif: Tuple[EvidenceToken, ...]
    # The actual token sequence (length 2 or 3)
    # Example: (OB_APPEAR, TRADE_EXEC) or (TRADE_EXEC, LIQ_OCCUR, PRICE_EXIT)
    # Purpose: Identify which sequence these metrics apply to
    
    count: int
    # Number of times this motif has been observed
    # Purpose: Historical occurrence frequency (cumulative, never decreases)
    # Incremented by 1 each time motif extracted
    # NOT a probability or importance score
    
    last_seen_ts: float
    # Unix timestamp of most recent observation
    # Purpose: Track recency for decay calculation and queries
    # NOT a prediction of next occurrence
    
    strength: float
    # Mechanically decayed strength value
    # Purpose: Temporal relevance weighting (recent = higher)
    # Formula: strength *= (1 - decay_rate * time_elapsed)
    # NOT an importance score or reliability measure
    # Decays at same rate as parent node (ACTIVE/DORMANT/ARCHIVED)


def extract_bigrams(tokens: List[EvidenceToken]) -> List[Tuple[EvidenceToken, EvidenceToken]]:
    """
    Extract all consecutive bigrams from token sequence.
    
    Sliding window of length 2, advancing 1 token at a time.
    NO gap-tolerance - pairs must be adjacent.
    
    Example:
        tokens = [A, B, C, D]
        bigrams = [(A,B), (B,C), (C,D)]
    
    Args:
        tokens: List of evidence tokens in chronological order
    
    Returns:
        List of bigram tuples (consecutive pairs)
    """
    if len(tokens) < 2:
        return []
    
    bigrams = []
    for i in range(len(tokens) - 1):
        bigram = (tokens[i], tokens[i + 1])
        bigrams.append(bigram)
    
    return bigrams


def extract_trigrams(tokens: List[EvidenceToken]) -> List[Tuple[EvidenceToken, EvidenceToken, EvidenceToken]]:
    """
    Extract all consecutive trigrams from token sequence.
    
    Sliding window of length 3, advancing 1 token at a time.
    NO gap-tolerance - triples must be adjacent.
    
    Example:
        tokens = [A, B, C, D]
        trigrams = [(A,B,C), (B,C,D)]
    
    Args:
        tokens: List of evidence tokens in chronological order
    
    Returns:
        List of trigram tuples (consecutive triples)
    """
    if len(tokens) < 3:
        return []
    
    trigrams = []
    for i in range(len(tokens) - 2):
        trigram = (tokens[i], tokens[i + 1], tokens[i + 2])
        trigrams.append(trigram)
    
    return trigrams


def extract_all_motifs(tokens: List[EvidenceToken]) -> List[Tuple[EvidenceToken, ...]]:
    """
    Extract all motifs (bigrams + trigrams) from token sequence.
    
    Args:
        tokens: List of evidence tokens in chronological order
    
    Returns:
        List of all motif tuples (bigrams + trigrams)
    """
    bigrams = extract_bigrams(tokens)
    trigrams = extract_trigrams(tokens)
    
    # Combine into single list
    # Cast to generic tuple type for consistency
    all_motifs: List[Tuple[EvidenceToken, ...]] = []
    all_motifs.extend(bigrams)
    all_motifs.extend(trigrams)
    
    return all_motifs


def count_motifs(motifs: List[Tuple[EvidenceToken, ...]]) -> Dict[Tuple[EvidenceToken, ...], int]:
    """
    Count occurrences of each motif in the list.
    
    If a motif appears multiple times in the list (e.g., from overlapping
    windows), all occurrences are counted.
    
    NO deduplication - reflects actual extraction frequency.
    
    Args:
        motifs: List of motif tuples
    
    Returns:
        Dict mapping motif → occurrence count
    """
    counts: Dict[Tuple[EvidenceToken, ...], int] = {}
    
    for motif in motifs:
        if motif in counts:
            counts[motif] += 1
        else:
            counts[motif] = 1
    
    return counts


def update_motif_metrics(
    existing_metrics: Dict[Tuple[EvidenceToken, ...], MotifMetrics],
    new_motifs: List[Tuple[EvidenceToken, ...]],
    timestamp: float,
    initial_strength: float = 0.1
) -> Dict[Tuple[EvidenceToken, ...], MotifMetrics]:
    """
    Update motif metrics with newly extracted motifs.
    
    For each new motif:
    - If it exists: increment count, update last_seen
    - If new: create with count=1, set initial strength
    
    NO ranking, sorting, or importance weighting.
    
    Args:
        existing_metrics: Current motif metrics dict
        new_motifs: List of newly extracted motifs
        timestamp: Timestamp of extraction
        initial_strength: Initial strength for new motifs
    
    Returns:
        Updated motif metrics dict (modified in place)
    """
    # Count new motifs
    new_counts = count_motifs(new_motifs)
    
    # Update existing metrics or create new
    for motif, count_increment in new_counts.items():
        if motif in existing_metrics:
            # Update existing motif
            metrics = existing_metrics[motif]
            metrics.count += count_increment
            metrics.last_seen_ts = timestamp
            # Note: strength decay applied separately, not here
        else:
            # Create new motif metrics
            existing_metrics[motif] = MotifMetrics(
                motif=motif,
                count=count_increment,
                last_seen_ts=timestamp,
                strength=initial_strength * count_increment
            )
    
    return existing_metrics


def get_motif_length(motif: Tuple[EvidenceToken, ...]) -> int:
    """
    Get the length of a motif (2 for bigram, 3 for trigram).
    
    Args:
        motif: Motif tuple
    
    Returns:
        Length of motif (2-3)
    """
    return len(motif)


def is_bigram(motif: Tuple[EvidenceToken, ...]) -> bool:
    """Check if motif is a bigram (length 2)."""
    return len(motif) == 2


def is_trigram(motif: Tuple[EvidenceToken, ...]) -> bool:
    """Check if motif is a trigram (length 3)."""
    return len(motif) == 3


def filter_motifs_by_length(
    motifs: List[Tuple[EvidenceToken, ...]],
    length: int
) -> List[Tuple[EvidenceToken, ...]]:
    """
    Filter motifs by length.
    
    Args:
        motifs: List of motifs
        length: Desired length (2 or 3)
    
    Returns:
        List of motifs with specified length
    """
    return [m for m in motifs if len(m) == length]


def get_unique_motifs(motifs: List[Tuple[EvidenceToken, ...]]) -> List[Tuple[EvidenceToken, ...]]:
    """
    Get unique motifs from list (de-duplicate).
    
    Preserves first occurrence order.
    
    Args:
        motifs: List of motifs (may contain duplicates)
    
    Returns:
        List of unique motifs
    """
    seen = set()
    unique = []
    
    for motif in motifs:
        if motif not in seen:
            seen.add(motif)
            unique.append(motif)
    
    return unique


def get_motif_statistics(
    metrics: Dict[Tuple[EvidenceToken, ...], MotifMetrics]
) -> Dict[str, int]:
    """
    Get factual statistics about motif collection.
    
    Returns counts only - NO scoring or ranking.
    
    Args:
        metrics: Motif metrics dict
    
    Returns:
        Dict with keys: total_motifs, unique_bigrams, unique_trigrams
    """
    bigram_count = sum(1 for m in metrics.keys() if len(m) == 2)
    trigram_count = sum(1 for m in metrics.keys() if len(m) == 3)
    
    return {
        "total_motifs": len(metrics),
        "unique_bigrams": bigram_count,
        "unique_trigrams": trigram_count
    }
