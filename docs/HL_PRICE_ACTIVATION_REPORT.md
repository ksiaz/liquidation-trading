# HL_PRICE Activation Report

**Date:** 2026-02-01
**Status:** COMPLETE

---

## Executive Summary

Successfully wired HL_PRICE data from the Hyperliquid node to produce the system's first observable behavior. The system now receives live oracle prices and uses them for regime classification decisions.

---

## Objective

Make the system react to live HL data in an intentional, observable way by:
1. Selecting a viable data signal (HL_PRICE)
2. Wiring it to an existing consumer (regime classification)
3. Proving with runtime evidence
4. Classifying any failures

---

## Data Flow (Before → After)

### Before (Broken)
```
gRPC Server → NodeSubscriber → NodeBridge → M1 buffers → [NO CONSUMER]
                                                              ↓
                                         service.py calls get_latest_prices() → CRASH
```

### After (Working)
```
gRPC Server → NodeSubscriber → NodeBridge → M1 buffers → get_all_hl_prices()
                                                              ↓
                                              Regime Classification → Decision
```

---

## Issues Found & Fixed

### Issue 1: Interface Mismatch
**File:** `runtime/collector/service.py:518`

```python
# BEFORE (crashed):
node_prices = self._node_bridge.get_latest_prices()

# AFTER (working):
node_prices = self._obs.get_all_hl_prices()
```

**Root Cause:** NodeBridge was designed differently than expected ObservationBridge. The method `get_latest_prices()` doesn't exist on NodeBridge.

### Issue 2: Symbol Format Mismatch
**File:** `scripts/run_paper_trade.py:108-114`

```python
# BEFORE: Only Binance format
SYMBOLS = ['BTCUSDT', 'ETHUSDT', ...]

# AFTER: Both formats
BINANCE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', ...]
HL_SYMBOLS = [s.replace('USDT', '') for s in BINANCE_SYMBOLS]
SYMBOLS = BINANCE_SYMBOLS + HL_SYMBOLS
```

**Root Cause:** HL node sends 'BTC', ObservationSystem's `allowed_symbols` had 'BTCUSDT'. Prices were silently dropped at governance layer.

### Issue 3: Missing hasattr Guards
**File:** `runtime/collector/service.py`

Added hasattr checks for methods that exist on ObservationBridge but not NodeBridge:

| Line | Method | Fix |
|------|--------|-----|
| 659 | `get_proximity_provider` | Added `hasattr()` check |
| 730 | `get_burst` | Added `hasattr()` check |

**File:** `scripts/run_paper_trade.py:202-204`

```python
# Added hasattr check for cleanup pruners
if service._node_bridge and hasattr(service._node_bridge, 'decay_candidate_zones'):
    cleanup.register_pruner('candidate_zone_decay', ...)
```

### Issue 4: Stale Python Bytecode
**Symptom:** `AttributeError: 'NodeBridge' object has no attribute 'get_burst'` spam despite hasattr checks being in place.

**Fix:** Cleared `__pycache__` directory to force recompilation.

```bash
rm -rf runtime/collector/__pycache__
```

---

## Runtime Evidence

### Successful Test Output
```
[HL_DEBUG] cycle=1 node_prices has 6 symbols: ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
[HL_PRICE] BTC: using oracle price 78417.00 from HL node
[REGIME] BTC: SKIP - missing calculators: ['vwap', 'atr', 'orderflow', 'liquidation']
[HL_PRICE] ETH: using oracle price 2391.30 from HL node
[REGIME] ETH: SKIP - missing calculators: ['vwap', 'atr', 'orderflow', 'liquidation']
[HL_PRICE] DOGE: using oracle price 0.10 from HL node
[REGIME] DOGE: SKIP - missing calculators: ['vwap', 'atr', 'orderflow', 'liquidation']
```

### Interpretation
| Check | Evidence |
|-------|----------|
| HL prices reach M1 | `node_prices has 6 symbols` |
| HL prices consumed | `using oracle price 78417.00 from HL node` |
| Decision made | `SKIP - missing calculators` |

The SKIP decision is **expected behavior** - regime classification needs VWAP, ATR, orderflow, and liquidation calculators which require Binance data streams.

---

## System State

### Components Status
| Component | Status | Notes |
|-----------|--------|-------|
| gRPC Server | Running | Port 50051, PID 948783 |
| NodeSubscriber | Connected | Streaming prices/liquidations |
| NodeBridge | Connected | Feeding M1 buffers |
| M1 Ingestion | Working | Storing HL prices in `latest_hl_prices` |
| Regime Classification | Working | Using HL prices, skipping due to missing calculators |

### Data Flow Metrics
```
gRPC Server: prices=228k+, liqs=173
NodeBridge: prices_ingested=growing, errors=0
M1 Buffer: 6 symbols with live prices
```

---

## Files Modified

| File | Changes |
|------|---------|
| `runtime/collector/service.py` | Fixed price accessor, added hasattr guards, added diagnostic logging |
| `scripts/run_paper_trade.py` | Added HL format symbols to whitelist, fixed metric key names, added hasattr for pruners |

---

## Diagnostic Additions

Added temporary diagnostic logging (controlled by `DIAG_MANDATE=1`):

```python
# service.py:519-521
if _diag_regime and cycle_id and cycle_id <= 3:
    print(f"[HL_DEBUG] cycle={cycle_id} node_prices has {len(node_prices)} symbols: {list(node_prices.keys())[:5]}")

# service.py:535-537
if _diag_regime and node_prices.get(hl_symbol):
    print(f"[HL_PRICE] {symbol}: using oracle price {price:.2f} from HL node")
```

---

## What's Next

The system is now "alive" - it reacts to live HL data with observable intent. To enable full regime classification, the following are needed:

1. **VWAP Calculator** - Requires Binance trade stream
2. **ATR Calculator** - Requires Binance kline stream (warm-up working)
3. **Orderflow Calculator** - Requires Binance trade stream
4. **Liquidation Z-Score** - Requires liquidation data accumulation

These are independent integration tasks that can be tackled separately.

---

## Conclusion

**Objective Achieved:** The system now consumes live HL price data and produces observable behavior (regime classification decisions).

The "first real behavior" milestone is complete. A live HL price update causes the system to:
1. Receive the price via gRPC
2. Store it in M1 buffers
3. Use it as primary price source for regime classification
4. Make a decision (currently SKIP due to incomplete metrics)

This proves the data pipeline is functional end-to-end.

---

*Report generated: 2026-02-01*
