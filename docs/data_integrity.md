# Data Integrity Protocol

## Problem Statement

**Historical data contamination** occurs when:
- Symbol scope changes (expansion or reduction)
- Data from multiple scope regimes mixes in persistence layer
- Baselines aggregate across incompatible datasets

This invalidates all statistical calculations.

## Decontamination Protocol

### When to Decontaminate

Run decontamination **any time** the `TOP_10_SYMBOLS` set changes.

Examples:
- Adding a new symbol
- Removing a symbol
- Replacing one symbol with another

### How to Decontaminate

#### Step 1: Stop All Processes
```bash
# Stop collector
pkill -f market_event_collector.py

# Stop API server
pkill -f api_server.py
```

#### Step 2: Run Decontamination Script
```bash
cd scripts
python decontaminate_db.py
```

This script:
1. Backs up current data to `data/backups/pre_decontamination_<timestamp>/`
2. Filters all parquet files to `TOP_10_SYMBOLS` only
3. Writes atomically (no partial updates)
4. Validates row counts before/after
5. Reports purged vs retained data

#### Step 3: Restart Processes
```bash
# Restart collector (fresh state)
python market_event_collector.py &

# Restart API server (fresh detectors)
python api_server.py &
```

#### Step 4: Verify
- Check detector count == `len(TOP_10_SYMBOLS)`
- Check UI symbol dropdown shows only TOP_10
- Check no non-TOP_10 symbols in parquet files

### Validation

After decontamination, verify data integrity:

```python
import pandas as pd
from symbol_config import TOP_10_SYMBOLS

df = pd.read_parquet("../data/v1_live_validation/market_events/market_events.parquet")
symbols_in_data = set(df["symbol"].unique())

assert symbols_in_data.issubset(TOP_10_SYMBOLS), f"Contamination detected: {symbols_in_data - TOP_10_SYMBOLS}"
```

## Baseline Warmup Impact

**Critical**: After decontamination, all baselines must re-warm.

- **Minimum**: 10 windows (10 seconds at 1s granularity)
- **Optimal**: 60 windows (60 seconds)
- **Expected Behavior**: Zero Peak Pressure events until baselines warm

This is **correct** behavior, not a bug.

## Backup Policy

Decontamination creates automatic backups at:
```
data/backups/pre_decontamination_YYYYMMDD_HHMMSS/
```

**Retention**: Keep backups for at least 7 days before manual deletion.

## Related Documentation

- [Symbol Scope Policy](system_scope.md): Why TOP_10 is hard-coded
- [CHANGELOG.md](../CHANGELOG.md): Version history
