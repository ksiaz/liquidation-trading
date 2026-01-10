# M3 Validation Plan

## Overview

This validation plan defines tests to verify M3 temporal evidence ordering implementation correctness. Tests focus on **functional correctness and prohibition compliance**, NOT performance or profitability.

---

## Test Matrix

### Category 1: Ordering Preservation Tests

**Purpose:** Verify temporal ordering is maintained correctly.

| Test ID | Test Name | Input | Expected Output | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **ORD-1** | Chronological Append | Tokens: [A@t1, B@t2, C@t3] | Buffer: [(A,t1), (B,t2), (C,t3)] | Order matches input exactly | Any reordering detected |
| **ORD-2** | Out-of-Order Reject | Tokens: [A@t3, B@t1, C@t2] | Buffer maintains arrival order | Tokens stored in arrival order (3,1,2) | Tokens auto-sorted by timestamp |
| **ORD-3** | Motif Extraction Order | Buffer: [A, B, C, D] | Bigrams: [(A,B), (B,C), (C,D)] | Consecutive pairs extracted in order | Pairs skip tokens or reorder |
| **ORD-4** | Duplicate Token Handling | Tokens: [A, B, A, B] | Bigrams: [(A,B), (B,A), (A,B)] | Both (A,B) occurrences counted | Deduplication occurs |
| **ORD-5** | Time Window Trimming | 150 tokens over 48hrs, window=24hr | Only tokens from last 24hrs retained | Old tokens removed, order preserved | Tokens reordered during trim |

**Expected Outcomes:**
- Buffer maintains **strict chronological order** of appends
- Motif extraction follows **sliding window** without gaps
- No automatic sorting by timestamp, frequency, or importance
- Time-based trimming removes old tokens **without reordering**

---

### Category 2: Decay Correctness Tests

**Purpose:** Verify M3 motif decay aligns exactly with M2 node decay.

| Test ID | Test Name | Input | Expected Output | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **DEC-1** | Active Decay Rate | Node ACTIVE, motif strength=1.0, Δt=1000s | strength = 0.9 | Decay rate = 0.0001/sec exactly | Any other decay rate |
| **DEC-2** | Dormant Decay Rate | Node DORMANT, motif strength=1.0, Δt=1000s | strength = 0.99 | Decay rate = 0.00001/sec exactly | Any other decay rate |
| **DEC-3** | Archived Freeze | Node ARCHIVED, motif strength=0.5, Δt=10000s | strength = 0.5 | No decay (frozen) | Any strength change |
| **DEC-4** | State Transition ACTIVE→DORMANT | Node→DORMANT, motif strength=0.5 | Motif decay rate changes to 0.00001/sec | Decay rate changes immediately | Decay rate unchanged |
| **DEC-5** | State Transition DORMANT→ACTIVE | Node→ACTIVE, motif strength=0.3 | Motif decay rate changes to 0.0001/sec | Decay rate changes immediately | Decay rate unchanged |
| **DEC-6** | Motif-Node Decay Sync | Node strength & motif strength both 1.0, Δt=5000s | Both decay proportionally | Ratio stays constant | Motif/node ratios diverge |
| **DEC-7** | No Negative Strength | Motif strength=0.01, decay for 200s | strength = 0.0 (floored) | Strength ≥ 0 always | Negative strength |

**Expected Outcomes:**
- Motif decay uses **exact same rates** as M2 (0.0001, 0.00001, 0)
- State transitions **immediately** update motif decay rates
- Decay formula: `strength *= max(0.0, 1 - rate * Δt)`
- Archived motifs **completely frozen**, no decay

---

### Category 3: No-Growth-Without-Events Tests

**Purpose:** Verify memory does not grow without new evidence.

| Test ID | Test Name | Input | Expected Output | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **GRW-1** | No Token Auto-Generation | No new evidence for 10000s | Buffer size unchanged | Buffer size constant | Buffer size increases |
| **GRW-2** | No Motif Auto-Generation | No new evidence for 10000s | Motif count unchanged | Motif count constant | New motifs appear |
| **GRW-3** | No Count Increment Without Observation | Motif (A,B) count=5, no new evidence | count remains 5 | Count unchanged | Count increases |
| **GRW-4** | Decay-Only Changes | No new evidence, only time passes | Strengths decrease or stay 0 | Only decay occurs | Counts/timestamps change |
| **GRW-5** | Buffer Trim Does Not Add | Buffer at capacity, old tokens expire | Tokens removed, none added | Size decreases or stays same | Size increases |
| **GRW-6** | Total Observed Counter | total_sequences_observed=100, no new evidence | Remains 100 | Counter unchanged | Counter increases |

**Expected Outcomes:**
- Zero growth in counts, buffer size, or motifs **without new tokens**
- Only decay can reduce strengths
- Trimming removes old data, never adds
- All counters frozen without new evidence

---

### Category 4: No-Signal Tests

**Purpose:** Verify M3 produces zero signals, predictions, or interpretations.

| Test ID | Test Name | Check | Expected Absence | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **SIG-1** | No Prediction Methods | Scan all methods | `predict_next_token()` absent | Method does not exist | Method exists |
| **SIG-2** | No Probability Outputs | Check all return types | No probability fields | All returns factual | Any P(x) outputs |
| **SIG-3** | No Signal Fields | Check node/motif structures | No `signal`, `action`, `recommendation` | Fields absent | Any signal fields |
| **SIG-4** | No Ranking Output | Check query results | Results not sorted by importance | Chronological/alphabetical only | Sorted by strength/count |
| **SIG-5** | No Directional Labels | Check all tokens/outputs | No bullish/bearish/support/resistance | Neutral labels only | Directional terms found |
| **SIG-6** | No Action Thresholds | Check all logic | No "if count > N then BUY" | Thresholds are factual filters | Action thresholds exist |
| **SIG-7** | No Confidence Scores | Check all metrics | No reliability/confidence fields | Factual counts only | Confidence metrics exist |

**Expected Outcomes:**
- **Zero methods** that predict, recommend, or signal
- **Zero outputs** containing probabilities or confidence
- **Zero fields** with interpretive names (importance, reliability)
- All thresholds are **factual filters** (min_count, time_window)

---

### Category 5: Data Integrity Tests

**Purpose:** Verify data structures maintain integrity.

| Test ID | Test Name | Input | Expected Output | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **INT-1** | Motif Count Accumulation | Observe (A,B) 3 times | count = 3 | Count equals observations | Count ≠ observations |
| **INT-2** | Last Seen Timestamp Update | Observe (A,B) at t=100, t=200 | last_seen = 200 | Last seen = most recent | Incorrect timestamp |
| **INT-3** | Motif Tuple Immutability | Create motif (A,B,C) | Tuple unchanged throughout | Tuple identity preserved | Tuple mutated |
| **INT-4** | Buffer Max Length Enforcement | Append 150 tokens, max=100 | Buffer size = 100 | Size capped at max | Size exceeds max |
| **INT-5** | Time Window Enforcement | Tokens at t=1000, t=50000, window=24hr | Only t=50000 retained (if current t=51000) | Old tokens removed | Old tokens retained |
| **INT-6** | Backward Compatibility | M2 node loaded | M3 fields initialized to defaults | No errors, defaults used | Errors or missing fields |

**Expected Outcomes:**
- Counts **exactly match** observed occurrences
- Timestamps **accurately track** last observation time
- Buffer bounds **strictly enforced** (length + time)
- M2 nodes work **without modification**

---

### Category 6: Query Interface Tests

**Purpose:** Verify queries return correct historical data.

| Test ID | Test Name | Input | Expected Output | PASS Criteria | FAIL Criteria |
|:--------|:----------|:------|:----------------|:--------------|:--------------|
| **QRY-1** | get_sequence_buffer() | Node with 5 tokens | Returns list of 5 (token, ts) tuples | Correct chronological list | Wrong order/count |
| **QRY-2** | get_recent_tokens(n=3) | Node with 10 tokens | Returns 3 most recent | Latest 3 in order | Wrong tokens |
| **QRY-3** | get_motifs_for_node() | Node with 4 motifs | Returns list of 4 dicts | All motifs present | Missing motifs |
| **QRY-4** | get_motif_by_pattern() | Pattern that exists | Returns dict with metrics | Correct motif returned | Wrong/no motif |
| **QRY-5** | get_motif_by_pattern() | Pattern never observed | Returns None | None returned | Invents data |
| **QRY-6** | get_nodes_with_motif() | Motif in 3 nodes | Returns 3 node IDs | Correct nodes | Wrong nodes |
| **QRY-7** | get_token_counts() | Buffer: [A,A,B,C,A] | {A:3, B:1, C:1} | Correct histogram | Wrong counts |
| **QRY-8** | get_sequence_diversity() | 10 unique bigrams, 50 total tokens | unique_bigrams=10 | Correct unique count | Wrong count |

**Expected Outcomes:**
- Queries return **factual historical data**
- No queries generate predictions or recommendations
- Missing data returns **None or empty list**, not errors
- All queries **read-only**, no mutations

---

## PASS/FAIL Criteria Summary

### Overall PASS Requirements

**All** of the following must be true:

1. **Ordering Preservation (ORD-1 to ORD-5):** 5/5 tests pass
   - Chronological order maintained
   - Motifs extracted consecutively
   - No auto-sorting or reordering

2. **Decay Correctness (DEC-1 to DEC-7):** 7/7 tests pass
   - Decay rates exactly match M2
   - State transitions update rates immediately
   - Archived motifs frozen

3. **No-Growth-Without-Events (GRW-1 to GRW-6):** 6/6 tests pass
   - Zero growth without new tokens
   - Only decay changes strengths
   - Counters frozen without evidence

4. **No-Signal (SIG-1 to SIG-7):** 7/7 tests pass
   - Zero prediction methods
   - Zero probability outputs
   - Zero directional labels
   - All thresholds factual

5. **Data Integrity (INT-1 to INT-6):** 6/6 tests pass
   - Counts accurate
   - Bounds enforced
   - M2 compatibility maintained

6. **Query Interface (QRY-1 to QRY-8):** 8/8 tests pass
   - Correct historical data returned
   - No predictions generated
   - Read-only operation

**Total:** 39/39 tests must pass

### Overall FAIL Conditions

**ANY** of the following causes immediate FAIL:

- ❌ Any prediction or probability method exists
- ❌ Any signal generation capability detected
- ❌ Any directional interpretation (bullish/bearish)
- ❌ Motif decay rates differ from M2 node rates
- ❌ Memory grows without new evidence
- ❌ Chronological order violated
- ❌ M2 backward compatibility broken

---

## Test Execution Plan

### Phase 1: Unit Tests (Isolated Components)

**Execute:**
1. Token enum definition tests
2. Sequence buffer tests (append, trim, bounds)
3. Motif extraction tests (sliding window, counts)
4. Decay formula tests (all 3 rates)

**Criteria:** All components pass individually before integration.

### Phase 2: Integration Tests

**Execute:**
1. Node + motif lifecycle (ACTIVE → DORMANT → ARCHIVED)
2. Query interface with real motifs
3. Cross-node motif queries
4. State transition cascades

**Criteria:** Components work together correctly.

### Phase 3: Prohibition Compliance Tests

**Execute:**
1. Method scanning (no predict/signal methods)
2. Output scanning (no probabilities)
3. Field name scanning (no interpretive labels)
4. Logic audit (no forward inference)

**Criteria:** Zero violations of prohibitions.

### Phase 4: M2 Compatibility Tests

**Execute:**
1. Load existing M2 nodes
2. Add M3 fields with defaults
3. Verify M2 queries still work
4. Verify M2 decay still works

**Criteria:** M2 functionality unaffected.

---

## Validation Report Format

### Required Sections

1. **Test Summary Table**
   - Test ID, Status (PASS/FAIL), Notes

2. **Category Scores**
   - Ordering: X/5
   - Decay: X/7
   - No-Growth: X/6
   - No-Signal: X/7
   - Integrity: X/6
   - Queries: X/8

3. **Failure Details** (if any)
   - Which test failed
   - Expected vs actual output
   - Root cause analysis

4. **Prohibition Compliance**
   - Explicit confirmation of zero violations
   - List of checked methods/fields

5. **Final Verdict**
   - ✅ PASS (39/39) or ❌ FAIL (X/39)
   - If FAIL: blockers listed

---

## Exclusions (Out of Scope)

The following are **NOT** part of M3 validation:

❌ **Performance benchmarks** - M3 is correctness-focused  
❌ **Profitability tests** - Memory doesn't trade  
❌ **Strategy integration tests** - Strategies interpret M3 data  
❌ **Optimization tests** - Correctness before performance  
❌ **Scalability tests** - Functional validation only  
❌ **UI/visualization tests** - Not applicable to M3  

---

## Success Criteria (Binary)

### ✅ PASS

**M3 implementation passes validation if:**
- 39/39 tests pass
- Zero prohibition violations
- M2 backward compatible
- All outputs factual
- All logic retrospective

### ❌ FAIL

**M3 implementation fails validation if:**
- ANY test fails
- ANY prohibition violated
- ANY signal/prediction capability exists
- M2 compatibility broken
- ANY forward inference detected

---

## Summary

**Total tests:** 39  
**Test categories:** 6  
**Pass threshold:** 39/39 (100%)  
**Key focus:** Correctness & prohibition compliance  
**Out of scope:** Performance, profitability, optimization  

**Validation is binary:** PASS (ready for use) or FAIL (requires fixes).

**Awaiting PASS to proceed with implementation.**
