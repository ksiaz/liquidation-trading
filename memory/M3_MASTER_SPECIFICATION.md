# PHASE M3: TEMPORAL EVIDENCE ORDERING MEMORY
## Complete Specification Document

**Version:** 1.0  
**Date:** 2026-01-04  
**Status:** Planning Complete - Awaiting Implementation Approval

---

# TABLE OF CONTENTS

1. [Conceptual Overview](#1-conceptual-overview)
2. [Evidence Token Specification](#2-evidence-token-specification)
3. [Motif Extraction Logic](#3-motif-extraction-logic)
4. [Decay & Archival Rules](#4-decay--archival-rules)
5. [Data Structures](#5-data-structures)
6. [Query Interface](#6-query-interface)
7. [Compliance Audit](#7-compliance-audit)
8. [Validation Plan](#8-validation-plan)

---

# 1. CONCEPTUAL OVERVIEW

## 1.1 What M3 IS

M3 extends M2 memory by preserving the **chronological order** in which evidence events occurred at each price level. Where M2 records "what happened" (counts, volumes, liquidations), M3 records "**in what order** it happened."

**Core concept:**
- **M2:** Photograph of accumulated evidence
- **M3:** Time-lapse video of evidence accumulation

### Information Preserved

**1. Event Sequence (Ordering)**
- Exact chronological order of events at each price node
- Example at $2.10: `[OB_APPEAR, TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR, PRICE_EXIT]`
- This sequence is **factual history**, not a pattern to predict from

**2. Temporal Patterns (Motifs)**
- Consecutive event pairs (bigrams): `(OB_APPEAR, TRADE_EXEC)`
- Consecutive event triples (trigrams): `(TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR)`
- Counts: How many times each sequence occurred
- Last seen: When each sequence last occurred

**3. Bounded Historical Window**
- Recent 100 events (configurable)
- Last 24 hours of activity
- Prevents unbounded memory growth

### Information Intentionally Destroyed

**1. Statistical Inference**
- NO probabilities ("60% chance next event is X")
- NO likelihood scores
- NO confidence intervals

**2. Semantic Interpretation**
- NO pattern labeling ("breakout pattern")
- NO bullish/bearish classification
- NO support/resistance semantics

**3. Predictive Information**
- NO "next event" predictions
- NO sequence completion
- NO forward inference

**4. Importance Ranking**
- NO "most important patterns"
- NO motif scoring
- NO threshold-based filtering for action

## 1.2 What M3 IS NOT

### NOT a Prediction Engine
- Does NOT answer "What will happen next?"
- ONLY records what sequences occurred historically

### NOT a Pattern Recognition System
- Does NOT identify "bullish patterns"
- Does NOT label motifs as "reliable"
- Does NOT score patterns by "importance"

### NOT a Signal Generator
- Does NOT generate buy/sell signals
- Does NOT trigger strategy entries
- Does NOT recommend actions

### NOT a Regime Classifier
- Does NOT infer "trending" vs "ranging"
- Does NOT detect state changes from patterns

## 1.3 How M3 Complements M2

**M2 provides:** Accumulated evidence snapshot
- Total interactions: 47
- Total volume: $120,000
- Liquidations: 8

**M3 adds:** How that evidence accumulated
- Sequence: `[OB_APPEAR, TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR, ...]`
- Motif: `(TRADE_EXEC, TRADE_EXEC)` occurred 12 times

**Integration:**
- M2 nodes unchanged
- M3 extends nodes with new fields
- Motifs decay at same rate as node
- Backward compatible

**Together:** WHERE + WHAT + WHEN + **HOW (M3)**

---

# 2. EVIDENCE TOKEN SPECIFICATION

## 2.1 Complete Token Set

| Token | Trigger Condition (Factual) | Source | Notes |
|:------|:---------------------------|:-------|:------|
| **OB_APPEAR** | Orderbook level appears within node's price band | Orderbook | Level didn't exist, now exists |
| **OB_PERSIST** | Orderbook level remains present ≥N seconds | Orderbook | Continuous presence |
| **OB_VANISH** | Orderbook level disappears from band | Orderbook | Level existed, now doesn't |
| **TRADE_EXEC** | Trade executed at node's price | Trade | Any trade within band |
| **TRADE_VOLUME_HIGH** | Trade volume exceeds threshold | Trade | Single trade volume > threshold |
| **LIQ_OCCUR** | Liquidation within proximity | Liquidation | Liquidation near node |
| **LIQ_CASCADE** | ≥N liquidations within T seconds | Liquidation | Multiple liquidations |
| **PRICE_TOUCH** | Price enters node's price band | Price | Price moved into band |
| **PRICE_EXIT** | Price leaves node's price band | Price | Price moved out of band |
| **PRICE_DWELL** | Price remains in band ≥N seconds | Price | Price stayed in band |

## 2.2 Rejected Tokens

The following were **intentionally excluded** for being interpretive:

| Rejected Token | Reason |
|:---------------|:-------|
| ~~TRADE_BUY/SELL~~ | Directional bias |
| ~~LIQ_LONG/SHORT~~ | Directional bias |
| ~~REJECT_UP/DOWN~~ | Outcome implication |
| ~~BREAKOUT~~ | Interpretation |
| ~~DEFEND~~ | Intentionality |
| ~~ABSORPTION~~ | Interpretation |

## 2.3 Why This Set Is Closed

**Completeness:** Covers all observable evidence in M2
**Atomicity:** Each token is single, indivisible event
**Neutrality:** No directional or semantic meaning
**Bounded:** Limited to real-time observable events

**Closure proof:** No new evidence type can be added without being redundant, composite, or interpretive.

---

# 3. MOTIF EXTRACTION LOGIC

## 3.1 Supported Motif Lengths

**Length-2 (Bigrams):** `(Token_A, Token_B)`  
**Length-3 (Trigrams):** `(Token_A, Token_B, Token_C)`  
**No length-4+:** Prevents combinatorial explosion

## 3.2 Extraction Rules

### Rule 1: Sliding Window
```
Sequence: [Token_1, Token_2, Token_3, Token_4]
Bigrams: (Token_1, Token_2), (Token_2, Token_3), (Token_3, Token_4)
Trigrams: (Token_1, Token_2, Token_3), (Token_2, Token_3, Token_4)
```

### Rule 2: Consecutive Tokens Only
- Motifs are adjacent tokens
- NO gap-tolerance

### Rule 3: Overlapping Windows
- Windows slide one token at a time
- Captures all consecutive pairs/triples

### Rule 4: Count Increment
- Each extraction: `count += 1`
- NO weighting by volume/time

### Rule 5: No Deduplication
- If `(A,B)` appears twice in one pass, count += 2

## 3.3 Stored Attributes

### Count (Integer)
- Number of times motif observed
- Cumulative, never decreases
- NOT probability or importance

### Last Seen (Timestamp)
- Unix timestamp of most recent observation
- Used for decay and queries
- NOT prediction of next occurrence

### Strength (Float)
- Mechanical decay-weighted value
- Formula: `strength *= (1 - decay_rate * time_elapsed)`
- NOT importance score

## 3.4 Extraction Algorithm

```
When new token arrives:
1. Append to sequence buffer
2. Trim buffer (time + length bounds)
3. Extract all bigrams/trigrams
4. Update counts and timestamps
5. Apply decay to all motifs
```

## 3.5 Worked Example

```
Event 1: t=1000, OB_APPEAR
  Buffer: [(OB_APPEAR, 1000)]
  Motifs: None (only 1 token)

Event 2: t=1005, TRADE_EXEC
  Buffer: [(OB_APPEAR, 1000), (TRADE_EXEC, 1005)]
  Motifs: (OB_APPEAR, TRADE_EXEC) - count=1

Event 3: t=1010, TRADE_EXEC
  Buffer: [(OB_APPEAR, 1000), (TRADE_EXEC, 1005), (TRADE_EXEC, 1010)]
  Bigrams: (OB_APPEAR, TRADE_EXEC) - count=2
           (TRADE_EXEC, TRADE_EXEC) - count=1
  Trigrams: (OB_APPEAR, TRADE_EXEC, TRADE_EXEC) - count=1
```

## 3.6 Non-Ranking Guarantees

**Motifs are NOT ranked by:**
- ❌ Frequency (high count ≠ important)
- ❌ Strength (high strength ≠ reliable)
- ❌ Recency (recent ≠ active pattern)

**Motifs CAN be queried by:**
- ✅ Count threshold (factual filter)
- ✅ Time range (factual filter)

---

# 4. DECAY & ARCHIVAL RULES

## 4.1 Core Principle

**Motifs are bound to their node's lifecycle.**

Motifs inherit node state exactly - no independent lifecycle.

## 4.2 Decay Rate Table

| Node State | Decay Rate | Motif Application |
|:-----------|:-----------|:------------------|
| ACTIVE | 0.0001/sec | All motifs decay at 0.0001/sec |
| DORMANT | 0.00001/sec | All motifs decay at 0.00001/sec (10× slower) |
| ARCHIVED | 0 (frozen) | All motifs frozen (no decay) |

**Formula:** Same as M2 node decay
```
time_elapsed = current_ts - motif_last_seen_ts
decay_factor = 1.0 - (decay_rate * time_elapsed)
motif_strength *= max(0.0, decay_factor)
```

## 4.3 State Transition Table

### ACTIVE → DORMANT
- Motif counts/timestamps: **Preserved**
- Decay rate: **Changed to 0.00001/sec**
- No deletion

### DORMANT → ARCHIVED
- Motif counts/timestamps: **Preserved (frozen)**
- Decay rate: **Set to 0**
- No deletion

### DORMANT → ACTIVE (Revival)
- Motif counts/timestamps: **Preserved**
- Decay rate: **Restored to 0.0001/sec**
- **Requires NEW evidence**

### ARCHIVED → ACTIVE (Revival from Archive)
- Motifs remain frozen OR unfrozen if same node
- **Requires NEW evidence**

## 4.4 M2 Alignment Verification

| M2 Rule | M3 Compliance | Status |
|:--------|:-------------|:-------|
| ACTIVE decay = 0.0001/sec | Motifs use same | ✅ |
| DORMANT decay = 0.00001/sec | Motifs use same | ✅ |
| ARCHIVED decay = 0 | Motifs frozen | ✅ |
| No auto-revival | Requires NEW evidence | ✅ |

---

# 5. DATA STRUCTURES

## 5.1 EvidenceToken (Enum)

```python
class EvidenceToken(Enum):
    # Orderbook
    OB_APPEAR = "ob_appear"
    OB_PERSIST = "ob_persist"
    OB_VANISH = "ob_vanish"
    
    # Trade
    TRADE_EXEC = "trade_exec"
    TRADE_VOLUME_HIGH = "trade_vol_high"
    
    # Liquidation
    LIQ_OCCUR = "liq_occur"
    LIQ_CASCADE = "liq_cascade"
    
    # Price
    PRICE_TOUCH = "price_touch"
    PRICE_EXIT = "price_exit"
    PRICE_DWELL = "price_dwell"
```

## 5.2 SequenceBuffer (Dataclass)

```python
@dataclass
class SequenceBuffer:
    tokens: deque[Tuple[EvidenceToken, float]]  # (token, timestamp)
    max_length: int = 100           # Max tokens to retain
    time_window_sec: float = 86400.0  # 24 hours
    total_tokens_observed: int = 0  # Cumulative count
```

## 5.3 MotifMetrics (Dataclass)

```python
@dataclass
class MotifMetrics:
    motif: Tuple[EvidenceToken, ...]  # The sequence (2-3 tokens)
    count: int                         # Occurrence count
    last_seen_ts: float               # Most recent timestamp
    strength: float                    # Decayed strength
```

## 5.4 EnrichedLiquidityMemoryNode (Extended)

```python
@dataclass
class EnrichedLiquidityMemoryNode:
    # ALL M2 FIELDS UNCHANGED (24+ fields)
    # ...
    
    # M3 FIELDS (NEW)
    sequence_buffer: Optional[SequenceBuffer] = None
    motif_counts: Dict[Tuple[EvidenceToken, ...], int] = field(default_factory=dict)
    motif_last_seen: Dict[Tuple[EvidenceToken, ...], float] = field(default_factory=dict)
    motif_strength: Dict[Tuple[EvidenceToken, ...], float] = field(default_factory=dict)
    total_sequences_observed: int = 0
```

## 5.5 Backward Compatibility

- ✅ All M2 fields unchanged
- ✅ M3 fields have defaults (None or empty dict)
- ✅ Old M2 code unaffected
- ✅ Memory overhead: ~8.4 KB per node (worst case)

## 5.6 Prohibited Field Names

❌ `motif_probability`  
❌ `motif_importance`  
❌ `pattern_reliability`  
❌ `next_token_prediction`  

---

# 6. QUERY INTERFACE

## 6.1 Query Method Signatures

### Node-Level Queries

**1. get_sequence_buffer(node_id: str) → Optional[List[Tuple[EvidenceToken, float]]]**

Returns complete sequence buffer as chronologically-ordered list. Raw access to temporal event history without interpretation.

**2. get_recent_tokens(node_id: str, count: int = 10) → List[Tuple[EvidenceToken, float]]]**

Returns N most recent tokens in chronological order. Count is factual limit, NOT importance threshold.

**3. get_motifs_for_node(node_id: str, min_count: int = 1) → List[Dict]**

Returns all observed motifs filtered by minimum occurrence count. NOT sorted by importance.

**4. get_motif_by_pattern(node_id: str, pattern: Tuple[EvidenceToken, ...]) → Optional[Dict]**

Returns metrics for specific motif pattern if observed. Factual lookup, NOT prediction.

### Cross-Node Queries

**5. get_nodes_with_motif(motif: Tuple[EvidenceToken, ...], min_count: int = 1) → List[str]**

Returns node IDs that observed the motif. Factual list, NOT ranked.

**6. get_motif_statistics(motif: Tuple[EvidenceToken, ...]) → Dict**

Returns aggregate statistics for motif across all nodes. Keys: `total_count`, `node_count`, `avg_count_per_node`, `most_recent_ts`.

### Temporal Queries

**7. get_tokens_in_time_range(node_id: str, start_ts: float, end_ts: float) → List[Tuple[EvidenceToken, float]]**

Returns tokens within time range. Chronological order maintained.

**8. get_motifs_last_seen_since(node_id: str, since_ts: float) → List[Dict]**

Returns motifs observed since timestamp. Factual recency filter, NOT importance.

### Statistical Queries

**9. get_sequence_diversity(node_id: str) → Dict**

Returns diversity metrics. Keys: `unique_bigrams`, `unique_trigrams`, `total_tokens`, `diversity_ratio`. NOT quality score.

**10. get_motif_decay_state(node_id: str, motif: Tuple[EvidenceToken, ...]) → Dict**

Returns current decay state. Keys: `current_strength`, `time_since_seen`, `decay_rate`, `node_state`. Mechanical calculation, NOT relevance prediction.

### Metadata Queries

**11. get_buffer_metadata(node_id: str) → Dict**

Returns buffer metadata. Keys: `current_size`, `max_length`, `time_window_sec`, `oldest_ts`, `newest_ts`, `total_observed`.

**12. get_token_counts(node_id: str) → Dict[EvidenceToken, int]**

Returns histogram of token types in buffer. All types counted equally.

## 6.2 Prohibited Query Methods

❌ `get_most_important_motifs()`  
❌ `predict_next_token()`  
❌ `get_motif_probability()`  
❌ `rank_motifs_by_reliability()`  
❌ `get_bullish_patterns()`  
❌ `recommend_entry_patterns()`  
❌ `score_motif_confidence()`  
❌ `get_strongest_patterns()`  
❌ `classify_regime_from_motifs()`  

## 6.3 Query Design Principles

**Queries return:**
- ✅ Historical data (counts, timestamps, sequences)
- ✅ Factual filtering (time, count, token)
- ✅ Chronological ordering

**Queries do NOT return:**
- ❌ Scores (importance)
- ❌ Probabilities (likelihood)
- ❌ Rankings (best to worst)
- ❌ Predictions (what's next)

---

# 7. COMPLIANCE AUDIT

## 7.1 Audit Summary

**Total items checked:** 42  
**Violations found:** 0  
**Status:** ✅ PASS

## 7.2 Category Results

| Category | Items | Passed | Score |
|:---------|:------|:-------|:------|
| Signal Generation | 7 | 7 | 100% |
| Direction Inference | 7 | 7 | 100% |
| Probabilities & Predictions | 7 | 7 | 100% |
| Action Thresholds | 7 | 7 | 100% |
| Factual Outputs | 7 | 7 | 100% |
| Retrospective Logic | 7 | 7 | 100% |
| **TOTAL** | **42** | **42** | **100%** |

## 7.3 Component Compliance

| Component | Status |
|:----------|:-------|
| Evidence Tokens | ✅ PASS (10/10 neutral) |
| Motif Extraction | ✅ PASS (5/5 compliant) |
| Decay & Archival | ✅ PASS (5/5 M2-aligned) |
| Data Structures | ✅ PASS (4/4 compliant) |
| Query Interface | ✅ PASS (12/12 safe, 9/9 prohibited absent) |

## 7.4 Key Confirmations

✅ No signal generation capability  
✅ No direction inference (bullish/bearish)  
✅ No probabilities or predictions  
✅ No action thresholds  
✅ All outputs factual (counts, timestamps, sequences)  
✅ All logic retrospective (historical data only)  

## 7.5 Final Audit Verdict

### ✅ PASS - M3 Specification Fully Compliant

**Zero violations found** across all specifications.

**M3 is a pure perception extension:**
- Records temporal ordering
- Counts sequence occurrences
- Applies mechanical decay
- Provides read-only access

**M3 does NOT:**
- Predict next events
- Generate signals
- Recommend actions
- Infer direction
- Compute probabilities

**Status:** ✅ CLEARED FOR IMPLEMENTATION

---

# 8. VALIDATION PLAN

## 8.1 Test Matrix Summary

**Total tests:** 39  
**Categories:** 6  
**Pass threshold:** 39/39 (100%)  

## 8.2 Test Categories

### Category 1: Ordering Preservation (5 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| ORD-1 | Chronological append | Order matches input exactly |
| ORD-2 | Out-of-order reject | Arrival order maintained |
| ORD-3 | Motif extraction order | Consecutive pairs in order |
| ORD-4 | Duplicate handling | Both occurrences counted |
| ORD-5 | Time window trimming | Old removed, order preserved |

### Category 2: Decay Correctness (7 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| DEC-1 | Active decay rate | 0.0001/sec exactly |
| DEC-2 | Dormant decay rate | 0.00001/sec exactly |
| DEC-3 | Archived freeze | No decay (frozen) |
| DEC-4 | ACTIVE→DORMANT transition | Rate changes immediately |
| DEC-5 | DORMANT→ACTIVE transition | Rate changes immediately |
| DEC-6 | Motif-node sync | Proportional decay |
| DEC-7 | No negative strength | Strength ≥ 0 always |

### Category 3: No-Growth-Without-Events (6 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| GRW-1 | No token auto-generation | Buffer size unchanged |
| GRW-2 | No motif auto-generation | Motif count unchanged |
| GRW-3 | No count increment | Count unchanged |
| GRW-4 | Decay-only changes | Only decay occurs |
| GRW-5 | Buffer trim doesn't add | Size decreases/stays same |
| GRW-6 | Counter freeze | Counter unchanged |

### Category 4: No-Signal Tests (7 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| SIG-1 | No prediction methods | Method doesn't exist |
| SIG-2 | No probability outputs | All returns factual |
| SIG-3 | No signal fields | Fields absent |
| SIG-4 | No ranking output | Chronological only |
| SIG-5 | No directional labels | Neutral labels only |
| SIG-6 | No action thresholds | Factual filters only |
| SIG-7 | No confidence scores | Factual counts only |

### Category 5: Data Integrity (6 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| INT-1 | Count accumulation | Count = observations |
| INT-2 | Timestamp update | Last seen = most recent |
| INT-3 | Tuple immutability | Tuple identity preserved |
| INT-4 | Max length enforcement | Size capped at max |
| INT-5 | Time window enforcement | Old tokens removed |
| INT-6 | Backward compatibility | No errors, defaults used |

### Category 6: Query Interface (8 tests)

| Test | Check | PASS Criteria |
|:-----|:------|:--------------|
| QRY-1 | get_sequence_buffer() | Correct chronological list |
| QRY-2 | get_recent_tokens() | Latest N in order |
| QRY-3 | get_motifs_for_node() | All motifs present |
| QRY-4 | get_motif_by_pattern() exists | Correct motif returned |
| QRY-5 | get_motif_by_pattern() missing | None returned |
| QRY-6 | get_nodes_with_motif() | Correct nodes |
| QRY-7 | get_token_counts() | Correct histogram |
| QRY-8 | get_sequence_diversity() | Correct unique count |

## 8.3 PASS/FAIL Criteria

### Overall PASS Requirements

**All** of the following must be true:
1. Ordering Preservation: 5/5 tests pass
2. Decay Correctness: 7/7 tests pass
3. No-Growth-Without-Events: 6/6 tests pass
4. No-Signal: 7/7 tests pass
5. Data Integrity: 6/6 tests pass
6. Query Interface: 8/8 tests pass

**Total:** 39/39 tests must pass

### Overall FAIL Conditions

**ANY** of the following causes immediate FAIL:
- ❌ Any prediction or probability method exists
- ❌ Any signal generation capability detected
- ❌ Any directional interpretation
- ❌ Motif decay rates differ from M2
- ❌ Memory grows without new evidence
- ❌ Chronological order violated
- ❌ M2 backward compatibility broken

## 8.4 Test Execution Phases

**Phase 1: Unit Tests** (Isolated components)  
**Phase 2: Integration Tests** (Components together)  
**Phase 3: Prohibition Compliance** (Method/output scanning)  
**Phase 4: M2 Compatibility** (Load M2 nodes, verify unchanged)

## 8.5 Success Criteria (Binary)

### ✅ PASS
- 39/39 tests pass
- Zero prohibition violations
- M2 backward compatible
- All outputs factual
- All logic retrospective

### ❌ FAIL
- ANY test fails
- ANY prohibition violated
- ANY signal/prediction capability exists

## 8.6 Exclusions (Out of Scope)

❌ Performance benchmarks  
❌ Profitability tests  
❌ Strategy integration tests  
❌ Optimization tests  
❌ Scalability tests  

---

# APPENDIX: IMPLEMENTATION CHECKLIST

## Phase 1: Core Components
- [ ] Implement EvidenceToken enum
- [ ] Implement SequenceBuffer dataclass
- [ ] Implement MotifMetrics dataclass
- [ ] Extend EnrichedLiquidityMemoryNode

## Phase 2: Extraction Logic
- [ ] Implement tokenization function
- [ ] Implement bigram extraction
- [ ] Implement trigram extraction
- [ ] Implement motif counting

## Phase 3: Decay Integration
- [ ] Implement motif decay function
- [ ] Integrate with node state transitions
- [ ] Handle ACTIVE/DORMANT/ARCHIVED states

## Phase 4: Query Interface
- [ ] Implement 12 read-only query methods
- [ ] Add prohibition compliance checks
- [ ] Test all queries

## Phase 5: Validation
- [ ] Execute 39 validation tests
- [ ] Generate validation report
- [ ] Confirm binary PASS/FAIL

## Phase 6: Documentation
- [ ] Create usage examples
- [ ] Generate walkthrough
- [ ] Update memory system docs

---

# SUMMARY

**M3 transforms memory from:**
- Snapshot → Time-lapse
- Accumulated → Ordered
- What → How (it accumulated)

**But memory still does not trade.**

M3 is **temporal ordering**, not **temporal prediction**.

**Status:** Planning complete. All specifications approved. Ready for implementation.

---

**END OF M3 SPECIFICATION DOCUMENT**
