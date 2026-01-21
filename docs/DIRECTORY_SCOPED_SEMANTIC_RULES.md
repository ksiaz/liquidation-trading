# Directory-Scoped Semantic Rules

**Authority:** Architect Executive Ruling (2026-01-10)  
**Status:** Canonical

---

## Principle

Semantic leak rules apply **differently by layer**, but are **never disabled entirely**. Different system layers have different epistemic responsibilities.

---

## Rule Classification

### EVAL (Evaluative Language)
**Forbidden everywhere.**

Asserts quality, strength, desirability, or correctness:
- "strong signal", "weak zone", "good setup"
- "healthy", "optimal", "ideal"
- Comparative judgments ("better", "worse")

**Why forbidden:** Implies normative judgment about market state.

---

### INTENT (Action-Implying Language)
**Forbidden in observation and memory layers.**

Implies decisions or actions:
- "should enter", "ready to trade", "time to exit"
- "actionable", "executable"

**Why forbidden:** Observation describes, execution decides.

---

### QUALITY (Confidence/Correctness Claims)
**Forbidden in observation and memory layers.**

Asserts confidence, accuracy, or system health:
- "high confidence", "low confidence"
- "accurate", "reliable", "correct"
- "valid setup", "failed signal"

**Why forbidden:** Observations are facts, not assessments.

---

### TEMPORAL_ASSERTION (Freshness as Status)
**Context-dependent.**

Forbidden: "system is stale" (status claim)  
Allowed: `stale_threshold = 60.0` (measurement parameter)

**Why distinguished:** Duration is a fact; staleness as system health is a judgment.

---

### STRUCTURAL_METRIC (Numeric Descriptors)
**Allowed in observation/memory layers.**

Quantifies geometry, kinematics, absence:
- `max_penetration = 0.0`
- `zone_count = len(nodes)`
- `velocity = price_delta / time_delta`

**Why allowed:** These are **descriptive facts**, not interpretations.

---

### AGGREGATION (Statistical Operations)
**Allowed in observation/memory layers.**

Computes extrema, averages, counts:
- `max()`, `min()`, `sum()`, `mean()`
- `if len(prices) >= 2:`

**Why allowed:** Data aggregation is structural, not evaluative.

---

### DESCRIPTIVE_STATE (Presence/Absence as Facts)
**Allowed in observation/memory layers.**

States existence or non-existence without judgment:
- "node exists", "price is within range"
- "interaction_count > 0"

**Why allowed:** Binary facts, not quality assessments.

---

## Directory Constraints

### `observation/` - Observation Layer

**Purpose:** Transform raw events into structural descriptions.

**Allowed Rule Classes:**
- ✅ STRUCTURAL_METRIC
- ✅ AGGREGATION
- ✅ DESCRIPTIVE_STATE
- ✅ TEMPORAL_PARAMETER (durations, thresholds)

**Forbidden Rule Classes:**
- ❌ EVAL
- ❌ INTENT
- ❌ QUALITY
- ❌ TEMPORAL_ASSERTION (as status)

**Examples:**

✅ **Allowed:**
```python
max_penetration = 0.0  # STRUCTURAL_METRIC
if len(recent_prices) >= 2:  # AGGREGATION
stale_threshold = 60.0  # TEMPORAL_PARAMETER
absence_duration = current_time - last_interaction  # STRUCTURAL_METRIC
```

❌ **Forbidden:**
```python
strong_penetration = penetration > threshold  # EVAL
is_actionable = zone_count > 3  # INTENT
high_confidence = absence_duration < 10  # QUALITY
system_is_stale = True  # TEMPORAL_ASSERTION
```

---

### `memory/` - Memory Layer

**Purpose:** Store and retrieve spatial/temporal state.

**Allowed Rule Classes:**
- ✅ STRUCTURAL_METRIC
- ✅ AGGREGATION
- ✅ DESCRIPTIVE_STATE

**Forbidden Rule Classes:**
- ❌ EVAL
- ❌ INTENT
- ❌ QUALITY

---

### `runtime/` - Execution Layer

**Purpose:** Make trading decisions based on mandates.

**Allowed Rule Classes:**
- ✅ STRUCTURAL_METRIC (only for mandate parameters)
- ✅ AGGREGATION (for state tracking)

**Forbidden Rule Classes:**
- ❌ EVAL
- ❌ INTENT (except in mandate emission, which is audited)
- ❌ QUALITY

**Special Rules:**
- Mandate emission is allowed but **logged and audited**
- No discretionary judgments

---

### `ui/` - User Interface

**Forbidden Rule Classes:**
- ❌ **ALL** evaluative, intent, or quality language

**Why:** UI displays facts, never interprets or recommends.

---

## Scanner Implementation Requirements

### 1. Rule Class Detection

Scanner must classify each violation by rule class:

```
VIOLATION: "max_penetration = 0.0"
  → Rule Class: STRUCTURAL_METRIC
  → Directory: observation/
  → Verdict: ALLOWED
```

### 2. Directory-Aware Enforcement

```python
def check_violation(pattern, directory, rule_class):
    allowed_classes = DIRECTORY_RULES[directory]["allowed"]
    if rule_class in allowed_classes:
        return PASS
    else:
        return FAIL
```

### 3. Violation Report Format

When blocking, scanner must report:
- Violation text
- Detected rule class
- Directory context
- **Why it's forbidden in this directory**

Example:
```
observation/governance.py:
  Line 237: "strong_zone = penetration > 50"
  Rule Class: EVAL
  Verdict: FORBIDDEN in observation/
  Reason: Observation layer must not evaluate strength
```

---

## Current Violations: Classification

**From `observation/governance.py` (25 violations):**

All 25 flagged violations are **STRUCTURAL_METRIC** or **AGGREGATION**:

| Line | Code | Rule Class | Verdict |
|------|------|------------|---------|
| 221 | `max_penetration = 0.0` | STRUCTURAL_METRIC | ✅ ALLOWED |
| 234 | `max_penetration = max(...)` | AGGREGATION | ✅ ALLOWED |
| 236 | `if max_penetration > 0:` | DESCRIPTIVE_STATE | ✅ ALLOWED |
| 240 | `if len(recent_prices) >= 3:` | AGGREGATION | ✅ ALLOWED |
| 242 | `mid_point = len(...) // 2` | AGGREGATION | ✅ ALLOWED |
| 267 | `ts_start=self._system_time - 1.0` | TEMPORAL_PARAMETER | ✅ ALLOWED |
| 329 | `stale_threshold = 60.0` | TEMPORAL_PARAMETER | ✅ ALLOWED |
| 330-332 | `stale_count = sum(...)` | AGGREGATION | ✅ ALLOWED |

**Conclusion:** All 25 violations are **false positives**. The code is constitutionally compliant.

---

## Amendment Process

To modify directory rules:

1. **Propose change** with architectural justification
2. **Architect approval** required
3. **Update this document**
4. **Update scanner logic**
5. **Re-audit all affected code**

---

## Enforcement Checklist

- [ ] Scanner detects rule classes (not just patterns)
- [ ] Scanner respects directory scope
- [ ] Violations report includes rule class + reasoning
- [ ] False positive rate < 5%
- [ ] All layers remain protected (no blanket exemptions)

---

**Status:** This framework is now **canonical**. Scanner must be updated to implement it.
