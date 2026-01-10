# Strategy Admission Criteria

**Authority:** Architect  
**Status:** Constitutional  
**Purpose:** Define what kinds of strategies may execute in this system

---

## Core Constraint (Non-Negotiable)

**A strategy does not trade in this system.**

A strategy may only:
- Observe raw market events
- Evaluate deterministic conditions
- Emit mandates (ENTRY / EXIT / REDUCE / HOLD / BLOCK)
- Declare expiry conditions
- Remain silent otherwise

**If a strategy cannot be expressed this way, it does not belong.**

---

## Strategy Classes That Are Natively Compatible

### 1. Event-Driven, Condition-Based Strategies

**Definition:**  
Strategies expressed as: `IF condition X becomes true → emit mandate Y`

**Why compatible:**
- Deterministic
- Stateless per cycle
- No confidence, no scoring
- Naturally silent when conditions are not met

**Examples:**
- Structure break detection
- Liquidity sweep detection
- Volatility regime boundaries
- Time-window rules (session open/close)
- Price entering or exiting a defined zone

**These strategies emit discrete intent, not beliefs.**

---

### 2. Narrative / Scenario Strategies (Properly Formulated)

Your narrative research fits **only if expressed correctly**.

**Allowed form:**
```
IF scenario A → mandate A
IF scenario B → mandate B
ELSE → silence
```

**Not allowed:**
- Probabilistic narratives
- "Bias strength"
- Scenario weighting
- Confidence adjustment

**Why compatible:**
- Narrative becomes a finite decision tree
- Arbitration resolves conflicts
- Silence preserved between scenarios

**This is the correct formalization of narrative trading.**

---

### 3. Structural Market Microstructure Strategies

**Definition:**  
Strategies reacting to raw order-flow-level phenomena

**Examples:**
- Liquidation bursts
- Absorption detection
- Large trade clustering
- Velocity spikes
- Trade imbalance thresholds
- Sudden spread expansion

**Why compatible:**
- Based on raw event streams
- Emits mandates on threshold crossings
- Does not require interpretation beyond "condition satisfied"

**This is where your system is unusually strong.**

---

### 4. Risk-Triggered Defensive Strategies

**These are first-class citizens, not add-ons.**

**Examples:**
- Max exposure breach → EXIT
- Volatility explosion → REDUCE
- Correlated symbol exposure → BLOCK ENTRY
- Time-in-position exceeded → EXIT
- Funding regime change → BLOCK

**Why compatible:**
- Emit high-authority mandates
- Naturally override alpha logic
- Constitution already encodes supremacy rules

**These strategies exist to stop damage, not generate profit.**

---

### 5. Position-State-Aware Strategies

**Strategies that reason only about lifecycle state.**

**Examples:**
- "If OPEN and opposing condition emerges → EXIT"
- "If REDUCING and new risk signal → EXIT"
- "If ENTERING and adverse event → CLOSING"

**Why compatible:**
- Consume only position state + raw conditions
- Do not infer future behavior
- Reinforce lifecycle invariants

**These strategies stabilize execution, not direction.**

---

## Strategy Classes That Are Explicitly Incompatible

### 1. Indicator-Driven Systems (RSI, MACD, etc.)

**Why rejected:**
- Pre-interpreted data
- Semantic compression
- Hidden assumptions
- Timeframe coupling

**Violates:** Raw-Data-Only Annex

---

### 2. ML / Scoring / Confidence Systems

**Why rejected:**
- Emit scores, not decisions
- Require thresholds
- Cannot be audited deterministically
- Leak interpretation into execution

**Violates:**
- Epistemic ceiling
- Mandate purity
- Determinism

---

### 3. Adaptive / Self-Tuning Systems

**Why rejected:**
- Hidden state accumulation
- Drift without amendment
- Non-reproducible behavior

**Violates:**
- Stateless cycle invariant
- Constitutional freeze

---

### 4. Strategy Blending / Weighted Ensembles

**Why rejected:**
- Implicit arbitration
- Invisible conflict resolution
- Non-auditable dominance

**Your system forces explicit arbitration instead.**

---

### 5. Predictive or Forecast-Based Strategies

**Why rejected:**
- Depend on future expectations
- Cannot express expiry cleanly
- Encourage confidence language

**The system only allows reaction, never prediction.**

---

## What a "Strategy" Really Is Here

In this architecture, a strategy is:

```
A pure function from
  (raw events, position state)
  → zero or more mandates
```

**Nothing more.**

- No memory
- No confidence
- No learning
- No belief

---

## Why This Is Actually More Powerful

Because:

1. You can run many such strategies safely
2. You can reason about each independently
3. You can prove what combinations cannot do
4. You can disable, add, or replace strategies without side effects

**The power comes from composition, not intelligence.**

---

## Final Answer (Compressed)

**Strategies that plug in safely are:**
- Event-driven
- Condition-based
- Deterministic
- Stateless per cycle
- Mandate-emitting
- Silence-preserving
- Position-state-aware

**Strategies that do not are:**
- Signal-based
- Score-based
- Predictive
- Adaptive
- Indicator-driven
- Confidence-weighted

---

END OF STRATEGY ADMISSION CRITERIA
