# Symbol Scope Policy v1.0

## Overview

The Peak Pressure detection system intentionally monitors a fixed set of the **top-10 futures symbols by trading volume**.

This is a **stability and correctness constraint**, not a limitation.

## Current Scope

```python
TOP_10_SYMBOLS = {
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "MATICUSDT",
}
```

**Source of Truth**: `scripts/symbol_config.py`

## Rationale

### 1. Prevent Cross-Symbol Contamination
- Baselines aggregate data over time per symbol
- Mixing hundreds of symbols creates invalid statistical distributions
- Contaminated baselines lead to false positives/negatives

### 2. Ensure Meaningful Baselines
- Baseline warmup requires minimum 60 windows of data
- Low-volume symbols produce sparse, unreliable baselines
- TOP_10 symbols have sufficient activity for statistical validity

### 3. Reduce Failure Modes
- High-cardinality persistence causes file lock contention (Windows)
- Hundreds of WebSocket connections increase connection failures
- More symbols = more debugging surface area

### 4. Enable Deterministic Debugging
- With 10 symbols, all events can be traced
- Reproducible test cases possible
- Clear cause-effect relationships

## Enforcement

The allowlist is enforced at **all ingestion entry points**:

| Layer | File | Methods |
|-------|------|---------|
| Collector | `market_event_collector.py` | `log_trade()`, `log_liquidation()`, `log_kline()`, `log_oi()` |
| Detector | `peak_pressure_detector.py` | `process_trade()`, `process_liquidation()`, `process_kline()`, `process_oi()` |
| API | `api_server.py` | Event processor loop |

**Behavior**: Events for non-TOP_10 symbols are **silently dropped** (no logging, no counters).

## Expansion Policy

Adding new symbols requires:

1. **Code Change**: Update `TOP_10_SYMBOLS` in `symbol_config.py`
2. **Data Migration**: Run `decontaminate_db.py` to purge non-allowed historical data
3. **Runtime Reset**: Restart collector + API server
4. **Verification**: Confirm detector count matches allowlist size

**No dynamic configuration**. **No environment overrides**. This is intentional.

## Related Documentation

- [Data Integrity](data_integrity.md): Decontamination protocol
- [CHANGELOG.md](../CHANGELOG.md): Version history
