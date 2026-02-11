# HL_PRICE ACTIVATION PLAN

**Date:** 2026-02-01
**Purpose:** Wire HL_PRICE to produce first observable behavior
**Type:** Minimal Activation (No New Components)

---

## SELECTED SIGNAL

**HL_PRICE** (oracle prices from Hyperliquid node)

**Why:** Only viable live data lane. Liquidations cannot produce behavior (cascade primitives require position data that doesn't exist).

---

## SELECTED BEHAVIOR

**Regime Classification Update**

**Why:**
1. Code already exists to consume HL prices (`service.py:517-529`)
2. Only blocked by one broken method call
3. Even partial execution proves system consumed the data

---

## EXACT SOURCE

**File:** `observation/internal/m1_ingestion.py`
**Function:** `normalize_hl_price()` (lines 449-495)
**Storage:** `self.latest_hl_prices[symbol]`

```python
# Line 484-488
self.latest_hl_prices[symbol] = {
    'oracle_price': event['oracle_price'],
    'mark_price': event['mark_price'],
    'timestamp': event['timestamp']
}
```

**Accessor:** `observation/governance.py:246-252`
```python
def get_all_hl_prices(self) -> Dict[str, float]:
    return self._m1.get_all_hl_prices()
```

---

## EXACT CONSUMER

**File:** `runtime/collector/service.py`
**Function:** `_execute_m6_cycle()` (lines 517-529)

```python
# Current (broken):
if self._node_bridge:
    node_prices = self._node_bridge.get_latest_prices()  # LINE 518 - CRASHES

# Used by (lines 522-529):
for symbol in snapshot.symbols_active:
    hl_symbol = symbol.replace('USDT', '')
    price = node_prices.get(hl_symbol) or self._current_prices.get(symbol)
    if price is None:
        print(f"[REGIME] {symbol}: SKIP - no price", flush=True)
        continue
```

---

## MINIMAL WIRING

**Total Lines Changed: 2**

### Change 1: service.py line 518

```python
# BEFORE:
node_prices = self._node_bridge.get_latest_prices()

# AFTER:
node_prices = self._obs.get_all_hl_prices()
```

### Change 2: Add diagnostic when HL price is used

```python
# After line 525, add:
if node_prices.get(hl_symbol):
    print(f"[HL_PRICE] {symbol}: using oracle price {price:.2f}", flush=True)
```

---

## WHY THIS CONSUMER IS SAFE

| Dependency | Status | Explanation |
|------------|--------|-------------|
| Binance data | NOT REQUIRED | HL price is primary, Binance is fallback |
| Position data | NOT REQUIRED | Regime uses price + calculators, not positions |
| Dead collectors | NOT REQUIRED | Reads from M1 buffers populated by NodeBridge |
| Cascade primitives | NOT USED | Regime classification is independent path |

**Safety Proof:**
- `get_all_hl_prices()` reads from M1's `latest_hl_prices` dict
- This dict is populated by `normalize_hl_price()` when HL_PRICE events arrive
- NodeBridge already populates this via `ingest_observation(event_type='HL_PRICE')`
- No new data path created, just fixing broken accessor

---

## EXPECTED BEHAVIOR

### With HL_PRICE Only (No Binance):

```
[HL_PRICE] BTCUSDT: using oracle price 78801.00
[REGIME] BTCUSDT: SKIP - missing metrics: [vwap_dist, atr_5m, atr_30m, orderflow, liq_z]
```

**Interpretation:** System received HL price, attempted regime classification, decided to SKIP due to incomplete metrics. This IS observable behavior.

### With HL_PRICE + Binance Data:

```
[HL_PRICE] BTCUSDT: using oracle price 78801.00
[REGIME] BTCUSDT: NEUTRAL (vwap=78650, atr_5m=120, ...)
```

**Interpretation:** Full regime classification with HL oracle price as source.

---

## SECONDARY FIX (run_paper_trade.py)

Lines 266-271 also crash. Fix:

```python
# BEFORE (lines 266-271):
prices_dict = service._node_bridge.get_latest_prices()
logger.info(
    f'Status: prices={metrics["prices_forwarded"]}, '
    f'liqs={metrics["liquidations_forwarded"]}, '
    f'alerts={metrics["proximity_alerts"]}, '

# AFTER:
logger.info(
    f'Status: prices={metrics["prices_ingested"]}, '
    f'liqs={metrics["liquidations_ingested"]}, '
    f'errors={metrics["errors"]}, '
```

---

## VERIFICATION COMMAND

```bash
cd /media/ksiaz/D/liquidation-trading

# Ensure gRPC server running
ss -tlnp | grep 50051

# Run with diagnostic enabled
DIAG_MANDATE=1 timeout 30 python scripts/run_paper_trade.py 2>&1 | grep -E "\[HL_PRICE\]|\[REGIME\]"
```

---

## SUCCESS CRITERIA

| Check | Evidence |
|-------|----------|
| No crash | Script runs for 30 seconds |
| HL_PRICE consumed | Log: `[HL_PRICE] BTCUSDT: using oracle price 78xxx` |
| Decision made | Log: `[REGIME] BTCUSDT: SKIP - missing metrics` OR `[REGIME] BTCUSDT: NEUTRAL` |

---

## FAILURE CLASSIFICATION (Pre-declared)

If this fails, classify as:

| Failure Type | Symptom |
|--------------|---------|
| ❌ Wiring bug | Script still crashes on different method |
| ❌ Data insufficiency | HL prices not reaching M1 |
| ❌ Architectural | Regime loop doesn't run at all |
| ❌ Conceptual | N/A - regime can act on price alone (partial) |

---

*This plan requires 2 line changes and produces observable behavior.*

---

## EXECUTION RESULTS

**Date:** 2026-02-01 12:15
**Status:** SUCCESS

### Runtime Evidence

```
[HL_DEBUG] cycle=1 node_prices has 6 symbols: ['BTC', 'ETH', 'SOL', 'DOGE', 'XRP']
[HL_PRICE] BTC: using oracle price 78417.00 from HL node
[REGIME] BTC: SKIP - missing calculators: ['vwap', 'atr', 'orderflow', 'liquidation']
[HL_PRICE] ETH: using oracle price 2391.30 from HL node
[REGIME] ETH: SKIP - missing calculators: ['vwap', 'atr', 'orderflow', 'liquidation']
[HL_PRICE] DOGE: using oracle price 0.10 from HL node
[HL_PRICE] HYPE: using oracle price 0.26 from HL node
```

### What Was Proven

| Check | Evidence |
|-------|----------|
| HL prices reach M1 | `node_prices has 6 symbols` |
| HL prices consumed | `using oracle price 78417.00 from HL node` |
| Decision made | `SKIP - missing calculators` |

### Wiring Fixes Applied

1. **service.py:517** - Changed `get_latest_prices()` to `get_all_hl_prices()`
2. **service.py:653** - Added hasattr check for `get_proximity_provider`
3. **service.py:724** - Added hasattr check for `get_burst`
4. **run_paper_trade.py:108-113** - Added HL format symbols to whitelist
5. **run_paper_trade.py:199** - Added hasattr check for cleanup pruners

### Failure Classification

**NOT A FAILURE** - Partial behavior is expected.

The system correctly:
1. Received live HL price data
2. Used it as primary price source for regime classification
3. Identified missing metrics (VWAP, ATR, orderflow, liquidation zscore)
4. Made a decision (SKIP) and logged it

The missing metrics require Binance data streams, which is a separate integration.

### Conclusion

**The system is ALIVE.**

A live HL price update caused the system to decide something (SKIP regime classification due to incomplete metrics). This is observable intent.

---

*Generated: 2026-02-01*
