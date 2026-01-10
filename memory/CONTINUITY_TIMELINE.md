# CONTINUITY LOGIC — Timeline Example

##10-Day Lifecycle: t0 → Dormancy → t+10 Days → Revisit

### DAY 0: Node Creation (t0)
```
Time: 2024-01-01 00:00:00
Action: Node created with evidence

Evidence accumulated:
- 4 interactions (3 trades, 2 liquidations)
- $40,000 total volume
- Strength: 0.6000
- State: ACTIVE
```

### DAY 1: Transition to DORMANT
```
Time: 2024-01-02 00:00:00 (t+24hr)
Trigger: Strength below threshold (0.12 < 0.15)

State change:
- State: ACTIVE → DORMANT
- Decay rate: 0.0001 → 0.00001 (10× slower)
- Queryable: Yes → No (dormant queries only)

✅ Historical evidence preserved:
- 4 interactions
- $40,000 volume
- 2 liquidations
```

### DAYS 2-9: Dormant Period
```
Time: 2024-01-03 to 2024-01-10
Activity: NONE (no price interaction)

Node status:
- State: DORMANT (unchanged)
- Strength: 0.12 → 0.12 (minimal decay)
- Auto-activation: NO
- Evidence: PRESERVED
```

### DAY 10: Price Revisits with NEW Evidence (t+10 days)
```
Time: 2024-01-11 00:00:00 (t+10 days)
NEW evidence: $30,000 trade execution

Revival triggered:
- State: DORMANT → ACTIVE
- Decay rate: 0.00001 → 0.0001 (restored)
- Strength: 0.7800 (NOT zero!)

Strength computation:
- Historical context: ~0.38 (from Day 0 evidence)
- NEW evidence: ~0.40 (from $30k trade)
- Combined: 0.7800
```

---

## Continuity Rules Demonstrated

### ✅ Rule 1: NO Auto-Activation
```
Days 2-9: Node stayed dormant WITHOUT new evidence
Day 10: Reactivated ONLY when NEW evidence arrived
```

### ✅ Rule 2: NEW Evidence Required
```
Activation trigger: $30,000 NEW trade execution
Not automatic: ✓
Not predicted: ✓  
Not assumed: ✓
```

### ✅ Rule 3: Historical Evidence Retained
```
Day 0 evidence → Day 10:
- 4 interactions: PRESERVED
- $40,000 volume: PRESERVED
- 2 liquidations: PRESERVED
```

### ✅ Rule 4: Strength Recomputed
```
Formula: historical_contribution + new_evidence_contribution

Day 0 strength: 0.6000
Day 9 strength: 0.1200 (dormant)
Day 10 strength: 0.7800 (historical + new)
```

### ✅ Rule 5: Strength NOT Zero
```
If reset to zero: 0.0000
Actual revival: 0.7800
Includes history: YES
```

### ✅ Rule 6: No Assumptions
```
❌ No prediction: "This level will hold"
❌ No interpretation: "This is support"
✅ Pure facts: counts + volumes + history
```

---

## Code Implementation

### Revisit Detection
```python
# In ContinuityMemoryStore.add_or_update_node()

if node_id in self._dormant_nodes:
    return self._revive_dormant_node(node_id, timestamp, volume)
```

### Revival Logic
```python
def _revive_dormant_node(self, node_id, timestamp, volume):
    # Get dormant node + historical evidence
    node = self._dormant_nodes.pop(node_id)
    historical = self._dormant_evidence.get(node_id)
    
    # Compute strength from history + new evidence
    new_evidence_strength = min(0.4, volume / 10000.0)
    node.strength = compute_revival_strength(historical, new_evidence_strength)
    
    # Restore active state
    node.decay_rate = ACTIVE_DECAY_RATE
    node.last_interaction_ts = timestamp
    
    self._active_nodes[node_id] = node
    return node
```

### Strength Recomputation (Non-Interpretive)
```python
def compute_revival_strength(historical, new_evidence_strength):
    # Historical contribution (factual, not predictive)
    historical_factor = min(0.5, historical.total_interactions * 0.02)
    volume_factor = min(0.3, historical.total_volume / 100000.0)
    
    # Combine factually
    return min(1.0, historical_factor + volume_factor + new_evidence_strength)
```

---

## Key Insights

**Time Continuity:** Historical evidence preserved across 10 days  
**No Amnesia:** Revival strength includes context (0.78 vs 0.0)  
**No Predictions:** Purely factual accumulation  
**Deterministic:** Same inputs → same revival strength  

**Memory remembers. Memory does not predict.**
