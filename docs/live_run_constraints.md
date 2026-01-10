# Live Run Constraints & Recovery Procedures

## Symbol Whitelist Policy

### TOP 10 Dynamic Selection

The system **automatically selects the TOP 10 USDT-margined perpetuals by 24h quote volume** at startup.

**Why TOP 10 only:**
1. **Baseline Validity**: Low-liquidity symbols produce sparse, unreliable baselines
2. **Cross-Symbol Contamination**: Mixing 100+ symbols creates invalid statistical distributions
3. **Failure Mode Reduction**: High cardinality causes Windows file locking issues
4. **Debugging Surface Area**: 10 symbols allows complete event traceability

**Selection Method:**
```python
# Query Binance Futures 24h ticker
GET /fapi/v1/ticker/24hr

# Filter to USDT perpetuals
# Sort by quoteVolume descending
# Select TOP 10
```

**Fallback**: If API query fails, system falls back to known high-liquidity symbols:
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT
- ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT, MATICUSDT

### Enforcement

**DROP Rule**: Any event where `symbol NOT IN TOP_10_SYMBOLS` is **silently dropped**.

Applies to:
- Trades
- Liquidations
- Klines (1s)
- Open Interest

**No exceptions. No logging spam. No baseline updates.**

---

## Symbol Isolation Invariants

### Fundamental Rule

**NO object, buffer, window, baseline, or counter may EVER aggregate across symbols.**

### Canonical Structure

```python
state[symbol][window_size][component]
```

Every stateful structure must be keyed by symbol first:
```python
detectors_by_symbol: Dict[str, PeakPressureDetector] = {}
detector = detectors_by_symbol[symbol]
detector.process_event(event)
```

### Runtime Guards

Every `process_*` method has:
```python
assert event.symbol == self.symbol, f"Symbol leak: got {event.symbol}, expected {self.symbol}"
```

**Crash fast if violated** (indicates architectural bug).

---

## What Constitutes "Data Contamination"

### Definition

Data contamination occurs when:
1. **Cross-symbol mixing**: Events from symbol A aggregate with events from symbol B
2. **Scope mixing**: Historical data from different symbol allowlists coexist
3. **Invalid baselines**: P90/P95 thresholds calculated across incompatible datasets

### Symptoms

- Liquidations appear then disappear
- Trade quantities intermittently zero
- Peak Pressure never triggers (baselines invalid)
- Parquet write failures (high cardinality)
- UI counters inconsistent with backend

### Root Causes

- No symbol filtering at ingestion
- Shared global windows/buffers
- Persistence from 100+ symbols
- Dynamic symbol expansion without cleanup

---

## Recovery Procedure (Database Decontamination)

### When to Run

**ANY TIME** the `TOP_10_SYMBOLS` set changes:
- Adding a symbol
- Removing a symbol  
- Changing selection criteria
- After detecting contamination symptoms

### Step-by-Step Protocol

#### 1. Stop All Processes
```bash
# Windows PowerShell
Stop-Process -Name python -Force
```

#### 2. Run Decontamination Script
```bash
cd scripts
python decontaminate_db.py
```

**What it does:**
- Backs up current data to `data/backups/pre_decontamination_<timestamp>/`
- Filters all parquet files to `TOP_10_SYMBOLS` only
- Writes atomically (no partial updates)
- Validates row counts before/after
- Reports purged vs retained data

#### 3. Restart Processes
```bash
# Terminal 1: Collector
cd scripts
python market_event_collector.py

# Terminal 2: API Server
cd ui/backend
python api_server.py
```

#### 4. Verify Clean State

**Expected behaviors:**
- Collector prints: "Fetched TOP 10 symbols by 24h volume"
- API server prints: "Initialized 10 detectors for TOP_10_SYMBOLS"
- UI shows exactly 10 symbols
- No parquet write errors in logs

**Baseline warmup:**
- Minimum: 10 windows (10 seconds)
- Optimal: 60 windows (60 seconds)
- **Expected: Zero Peak Pressure events until baselines warm**

This is **correct** behavior, not a bug.

---

## Silent Operation is Normal

### Expected Behavior

Under normal market conditions, the system **will remain silent**.

Peak Pressure detection requires **ALL 4 conditions simultaneously**:
1. Trade flow surge (abs_flow >= P90)
2. Large trade participation (count >= 1)
3. Compression OR expansion (P95 band touch)
4. External stress (liquidations OR OI delta)

**This is rare** (~0.1-1% of 1s windows).

### What to Check

If system is silent for extended periods:

1. **Baseline Warmup**: Check `/api/market/stats`
   - `baselines_warm` should equal 10
   - If < 10, wait longer

2. **Condition Failures**: Check `condition_failures` breakdown
   - `stress` being high is normal (most common failure)

3. **Data Ingestion**: Check collector logs
   - Should see `[TRADES] Connected: BTCUSDT` etc.
   - Should see `[DEBUG] LIQUIDATION Raw: X -> Parsed: Y`

**Do NOT:**
- Lower thresholds to "make it visible"
- Aggregate across symbols to inflate counts
- Silence errors to hide contamination

---

## Validation Checklist

### After Decontamination

```python
import pandas as pd
from symbol_config import TOP_10_SYMBOLS

df = pd.read_parquet("../data/v1_live_validation/market_events/market_events.parquet")
symbols_in_data = set(df["symbol"].unique())

# MUST pass
assert symbols_in_data.issubset(TOP_10_SYMBOLS), \
    f"Contamination detected: {symbols_in_data - TOP_10_SYMBOLS}"
```

### Runtime Health

- Detector count == 10
- No non-TOP_10 symbols in UI
- Liquidations persist across refresh
- Trade quantities > 0
- No parquet exceptions in logs

---

## Backup Policy

**Automatic backups** created at:
```
data/backups/pre_decontamination_YYYYMMDD_HHMMSS/
```

**Retention**: Keep for at least 7 days before manual deletion.

---

## Related Documentation

- [Symbol Scope Policy](system_scope.md): Rationale for TOP_10 constraint
- [Data Integrity Protocol](data_integrity.md): Decontamination details
- [CHANGELOG.md](../CHANGELOG.md): Version history
