# M3 — ENHANCED DECAY & LIFECYCLE STATES

**Phase:** M3  
**Status:** Complete  
**Purpose:** Advanced decay logic with invalidation and implicit state transitions

---

## M3.1: Enhanced Decay Logic ✅

### Time-Based Decay (Exponential)

**Formula:**
```
decay_factor = 1.0 - (decay_rate × time_since_last_interaction)
strength_new = strength_old × max(0, decay_factor)
```

**Default rate:** 0.0001 (0.01% per second)

### Invalidation Decay (Accelerated)

**Two invalidation types:**

#### 1. Clean Break
- Price moves >2× band width away
- Stays away for >5 minutes (300s)
- **Decay multiplier:** 10x faster

#### 2. No Reaction
- Price is AT node level
- But no interaction for >5 minutes
- **Decay multiplier:** 10x faster

**Rationale:** Levels that fail to hold or react are memory noise.

---

## M3.2: Implicit Lifecycle States ✅

States are **derived**, not hardcoded:

### State Transitions

```
forming → active → established → dormant → archived
    ↓         ↓          ↓           ↓
    └─────────┴──────────┴───────────┴→ archived
```

### State Definitions

| State | Criteria |
|:------|:---------|
| **forming** | Age <60s AND strength <0.3 |
| **active** | Last interaction <10min AND strength ≥0.4 |
| **established** | Strength ≥0.5 AND interactions ≥2 (but not recently active) |
| **dormant** | Last interaction <1hr AND strength ≥0.1 |
| **archived** | Strength <0.01 OR active=False |

### Priority Order

1. Check if archived (strength < 0.01)
2. Check if forming (young + weak)
3. **Check if active (PRIORITIZED - recent interaction)**
4. Check if established (strong + proven but not recent)
5. Check if dormant (older but has strength)
6. Default to dormant

**Key insight:** Active state takes priority over established because recent activity is more important than historical strength.

---

## Implementation Details

### EnhancedDecayEngine

**Methods:**
- `apply_decay(node, context)` → Returns decay details
- `_check_invalidation(node, current_price, time_elapsed)` → Detects breaks/stagnation

**Invalidation thresholds:**
- Clean break: 2× band width
- No reaction: 300 seconds
- Decay multiplier: 10×

### NodeLifecycleAnalyzer

**Methods:**
- `get_lifecycle_state(node, current_time, current_price)` → Returns state name
- `get_lifecycle_metadata(node, current_time, current_price)` → Returns full metadata
- `describe_transition(old_state, new_state)` → Human-readable description

**NO enum classes.** States are strings computed on-demand.

---

## Usage Example

```python
from memory import LiquidityMemoryNode, CreationReason

# Create node
node = LiquidityMemoryNode(
    id="bid_2.00",
    price_center=2.00,
    price_band=0.002,
    side="bid",
    first_seen_ts=1000.0,
    last_interaction_ts=1000.0,
    strength=0.6,
    confidence=0.7,
    creation_reason=CreationReason.EXECUTED_LIQUIDITY,
    decay_rate=0.0001,
    active=True
)

# Check lifecycle state
state = node.get_lifecycle_state(1100.0, current_price=2.005)
# Returns: "active" (recent interaction within 10 min)

# Apply enhanced decay
decay_info = node.apply_enhanced_decay(1500.0, current_price=2.05)
# decay_info = {
#     'decay_type': 'invalidation_clean_break',
#     'decay_rate': 0.001,  # 10x faster
#     'old_strength': 0.6,
#     'new_strength': 0.3,
#     'archived': False
# }

# Get full metadata
metadata = node.get_lifecycle_metadata(1500.0, current_price=2.05)
# metadata = {
#     'state': 'dormant',
#     'age_seconds': 500.0,
#     'time_since_interaction': 500.0,
#     'strength': 0.3,
#     'distance_from_price_bps': 243.9,
#     'is_at_price': False
# }
```

---

## Test Coverage

✅ All 7 unit tests passing:

1. `test_enhanced_decay_time_based` - Normal time decay
2. `test_invalidation_clean_break` - Accelerated decay from price break
3. `test_lifecycle_forming` - Young, weak node
4. `test_lifecycle_established` - Strong, proven but not recent
5. `test_lifecycle_active` - Recent interaction
6. `test_lifecycle_dormant` - Older but maintained
7. `test_lifecycle_metadata` - Full metadata extraction

---

## Design Compliance

✅ **Gradual decay** - Never jumps to zero without reason  
✅ **Exponential formula** - Time-based smooth reduction  
✅ **Invalidation detection** - Clean breaks accelerate decay  
✅ **Implicit states** - Derived from properties, not enums  
✅ **Deterministic** - Same inputs → same state

---

**M3 COMPLETE** — Memory nodes now have intelligent decay and lifecycle awareness.
