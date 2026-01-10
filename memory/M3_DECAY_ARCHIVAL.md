# M3 Motif Decay & Archival (M2 Alignment)

## Core Principle

**Motifs are bound to their node's lifecycle.**

When a node's state changes, all motifs attached to that node follow the same state transition. Motifs do NOT have independent lifecycle - they inherit the node's state exactly.

---

## Decay Rate Table

| Node State | Decay Rate | Application to Motifs |
|:-----------|:-----------|:---------------------|
| **ACTIVE** | 0.0001/sec | All motifs decay at 0.0001/sec |
| **DORMANT** | 0.00001/sec | All motifs decay at 0.00001/sec (10× slower) |
| **ARCHIVED** | 0 (frozen) | All motifs frozen (no decay) |

**Formula (identical to M2 node decay):**
```
time_elapsed = current_ts - motif_last_seen_ts
decay_factor = 1.0 - (decay_rate * time_elapsed)
motif_strength *= max(0.0, decay_factor)
```

**Critical:** Motifs use the **exact same decay rate** as their parent node. No independent decay logic.

---

## State Transition Table

### Transition 1: ACTIVE → DORMANT

**When:** Node transitions to DORMANT (strength < 0.15 OR idle > 3600s)

**Motif behavior:**
| Attribute | Before (ACTIVE) | After (DORMANT) | Changed? |
|:----------|:---------------|:---------------|:---------|
| `motif_counts` | Preserved | Preserved | ❌ No |
| `motif_last_seen` | Preserved | Preserved | ❌ No |
| `motif_strength` | Decaying at 0.0001/sec | Decaying at 0.00001/sec | ✅ Yes (decay rate) |
| **Decay rate** | 0.0001/sec | 0.00001/sec | ✅ Yes (10× slower) |

**Actions:**
1. Change decay rate to DORMANT_DECAY_RATE
2. Continue applying decay at new rate
3. All counts and timestamps preserved
4. No motifs deleted

**NO deletion:** Motifs transition to dormant state, not removed.

---

### Transition 2: DORMANT → ARCHIVED

**When:** Node transitions to ARCHIVED (strength < 0.01 OR idle > 86400s)

**Motif behavior:**
| Attribute | Before (DORMANT) | After (ARCHIVED) | Changed? |
|:----------|:----------------|:----------------|:---------|
| `motif_counts` | Preserved | Preserved (frozen) | ❌ No |
| `motif_last_seen` | Preserved | Preserved (frozen) | ❌ No |
| `motif_strength` | Decaying at 0.00001/sec | Frozen at current value | ✅ Yes (stopped) |
| **Decay rate** | 0.00001/sec | 0 (no decay) | ✅ Yes (frozen) |

**Actions:**
1. Stop applying decay (rate = 0)
2. Freeze motif_strength at current value
3. All counts and timestamps preserved
4. No motifs deleted

**NO deletion:** Motifs archived with node, not removed.

---

### Transition 3: DORMANT → ACTIVE (Revival)

**When:** Node revived with NEW evidence (new interaction at dormant node)

**Motif behavior:**
| Attribute | Before (DORMANT) | After (ACTIVE) | Changed? |
|:----------|:----------------|:---------------|:---------|
| `motif_counts` | Preserved | Preserved | ❌ No |
| `motif_last_seen` | Preserved | Preserved | ❌ No |
| `motif_strength` | Current (decayed) | Restored to historical context | ✅ Yes (boosted) |
| **Decay rate** | 0.00001/sec | 0.0001/sec | ✅ Yes (faster) |

**Actions:**
1. Restore decay rate to ACTIVE_DECAY_RATE
2. Motif strengths retain their decayed values (historical context)
3. NEW evidence adds new tokens → new motifs extracted
4. Old motif counts/timestamps unchanged

**Revival boost:** Motifs benefit from historical context (like node strength revival).

**Critical:** Revival requires NEW evidence token. Motifs do NOT auto-revive.

---

### Transition 4: ARCHIVED → ACTIVE (Revival from Archive)

**When:** Node revisited with NEW evidence after archival

**Current M2 behavior:** Archived nodes create NEW node with NEW ID (or reactivate with evidence)

**Motif behavior (two scenarios):**

**Scenario A: New node created**
- Old archived motifs remain frozen with old node
- New node starts with empty motif store
- NO motifs transferred

**Scenario B: Same node reactivated** (if using same ID)
- Archived motifs unfrozen
- Decay rate restored to ACTIVE_DECAY_RATE
- Motif counts/timestamps preserved
- NEW evidence adds new motifs

**Critical:** Archived motifs do NOT auto-revive. Revival requires NEW evidence interaction.

---

## Motif-Specific Rules (Aligned with M2)

### Rule 1: Motifs Never Auto-Generate

❌ Motifs do NOT:
- Auto-revive without new evidence
- Generate themselves from historical patterns
- Predict future sequences
- Self-propagate across nodes

✅ Motifs ONLY exist when:
- Tokens observed in sequence
- Extracted from actual events
- Updated via new evidence

### Rule 2: Motif Decay is Purely Mechanical

Decay formula (identical to M2):
```python
def decay_motif(motif, current_ts, node_decay_rate):
    time_elapsed = current_ts - motif['last_seen_ts']
    decay_factor = 1.0 - (node_decay_rate * time_elapsed)
    motif['strength'] *= max(0.0, decay_factor)
```

**NO special cases:** All motifs decay uniformly at node's rate.

### Rule 3: Motif Archival is Passive

When node archived:
- Motifs frozen (not deleted)
- Counts preserved (historical record)
- Timestamps preserved (last occurrence)
- Strength frozen (no further decay)

**Rationale:** Archived motifs are historical facts that don't expire.

### Rule 4: Motif Revival Requires New Evidence

Motifs revive ONLY when:
1. Node receives NEW evidence token
2. Token appended to sequence buffer
3. New motifs extracted (may include old patterns)

**Revival does NOT:**
- ❌ Automatically restore old motifs
- ❌ Boost motif strength without new evidence
- ❌ Predict which motifs will reoccur

**Revival DOES:**
- ✅ Restore decay rate to active
- ✅ Continue counting if same pattern reoccurs
- ✅ Preserve historical counts

---

## Node State Change Flow (Complete)

### ACTIVE Node Processing

```
1. New evidence token arrives
2. Append to sequence buffer
3. Extract motifs (bigrams + trigrams)
4. Update motif counts
5. Apply decay (rate = 0.0001/sec)
6. Check node state transition conditions
```

### ACTIVE → DORMANT Transition

```
1. Node strength < 0.15 OR idle > 3600s
2. Node state = DORMANT
3. Motif decay rate = 0.00001/sec (10× slower)
4. Continue decay at new rate
5. No motif deletion
```

### DORMANT Node Processing

```
1. No new evidence (dormant)
2. Apply decay (rate = 0.00001/sec)
3. Check node state transition conditions
```

### DORMANT → ARCHIVED Transition

```
1. Node strength < 0.01 OR idle > 86400s
2. Node state = ARCHIVED
3. Motif decay rate = 0 (frozen)
4. Stop decay
5. No motif deletion
```

### DORMANT → ACTIVE Revival

```
1. NEW evidence token arrives
2. Node state = ACTIVE
3. Motif decay rate = 0.0001/sec (restored)
4. Append token to sequence buffer
5. Extract new motifs
6. Update counts (old + new)
```

---

## Alignment Verification

### M2 Principles Applied to M3

| M2 Principle | M3 Application |
|:-------------|:---------------|
| Nodes decay over time | Motifs decay at same rate as node |
| Dormant decays 10× slower | Dormant motifs decay 10× slower |
| Archived nodes frozen | Archived motifs frozen |
| No auto-revival | Motifs require NEW evidence to revive |
| Revival uses historical context | Motif counts preserved, strength restored |
| No predictions | Motifs are counts, not predictions |

### Decay Rate Consistency Check

```
Node ACTIVE:   decay_rate = 0.0001/sec  ✅ Motifs use 0.0001/sec
Node DORMANT:  decay_rate = 0.00001/sec ✅ Motifs use 0.00001/sec
Node ARCHIVED: decay_rate = 0          ✅ Motifs use 0
```

**Verified:** Motifs use node's decay rate exactly.

### State Transition Consistency Check

```
Node ACTIVE → DORMANT    ✅ Motifs transition to dormant
Node DORMANT → ARCHIVED  ✅ Motifs transition to archived
Node DORMANT → ACTIVE    ✅ Motifs revive with node
```

**Verified:** Motif state always matches node state.

---

## Summary

**Motifs follow M2 lifecycle exactly:**
- ✅ Same decay rates (active/dormant/archived)
- ✅ Same state transitions
- ✅ Same revival rules (requires NEW evidence)
- ✅ Same archival behavior (frozen, not deleted)

**No new decay logic introduced:**
- ✅ Reuses ACTIVE_DECAY_RATE (0.0001/sec)
- ✅ Reuses DORMANT_DECAY_RATE (0.00001/sec)
- ✅ Reuses archival freeze (rate = 0)

**Archived motifs:**
- ❌ Do NOT auto-revive
- ❌ Do NOT generate predictions
- ✅ Require NEW evidence for revival
- ✅ Preserved as historical facts

**M3 is M2-aligned temporal ordering, not a new lifecycle.**

**Awaiting PASS to proceed.**
