PHASE M3 — TEMPORAL EVIDENCE ORDERING MEMORY
Objective

Increase memory information density by preserving historical ordering of evidence events at each price node, without introducing signals, predictions, or strategy logic.

M3.1 Core Components
1. Evidence Tokenizer

Maps raw events → neutral tokens

Deterministic, rule-based

Stateless

2. Per-Node Sequence Buffer

Rolling window (time-bounded)

Ordered list of tokens

Max length capped

3. Motif Extractor

Extracts bigrams/trigrams

Updates counts and decay

No interpretation

4. Motif Store

Attached to node

Decays with node state

Archived with node

M3.2 Data Stored (Per Node)

Additional fields (illustrative):

motif_counts: Dict[Tuple[token], count]

motif_last_seen: Dict[Tuple[token], timestamp]

motif_strength: Dict[Tuple[token], float]

sequence_window_size

total_sequences_observed

No probabilities. No classifications.

M3.3 Decay Rules

Motifs decay at same rate as node

Dormant motifs decay 10× slower

Archived motifs frozen

No spontaneous revival.

M3.4 Prohibitions (Explicit)

M3 MUST NOT:

Predict next event

Score likelihoods

Rank motifs by “importance”

Convert motifs into signals

Label motifs as bullish/bearish

M3.5 Validation Criteria

To pass M3:

Ordering information preserved

No forward inference possible

Memory size bounded

Decay & archival consistent with M2

Zero signal logic confirmed

5. Why M3 Is the Correct Next Step (and Not a Strategy)

You paused strategies for the right reason.

M3 gives you:

Process memory

Structural narrative

Historical causality (not prediction)

It turns memory from a map into a history book.

Strategies still decide what matters.

Final Summary

M3 is about ordering, not outcomes

It captures how markets behave, not how to trade them

It strictly extends perception, not action

It preserves falsifiability and auditability