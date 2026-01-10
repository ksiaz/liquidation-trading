# M3 Query Interface Specification (Read-Only)

## Overview

M3 query methods are **strictly read-only** and return **historical data only**. No method may rank, score, recommend, or predict. All queries return factual counts, timestamps, and sequences.

---

## Query Method Signatures

### Node-Level Queries

#### 1. get_sequence_buffer(node_id: str) → Optional[List[Tuple[EvidenceToken, float]]]

Returns the complete sequence buffer for a node as a chronologically-ordered list of (token, timestamp) tuples. Returns None if node has no sequence buffer. This method provides raw access to the temporal event history without any interpretation or filtering. The sequence represents the exact order in which evidence events occurred at this price level.

**Returns:** Raw chronological token sequence, or None if no buffer exists.

---

#### 2. get_recent_tokens(node_id: str, count: int = 10) → List[Tuple[EvidenceToken, float]]

Returns the N most recent tokens from a node's sequence buffer, preserving chronological order (oldest to newest). This is a convenience method for accessing recent temporal context without retrieving the entire buffer. The count parameter is a factual limit, NOT an importance threshold.

**Returns:** List of up to N most recent (token, timestamp) tuples in chronological order.

---

#### 3. get_motifs_for_node(node_id: str, min_count: int = 1) → List[Dict]

Returns all observed motifs (bigrams and trigrams) for a specific node, filtered by minimum occurrence count. Each motif is returned as a dictionary containing the sequence, count, last_seen timestamp, and current strength. The min_count parameter is a factual filter (occurrence threshold), NOT an importance ranking. Results are NOT sorted by importance, only by motif tuple for deterministic ordering.

**Returns:** List of dicts with keys: `motif`, `count`, `last_seen_ts`, `strength`.

---

#### 4. get_motif_by_pattern(node_id: str, pattern: Tuple[EvidenceToken, ...]) → Optional[Dict]

Returns metrics for a specific motif pattern if it has been observed at the node. This allows checking whether a particular sequence (e.g., `(OB_APPEAR, TRADE_EXEC)`) has occurred historically. Returns None if the pattern has never been observed. This is a factual lookup, NOT a prediction of whether the pattern will occur again.

**Returns:** Dict with `motif`, `count`, `last_seen_ts`, `strength`, or None if not observed.

---

### Cross-Node Queries

#### 5. get_nodes_with_motif(motif: Tuple[EvidenceToken, ...], min_count: int = 1) → List[str]

Returns list of node IDs that have observed the specified motif at least min_count times. This allows identifying which price levels have exhibited a particular sequence historically. The result is a factual list of node IDs, NOT ranked by importance or relevance. Useful for understanding spatial distribution of temporal patterns.

**Returns:** List of node IDs (strings) that observed the motif.

---

#### 6. get_motif_statistics(motif: Tuple[EvidenceToken, ...]) → Dict

Returns aggregate statistics for a specific motif across all nodes. Includes total observation count (sum across all nodes), number of nodes where observed, average count per node, and most recent observation timestamp globally. This provides a factual summary of how widespread a sequence pattern is, NOT a prediction of its future occurrence.

**Returns:** Dict with keys: `total_count`, `node_count`, `avg_count_per_node`, `most_recent_ts`.

---

### Temporal Queries

#### 7. get_tokens_in_time_range(node_id: str, start_ts: float, end_ts: float) → List[Tuple[EvidenceToken, float]]

Returns all tokens from a node's sequence buffer that occurred within the specified time range [start_ts, end_ts], inclusive. This allows querying temporal context for a specific time period. Results maintain chronological order. The time range is a factual filter, NOT a "recent = important" weighting.

**Returns:** List of (token, timestamp) tuples within time range, chronologically ordered.

---

#### 8. get_motifs_last_seen_since(node_id: str, since_ts: float) → List[Dict]

Returns all motifs that have been observed at least once since the specified timestamp. This allows filtering for "recently active" patterns based on factual recency, NOT importance. Each motif includes full metrics (count, last_seen, strength). Results are NOT ranked by recency.

**Returns:** List of dicts with keys: `motif`, `count`, `last_seen_ts`, `strength`.

---

### Statistical Queries (Factual Only)

#### 9. get_sequence_diversity(node_id: str) → Dict

Returns factual diversity metrics for a node's temporal sequences. Includes total unique bigrams observed, total unique trigrams observed, total tokens in buffer, and ratio of unique motifs to total possible motifs. This quantifies sequence variety, NOT quality or importance. High diversity is a factual observation, NOT a signal.

**Returns:** Dict with keys: `unique_bigrams`, `unique_trigrams`, `total_tokens`, `diversity_ratio`.

---

#### 10. get_motif_decay_state(node_id: str, motif: Tuple[EvidenceToken, ...]) → Dict

Returns the current decay state of a specific motif, including current strength, time since last seen, decay rate being applied (ACTIVE/DORMANT/ARCHIVED), and projected strength at future timestamp (purely mechanical calculation). The projection is NOT a prediction of relevance, only a factual decay calculation.

**Returns:** Dict with keys: `current_strength`, `time_since_seen`, `decay_rate`, `node_state`.

---

### Buffer Metadata Queries

#### 11. get_buffer_metadata(node_id: str) → Dict

Returns metadata about a node's sequence buffer, including current buffer size (number of tokens), maximum capacity, time window setting, oldest token timestamp, newest token timestamp, and total tokens ever observed (cumulative). This provides factual information about buffer state and history.

**Returns:** Dict with keys: `current_size`, `max_length`, `time_window_sec`, `oldest_ts`, `newest_ts`, `total_observed`.

---

#### 12. get_token_counts(node_id: str) → Dict[EvidenceToken, int]

Returns count of each token type in the node's sequence buffer. For example, how many `TRADE_EXEC` tokens vs `OB_APPEAR` tokens are in recent history. This is a factual histogram of token types, NOT an importance weighting. All token types are counted equally.

**Returns:** Dict mapping each EvidenceToken to its occurrence count in buffer.

---

## Prohibited Query Methods

The following methods are **EXPLICITLY FORBIDDEN** as they introduce interpretation:

❌ `get_most_important_motifs()` - Ranking by importance  
❌ `predict_next_token()` - Prediction  
❌ `get_motif_probability()` - Probabilistic inference  
❌ `rank_motifs_by_reliability()` - Reliability scoring  
❌ `get_bullish_patterns()` - Directional semantics  
❌ `recommend_entry_patterns()` - Action recommendation  
❌ `score_motif_confidence()` - Confidence scoring  
❌ `get_strongest_patterns()` - Strength-based ranking  
❌ `classify_regime_from_motifs()` - Regime inference  

---

## Query Design Principles

### Principle 1: Queries Return Raw Data

All queries return **unprocessed historical facts**:
- Counts (how many times)
- Timestamps (when it occurred)
- Sequences (what order)
- States (current decay state)

NO queries return:
- Scores (how important)
- Probabilities (how likely)
- Rankings (best to worst)
- Predictions (what's next)

### Principle 2: Filtering is Factual

Queries may filter by:
- ✅ Time range (factual boundary)
- ✅ Count threshold (factual minimum)
- ✅ Token type (factual category)
- ✅ Node ID (factual identity)

Queries may NOT filter by:
- ❌ Importance (interpretive)
- ❌ Reliability (interpretive)
- ❌ Confidence (interpretive)
- ❌ Strength ranking (interpretive)

### Principle 3: No Implicit Ordering

When queries return lists, ordering is:
- ✅ Chronological (factual time order)
- ✅ Alphabetical (deterministic)
- ✅ By node ID (deterministic)

Ordering is NOT:
- ❌ By importance (interpretive)
- ❌ By strength (interpreted as significance)
- ❌ By frequency (interpreted as reliability)

### Principle 4: Metadata is Descriptive

Query results may include metadata that describes:
- ✅ When data was collected
- ✅ How many items match filter
- ✅ What time range is covered

Metadata does NOT include:
- ❌ Confidence scores
- ❌ Importance ratings
- ❌ Recommended actions

---

## Usage Examples (What Strategies May Do)

**Example 1: Check if specific sequence occurred**
```python
# Strategy checks if (LIQ_OCCUR, TRADE_EXEC) has been observed
motif = store.get_motif_by_pattern("node_2.10", (LIQ_OCCUR, TRADE_EXEC))
if motif and motif['count'] >= 3:
    # Strategy interprets: "This sequence happened 3+ times"
    # M3 only provided: factual count
```

**Example 2: Compare sequence diversity across nodes**
```python
# Strategy compares diversity at two levels
diversity_A = store.get_sequence_diversity("node_2.10")
diversity_B = store.get_sequence_diversity("node_2.15")

if diversity_A['unique_bigrams'] > diversity_B['unique_bigrams']:
    # Strategy interprets: "Node A has more varied patterns"
    # M3 only provided: factual counts
```

**Example 3: Query recent temporal context**
```python
# Strategy examines last 50 tokens before entry decision
recent = store.get_recent_tokens("node_2.10", count=50)

# Strategy may look for specific patterns in recent history
# M3 only provided: chronological token list
# Strategy does the interpretation
```

**Critical:** In all cases, **strategies interpret**, **M3 provides facts**.

---

## Return Type Conventions

**Single item queries:**
- Return `None` if not found
- Return `Dict` or specific type if found

**List queries:**
- Return empty list `[]` if no matches
- Return list of items (may be dicts, tuples, etc.)

**Metadata queries:**
- Always return `Dict` with standard keys
- Missing data represented as `None` in dict

**No exceptions for "not found":** Queries return None or empty list, not errors.

---

## Summary

**M3 query interface provides:**
- ✅ Historical data access
- ✅ Factual filtering (time, count, token)
- ✅ Chronological ordering
- ✅ Metadata about sequences

**M3 query interface does NOT provide:**
- ❌ Rankings or scores
- ❌ Predictions or probabilities
- ❌ Recommendations or actions
- ❌ Importance weighting

**Total query methods:** 12 read-only methods  
**Prohibited methods:** 9 explicitly forbidden  
**Design principle:** Factual data access, zero interpretation  

**Awaiting PASS to proceed.**
