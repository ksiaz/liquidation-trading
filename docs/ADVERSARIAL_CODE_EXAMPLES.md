# ADVERSARIAL CODE EXAMPLES (ALMOST VALID BUT FORBIDDEN)

**Status:** Authoritative  
**Purpose:** Test semantic leak detection with subtle boundary violations  
**Authority:** Semantic Leak Audit, Directory-Scoped Exception Framework

---

## PURPOSE

These examples:
- **Look plausible** - Would pass casual code review
- **Are subtle** - Violate boundaries in non-obvious ways
- **Test enforcement** - Validate CI detection rules
- **Train reviewers** - Show what to catch

Each example includes:
- The violating code
- Which boundary it crosses
- Which leak category it violates
- Why it's dangerous
- How to detect it
- The correct alternative

---

## EXAMPLE 1: Linguistic Leak in Public Type

### ❌ FORBIDDEN CODE

```python
# File: observation/types.py

@dataclass(frozen=True)
class SystemCounters:
    windows_processed: Optional[int]
    signal_strength: Optional[float]  # LEAK: "signal" + "strength"
    dropped_events: Optional[Dict[str, int]]
```

**Location:** `observation/` (ZERO-tolerance boundary)  
**Leak Type:** Linguistic (naming)  
**Boundary Crossed:** Observation → Execution  

**Why Dangerous:**
- Field name implies interpretation ("signal" + "strength")
- Even if value is None, name leaks semantics
- Consumer assumes strength measurement exists
- Opens door for interpretation-based logic in M6

**Detection:**
- Regex: `signal|strength|confidence|quality` in `observation/types.py`
- Field name semantic audit
- Constitutional compliance scan

**Correct Alternative:**
```python
@dataclass(frozen=True)
class SystemCounters:
    windows_processed: Optional[int]
    exceedance_count: Optional[int]  # Neutral count
    dropped_events: Optional[Dict[str, int]]
```

---

## EXAMPLE 2: Structural Leak via Boolean Flag

### ❌ FORBIDDEN CODE

```python
# File: observation/types.py

@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    is_ready: bool  # LEAK: Readiness judgment
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]
```

**Location:** `observation/` (ZERO-tolerance boundary)  
**Leak Type:** Structural (boolean implies interpretation)  
**Boundary Crossed:** Observation → Execution

**Why Dangerous:**
- `is_ready` encodes interpretation (what makes data "ready"?)
- Boolean creates implicit threshold
- M6 would use flag without understanding meaning
- Violates "silence over ambiguity"

**Detection:**
- Regex: `is_\w+|has_\w+|can_\w+` in public types
- Boolean flag audit in ObservationSnapshot
- Readiness assertion scan

**Correct Alternative:**
```python
# Remove flag entirely - M6 operates on status only
@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus  # UNINITIALIZED or FAILED only
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]
```

---

## EXAMPLE 3: Aggregation Leak in Exposed Field

### ❌ FORBIDDEN CODE

```python
# File: observation/governance.py

def _get_snapshot(self) -> ObservationSnapshot:
    baseline_mean, baseline_std = self._m3.get_baseline()  # Internal - OK
    
    return ObservationSnapshot(
        status=self._status,
        timestamp=self._system_time,
        symbols_active=sorted(self._allowed_symbols),
        counters=SystemCounters(
            windows_processed=self._m3.stats['windows_processed'],
            baseline_volatility=baseline_std,  # LEAK: Derived metric
            dropped_events=None
        ),
        promoted_events=None
    )
```

**Location:** `observation/governance.py` (ZERO-tolerance boundary)  
**Leak Type:** Aggregation (derived meaning)  
**Boundary Crossed:** Internal computation → External exposure

**Why Dangerous:**
- `baseline_volatility` is statistical interpretation
- Standard deviation implies normality assumptions
- Consumer must interpret what volatility "means"
- Raw data provenance lost

**Detection:**
- Field name contains statistical terms
- Derived metric in public snapshot
- Aggregation without raw data access

**Correct Alternative:**
```python
def _get_snapshot(self) -> ObservationSnapshot:
    # Internal computation stays internal
    baseline_mean, baseline_std = self._m3.get_baseline()
    
    return ObservationSnapshot(
        status=self._status,
        timestamp=self._system_time,
        symbols_active=sorted(self._allowed_symbols),
        counters=SystemCounters(
            windows_processed=self._m3.stats['windows_processed'],
            dropped_events=None
        ),
        promoted_events=None  # Baseline never exposed
    )
```

---

## EXAMPLE 4: Temporal Leak in Log Message

### ❌ FORBIDDEN CODE

```python
# File: runtime/collector/service.py

async def _run_binance_stream(self):
    stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
    
    async with websockets.connect(stream_url) as ws:
        self._logger.info("Stream is now live and flowing")  # LEAK
        while self._running:
            msg = await ws.recv()
            # ...
```

**Location:** `runtime/` (ZERO-tolerance boundary)  
**Leak Type:** Temporal + Activity (freshness + flow assertion)  
**Boundary Crossed:** Runtime → External (logs)

**Why Dangerous:**
- "live" implies freshness judgment
- "flowing" implies activity assessment
- Operator infers health from message
- Violates external speech prohibition

**Detection:**
- Regex: `live|flowing|fresh|stale|active|processing` in log messages
- String purity audit in runtime/
- Activity assertion scan

**Correct Alternative:**
```python
async def _run_binance_stream(self):
    stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
    
    async with websockets.connect(stream_url) as ws:
        # No log message - silence
        while self._running:
            msg = await ws.recv()
            # ...
```

---

## EXAMPLE 5: Causal Leak in Internal Naming Exposed

### ❌ FORBIDDEN CODE

```python
# File: observation/types.py

@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    events_triggered_by_threshold: Optional[List[Dict]]  # LEAK: Causality
```

**Location:** `observation/` (ZERO-tolerance boundary)  
**Leak Type:** Causal (implies cause-effect)  
**Boundary Crossed:** Observation → Execution

**Why Dangerous:**
- "triggered_by" encodes causality
- Implies threshold caused event
- Consumer assumes causal relationship valid
- Interpretation masked as fact

**Detection:**
- Regex: `triggered|caused|due_to|because|led_to` in field names
- Causal language in public types
- Cause-effect naming patterns

**Correct Alternative:**
```python
@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict]]  # Neutral: events exist
```

---

## EXAMPLE 6: Absence-as-Signal Leak in M6

### ❌ FORBIDDEN CODE

```python
# File: runtime/m6_executor.py

def execute(observation_snapshot: ObservationSnapshot) -> None:
    if observation_snapshot.status == ObservationStatus.FAILED:
        raise SystemHaltedException("Observation FAILED")
    
    if observation_snapshot.status == ObservationStatus.UNINITIALIZED:
        return  # OK
    
    # LEAK: Silence interpreted as safe to proceed
    if observation_snapshot.promoted_events is None:
        # Assume "quiet market" - safe to continue
        perform_default_action()  # FORBIDDEN
```

**Location:** `runtime/m6_executor.py` (ZERO-tolerance boundary)  
**Leak Type:** Absence-as-Signal  
**Boundary Crossed:** M6 interpretation

**Why Dangerous:**
- None interpreted as meaning (quiet/safe)
- Absence triggers action
- Violates "silence must remain silence"
- Creates inference from lack of data

**Detection:**
- Logic branching on None with action
- Default behaviors when data absent
- Assumptions from silence

**Correct Alternative:**
```python
def execute(observation_snapshot: ObservationSnapshot) -> None:
    if observation_snapshot.status == ObservationStatus.FAILED:
        raise SystemHaltedException("Observation FAILED")
    
    if observation_snapshot.status == ObservationStatus.UNINITIALIZED:
        return
    
    # Silence remains silence - no action
    return
```

---

## EXAMPLE 7: Threshold Leak in UI Display

### ❌ FORBIDDEN CODE

```python
# File: runtime/native_app/main.py

def update_ui(self):
    snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})
    
    window_count = snapshot.counters.windows_processed or 0
    
    if window_count > 100:
        self.status_label.setText("System is warmed up")  # LEAK
        self.status_label.setStyleSheet("color: green;")
    else:
        self.status_label.setText("System warming up")  # LEAK
        self.status_label.setStyleSheet("color: yellow;")
```

**Location:** `runtime/` (ZERO-tolerance boundary)  
**Leak Type:** Threshold + Readiness  
**Boundary Crossed:** Runtime → UI (external)

**Why Dangerous:**
- Threshold (100) implies judgment of readiness
- "warmed up" is interpretation
- Color coding adds semantic layer
- Operator infers system state from arbitrary cutoff

**Detection:**
- Conditional UI text based on thresholds
- Readiness language in UI updates
- Color coding based on derived judgments

**Correct Alternative:**
```python
def update_ui(self):
    snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})
    
    # Display raw facts only
    self.status_label.setText(
        f"{snapshot.status.name}\n"
        f"Time: {snapshot.timestamp:.2f}\n"
        f"Symbols: {len(snapshot.symbols_active)}"
    )
```

---

## EXAMPLE 8: Statistical Framing Leak via Export

### ❌ FORBIDDEN CODE

```python
# File: observation/governance.py

def get_statistical_summary(self) -> Dict[str, float]:
    """FORBIDDEN: Exposes statistical interpretation"""
    baseline_mean, baseline_std = self._m3.get_baseline()
    
    return {
        'mean': baseline_mean,
        'stddev': baseline_std,
        'z_score': self._calculate_z_score(),  # LEAK
        'outlier_count': self._count_outliers()  # LEAK
    }
```

**Location:** `observation/governance.py` (ZERO-tolerance boundary)  
**Leak Type:** Statistical Framing  
**Boundary Crossed:** Internal stats → External exposure

**Why Dangerous:**
- Z-score implies normal distribution assumption
- "outlier" is interpretive classification
- Consumer treats as facts not statistical constructs
- Hides assumptions in calculation

**Detection:**
- Public methods returning statistical summaries
- Field names: mean, stddev, z_score, outlier
- Statistical terminology in public API

**Correct Alternative:**
```python
# Remove method entirely
# Internal stats stay in observation/internal/
# Only query() method exists for public access
```

---

## EXAMPLE 9: Cross-Layer Knowledge Leak via Callback

### ❌ FORBIDDEN CODE

```python
# File: observation/governance.py

class ObservationSystem:
    def __init__(self, allowed_symbols):
        self._allowed_symbols = set(allowed_symbols)
        self._system_time = 0.0
        self._status = ObservationStatus.UNINITIALIZED
        self._observers = []  # LEAK: Observer pattern
        
    def register_observer(self, callback):  # FORBIDDEN
        """Allow external registration"""
        self._observers.append(callback)
    
    def advance_time(self, new_timestamp):
        # ... existing logic ...
        
        # LEAK: Notify observers
        snapshot = self._get_snapshot()
        for observer in self._observers:
            observer(snapshot)  # Observation knows about execution
```

**Location:** `observation/governance.py` (ZERO-tolerance boundary)  
**Leak Type:** Cross-Layer Knowledge  
**Boundary Crossed:** Observation → Execution (implicit)

**Why Dangerous:**
- Observer pattern creates bidirectional coupling
- Observation "knows" execution exists
- Violates one-way dependency (Observation must not reference M6)
- Creates hidden invocation path

**Detection:**
- Observer/callback patterns in observation layer
- Registration methods in sealed systems
- Notification loops

**Correct Alternative:**
```python
# No observer pattern
# Observation is query-only
# M6 invocation is explicit, not via callback
```

---

## EXAMPLE 10: Import Violation (Subtle)

### ❌ FORBIDDEN CODE

```python
# File: observation/types.py

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum, auto
from observation.internal.m3_temporal import PromotedEventInternal  # LEAK

@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[PromotedEventInternal]]  # LEAK: Internal type
```

**Location:** `observation/types.py` (ZERO-tolerance boundary)  
**Leak Type:** Cross-Layer Knowledge (import)  
**Boundary Crossed:** Internal → Public API

**Why Dangerous:**
- Internal dataclass exposed in public type signature
- Consumers see internal implementation details
- `PromotedEventInternal` has semantic fields (baseline_mean, sigma_distance)
- Breaks encapsulation

**Detection:**
- Import statements from `observation.internal` in `observation/` root
- Internal types in public signatures
- Import path analysis

**Correct Alternative:**
```python
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum, auto
# No internal imports

@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: List[str]
    counters: SystemCounters
    promoted_events: Optional[List[Dict[str, Any]]]  # Generic dict, no semantics
```

---

## EXAMPLE 11: Mutation During Read (Subtle Leak)

### ❌ FORBIDDEN CODE

```python
# File: observation/governance.py

def query(self, query_spec: Dict) -> Any:
    if self._status == ObservationStatus.FAILED:
        raise SystemHaltedException(f"SYSTEM HALTED: {self._failure_reason}")
    
    q_type = query_spec.get('type')
    
    if q_type == 'snapshot':
        # LEAK: Side effect during read
        self._last_query_time = time.time()  # Mutation!
        self._query_count += 1  # Mutation!
        return self._get_snapshot()
```

**Location:** `observation/governance.py` (ZERO-tolerance boundary)  
**Leak Type:** Structural (mutation during read implies meaning)  
**Boundary Crossed:** Query → State mutation

**Why Dangerous:**
- Read operation has side effects
- Implies query timing/frequency matters
- Creates hidden state dependencies
- Violates query purity

**Detection:**
- State mutations in query methods
- Assignments in read-only operations
- Side effects in getters

**Correct Alternative:**
```python
def query(self, query_spec: Dict) -> Any:
    if self._status == ObservationStatus.FAILED:
        raise SystemHaltedException(f"SYSTEM HALTED: {self._failure_reason}")
    
    q_type = query_spec.get('type')
    
    if q_type == 'snapshot':
        return self._get_snapshot()  # Pure read, no mutation
```

---

## EXAMPLE 12: Config-Based Semantic Leak

### ❌ FORBIDDEN CODE

```python
# File: runtime/config.py

SYSTEM_CONFIG = {
    'observation': {
        'health_check_enabled': True,  # LEAK: Health concept
        'staleness_threshold_seconds': 30.0,  # LEAK: Staleness judgment
        'warmup_window_count': 100,  # LEAK: Warmup / readiness
        'confidence_minimum': 0.8  # LEAK: Confidence threshold
    }
}
```

**Location:** Configuration (would affect multiple boundaries)  
**Leak Type:** Multiple (health, temporal, threshold, statistical)  
**Boundary Crossed:** Config → System behavior

**Why Dangerous:**
- Configuration encodes interpretive concepts
- "Health check" implies health assessment
- "Staleness threshold" creates temporal judgment
- "Confidence minimum" implies quality filtering
- Config looks innocent but violates constitution

**Detection:**
- Semantic terms in config keys
- Threshold values with interpretive names
- Config options that enable forbidden features

**Correct Alternative:**
```python
# Minimal config - only structural parameters
SYSTEM_CONFIG = {
    'observation': {
        'allowed_symbols': ['BTCUSDT', 'ETHUSDT'],
        'max_buffer_size': 500
    }
}
```

---

## DETECTION SUMMARY TABLE

| Example | Leak Type | Location | Detection Method |
|---------|-----------|----------|------------------|
| 1 | Linguistic | observation/types.py | Regex: signal\|strength\|confidence |
| 2 | Structural (boolean) | observation/types.py | Pattern: `is_\w+` in public types |
| 3 | Aggregation | observation/governance.py | Derived metrics in snapshot |
| 4 | Temporal + Activity | runtime/collector | Log message semantic scan |
| 5 | Causal | observation/types.py | Regex: triggered\|caused\|due_to |
| 6 | Absence-as-Signal | runtime/m6_executor.py | Logic on None with action |
| 7 | Threshold + Readiness | runtime/native_app | Conditional UI based on cutoff |
| 8 | Statistical Framing | observation/governance.py | Public methods returning stats |
| 9 | Cross-Layer Knowledge | observation/governance.py | Observer pattern detection |
| 10 | Import Violation | observation/types.py | Import path analysis |
| 11 | Mutation During Read | observation/governance.py | State changes in query |
| 12 | Config Semantic | config.py | Semantic keys in configuration |

---

## ENFORCEMENT PRIORITIES

**P0 (Critical):**
- Examples 2, 6, 9 - Structural violations enabling interpretation
- Example 10 - Import violations breaking encapsulation

**P1 (High):**
- Examples 1, 3, 5, 8 - Direct semantic exposure
- Example 11 - Purity violations

**P2 (Medium):**
- Examples 4, 7 - External communication leaks
- Example 12 - Configuration leaks

---

## USAGE

**For Code Review:**
- Check new code against all 12 patterns
- Flag anything structurally similar

**For CI Design:**
- Each example maps to detection rule
- Combine for comprehensive scanning

**For Training:**
- Show reviewers subtle violations
- Explain why each is dangerous

---

END OF ADVERSARIAL EXAMPLES
