# M3 Motif Extraction Logic (Non-Interpretive)

## Overview

Motif extraction is the **purely mechanical** process of identifying consecutive token sequences in the sequence buffer and maintaining factual counts. Motifs are **NOT** ranked, scored, or used for prediction.

---

## Supported Motif Lengths

**Length-2 (Bigrams):**
- Two consecutive tokens: `(Token_A, Token_B)`
- Example: `(OB_APPEAR, TRADE_EXEC)`

**Length-3 (Trigrams):**
- Three consecutive tokens: `(Token_A, Token_B, Token_C)`
- Example: `(OB_APPEAR, TRADE_EXEC, PRICE_TOUCH)`

**Why only 2 and 3:**
- Longer sequences (4+) explode combinatorially
- Most temporal patterns observable in short windows
- Bounded memory requirement

**No higher-order motifs:** M3 stops at trigrams to prevent unbounded growth.

---

## Extraction Rules (Step-by-Step)

### Rule 1: Sliding Window Extraction

Given a sequence buffer: `[Token_1, Token_2, Token_3, Token_4, Token_5]`

**Bigram extraction:**
```
Window position 1: (Token_1, Token_2)
Window position 2: (Token_2, Token_3)
Window position 3: (Token_3, Token_4)
Window position 4: (Token_4, Token_5)
```

**Trigram extraction:**
```
Window position 1: (Token_1, Token_2, Token_3)
Window position 2: (Token_2, Token_3, Token_4)
Window position 3: (Token_3, Token_4, Token_5)
```

**Critical:** Extraction is **chronological order only**. No reordering by frequency or "importance".

### Rule 2: Consecutive Tokens Only

Motifs are **adjacent** tokens only:
- ✅ `(OB_APPEAR, TRADE_EXEC)` if they occurred consecutively
- ❌ NOT `(OB_APPEAR, TRADE_EXEC)` if separated by other tokens

**No gap-tolerance:** Motifs require strict temporal adjacency.

### Rule 3: Overlapping Windows

Windows **overlap** when sliding:
- Sequence: `[A, B, C]`
- Bigrams: `(A, B)` and `(B, C)` ← B appears in both
- This is **intentional** - captures all consecutive pairs

### Rule 4: Count Increment

When a motif is extracted:
1. Check if motif already exists in `motif_counts`
2. If exists: `count += 1`
3. If new: `count = 1`
4. Update `last_seen_ts = current_timestamp`

**No weighting:** All occurrences count equally (1, not weighted by volume/time).

### Rule 5: No Deduplication Within Sequence

If the same motif appears multiple times in one extraction pass:
- Sequence: `[A, B, A, B]`
- Bigrams: `(A, B)`, `(B, A)`, `(A, B)` ← `(A, B)` extracted twice
- Both count: `motif_counts[(A, B)] += 2`

**Rationale:** Reflects actual occurrence frequency.

---

## Update Logic

### When to Extract Motifs

**Trigger:** New token appended to sequence buffer

**Process:**
1. Append new token to buffer
2. Extract motifs from **full buffer** (not just new token)
3. Update counts for all extracted motifs
4. Apply decay to all existing motifs

**Frequency:** After every token append (real-time).

### Extraction Algorithm (Pseudocode)

```
function extract_and_update_motifs(sequence_buffer, new_token, timestamp):
    # Step 1: Append new token
    sequence_buffer.append((new_token, timestamp))
    
    # Step 2: Trim buffer (enforce time + length bounds)
    sequence_buffer.trim_old(timestamp)
    sequence_buffer.enforce_max_length()
    
    # Step 3: Extract motifs from full buffer
    tokens = [token for (token, ts) in sequence_buffer]
    
    bigrams = extract_bigrams(tokens)
    trigrams = extract_trigrams(tokens)
    
    # Step 4: Update counts
    for motif in bigrams + trigrams:
        if motif in motif_counts:
            motif_counts[motif] += 1
        else:
            motif_counts[motif] = 1
        
        motif_last_seen[motif] = timestamp
    
    # Step 5: Apply decay to all motifs
    apply_motif_decay(current_time=timestamp)
```

### Decay Update (Separate from Extraction)

Motif decay happens:
1. **After extraction** (same as node decay timing)
2. **Mechanical formula:** `strength *= (1 - decay_rate * time_elapsed)`
3. **Same rate as node:** ACTIVE nodes → 0.0001/sec, DORMANT → 0.00001/sec

**No selective decay:** All motifs decay uniformly.

---

## Stored Attributes (Per Motif)

**Data structure:**
```python
motif_counts: Dict[Tuple[Token, ...], int]
motif_last_seen: Dict[Tuple[Token, ...], float]
motif_strength: Dict[Tuple[Token, ...], float]
```

### Attribute 1: Count (Integer)

**What it is:** Number of times this motif has been observed

**Update rule:**
- Initialized to `1` when first observed
- Incremented by `1` each time motif extracted
- **Never decreases** (count is cumulative)

**NOT:**
- ❌ Probability
- ❌ Importance score
- ❌ Confidence measure

### Attribute 2: Last Seen (Timestamp)

**What it is:** Unix timestamp of most recent observation

**Update rule:**
- Set to current time whenever motif extracted
- Used for decay calculation
- Used for recency queries (factual)

**NOT:**
- ❌ Prediction of next occurrence
- ❌ Expected time to next event

### Attribute 3: Decayed Strength (Float)

**What it is:** Mechanical decay-weighted strength

**Initial value:** `count * 0.1` (arbitrary but deterministic)

**Update rule:**
```python
time_elapsed = current_ts - last_seen_ts
decay_factor = 1.0 - (decay_rate * time_elapsed)
strength *= max(0.0, decay_factor)
```

**Decay rate:**
- ACTIVE node: `decay_rate = 0.0001/sec`
- DORMANT node: `decay_rate = 0.00001/sec` (10× slower)
- ARCHIVED node: `decay_rate = 0` (frozen)

**NOT:**
- ❌ Reliability score
- ❌ Importance weight
- ❌ Probability multiplier

**Purpose:** Strength provides temporal relevance weighting (recent motifs have higher strength) WITHOUT introducing importance ranking.

---

## Explicit Non-Ranking Guarantees

### Motifs Are NOT Ranked By:

❌ **Frequency** - High count does NOT mean "important"  
❌ **Strength** - High strength does NOT mean "reliable"  
❌ **Recency** - Recent does NOT mean "active pattern"  
❌ **Length** - Trigrams are NOT "better" than bigrams  

### Motifs CAN Be Queried By:

✅ **Count threshold** - "Motifs with count ≥ N" (factual filter)  
✅ **Strength threshold** - "Motifs with strength ≥ X" (factual filter)  
✅ **Recency** - "Motifs last seen within T seconds" (factual filter)  

**Critical distinction:** Filtering by thresholds is factual. Ranking by "importance" is interpretive.

---

## Non-Predictive Guarantee

### Motifs Do NOT:

❌ Predict next token  
❌ Complete partial sequences  
❌ Generate probabilities  
❌ Recommend actions  
❌ Score pattern reliability  

### Motifs ONLY:

✅ Record what sequences occurred  
✅ Count how many times they occurred  
✅ Track when they last occurred  
✅ Decay over time mechanically  

---

## Worked Example

### Scenario

**Node:** `level_2.10` at price $2.10

**Sequence buffer (initially empty):**
```
[]
```

**Token sequence arrives over time:**
```
t=1000: OB_APPEAR
t=1005: TRADE_EXEC
t=1010: TRADE_EXEC
t=1015: LIQ_OCCUR
t=1020: PRICE_EXIT
```

### Step-by-Step Extraction

#### Event 1: t=1000, Token=OB_APPEAR

**Buffer after append:**
```
[(OB_APPEAR, 1000)]
```

**Motifs extracted:**
- Bigrams: None (only 1 token)
- Trigrams: None

**Motif state:**
```
motif_counts = {}
motif_last_seen = {}
motif_strength = {}
```

---

#### Event 2: t=1005, Token=TRADE_EXEC

**Buffer after append:**
```
[(OB_APPEAR, 1000), (TRADE_EXEC, 1005)]
```

**Motifs extracted:**
- Bigrams: `(OB_APPEAR, TRADE_EXEC)`
- Trigrams: None (only 2 tokens)

**Motif updates:**
```
motif_counts[(OB_APPEAR, TRADE_EXEC)] = 1
motif_last_seen[(OB_APPEAR, TRADE_EXEC)] = 1005
motif_strength[(OB_APPEAR, TRADE_EXEC)] = 0.1  # Initial: count * 0.1
```

**Decay applied:** None (no motifs existed before)

---

#### Event 3: t=1010, Token=TRADE_EXEC

**Buffer after append:**
```
[(OB_APPEAR, 1000), (TRADE_EXEC, 1005), (TRADE_EXEC, 1010)]
```

**Motifs extracted:**
- Bigrams: `(OB_APPEAR, TRADE_EXEC)`, `(TRADE_EXEC, TRADE_EXEC)`
- Trigrams: `(OB_APPEAR, TRADE_EXEC, TRADE_EXEC)`

**Motif updates:**

**Bigram `(OB_APPEAR, TRADE_EXEC)`:**
- Already exists, increment count
- `count = 1 → 2`
- `last_seen = 1010`

**Bigram `(TRADE_EXEC, TRADE_EXEC)`:**
- New motif
- `count = 1`
- `last_seen = 1010`
- `strength = 0.1`

**Trigram `(OB_APPEAR, TRADE_EXEC, TRADE_EXEC)`:**
- New motif
- `count = 1`
- `last_seen = 1010`
- `strength = 0.1`

**Decay applied (to existing motifs):**
```
# Motif (OB_APPEAR, TRADE_EXEC) existed since t=1005
time_elapsed = 1010 - 1005 = 5 seconds
decay_factor = 1.0 - (0.0001 * 5) = 0.9995
strength = 0.1 * 0.9995 = 0.09995
```

**Final state:**
```
motif_counts = {
    (OB_APPEAR, TRADE_EXEC): 2,
    (TRADE_EXEC, TRADE_EXEC): 1,
    (OB_APPEAR, TRADE_EXEC, TRADE_EXEC): 1
}

motif_last_seen = {
    (OB_APPEAR, TRADE_EXEC): 1010,
    (TRADE_EXEC, TRADE_EXEC): 1010,
    (OB_APPEAR, TRADE_EXEC, TRADE_EXEC): 1010
}

motif_strength = {
    (OB_APPEAR, TRADE_EXEC): 0.09995,
    (TRADE_EXEC, TRADE_EXEC): 0.1,
    (OB_APPEAR, TRADE_EXEC, TRADE_EXEC): 0.1
}
```

---

#### Event 4: t=1015, Token=LIQ_OCCUR

**Buffer after append:**
```
[(OB_APPEAR, 1000), (TRADE_EXEC, 1005), (TRADE_EXEC, 1010), (LIQ_OCCUR, 1015)]
```

**Motifs extracted:**
- Bigrams: `(OB_APPEAR, TRADE_EXEC)`, `(TRADE_EXEC, TRADE_EXEC)`, `(TRADE_EXEC, LIQ_OCCUR)`
- Trigrams: `(OB_APPEAR, TRADE_EXEC, TRADE_EXEC)`, `(TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR)`

**New motifs:**
- `(TRADE_EXEC, LIQ_OCCUR)` - bigram
- `(TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR)` - trigram

**Incremented motifs:**
- `(OB_APPEAR, TRADE_EXEC)` - now count=3
- `(TRADE_EXEC, TRADE_EXEC)` - now count=2
- `(OB_APPEAR, TRADE_EXEC, TRADE_EXEC)` - now count=2

**Decay applied:** All existing motifs decay based on `time_elapsed = 1015 - last_seen`

---

#### Event 5: t=1020, Token=PRICE_EXIT

**Buffer after append:**
```
[(OB_APPEAR, 1000), (TRADE_EXEC, 1005), (TRADE_EXEC, 1010), (LIQ_OCCUR, 1015), (PRICE_EXIT, 1020)]
```

**Motifs extracted:**
- Bigrams: `(OB_APPEAR, TRADE_EXEC)`, `(TRADE_EXEC, TRADE_EXEC)`, `(TRADE_EXEC, LIQ_OCCUR)`, `(LIQ_OCCUR, PRICE_EXIT)`
- Trigrams: `(OB_APPEAR, TRADE_EXEC, TRADE_EXEC)`, `(TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR)`, `(TRADE_EXEC, LIQ_OCCUR, PRICE_EXIT)`

**Final motif counts:**
```
Bigrams:
  (OB_APPEAR, TRADE_EXEC): 4 times
  (TRADE_EXEC, TRADE_EXEC): 3 times
  (TRADE_EXEC, LIQ_OCCUR): 2 times
  (LIQ_OCCUR, PRICE_EXIT): 1 time

Trigrams:
  (OB_APPEAR, TRADE_EXEC, TRADE_EXEC): 3 times
  (TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR): 2 times
  (TRADE_EXEC, LIQ_OCCUR, PRICE_EXIT): 1 time
```

---

### Example Interpretation (What This IS and IS NOT)

**What we can factually say:**
- ✅ "The sequence (OB_APPEAR, TRADE_EXEC) occurred 4 times"
- ✅ "The trigram (TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR) was observed twice"
- ✅ "The most recent motif was (LIQ_OCCUR, PRICE_EXIT) at t=1020"

**What we CANNOT say:**
- ❌ "(OB_APPEAR, TRADE_EXEC) is a reliable pattern"
- ❌ "After TRADE_EXEC, there's a high chance of LIQ_OCCUR"
- ❌ "(TRADE_EXEC, TRADE_EXEC, LIQ_OCCUR) predicts price movement"
- ❌ "This node has bullish sequences"

---

## Summary

**Motif extraction is:**
- ✅ Mechanical sliding window over sequence buffer
- ✅ Factual counting of consecutive tokens
- ✅ Decay-weighted strength (temporal relevance)
- ✅ Bounded to bigrams and trigrams

**Motif extraction is NOT:**
- ❌ Pattern recognition
- ❌ Probability modeling
- ❌ Importance ranking
- ❌ Predictive inference

**Motifs are historical facts, not predictive patterns.**

**Awaiting PASS to proceed.**
