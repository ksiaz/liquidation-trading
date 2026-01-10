# M3 Data Structures Specification

## Overview

M3 extends M2 by **adding new fields** to existing structures. No M2 fields are modified or removed.

---

## Structure 1: EvidenceToken (Enum)

```python
from enum import Enum

class EvidenceToken(Enum):
    """
    Neutral event tokens for M3 temporal ordering.
    
    Each token represents a single, observable event type.
    NO directional or semantic interpretation.
    """
    
    # Orderbook events
    OB_APPEAR = "ob_appear"          # Orderbook level appeared within node band
    OB_PERSIST = "ob_persist"        # Orderbook level persisted ≥N seconds
    OB_VANISH = "ob_vanish"          # Orderbook level disappeared from band
    
    # Trade events
    TRADE_EXEC = "trade_exec"        # Trade executed at node price
    TRADE_VOLUME_HIGH = "trade_vol_high"  # Trade volume exceeded threshold
    
    # Liquidation events
    LIQ_OCCUR = "liq_occur"          # Liquidation within proximity to node
    LIQ_CASCADE = "liq_cascade"      # Multiple liquidations in time window
    
    # Price events
    PRICE_TOUCH = "price_touch"      # Price entered node's price band
    PRICE_EXIT = "price_exit"        # Price exited node's price band
    PRICE_DWELL = "price_dwell"      # Price remained in band ≥N seconds
```

**Purpose:** Complete, closed set of observable event types for temporal ordering.

---

## Structure 2: SequenceBuffer

```python
from dataclasses import dataclass, field
from typing import List, Tuple
from collections import deque

@dataclass
class SequenceBuffer:
    """
    Rolling window of recent evidence tokens with timestamps.
    
    Bounded by time window and max length to prevent unbounded growth.
    Tokens stored in chronological order (FIFO).
    """
    
    # Core sequence storage
    tokens: deque[Tuple[EvidenceToken, float]] = field(default_factory=deque)
    # Deque of (token, timestamp) tuples
    # Chronologically ordered (oldest first, newest last)
    # Purpose: Recent temporal context for motif extraction
    
    # Buffer bounds
    max_length: int = 100
    # Maximum number of tokens to retain
    # Purpose: Prevent unbounded memory growth
    # Default: 100 tokens per node
    
    time_window_sec: float = 86400.0
    # Time window for token retention (seconds)
    # Purpose: Only keep tokens from last N seconds
    # Default: 86400 = 24 hours
    
    # Metadata
    total_tokens_observed: int = 0
    # Cumulative count of all tokens ever appended
    # Purpose: Track total event activity (never decreases)
    # NOT used for prediction or importance
```

**Backward compatibility:** New structure, no conflict with M2.

---

## Structure 3: MotifMetrics

```python
from dataclasses import dataclass

@dataclass
class MotifMetrics:
    """
    Metrics for a single observed motif (bigram or trigram).
    
    Stores factual counts and decay-weighted strength.
    NO predictions, probabilities, or importance scores.
    """
    
    # Motif identity
    motif: Tuple[EvidenceToken, ...]
    # The actual token sequence (length 2 or 3)
    # Example: (OB_APPEAR, TRADE_EXEC) or (TRADE_EXEC, LIQ_OCCUR, PRICE_EXIT)
    # Purpose: Identify which sequence this metrics applies to
    
    # Factual counts
    count: int
    # Number of times this motif has been observed
    # Purpose: Historical occurrence frequency (cumulative, never decreases)
    # Incremented by 1 each time motif extracted
    # NOT a probability or importance score
    
    # Temporal tracking
    last_seen_ts: float
    # Unix timestamp of most recent observation
    # Purpose: Track recency for decay calculation and queries
    # NOT a prediction of next occurrence
    
    # Decay-weighted strength
    strength: float
    # Mechanically decayed strength value
    # Purpose: Temporal relevance weighting (recent = higher)
    # Formula: strength *= (1 - decay_rate * time_elapsed)
    # NOT an importance score or reliability measure
    # Decays at same rate as parent node (ACTIVE/DORMANT/ARCHIVED)
```

**Backward compatibility:** New structure, no conflict with M2.

---

## Structure 4: EnrichedLiquidityMemoryNode (M3 Extension)

```python
from dataclasses import dataclass, field
from typing import Dict, Optional

@dataclass
class EnrichedLiquidityMemoryNode:
    """
    M2 enriched node extended with M3 temporal ordering fields.
    
    ALL M2 FIELDS UNCHANGED - only new M3 fields added below.
    """
    
    # ========================================================================
    # M2 FIELDS (UNCHANGED - DO NOT MODIFY)
    # ========================================================================
    
    # Core identification
    id: str
    price_center: float
    price_band: float
    side: str  # "bid", "ask", "both"
    
    # Temporal
    first_seen_ts: float
    last_interaction_ts: float
    
    # Strength & confidence
    strength: float
    confidence: float
    
    # Metadata
    creation_reason: str
    decay_rate: float
    active: bool
    
    # M2 Enriched Evidence (4 dimensions)
    # ... (all 24 M2 enriched fields remain unchanged)
    # interaction_count, orderbook_appearance_count, trade_execution_count,
    # liquidation_proximity_count, volume_total, volume_largest_event,
    # buyer_initiated_volume, seller_initiated_volume, liquidations_within_band,
    # long_liquidations, short_liquidations, max_liquidation_cascade_size,
    # interaction_gap_median, interaction_gap_stddev, time_since_last_interaction,
    # persistence_duration_total, max_single_persistence, rejection_count,
    # stress_proximity_events, stress_proximity_min_distance,
    # cumulative_stress_exposure, max_stress_cascade_size,
    # flow_imbalance_ratio, flow_reversal_count
    
    # ========================================================================
    # M3 FIELDS (NEW - TEMPORAL ORDERING)
    # ========================================================================
    
    # Sequence buffer
    sequence_buffer: Optional[SequenceBuffer] = None
    # Rolling window of recent evidence tokens
    # Purpose: Store chronological event sequence for motif extraction
    # Initialized on first evidence token
    # Trimmed by time window and max length
    
    # Motif storage
    motif_counts: Dict[Tuple[EvidenceToken, ...], int] = field(default_factory=dict)
    # Maps motif → count
    # Example: {(OB_APPEAR, TRADE_EXEC): 5, (TRADE_EXEC, LIQ_OCCUR): 3}
    # Purpose: Track how many times each sequence occurred
    # Keys: tuples of 2-3 EvidenceTokens (bigrams/trigrams)
    # Values: occurrence count (cumulative, never decreases)
    
    motif_last_seen: Dict[Tuple[EvidenceToken, ...], float] = field(default_factory=dict)
    # Maps motif → timestamp
    # Example: {(OB_APPEAR, TRADE_EXEC): 1704067200.0}
    # Purpose: Track when each motif last occurred
    # Used for decay calculation and recency queries
    
    motif_strength: Dict[Tuple[EvidenceToken, ...], float] = field(default_factory=dict)
    # Maps motif → decayed strength
    # Example: {(OB_APPEAR, TRADE_EXEC): 0.45}
    # Purpose: Mechanical decay-weighted strength
    # Decays at same rate as node (ACTIVE/DORMANT/ARCHIVED)
    # NOT an importance score
    
    # Metadata
    total_sequences_observed: int = 0
    # Total number of motifs extracted (cumulative)
    # Purpose: Track total pattern extraction activity
    # Incremented when new motifs extracted
    # NOT used for importance ranking
```

**Backward compatibility guarantees:**
- ✅ All M2 fields unchanged
- ✅ Only new M3 fields added (sequence_buffer, motif_*)
- ✅ New fields have defaults (None or empty dict)
- ✅ Old M2 code continues to work (ignores M3 fields)

---

## Field Naming Conventions

**M3 follows M2 naming:**
- Lowercase with underscores: `motif_counts`, `sequence_buffer`
- Descriptive, not semantic: `motif_strength` (not `motif_importance`)
- Neutral labels: `EvidenceToken` (not `SignalToken`)

**Prohibited field names:**
- ❌ `motif_probability`
- ❌ `motif_importance`
- ❌ `motif_confidence`
- ❌ `pattern_reliability`
- ❌ `next_token_prediction`

---

## Memory Footprint Estimate

**Per node (worst case):**

**Sequence buffer:**
- 100 tokens × (enum + float) ≈ 100 × 16 bytes = 1.6 KB

**Motifs:**
- Bigrams: ~90 possible in 100-token sequence
- Trigrams: ~80 possible in 100-token sequence
- Total: ~170 motifs max
- Per motif: (tuple + int + float + float) ≈ 40 bytes
- Total: 170 × 40 = 6.8 KB

**Total M3 overhead per node:** ~8.4 KB (worst case)

**For 100 nodes:** ~840 KB
**For 1000 nodes:** ~8.4 MB

**Acceptable:** M3 adds minimal memory overhead to M2.

---

## Type Compatibility

**Python type hints:**
```python
# M3 types are standard Python
EvidenceToken: Enum
SequenceBuffer: dataclass
MotifMetrics: dataclass
EnrichedLiquidityMemoryNode: dataclass (extended)

# Collections
motif_counts: Dict[Tuple[EvidenceToken, ...], int]
motif_last_seen: Dict[Tuple[EvidenceToken, ...], float]
motif_strength: Dict[Tuple[EvidenceToken, ...], float]
tokens: deque[Tuple[EvidenceToken, float]]
```

**Serialization:**
- Enum → string (`EvidenceToken.OB_APPEAR` → `"ob_appear"`)
- Tuple[EvidenceToken] → List[str] (for JSON)
- deque → list (for JSON)

---

## Initialization Patterns

**New node (no M3 data):**
```python
node = EnrichedLiquidityMemoryNode(
    # ... M2 fields ...
    sequence_buffer=None,  # Initialized on first evidence
    motif_counts={},
    motif_last_seen={},
    motif_strength={},
    total_sequences_observed=0
)
```

**First evidence token:**
```python
if node.sequence_buffer is None:
    node.sequence_buffer = SequenceBuffer()

node.sequence_buffer.append((token, timestamp))
node.total_sequences_observed += 1
```

**Revival from dormant:**
```python
# M3 fields preserved (same as M2 revival)
# sequence_buffer retained
# motif_counts retained
# motif_last_seen retained
# motif_strength restored with decay
```

---

## Summary

**New structures:**
1. `EvidenceToken` (Enum) - 10 neutral token types
2. `SequenceBuffer` (dataclass) - Rolling window of tokens
3. `MotifMetrics` (dataclass) - Per-motif tracking data
4. `EnrichedLiquidityMemoryNode` extension - Add 5 M3 fields

**Backward compatibility:**
- ✅ No M2 fields modified
- ✅ All M3 fields optional/default
- ✅ M2 code unaffected by M3 extension

**Field guarantees:**
- ✅ Neutral naming (no "importance", "probability")
- ✅ Factual types (counts, timestamps, mechanical strength)
- ✅ Bounded memory (max 100 tokens, time window)

**Awaiting PASS to proceed.**
