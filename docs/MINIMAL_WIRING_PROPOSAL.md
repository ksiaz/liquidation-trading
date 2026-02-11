# MINIMAL WIRING PROPOSAL

**Date:** 2026-02-01
**Purpose:** Propose smallest change to make existing code functional
**Type:** Repair Proposal (Not Enhancement)

---

## CONDITION MET

**Finding:** Data reaches M1 but downstream consumers cannot access it due to:

1. **Missing method:** `NodeBridge.get_latest_prices()` doesn't exist
2. **Wrong metric keys:** `prices_forwarded` and `proximity_alerts` don't exist
3. **No price consumer:** HL_PRICE data is stored but never read

---

## PROPOSAL 1: FIX BROKEN PAPER TRADING SCRIPT

### File: `scripts/run_paper_trade.py`

**Problem:** Lines 266-271 call non-existent methods

```python
# Current (broken):
prices_dict = service._node_bridge.get_latest_prices()
logger.info(
    f'Status: prices={metrics["prices_forwarded"]}, '
    f'liqs={metrics["liquidations_forwarded"]}, '
    f'alerts={metrics["proximity_alerts"]}, '
```

**Fix:** Use existing methods

```python
# Fixed:
# Remove get_latest_prices() call - data flows via callbacks, not polling
logger.info(
    f'Status: prices={metrics["prices_ingested"]}, '
    f'liqs={metrics["liquidations_ingested"]}, '
    f'errors={metrics["errors"]}, '
```

**Lines to change:** 266-271
**Risk:** Low (logging only)

---

## PROPOSAL 2: FIX SERVICE.PY NODE PRICE LOOKUP

### File: `runtime/collector/service.py`

**Problem:** Line 518 calls non-existent method

```python
# Current (broken):
if self._node_bridge:
    node_prices = self._node_bridge.get_latest_prices()
```

**Fix:** Use observation system's existing accessor

```python
# Fixed:
if self._node_bridge:
    node_prices = self._obs.get_all_hl_prices()
```

**Lines to change:** 517-518
**Risk:** Low (uses existing tested method)

**Why this works:**
- `get_all_hl_prices()` already exists in governance.py:246-252
- It reads from M1's `latest_hl_prices` cache
- NodeBridge already populates this cache via ingest_observation()

---

## PROPOSAL 3: ADD MISSING METHOD (ALTERNATIVE)

### File: `runtime/node_client/bridge.py`

**If backward compatibility with get_latest_prices() is required:**

```python
def get_latest_prices(self) -> Dict[str, float]:
    """Get latest HL oracle prices.

    Delegates to observation system's M1 cache.
    """
    if self._obs is None:
        return {}
    return self._obs.get_all_hl_prices()
```

**Lines to add:** After line 207 (after get_metrics)
**Risk:** Low (simple delegation)

**Trade-off:** This adds a method vs fixing the caller. Proposal 2 is cleaner.

---

## VERIFICATION PLAN

### Step 1: Apply Proposal 2

```bash
# Edit service.py line 518
# Change: node_prices = self._node_bridge.get_latest_prices()
# To:     node_prices = self._obs.get_all_hl_prices()
```

### Step 2: Apply Proposal 1

```bash
# Edit run_paper_trade.py lines 266-271
# Change metric key names to match actual keys
```

### Step 3: Run Test

```bash
cd /media/ksiaz/D/liquidation-trading

# Ensure gRPC server is running
ss -tlnp | grep 50051

# Run paper trade for 60 seconds
timeout 60 python scripts/run_paper_trade.py 2>&1 | tee test_output.log
```

### Step 4: Verify Success

**Success Criteria:**
1. No AttributeError on get_latest_prices()
2. No KeyError on metrics dict access
3. Log shows `Status: prices=N, liqs=M, errors=0`
4. HL prices appear in regime calculation:
   - `[REGIME] BTC: price=78xxx` in logs

**Failure Criteria:**
1. Stack trace containing `get_latest_prices`
2. Stack trace containing `KeyError: 'prices_forwarded'`
3. `prices=0` after 60 seconds

---

## WHAT THIS DOES NOT FIX

| Issue | Why Not Fixed Here |
|-------|-------------------|
| Cascade primitives dead | Requires HyperliquidCollector position data |
| SLBRS/EFFCS dormant | Requires specific regime states |
| HL_PRICE not used by strategies | Geometry uses M2 nodes, not prices |
| Cascade Sniper dead | Requires proximity data |

**This proposal only fixes the wiring bug that prevents node mode from running at all.**

---

## DECISION

**Recommended:** Apply Proposals 1 and 2.

**Rationale:**
- Fixes known crash points
- Uses existing code paths
- No new functionality added
- Enables verification of full pipeline

---

*This is a repair proposal, not a feature request.*

*Generated: 2026-02-01*
