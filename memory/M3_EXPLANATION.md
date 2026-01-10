# Temporal Evidence Ordering Memory (M3) — Conceptual Explanation

## What M3 IS

### Core Concept

M3 extends M2 memory by preserving the **chronological order** in which evidence events occurred at each price level. Where M2 records "what happened" (counts, volumes, liquidations), M3 records "**in what order** it happened."

Think of it as the difference between:
- **M2:** A photograph showing current accumulated evidence
- **M3:** A time-lapse video showing how that evidence accumulated over time

### Information Preserved

**1. Event Sequence (Ordering)**
- The exact chronological order of events at each price node
- Example: At $2.10, we observed:
  1. `OB_APPEAR` (orderbook level appeared)
  2. `TRADE_BUY` (buyer-initiated trade)
  3. `TRADE_BUY` (another buyer-initiated trade)
  4. `LIQ_LONG` (long liquidation)
  5. `OB_DISAPPEAR` (orderbook level disappeared)

This sequence is **factual history**, not a pattern to predict from.

**2. Temporal Patterns (Motifs)**
- Consecutive event pairs (bigrams): `(OB_APPEAR, TRADE_BUY)`
- Consecutive event triples (trigrams): `(TRADE_BUY, TRADE_BUY, LIQ_LONG)`
- Counts: How many times each sequence occurred
- Last seen: When each sequence last occurred

These are **historical facts** about what sequences happened, not predictions about what sequences will happen next.

**3. Bounded Historical Window**
- Recent 100 events (configurable)
- Last 24 hours of activity
- Older events fall off the window

This prevents unbounded memory growth while retaining recent processual context.

### Information Intentionally Destroyed

**1. Statistical Inference**
- NO probabilities ("60% chance next event is X")
- NO likelihood scores ("how likely is this sequence?")
- NO confidence intervals

**2. Semantic Interpretation**
- NO pattern labeling ("this is a breakout pattern")
- NO bullish/bearish classification
- NO support/resistance semantics

**3. Predictive Information**
- NO "next event" predictions
- NO sequence completion
- NO forward inference of any kind

**4. Importance Ranking**
- NO "most important patterns"
- NO motif scoring
- NO threshold-based filtering for action

**5. Old Sequential Context Beyond Window**
- Events older than 24 hours are dropped
- Sequences beyond the 100-event buffer are forgotten
- This is **intentional** - we preserve recent process, not infinite history

---

## What M3 IS NOT

### NOT a Prediction Engine

M3 does **NOT** answer:
- "What will happen next?"
- "How likely is this to reverse?"
- "Should I enter a trade here?"

It **ONLY** records what sequences occurred historically.

### NOT a Pattern Recognition System

M3 does **NOT**:
- Identify "bullish patterns" or "bearish patterns"
- Label motifs as "reliable" or "unreliable"
- Score patterns by "importance"
- Classify market behavior

It **ONLY** counts how many times sequences occurred.

### NOT a Signal Generator

M3 does **NOT**:
- Generate buy/sell signals
- Trigger strategy entries
- Recommend actions based on sequences

Strategies may **consume** M3 data, but M3 itself generates **nothing actionable**.

### NOT a Regime Classifier

M3 does **NOT**:
- Infer "trending" vs "ranging" from sequences
- Detect state changes from patterns
- Classify market conditions

It **ONLY** records the sequence of events that occurred.

---

## How M3 Complements M2 (Without Modifying It)

### M2 Provides: Accumulated Evidence Snapshot

M2 records **what** evidence exists at a price level:
- Total interactions: 47
- Total volume: $120,000
- Liquidations: 8 (5 long, 3 short)
- Buyer volume: $75,000
- Seller volume: $45,000

**M2 tells you:** "This level has significant accumulated evidence."

### M3 Adds: How That Evidence Accumulated

M3 records **in what order** that evidence arrived:
- Sequence: `[OB_APPEAR, TRADE_BUY, TRADE_BUY, LIQ_LONG, TRADE_SELL, ...]`
- Motif counts: `(TRADE_BUY, TRADE_BUY)` occurred 12 times
- Motif counts: `(LIQ_LONG, TRADE_SELL)` occurred 3 times

**M3 tells you:** "This level's evidence accumulated in these temporal sequences."

### Integration Without Modification

**M2 remains unchanged:**
- M2 nodes still have all their M2 fields
- M2 decay logic unchanged
- M2 state transitions unchanged
- M2 topology/pressure metrics unchanged

**M3 extends nodes with new fields:**
- `sequence_buffer` - rolling window of recent events
- `motif_counts` - counts of observed sequences
- `motif_last_seen` - timestamps of last occurrence
- `motif_strength` - decay-weighted sequence strength

**M3 follows M2 lifecycle:**
- Motifs decay at the same rate as the node
- ACTIVE node motifs decay at ACTIVE_DECAY_RATE
- DORMANT node motifs decay at DORMANT_DECAY_RATE (10× slower)
- ARCHIVED node motifs are frozen
- Motif revival follows node revival rules

### Complementary Perspective

**M2 answers:** "What evidence exists?"  
**M3 answers:** "In what order did it arrive?"

**M2 is spatial:** Evidence distribution across price levels  
**M3 is temporal:** Evidence ordering within each price level

**Together they provide:**
- **WHERE** evidence is concentrated (M2 topology/pressure)
- **WHAT** evidence exists (M2 enriched fields)
- **WHEN** evidence arrived (M2 timestamps)
- **HOW** evidence accumulated (M3 sequences) ← NEW

---

## Strict Prohibitions Confirmed

### NO Prediction
- M3 does NOT predict the next token in a sequence
- M3 does NOT complete partial sequences
- M3 does NOT forecast future patterns

**Example of what M3 will NOT do:**
```
✗ "After (TRADE_BUY, TRADE_BUY), there's a 70% chance of LIQ_LONG"
✓ "(TRADE_BUY, TRADE_BUY, LIQ_LONG) has occurred 3 times"
```

### NO Signal Generation
- M3 does NOT generate buy/sell signals
- M3 does NOT recommend entries/exits
- M3 does NOT trigger strategy actions

**Example of what M3 will NOT do:**
```
✗ "Sequence (LIQ_LONG, TRADE_SELL) detected → SELL signal"
✓ "Sequence (LIQ_LONG, TRADE_SELL) count: 5"
```

### NO Regime Inference
- M3 does NOT classify sequences as "trending" or "ranging"
- M3 does NOT infer market state from patterns
- M3 does NOT map motifs to market conditions

**Example of what M3 will NOT do:**
```
✗ "High (TRADE_BUY, TRADE_BUY) count → trending market"
✓ "(TRADE_BUY, TRADE_BUY) count: 23"
```

---

## Design Principles

### 1. Tokens Are Neutral Labels

Evidence tokens (e.g., `TRADE_BUY`, `LIQ_LONG`) are **factual event types**, not semantic interpretations.

- `TRADE_BUY` means "a buyer-initiated trade occurred" (factual)
- NOT "bullish pressure" (interpretive)

### 2. Motifs Are Historical Counts

Motifs are **counts of how many times a sequence occurred**, not predictive patterns.

- `(TRADE_BUY, TRADE_BUY)` count = 12 means "this sequence happened 12 times"
- NOT "this is a reliable bullish pattern" (interpretive)

### 3. Sequences Are Ordered Facts

The sequence buffer records **the order in which events happened**, not the order we think they "should" happen.

- No reordering by "importance"
- No filtering by "relevance"
- Chronological order only

### 4. Memory Follows M2 Lifecycle

Motifs are **attached to nodes** and follow the node's lifecycle exactly:

- When a node becomes DORMANT, its motifs decay 10× slower
- When a node is ARCHIVED, its motifs are frozen
- When a node is revived, its motifs are restored with historical context
- Motifs never auto-generate or self-propagate

---

## Use Case: What Can Strategies Do With M3?

While M3 itself generates no signals, strategies MAY:

1. **Query historical sequences** to understand recent process
   - "What sequences occurred at this level in the last 24 hours?"
   - NOT: "What sequence will occur next?"

2. **Check if a specific sequence has occurred before**
   - "Has (LIQ_LONG, TRADE_SELL) occurred at this node?"
   - NOT: "Is (LIQ_LONG, TRADE_SELL) a reliable pattern?"

3. **Compare sequence diversity across nodes**
   - "Node A has 5 unique motifs, Node B has 15"
   - NOT: "Node B is more important because it has more motifs"

**Critical:** Strategies interpret M3 data. M3 does NOT interpret itself.

---

## Summary

**M3 is:**
- A factual recording of event order
- A historical sequence buffer per node
- A count-based motif tracker
- Decay-consistent with M2 lifecycle
- Purely observational

**M3 is NOT:**
- A prediction engine
- A pattern recognition system
- A signal generator
- A regime classifier
- A trading strategy

**M3 transforms memory from:**
- Snapshot → Time-lapse
- Accumulated → Ordered
- What → How (it accumulated)

**But memory still does not trade.**

M3 is **temporal ordering**, not **temporal prediction**.

---

**Awaiting explicit PASS to proceed with implementation.**
