# Constitutional Execution System - Operator Manual

**Version:** 1.0
**Date:** 2026-01-14
**Status:** Operational Guide for Ghost Trading Calibration

---

## Overview

This manual guides operators through the empirical threshold calibration workflow (Stages 1A, 1B, and 2). The goal is to establish data-driven threshold values for policy strategies that balance selectivity and outcome diversity.

**Prerequisites:**
- All 19 M4 primitives computing (verify with `python check_primitives_quick.py`)
- Ghost trading functional (entry/exit lifecycle complete)
- Database accessible (`logs/execution.db`)
- No blocking issues from `MISSING_COMPONENTS_AUDIT.md`

---

## Stage 1A: Baseline Collection (24-48 hours)

### Purpose

Establish primitive value distributions to understand what's "typical" vs "exceptional" in normal market conditions.

### Configuration

**File:** `external_policy/ep2_strategy_geometry.py`

Set trivially permissive thresholds to allow all conditions:

```python
def _entry_conditions_met(self, bundle: M4PrimitiveBundle) -> bool:
    """Permissive Stage 1A configuration."""

    # Zone penetration: any non-zero depth
    zone_ok = (bundle.zone_penetration is not None and
               bundle.zone_penetration.penetration_depth > 0)

    # Traversal compactness: any non-zero ratio
    compact_ok = (bundle.traversal_compactness is not None and
                  bundle.traversal_compactness.compactness_ratio > 0)

    # Central tendency: any non-zero deviation
    deviation_ok = (bundle.central_tendency_deviation is not None and
                    bundle.central_tendency_deviation.deviation_value > 0)

    return zone_ok and compact_ok and deviation_ok
```

### Execution

```bash
# Start collector
python runtime/native_app/main.py

# Expected behavior:
# - Continuous primitive computation
# - Frequent ENTRY/EXIT mandates (system explores all conditions)
# - Ghost trades with short holding periods
```

### Monitoring

```bash
# Check primitive computation rates (every 10 minutes)
python check_primitives_quick.py

# Expected output:
# displacement_anchor_dwell_time:  90%
# zone_penetration_depth:          90%
# price_velocity:                  90%
# traversal_compactness:           90%
# central_tendency_deviation:      90%
# directional_continuity_value:    90%
# trade_burst_count:               90%

# Check database growth
ls -lh logs/execution.db  # Should grow steadily

# Check ghost trades
sqlite3 logs/execution.db "SELECT COUNT(*) FROM ghost_trades WHERE pnl IS NOT NULL;"
# Expected: 100+ completed trades after 24h
```

### Stopping Criteria

Stop Stage 1A when ALL conditions met:

✅ **Minimum 10,000 cycles** with all 3 core primitives computed
✅ **Minimum 1,000 samples** per symbol
✅ **Coverage of 3+ volatility regimes** (low/med/high price movement)
✅ **Zero time regressions** (system hasn't halted)
✅ **Primitive success rate > 95%** (check with quick script)

**Typical Duration:** 24-48 hours

---

## Stage 1A Analysis: Extract Percentile Distributions

### Script

```bash
# Extract percentile distributions
python scripts/analyze_stage_1a_distributions.py
```

### Output Format

```
=================================================================
STAGE 1A PERCENTILE DISTRIBUTIONS
=================================================================

Symbol: BTC
Samples: 15,234

zone_penetration.penetration_depth:
  P1:   $0.50    P25:  $125.50    P50:  $285.20    P75:  $512.80    P95:  $895.40    P99:  $1425.60

traversal_compactness.compactness_ratio:
  P1:   0.05     P25:  0.28       P50:  0.52       P75:  0.72       P95:  0.88       P99:  0.94

central_tendency_deviation.deviation_value:
  P1:   $0.10    P25:  $0.85      P50:  $1.75      P75:  $3.20      P95:  $8.50      P99:  $18.20

... (repeat for all symbols)
```

### Interpretation

- **P50 (median)**: Typical value in normal conditions
- **P75**: Moderately elevated
- **P90**: Strong condition (1 in 10 cycles)
- **P95**: Very strong condition (1 in 20 cycles)
- **P99**: Extreme condition (1 in 100 cycles)

**No interpretation claims allowed.** These are factual percentiles only.

---

## Stage 1B: Test Thresholds (12-24 hours)

### Purpose

Generate actual ghost trades with low frequency to enable outcome attribution. Use restrictive thresholds from Stage 1A distributions.

### Configuration

**Starting Test Thresholds:** Use P95 from Stage 1A

```python
def _entry_conditions_met(self, bundle: M4PrimitiveBundle) -> bool:
    """Stage 1B test configuration (P95 thresholds from Stage 1A)."""

    # Example values from Stage 1A BTC analysis:
    P95_ZONE_DEPTH = 895.40  # dollars
    P95_COMPACTNESS = 0.88  # ratio
    P95_DEVIATION = 8.50  # dollars

    zone_ok = (bundle.zone_penetration is not None and
               bundle.zone_penetration.penetration_depth > P95_ZONE_DEPTH)

    compact_ok = (bundle.traversal_compactness is not None and
                  bundle.traversal_compactness.compactness_ratio > P95_COMPACTNESS)

    deviation_ok = (bundle.central_tendency_deviation is not None and
                    bundle.central_tendency_deviation.deviation_value > P95_DEVIATION)

    return zone_ok and compact_ok and deviation_ok
```

### Execution

```bash
# Update thresholds in strategy files
# Restart collector
python runtime/native_app/main.py

# Expected behavior:
# - Sparse ENTRY mandates (< 10 per hour)
# - Ghost trades with longer holding periods
# - EXIT mandates generating (verify != 0)
```

### Monitoring

```bash
# Check trade frequency
sqlite3 logs/execution.db "SELECT COUNT(*) FROM ghost_trades WHERE entry_ts > $(date +%s -d '1 hour ago');"
# Expected: < 10 trades/hour

# Check EXIT mandate generation (CRITICAL)
sqlite3 logs/execution.db "SELECT COUNT(*) FROM mandates WHERE mandate_type='EXIT';"
# Expected: > 0 (if zero, EXIT logic is broken - BLOCK STAGE 2)

# Check outcome diversity
sqlite3 logs/execution.db "SELECT
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
    COUNT(*) as total
FROM ghost_trades WHERE pnl IS NOT NULL;"

# Expected: 30-70% win rate (avoid all wins or all losses)
```

### Stopping Criteria

Stop Stage 1B when ALL conditions met:

✅ **Minimum 100 completed ghost trades** (entry + exit pairs)
✅ **Minimum 10 trades per symbol**
✅ **Outcome diversity:** At least 30% wins AND 30% losses
✅ **Trade frequency < 10 per hour** (demonstrates selectivity)
✅ **EXIT mandates generating** (> 0 exits observed)
✅ **Maximum 7 days runtime** (avoid overfitting to single regime)

**Typical Duration:** 12-24 hours (depends on threshold restrictiveness)

**CRITICAL BLOCKER:** If EXIT mandates = 0, STOP and fix EXIT logic before proceeding to Stage 2.

---

## Stage 2: Threshold Sweep (7-14 days)

### Purpose

Test 125 threshold combinations to identify Pareto-optimal configurations balancing selectivity, outcome diversity, and holding duration consistency.

### Configuration Grid

Test 5 levels per primitive (P50, P70, P85, P95, P99):

```python
# From Stage 1A percentiles
THRESHOLDS = {
    'BTC': {
        'zone_penetration': [285.20, 512.80, 750.00, 895.40, 1425.60],  # P50, P75, P85, P95, P99
        'compactness': [0.52, 0.72, 0.82, 0.88, 0.94],
        'deviation': [1.75, 3.20, 5.50, 8.50, 18.20]
    },
    # ... repeat for all symbols
}

# Total configurations: 5 × 5 × 5 = 125
```

### Implementation: Adaptive Pruning (Recommended)

**Method:** Rotate through configurations, eliminate underperformers

```bash
# Day 0: Start with all 125 configurations
python scripts/run_threshold_sweep.py --mode adaptive --duration 14d

# Adaptive pruning schedule:
# Day 1: Eliminate bottom quartile (31 configs) by trade count
# Day 2: Eliminate another quartile (31 configs)
# Days 3-14: Focus on top 63 configurations
```

**Alternative: Time-Sliced Rotation**

```bash
# Rotate through all 125 configs every 2 hours
# Each config gets 2-hour sample every 250 hours
python scripts/run_threshold_sweep.py --mode rotation --slice 2h --duration 14d
```

### Monitoring

```bash
# Check current configuration
tail -f logs/threshold_sweep.log

# Check per-configuration metrics
sqlite3 logs/execution.db "SELECT
    config_id,
    COUNT(*) as trades,
    AVG(pnl) as avg_pnl,
    AVG(holding_duration_sec) as avg_hold
FROM ghost_trades
GROUP BY config_id
ORDER BY avg_pnl DESC
LIMIT 10;"
```

### Data Collection Per Configuration

```sql
-- Metrics tracked automatically
CREATE TABLE IF NOT EXISTS threshold_configs (
    config_id INTEGER PRIMARY KEY,
    zone_threshold REAL,
    compactness_threshold REAL,
    deviation_threshold REAL,
    trade_count INTEGER,
    win_rate REAL,
    avg_pnl REAL,
    total_pnl REAL,
    pnl_stddev REAL,
    avg_holding_duration_sec REAL,
    mandate_generation_rate REAL,
    arbitration_pass_rate REAL
);
```

### Stopping Criteria

Stop Stage 2 when:

✅ **Each configuration:** Minimum 20 completed trades OR 48 hours runtime
✅ **Overall:** 80% of configurations meet minimum sample size
✅ **Time limit:** 14 days maximum (hard stop)

**Typical Duration:** 7-14 days

---

## Post-Sweep Analysis: Pareto Frontier

### Objective Functions (Non-Interpretive)

1. **Selectivity:** Minimize mandates per hour
2. **Outcome Diversity:** Balance wins/losses (aim for 40-60% win rate)
3. **Duration Consistency:** Minimize holding duration variance

### Run Analysis

```bash
python scripts/analyze_pareto_frontier.py
```

### Output

```
=================================================================
PARETO FRONTIER CONFIGURATIONS
=================================================================

Non-dominated configurations (sorted by avg_pnl descending):

Config ID: 42
  Zone:        P95 ($895.40)
  Compactness: P85 (0.82)
  Deviation:   P90 ($5.50)
  ---
  Trades:      156
  Win Rate:    52.5%
  Avg PNL:     $12.30
  Hold Duration: 1245s (σ=320s)
  Mandates/hour: 2.3

Config ID: 71
  Zone:        P99 ($1425.60)
  Compactness: P95 (0.88)
  Deviation:   P85 ($5.50)
  ---
  Trades:      89
  Win Rate:    48.3%
  Avg PNL:     $18.70
  Hold Duration: 2100s (σ=560s)
  Mandates/hour: 1.1

... (3-5 total non-dominated configs)
```

### Selection

**Operator Decision:** Choose from Pareto frontier based on operational constraints:
- **Higher selectivity** (fewer mandates) → Choose configs with P95-P99 thresholds
- **More data** (more trades) → Choose configs with P85-P90 thresholds
- **Consistency** (lower variance) → Choose configs with low hold duration σ

**No automated selection.** Human operator decides based on system goals.

---

## Validation: Hold-Out Testing

### Purpose

Verify selected thresholds generalize to unseen data (different time period).

### Method

```bash
# Use last 25% of Stage 2 data as validation set
python scripts/validate_threshold_config.py --config_id 42 --validation_split 0.25
```

### Pass Conditions

✅ **Trade frequency within 50%** of training frequency
✅ **Outcome distributions not significantly different** (K-S test, p > 0.05)
✅ **Mandate generation rate stable** (within 40%)

### If Validation Fails

1. **Regime shift:** Market conditions changed (expected, document)
2. **Overfitting:** Extend training period or choose more robust config
3. **Invalid assumptions:** Revisit threshold selection criteria

---

## Emergency Procedures

### System Halts with Time Regression

**Symptom:** `Time Regression: <timestamp> < <system_time>` error

**Cause:** WebSocket timestamp out of order (constitutional violation)

**Action:**
```bash
# SYSTEM WILL AUTO-HALT (by design)
# Restart collector - time will reset
python runtime/native_app/main.py
```

### Zero EXIT Mandates (Stage 1B/2)

**Symptom:** `SELECT COUNT(*) FROM mandates WHERE mandate_type='EXIT'` returns 0

**Cause:** EXIT logic not functional

**Action:** BLOCK STAGE 2. Fix EXIT conditions in strategy policies.

**Files to Check:**
- `external_policy/ep2_strategy_geometry.py` (lines 100-120)
- `external_policy/ep2_strategy_kinematics.py`
- `external_policy/ep2_strategy_absence.py`

### Database Lock Error

**Symptom:** `sqlite3.OperationalError: database is locked`

**Cause:** Multiple processes accessing logs/execution.db

**Action:**
```bash
# Stop all python processes
taskkill /F /IM python.exe

# Remove lock file
rm logs/execution.db-wal

# Restart
python runtime/native_app/main.py
```

### Primitives Stop Computing

**Symptom:** `check_primitives_quick.py` shows 0% rates

**Cause:** M1 ingestion failure or M3 temporal issue

**Action:**
```bash
# Check M1 trade buffer
sqlite3 logs/execution.db "SELECT symbol, COUNT(*) FROM primitive_values WHERE zone_penetration_depth IS NOT NULL GROUP BY symbol;"

# If all zeros, check collector logs for ingestion errors
# Restart collector
```

---

## Verification Commands

### Stage 1A Checklist

```bash
# 1. Cycles processed
sqlite3 logs/execution.db "SELECT MAX(cycle_id) FROM primitive_values;"
# Expected: > 10,000

# 2. Samples per symbol
sqlite3 logs/execution.db "SELECT symbol, COUNT(*) FROM primitive_values WHERE zone_penetration_depth IS NOT NULL GROUP BY symbol;"
# Expected: > 1,000 per symbol

# 3. Primitive success rates
python check_primitives_quick.py
# Expected: > 95% for core primitives

# 4. Time regressions
grep "Time Regression" logs/collector.log
# Expected: 0 occurrences
```

### Stage 1B Checklist

```bash
# 1. Completed trades
sqlite3 logs/execution.db "SELECT COUNT(*) FROM ghost_trades WHERE pnl IS NOT NULL;"
# Expected: > 100

# 2. Trades per symbol
sqlite3 logs/execution.db "SELECT symbol, COUNT(*) FROM ghost_trades WHERE pnl IS NOT NULL GROUP BY symbol;"
# Expected: > 10 per symbol

# 3. Exit mandates
sqlite3 logs/execution.db "SELECT COUNT(*) FROM mandates WHERE mandate_type='EXIT';"
# Expected: > 0 (CRITICAL)

# 4. Trade frequency
sqlite3 logs/execution.db "SELECT COUNT(*) / ((MAX(entry_ts) - MIN(entry_ts)) / 3600.0) as trades_per_hour FROM ghost_trades WHERE entry_ts IS NOT NULL;"
# Expected: < 10 trades/hour
```

### Stage 2 Checklist

```bash
# 1. Configurations tested
sqlite3 logs/execution.db "SELECT COUNT(DISTINCT config_id) FROM threshold_configs;"
# Expected: 125 (or 63 after pruning)

# 2. Sample sizes
sqlite3 logs/execution.db "SELECT config_id, trade_count FROM threshold_configs WHERE trade_count < 20;"
# Expected: < 20% of configs

# 3. Pareto frontier
python scripts/analyze_pareto_frontier.py | grep "Non-dominated:"
# Expected: 3-5 configurations
```

---

## Appendix A: File Locations

### Scripts

```
scripts/
├── analyze_stage_1a_distributions.py  # Percentile extraction
├── run_threshold_sweep.py             # Stage 2 execution
├── analyze_pareto_frontier.py         # Multi-objective optimization
└── validate_threshold_config.py       # Hold-out validation
```

### Strategy Policies (Manual Threshold Updates)

```
external_policy/
├── ep2_strategy_geometry.py     # Zone/compactness/deviation thresholds
├── ep2_strategy_kinematics.py   # Velocity/acceptance thresholds
└── ep2_strategy_absence.py      # Absence/persistence thresholds
```

### Monitoring

```
logs/
├── execution.db                 # Primary data store
├── collector.log                # System log
└── threshold_sweep.log          # Stage 2 configuration log
```

---

## Appendix B: Constitutional Compliance

**This manual does NOT:**
- ❌ Claim thresholds are "optimal", "good", or "correct"
- ❌ Predict future trading performance
- ❌ Interpret primitive values as "signals"
- ❌ Score configurations as "better" or "worse"
- ❌ Guarantee profitability

**This manual ONLY:**
- ✅ Describes factual data collection procedures
- ✅ Provides statistical analysis methods
- ✅ Documents empirical testing protocols
- ✅ Lists verification commands
- ✅ Presents decision support data without recommendations

**Silence Rule:** If convergence not achieved, report "insufficient data" NOT "system broken".

---

## Appendix C: Glossary

- **Baseline Collection (Stage 1A):** Gathering primitive value distributions without restrictive filtering
- **Percentile (P95):** Value below which 95% of observations fall
- **Test Thresholds (Stage 1B):** Restrictive threshold values from Stage 1A used to generate sparse trades
- **Threshold Sweep (Stage 2):** Systematic testing of multiple threshold combinations
- **Pareto Frontier:** Set of non-dominated configurations (no single objective can improve without worsening another)
- **Hold-Out Validation:** Testing threshold performance on unseen time period
- **Outcome Diversity:** Avoiding all-win or all-loss scenarios (aim for balanced results)
- **Selectivity:** Trade frequency (mandates per hour)

---

## Appendix D: Support

**Before reporting issues:**
1. Run verification commands from this manual
2. Check logs/collector.log for errors
3. Verify database integrity with `sqlite3 logs/execution.db ".schema"`

**For frozen layer modifications:**
- See: `docs/CODE_FREEZE.md`
- Requires logged evidence from live runs

**For constitutional interpretation:**
- See: `docs/EPISTEMIC_CONSTITUTION.md`
- See: `docs/SYSTEM_CANON.md`

**This system is frozen by design. Stability > features.**
