# DORMANT State — Before/After Comparison

## BEFORE DORMANCY (ACTIVE)

```
Node: demo_level
Price: $2.0500 ± $0.0020
Strength: 0.5000
Decay Rate: 0.000100/sec (ACTIVE rate)
Active: True

Evidence Accumulated:
  • 6 total interactions
  • $15,000 volume ($12k buyer, $3k seller)
  • 3 liquidations (2 long, 1 short)
  • Largest event: $7,000
  • Median gap: 10.0s
```

---

## AFTER DORMANCY (DORMANT)

```
Node: demo_level
Price: $2.0500 ± $0.0020
Strength: 0.1000
Decay Rate: 0.000010/sec (10× SLOWER)
Active: False

Evidence Preserved:
  • 6 total interactions ✓ UNCHANGED
  • $15,000 volume ✓ UNCHANGED
  • 3 liquidations ✓ UNCHANGED
  • Largest event: $7,000 ✓ UNCHANGED
  • Median gap: 10.0s ✓ UNCHANGED
```

---

## Key Differences

| Property | ACTIVE | DORMANT | Change |
|:---------|:-------|:--------|:-------|
| **Decay Rate** | 0.0001/sec | 0.00001/sec | 10× slower |
| **Queryable as active** | Yes | No | Not in `get_active_nodes()` |
| **Deleted** | No | No | Preserved |
| **Historical evidence** | N/A | Stored | Separately archived |

---

## Evidence Preservation Detail

### ✅ PRESERVED (Cumulative)
- Interaction counts (orderbook, trades, liquidations)
- Volume totals (total, buyer, seller, largest)
- Liquidation counts (long, short, cascade size)
- Temporal stats (first seen, last interaction, gaps)

### 📉 CHANGED (State-Specific)
- Decay rate: 10× slower
- Active flag: False
- Queryability: Dormant queries only

### ❌ DISCARDED
- Temporary strength boosts
- Session-specific counters

---

## Decay Rate Comparison (1 hour)

**ACTIVE:** 36.0% decay  
**DORMANT:** 3.6% decay  
**Ratio:** 10× slower persistence

---

## Revival Example

**Dormant node** with $15,000 historical volume  
**+** NEW evidence: $5,000 volume  
**=** Revival strength: **0.570** (includes history, not zero)

✅ **Historical context preserved across revival**

---

## Queryability

```python
# DORMANT nodes NOT in active queries
active = store.get_active_nodes()  # Empty

# But accessible via dormant queries
dormant = store.get_dormant_nodes()  # Returns node

# Included in topology/pressure analysis
clusters = store.get_topological_clusters()  # Includes
pressure = store.get_pressure_map((2.0, 2.1))  # Includes
```

---

**Memory Layer Principle:** Historical evidence never deleted, only transition states change.
