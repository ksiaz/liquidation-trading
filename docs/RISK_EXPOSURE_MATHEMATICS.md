# RISK & EXPOSURE MATHEMATICS FORMALIZATION

**Status:** Authoritative Specification  
**Authority:** Position & Execution Constitution, PROJECT SPECIFICATION  
**Purpose:** Formal mathematical definition of risk bounds and exposure constraints

---

## 1. FOUNDATIONAL PRINCIPLES

### 1.1 Constitutional Constraints

**From Constitution:**
- One position per symbol (no hedging)
- No directional reversal without EXIT
- Exposure must be bounded
- REDUCE does not change direction
- Deterministic, no interpretation

**Mathematical Implications:**
- Position size ∈ {0} ∪ [min_size, max_size]
- Direction ∈ {LONG, SHORT, FLAT}
- All bounds must be computable from constants only

---

## 2. NOTATION & DEFINITIONS

### 2.1 Core Variables

**Account State:**
- `E` = Account equity (USD)
- `M` = Maintenance margin (USD)
- `L` = Leverage ratio (dimensionless, e.g., 10x, 20x)
- `MMR` = Maintenance margin rate (exchange-defined, typically 0.5% - 2.5%)

**Position State:**
- `P_s` = Position for symbol `s`
- `Q_s` = Quantity (signed: positive = LONG, negative = SHORT, 0 = FLAT)
- `P_entry` = Entry price (USD per contract)
- `P_mark` = Mark price (current, USD per contract)
- `D_s` = Direction ∈ {LONG, SHORT, FLAT}

**Derived Values:**
- `Notional_s = |Q_s| × P_mark` = Position notional value (USD)
- `PnL_s = Q_s × (P_mark - P_entry)` = Unrealized profit/loss (USD)
- `Exposure_s = |Q_s × P_mark|` = Absolute exposure (USD)

---

### 2.2 Liquidation Mechanics (Exchange Reality)

**Liquidation Price (Approximation):**

For LONG position:
```
P_liq_long = P_entry × (1 - 1/L + MMR)
```

For SHORT position:
```
P_liq_short = P_entry × (1 + 1/L - MMR)
```

**Distance to Liquidation:**
```
D_liq_s = |P_mark - P_liq| / P_mark  (percentage)
```

**Critical Threshold:**
```
D_liq_s < D_min_safe  →  LIQUIDATION IMMINENT
```

Where `D_min_safe` is a system constant (e.g., 5% - 10%)

---

## 3. LEVERAGE BOUNDS (FORMAL)

### 3.1 Maximum Leverage Constraint

**Hard Invariant I-L1:**
```
L_actual ≤ L_max
```

Where:
- `L_actual = Σ_s Exposure_s / E` (total exposure / equity)
- `L_max` = Constitutional maximum (e.g., 10x, 15x, 20x)

**Enforcement Point:** Before ENTRY or REDUCE_UP

**Action if Violated:**
- ENTRY mandate → REJECT
- System → FAIL (liquidation risk)

---

### 3.2 Per-Symbol Leverage Constraint

**Hard Invariant I-L2:**
```
Exposure_s ≤ L_symbol_max × E
```

Where:
- `L_symbol_max` = Per-symbol leverage limit (e.g., 5x)
- Prevents concentration risk

**Purpose:** No single symbol can dominate portfolio

---

### 3.3 Leverage Target (Soft)

**Operational Target:**
```
L_actual ≤ L_target
```

Where `L_target < L_max` (e.g., L_target = 8x, L_max = 10x)

**Purpose:** Operating buffer before hard limit

**Enforcement:** Advisory, not mandatory

---

## 4. LIQUIDATION AVOIDANCE INVARIANT

### 4.1 Minimum Distance Invariant

**Hard Invariant I-LA1:**
```
For all positions s:
  D_liq_s ≥ D_min_safe
```

**Pre-Conditions:**
- Must hold BEFORE any position increase
- Must hold continuously (checked on mark price updates)

**Violation Response:**
```
If D_liq_s < D_min_safe:
  → Emit EXIT mandate immediately
  → BLOCK all ENTRY/REDUCE_UP for symbol s
```

---

### 4.2 Portfolio-Level Liquidation Buffer

**Aggregate Liquidation Risk:**
```
R_liq = min_s(D_liq_s)  (worst-case symbol)
```

**Hard Invariant I-LA2:**
```
R_liq ≥ R_liq_min
```

Where `R_liq_min` = Portfolio-wide minimum (e.g., 8%)

**Purpose:** Prevent correlated liquidations

---

### 4.3 Equity Drop Tolerance

**Maximum Tolerable Loss:**
```
Loss_max = E × (1 - 1/L_actual - MMR_avg)
```

**Hard Invariant I-LA3:**
```
Σ_s |PnL_s| (if all negative) < Loss_max × safety_factor
```

Where `safety_factor = 0.7` (70% of theoretical max loss)

**Purpose:** Exit before exchange force-liquidates

---

## 5. EXPOSURE AGGREGATION RULES

### 5.1 Total Exposure Calculation

**Definition:**
```
Exposure_total = Σ_s Exposure_s
```

Where sum is over all active symbols.

**Directional Exposure:**
```
Exposure_long = Σ_{s: D_s = LONG} Exposure_s
Exposure_short = Σ_{s: D_s = SHORT} Exposure_s
```

**Net Exposure:**
```
Exposure_net = Exposure_long - Exposure_short
```

---

### 5.2 Correlation Adjustment (Future)

**Current:** Exposure treated as uncorrelated

**Future Enhancement:**
```
Exposure_adjusted = Σ_s Exposure_s × √(1 + ρ_s)
```

Where `ρ_s` = correlation coefficient with portfolio

**Status:** Not implemented (requires interpretation, violates constitution)

---

### 5.3 Exposure Limits

**Hard Invariant I-E1:**
```
Exposure_total ≤ E × L_max
```

**Hard Invariant I-E2:**
```
Exposure_net ≤ E × L_max_net
```

Where `L_max_net < L_max` (e.g., 8x vs 10x)

**Purpose:** Limit directional risk

---

## 6. PARTIAL VS FULL EXIT RESOLUTION

### 6.1 Exit Decision Framework

**Given:** Position `P_s` with `D_liq_s < D_min_safe`

**Decision Variables:**
- `Q_exit` = Quantity to close
- `Exit_type` ∈ {FULL, PARTIAL}

---

### 6.2 Full Exit Conditions (Mandatory)

**Trigger FULL EXIT if:**

```
Condition FE-1: D_liq_s < D_critical
    where D_critical = 0.03 (3%)

Condition FE-2: Multiple symbols violating simultaneously
    count({s : D_liq_s < D_min_safe}) ≥ 2

Condition FE-3: Account equity drop > 20% from peak
    (E - E_peak) / E_peak < -0.20
```

**Action:**
```
Q_exit = Q_s  (close entire position)
```

---

### 6.3 Partial Exit Conditions (Allowed)

**Trigger PARTIAL EXIT if:**

```
Condition PE-1: Single symbol violation
    D_liq_s < D_min_safe AND count(violations) == 1

Condition PE-2: Liquidation distance improving
    dD_liq/dt > 0 (moving away from liquidation)

Condition PE-3: Not repeat violation
    last_violation_time(s) > T_cooldown (e.g., 5 minutes)
```

**Partial Reduction Amount:**
```
Q_exit = Q_s × reduction_factor

where reduction_factor ∈ [0.3, 0.7]  (30%-70% position reduction)
```

**Purpose:** Reduce exposure while maintaining position if recoverable

---

### 6.4 Exit Priority Ordering

**If multiple symbols require exit:**

```
Priority ranking:
1. D_liq_s (smallest first - most urgent)
2. |PnL_s| (largest loss first)
3. Exposure_s (largest exposure first)
```

**Sequential Processing:**
```
for symbol in sorted_by_priority:
    if still_violation(symbol):
        execute_exit(symbol)
        recalculate_exposure()
        if aggregate_safe():
            break  # Stop if portfolio safe
```

---

## 7. POSITION SIZING MATHEMATICS

### 7.1 Entry Size Calculation

**Given:**
- Available equity: `E_available`
- Target leverage: `L_target`
- Entry price: `P_entry`

**Maximum Position Size:**
```
Q_max = (E_available × L_target) / P_entry
```

**With Liquidation Safety:**
```
Q_safe = Q_max × (1 - safety_margin)

where safety_margin = 1 - (D_min_safe × L_target)
```

**Purpose:** Ensure position starts with safe liquidation buffer

---

### 7.2 Reduce Size Calculation

**Given:** REDUCE mandate for symbol `s`

**Current Exposure:**
```
Exposure_current = |Q_s × P_mark|
```

**Target Exposure (after reduction):**
```
Exposure_target = Exposure_current × (1 - reduction_pct)

where reduction_pct ∈ [0.3, 0.7]  (configurable)
```

**Quantity to Close:**
```
Q_reduce = Q_s × reduction_pct
```

---

## 8. MARGIN REQUIREMENT CALCULATIONS

### 8.1 Initial Margin

**Definition:**
```
IM_s = Exposure_s / L_actual
```

**Total Initial Margin:**
```
IM_total = Σ_s IM_s
```

---

### 8.2 Maintenance Margin

**Definition:**
```
MM_s = Exposure_s × MMR_s
```

Where `MMR_s` = exchange maintenance margin rate for symbol `s`

**Total Maintenance Margin:**
```
MM_total = Σ_s MM_s
```

---

### 8.3 Available Margin

**Definition:**
```
Margin_available = E - IM_total
```

**Hard Invariant I-M1:**
```
Margin_available ≥ 0
```

**If violated:**
```
→ BLOCK all ENTRY mandates
→ REDUCE or EXIT required
```

---

## 9. STRESS SCENARIOS & INVARIANTS

### 9.1 Simultaneous Adverse Move

**Scenario:** All positions move against simultaneously

**Maximum Loss (Worst Case):**
```
Loss_worst = Σ_s Exposure_s × max_move_pct

where max_move_pct = 10% (per symbol, 1-minute)
```

**Hard Invariant I-S1:**
```
E - Loss_worst ≥ MM_total × 1.5
```

**Purpose:** Survive 10% adverse move on all symbols

---

### 9.2 Flash Crash Protection

**Definition:** Mark price moves >15% in <1 second

**Hard Invariant I-S2:**
```
No position size shall exceed:
  Q_flash_safe = E × 0.5 / P_mark
```

**Purpose:** Prevent account wipeout on single flash crash

---

### 9.3 Exchange Halt Scenario

**Given:** Exchange halts trading for symbol `s`

**Constraint:**
```
Position must be closeable via other symbols if needed
```

**Hard Invariant I-S3:**
```
Exposure_s ≤ 0.3 × Exposure_total
```

**Purpose:** No single symbol dominates (max 30% exposure)

---

## 10. COMPUTATIONAL REQUIREMENTS

### 10.1 Required Calculations (Per Cycle)

**Mandatory Computations:**
1. `Exposure_total` = Σ_s |Q_s × P_mark|
2. `L_actual` = Exposure_total / E
3. `D_liq_s` for all active symbols
4. `R_liq` = min_s(D_liq_s)
5. `Margin_available` = E - IM_total

**Frequency:** Every mark price update (sub-second)

---

### 10.2 Constants (System Configuration)

**Hard Constants:**
```python
L_max = 10.0  # Maximum leverage
L_target = 8.0  # Operational target
L_symbol_max = 5.0  # Per-symbol limit
L_max_net = 8.0  # Net directional limit

D_min_safe = 0.08  # 8% minimum liquidation distance
D_critical = 0.03  # 3% immediate exit threshold
R_liq_min = 0.08  # Portfolio minimum

MMR_default = 0.005  # 0.5% maintenance margin (exchange varies)

reduction_pct_default = 0.5  # 50% default reduction
safety_factor = 0.7  # 70% of max loss tolerance
```

---

## 11. MANDATE IMPLICATIONS

### 11.1 ENTRY Mandate Validation

**Before accepting ENTRY:**

```python
def validate_entry(symbol, direction, size):
    # Check I-L1: Leverage constraint
    new_exposure = size × P_mark[symbol]
    if (Exposure_total + new_exposure) / E > L_max:
        return REJECT("Leverage limit violated")
    
    # Check I-L2: Per-symbol leverage
    if new_exposure > L_symbol_max × E:
        return REJECT("Symbol leverage limit violated")
    
    # Check I-M1: Margin available
    required_margin = new_exposure / L_actual
    if required_margin > Margin_available:
        return REJECT("Insufficient margin")
    
    # Check I-LA1: Post-entry liquidation safety
    estimated_D_liq = calculate_post_entry_liquidation_distance(...)
    if estimated_D_liq < D_min_safe:
        return REJECT("Insufficient liquidation buffer")
    
    return ACCEPT
```

---

### 11.2 REDUCE Mandate Execution

**REDUCE decreases exposure, always safe:**

```python
def execute_reduce(symbol, reduction_pct):
    Q_reduce = Q_s[symbol] × reduction_pct
    
    # Validate direction preservation
    if sign(Q_s[symbol] - Q_reduce) != sign(Q_s[symbol]):
        raise InvariantViolation("REDUCE changed direction")
    
    # Execute market close order
    close_position(symbol, Q_reduce)
    
    # Update exposure
    Q_s[symbol] -= Q_reduce
```

---

### 11.3 EXIT Mandate Execution

**EXIT closes entire position:**

```python
def execute_exit(symbol):
    # Full position close
    close_position(symbol, Q_s[symbol])
    
    # Reset position
    Q_s[symbol] = 0
    D_s[symbol] = FLAT
```

---

## 12. CONSTITUTIONAL ALIGNMENT

### 12.1 Determinism

**All calculations:**
- ✅ Pure functions of current state
- ✅ No randomness
- ✅ No interpretation
- ✅ No learning

**Risk math is constraint checking, not prediction.**

---

### 12.2 No Interpretation

**Forbidden:**
- ❌ "Market looks unsafe" → Use leverage calculation
- ❌ "High volatility" → Use liquidation distance
- ❌ "Probably will recover" → Use hard thresholds only

**Allowed:**
- ✅ `D_liq_s < D_min_safe` → EXIT
- ✅ `L_actual > L_max` → BLOCK ENTRY
- ✅ `Margin_available < 0` → REDUCE

---

### 12.3 Raw Data Only

**Inputs:**
- ✅ Account equity (exchange API)
- ✅ Mark prices (exchange feed)
- ✅ Position quantities (exchange API)
- ✅ Maintenance margin rates (exchange constants)

**No Derived Indicators:**
- ❌ Volatility estimates
- ❌ Correlation matrices
- ❌ Risk scores
- ❌ Confidence intervals

---

## 13. IMPLEMENTATION CHECKLIST

**Before System is Complete:**

- [ ] All constants defined in config
- [ ] Leverage calculation implemented
- [ ] Liquidation distance calculation implemented
- [ ] ENTRY validation logic implemented
- [ ] EXIT/REDUCE execution logic implemented
- [ ] Simultaneous multi-symbol exit priority
- [ ] Margin calculation verified against exchange
- [ ] Flash crash protection validated
- [ ] All invariants tested under stress

---

## 14. OPEN QUESTIONS (TO RESOLVE)

**Q1:** Exact MMR values per symbol (exchange-specific)  
**Q2:** Flash crash threshold (15% vs other)  
**Q3:** Cooldown period for repeat violations  
**Q4:** Reduction percentage configuration (30-70% range)  
**Q5:** Net exposure limit (needed or redundant with total?)

**Resolution Required Before:** Production deployment

---

## 15. FORMAL PROOF REQUIREMENTS

**Must Prove:**

**P1:** Under constraints I-L1, I-LA1, I-LA2, liquidation is impossible  
**P2:** REDUCE never changes direction (by construction)  
**P3:** EXIT always succeeds (may fail on exchange, but mandate valid)  
**P4:** No position can exceed L_symbol_max  
**P5:** Stress scenario I-S1 never violates margin requirements

**Method:** Formal verification (next phase)

---

END OF RISK MATHEMATICS SPECIFICATION
