# M2.2 — EVIDENCE ACCUMULATION RULES

**Phase:** M2  
**Purpose:** Define how evidence strengthens memory nodes  
**Design:** Additive logic, no binary filters

---

## Core Principle

Memory nodes accumulate strength and confidence through repeated evidence.  
NO binary thresholds - all evidence contributes additively.

---

## Rule 1: Orderbook Persistence

**Evidence:** A price level appears in the orderbook and persists over time.

**Strength Accumulation:**
```
strength = persistence_strength_base + (duration_seconds × persistence_strength_per_sec)
strength = min(1.0, strength)  # Capped at 1.0
```

**Parameters:**
- `persistence_strength_base`: 0.3 (30% base strength)
- `persistence_strength_per_sec`: 0.01 (1% per second)
- Minimum duration: 10 seconds (for creation)

**Example:**
- Zone persists for 30 seconds
- Strength = 0.3 + (30 × 0.01) = 0.3 + 0.3 = 0.6

**Confidence:** 0.6 (moderate - orderbook can be spoofed)

**Rationale:** Longer persistence = more meaningful level

---

## Rule 2: Executed Liquidity

**Evidence:** Significant trading volume executes at a price level.

**Strength Accumulation:**
```
strength = execution_strength_base + (volume_usd / 1000) × execution_strength_per_1k
strength = min(1.0, strength)  # Capped at 1.0
```

**Parameters:**
- `execution_strength_base`: 0.4 (40% base strength)
- `execution_strength_per_1k`: 0.05 (5% per $1k volume)
- Minimum volume: $1,000 (for creation)

**Example:**
- $5,000 volume executed
- Strength = 0.4 + (5.0 × 0.05) = 0.4 + 0.25 = 0.65

**Confidence:** 0.7 (high - execution is real, not spoofed)

**Rationale:** More volume = more significant level

### Update on Revisit

When price returns to same level and executes again:
- Existing node strength boosted by +10% (capped at 1.0)
- Volume accumulated

---

## Rule 3: Liquidation Proximity

**Evidence:** Liquidation occurs near a price level.

**Strength Accumulation:**
```
strength = liquidation_strength_base + (num_liquidations × liquidation_strength_per_event)
strength = min(1.0, strength)  # Capped at 1.0
```

**Parameters:**
- `liquidation_strength_base`: 0.3 (30% base strength)
- `liquidation_strength_per_event`: 0.05 (5% per liquidation)
- Proximity threshold: 5 bps

**Example:**
- 4 liquidations near level
- Strength = 0.3 + (4 × 0.05) = 0.3 + 0.2 = 0.5

**Confidence:** 0.5 (moderate - liquidations indicate stress)

**Rationale:** More liquidations = potential support/resistance

### Update on Additional Liquidations

Each new liquidation at same level:
- Existing node strength boosted by +5% (capped at 1.0)

---

## Rule 4: Price Rejection

**Evidence:** Price repeatedly approaches a level but doesn't break through.

**Confidence Accumulation:**
```
confidence = rejection_confidence_base + (visit_count × 0.05)
confidence = min(1.0, confidence)  # Capped at 1.0
```

**Parameters:**
- `rejection_confidence_base`: 0.5 (50% base confidence)
- Minimum visits: 3 (for creation)

**Example:**
- Price visits level 6 times
- Confidence = 0.5 + (6 × 0.05) = 0.5 + 0.3 = 0.8

**Strength:** 0.4 (moderate - observation-based)

**Rationale:** More rejections = stronger psychological level

---

## Rule 5: General Revisit Boost

**Evidence:** Price returns to a previously significant level.

**Strength Boost:**
```
On any interaction with existing node:
  strength = min(1.0, strength + 0.1)  # +10% boost
```

**Resurrection from Archive:**
```
If archived node is revisited:
  strength = min(1.0, old_strength + 0.2)  # +20% boost
  active = True  # Resurrect node
```

**Rationale:** Repeated importance compounds memory strength

---

## Decay Rule

**Time-Based Decay:**
```
decay_factor = 1.0 - (decay_rate × time_since_last_interaction)
strength_new = strength_old × max(0, decay_factor)
```

**Parameters:**
- `decay_rate_default`: 0.0001 (0.01% per second)
- Archival threshold: strength < 0.01

**Example:**
- Node with strength 0.5
- No interaction for 1000 seconds
- Decay = 1.0 - (0.0001 × 1000) = 0.9
- New strength = 0.5 × 0.9 = 0.45

**Rationale:** Older memories fade; recent interactions maintain relevance

---

## Combination Logic

**Multiple Evidence Sources:**

Nodes can be created from ONE source but strengthened by MULTIPLE sources.

Example sequence:
1. **T=0s**: Orderbook persistence (10s) → strength=0.4, confidence=0.6
2. **T=15s**: Execution ($3k) → strength += 0.1 = 0.5, confidence remains 0.6
3. **T=30s**: Liquidation nearby → strength += 0.1 = 0.6, confidence remains 0.6
4. **T=100s**: Decay applied → strength = 0.6 × (1 - 0.0001×70) = 0.596
5. **T=120s**: Price revisits (execution) → strength += 0.1 = 0.696

**Result:** Node has strength 0.696 from COMBINED evidence (persistence + execution + liquidation + revisit)

---

## NO Binary Filters

Traditional approach (WRONG):
```
if persistence_time < 30s:
    reject_zone()  # Binary threshold
```

Memory approach (CORRECT):
```
strength = f(persistence_time)  # Additive contribution
# Shorter persistence = lower strength, but STILL contributes
```

**All evidence matters. Strength is continuous, not binary.**

---

## Implementation Details

**Node Creation Thresholds:**

While accumulation is additive, we DO require minimum evidence to CREATE a node (to avoid spam):

- Persistence: ≥10 seconds
- Execution: ≥$1,000 volume
- Liquidation: Within 5 bps
- Rejection: ≥3 visits

**BUT:** Once created, ALL future evidence accumulates additively.

**Strength vs. Confidence:**

- **Strength:** How significant is this level? (from volume, persistence, etc.)
- **Confidence:** How reliable is this memory? (from evidence quality)

Both contribute to node's overall "importance" but serve different purposes.

---

## Summary Table

| Evidence Type | Base Strength | Scaling Factor | Base Confidence | Update Boost |
|:--------------|:--------------|:---------------|:----------------|:-------------|
| Orderbook Persistence | 0.3 | +0.01/sec | 0.6 | +0.1 |
| Executed Liquidity | 0.4 | +0.05/$1k | 0.7 | +0.1 |
| Liquidation Proximity | 0.3 | +0.05/event | 0.5 | +0.1 |
| Price Rejection | 0.4 | - | 0.5 + 0.05/visit | +0.1 |
| Decay | - | -0.0001/sec | - | - |
| Resurrection | old + 0.2 | - | old | - |

---

**M2.2 COMPLETE** — Evidence accumulation rules fully documented and implemented.
