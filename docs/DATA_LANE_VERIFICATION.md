# DATA LANE CONTRACT VERIFICATION

**Date:** 2026-02-01
**Purpose:** Verify field contracts between components
**Type:** Runtime Contract Verification

---

## HL_PRICE EVENT CONTRACT

### Path: NodeBridge → ingest_observation()

**Source:** `runtime/node_client/bridge.py:72-91`

| Field | Expected (Contract) | Observed (Runtime) | Match |
|-------|---------------------|-------------------|-------|
| `timestamp` | `float` (seconds) | `time.time()` = seconds | ✅ |
| `symbol` | `str` (e.g., "BTC") | `event.symbol` | ✅ |
| `event_type` | `'HL_PRICE'` | `'HL_PRICE'` | ✅ |
| `payload.oracle_price` | `float` | `event.oracle_float` | ✅ |
| `payload.mark_price` | `float` | `event.mark_float` | ✅ |
| `payload.block_height` | `int` | `event.block_height` | ✅ |
| `payload.exchange` | `str` | `'HYPERLIQUID'` | ✅ |
| `payload.timestamp` | `float` (ns→s) | `event.timestamp_ns / 1e9` | ✅ |

**Verified Sample (from test):**
```
symbol=BTC oracle=78801.00 mark=78764.00
```

---

### Path: ingest_observation() → M1.normalize_hl_price()

**Source:** `observation/internal/m1_ingestion.py:449-491`

| Field | Expected | Observed | Match |
|-------|----------|----------|-------|
| `timestamp` | `float` | `payload.get('timestamp', 0)` | ✅ |
| `symbol` | `str` | from caller | ✅ |
| `oracle_price` | `float` | `float(payload.get('oracle_price'))` | ✅ |
| `mark_price` | `float or None` | conditional | ✅ |
| `event_type` | `'HL_PRICE'` | hardcoded | ✅ |
| `exchange` | `'HYPERLIQUID'` | hardcoded | ✅ |

**Storage:**
```python
self.hl_prices[symbol].append(event)  # Buffer
self.latest_hl_prices[symbol] = {     # Cache
    'oracle_price': event['oracle_price'],
    'mark_price': event['mark_price'],
    'timestamp': event['timestamp']
}
```

---

## LIQUIDATION EVENT CONTRACT

### Path: NodeBridge → ingest_observation()

**Source:** `runtime/node_client/bridge.py:97-136`

| Field | Expected (Contract) | Observed (Runtime) | Match |
|-------|---------------------|-------------------|-------|
| `timestamp` | `float` (seconds) | `time.time()` | ✅ |
| `symbol` | `str` | `event.symbol` | ✅ |
| `event_type` | `'LIQUIDATION'` | `'LIQUIDATION'` | ✅ |
| `payload.E` | `int` (ms) | `event.timestamp_ms` | ✅ |
| `payload.o.p` | `str` (price) | `str(event.price_float)` | ✅ |
| `payload.o.q` | `str` (qty) | `str(event.size_float)` | ✅ |
| `payload.o.S` | `'BUY'` or `'SELL'` | Normalized from LONG/SHORT | ✅ |

**Side Normalization (Critical):**
```python
# LONG liquidation → SELL (must sell to close long)
# SHORT liquidation → BUY (must buy to close short)
canonical_side = 'SELL' if event.side == 'LONG' else 'BUY'
```

**Verified Sample (from historical data):**
```
symbol=BTC side=SHORT price=78215.0 size=0.48023
```

---

### Path: ingest_observation() → M1.normalize_liquidation()

**Source:** `observation/internal/m1_ingestion.py:162-191`

| Field | Expected | Observed | Match |
|-------|----------|----------|-------|
| `order` | `dict` | `raw_payload['o']` | ✅ |
| `price` | `float` | `float(order['p'])` | ✅ |
| `quantity` | `float` | `float(order['q'])` | ✅ |
| `timestamp` | `float` (s) | `int(raw_payload['E']) / 1000.0` | ✅ |
| `side` | `'BUY'` or `'SELL'` | `order['S']` | ✅ |

**Output Event:**
```python
event = {
    'timestamp': timestamp,
    'symbol': symbol,
    'price': price,
    'quantity': quantity,
    'side': side,
    'base_qty': quantity,
    'quote_qty': quantity * price
}
```

---

## CONTRACT MISMATCHES FOUND

### Mismatch 1: HL_LIQUIDATION vs LIQUIDATION Event Type

**Location:** Two different event types exist

| Source | Event Type | Handler |
|--------|------------|---------|
| NodeBridge (new) | `LIQUIDATION` | `normalize_liquidation()` |
| ObservationBridge (old) | `HL_LIQUIDATION` | `normalize_hl_liquidation()` |

**Consequence:**
- NodeBridge uses Binance-compatible format
- ObservationBridge uses HL-native format
- Both work, but different codepaths

**Downstream Impact:**
```python
# governance.py:282-283 handles LIQUIDATION
if normalized_event and event_type == 'LIQUIDATION':
    self._create_or_update_node_from_liquidation(normalized_event)
    self.record_hl_liquidation(...)

# governance.py:336-342 handles HL_LIQUIDATION (deprecated)
if normalized_event and event_type == 'HL_LIQUIDATION':
    self.record_hl_liquidation(...)
    self._create_or_update_node_from_liquidation(normalized_event)
```

**Verdict:** Both paths work. New path (LIQUIDATION) is preferred.

---

### Mismatch 2: Timestamp Semantics

| Component | Timestamp Used | Source |
|-----------|----------------|--------|
| NodeBridge | `time.time()` | Wall clock |
| Payload | `event.timestamp_ns / 1e9` | Node time |
| ingest_observation | Uses caller timestamp | Wall clock |
| M1 normalize | Uses payload timestamp | Node time |

**Consequence:**
- Governance freshness check uses wall clock (correct)
- Event storage uses node time (correct)
- No mismatch, just dual timestamps by design

---

### Mismatch 3: Symbol Format

| Source | Format | Example |
|--------|--------|---------|
| HL Node | Base only | `BTC`, `ETH`, `SOL` |
| Binance | With quote | `BTCUSDT`, `ETHUSDT`, `SOLUSDT` |
| M2 Store | Mixed | Depends on source |

**Location:** `runtime/collector/service.py:524`
```python
hl_symbol = symbol.replace('USDT', '')  # Convert Binance → HL
```

**Consequence:**
- Manual conversion required
- Potential for inconsistency in M2 node IDs
- Need to maintain mapping

---

## SILENT HANDLING (No Errors, Data Dropped)

### 1. Stale Timestamp Drops

**Location:** `observation/governance.py:263-265`
```python
if timestamp < self._system_time - 30.0:
    # Drop ancient history silently
    return
```

**Impact:** Events older than 30 seconds are silently dropped.

### 2. Symbol Whitelist Drops

**Location:** `observation/governance.py:269-271`
```python
if self._allowed_symbols is not None and symbol not in self._allowed_symbols:
    return
```

**Impact:** Events for non-whitelisted symbols are silently dropped.

### 3. Null Price Drops

**Location:** `observation/internal/m1_ingestion.py:467-469`
```python
oracle_price = payload.get('oracle_price')
if oracle_price is None:
    return None
```

**Impact:** Events without oracle_price are silently dropped.

---

## VERIFIED WORKING CONTRACTS

| Contract | Source → Target | Status |
|----------|-----------------|--------|
| gRPC PriceEvent | Server → Subscriber | ✅ VERIFIED |
| gRPC LiquidationEvent | Server → Subscriber | ✅ VERIFIED (parsing) |
| NodeBridge HL_PRICE | Bridge → M1 | ✅ VERIFIED |
| NodeBridge LIQUIDATION | Bridge → M1 | ✅ VERIFIED |
| M1 → M2 Node Creation | Liquidation → Store | ✅ VERIFIED |

---

## UNVERIFIED CONTRACTS (Never Exercised)

| Contract | Source → Target | Why Unverified |
|----------|-----------------|----------------|
| HL_PRICE → Strategy | M1 → PolicyAdapter | No consumer exists |
| HL_PRICE → Regime | M1 → classify_regime | get_latest_prices() broken |
| LIQUIDATION → Cascade | M1 → cascade primitives | HyperliquidCollector not running |

---

*This document verifies contracts through code inspection and runtime testing.*

*Generated: 2026-02-01*
