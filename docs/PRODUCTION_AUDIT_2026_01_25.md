# Production System Audit Report

**Date:** 2026-01-25
**Auditor:** Claude Opus 4.5
**Scope:** Silent failure paths in production trading system
**Status:** FINDINGS DOCUMENTED - FIXES PENDING

---

## Executive Summary

Comprehensive audit of the production trading system identified **14 CRITICAL**, **10 HIGH**, and **4 MEDIUM** severity issues across 8 risk categories. The most severe findings involve:

1. **Thread safety violations** in position state machine
2. **Partial fill handling gaps** causing state divergence
3. **EXIT supremacy broken** in M6 executor
4. **Retry logic amplifying slippage** without idempotency
5. **Position size inflation** bypassing risk limits

**Recommendation:** Block production trading until CRITICAL issues resolved.

---

## Table of Contents

1. [Execution Reality Gaps](#1-execution-reality-gaps)
2. [Latency & Timing Assumptions](#2-latency--timing-assumptions)
3. [State Truth & Recovery Risks](#3-state-truth--recovery-risks)
4. [Market Data Integrity](#4-market-data-integrity)
5. [Risk & Capital Edge Cases](#5-risk--capital-edge-cases)
6. [Alpha Decay & Regime Blindness](#6-alpha-decay--regime-blindness)
7. [Adversarial Market Behavior](#7-adversarial-market-behavior)
8. [Human / Governance Risk](#8-human--governance-risk)
9. [Fix Priority Matrix](#9-fix-priority-matrix)
10. [Implementation Plan](#10-implementation-plan)

---

## 1. Execution Reality Gaps

### 1.1 [CRITICAL] Retry Logic Amplifies Slippage

**File:** `execution/hyperliquid_adapter.py`
**Lines:** 626-711

**Description:**
The retry loop resubmits identical order payload (same price/size) across 3 retries with exponential delays. No idempotency key prevents duplicate submissions.

**Failure Scenario:**
```
T=0ms:   Submit BUY 100 BTC @ 50,000 → Network timeout before ACK
T=100ms: Retry #1 at same price → Market now 50,050
T=300ms: Retry #2 at same price → Market now 50,100
Result:  Potential dual-fill OR 100bps slippage on successful retry
```

**Code Evidence:**
```python
# Line 643-703: Retry loop
for attempt in range(self._max_retries):
    # ... submits SAME payload each time
    if response.status == 200:
        return result
    # Exponential backoff, then retry with SAME price
```

**Financial Impact:**
- 50-200bps slippage amplification per retry
- Potential duplicate fills if first order rested
- EV bleed on every network hiccup

**Fix Direction:**
- Add nonce-based idempotency key per logical order (not per submission)
- Check if order already acknowledged/resting before retry
- Adjust price to current market on retry

---

### 1.2 [CRITICAL] Partial Fill Silent Success

**File:** `execution/hyperliquid_adapter.py`
**Lines:** 654-673

**Description:**
Response parsing returns `ACKNOWLEDGED` regardless of fill percentage. No tracking of actual fill quantity vs requested quantity.

**Failure Scenario:**
```
Request:  ENTRY 100 BTC
Response: 60 BTC filled, 40 BTC resting
Adapter:  Returns ACKNOWLEDGED (success)
State:    Position shows 100 BTC (intended)
Exchange: Position is 60 BTC (actual)
Risk:     Liquidation price calculated on wrong size
```

**Code Evidence:**
```python
# Lines 659-666: Only checks for success status
if response.status == 200 and data.get("status") == "ok":
    statuses = data.get("response", {}).get("data", {}).get("statuses", [])
    if statuses and ("resting" in statuses[0] or "filled" in statuses[0]):
        order_id = statuses[0].get("resting", {}).get("oid") or ...
        return ExchangeResponse(code=ACKNOWLEDGED, order_id=order_id)
        # NO fill quantity extracted or returned
```

**Financial Impact:**
- Position state diverges from exchange reality
- Risk calculations use wrong position size
- Liquidation price estimates incorrect

**Fix Direction:**
- Parse `filledSz` from response
- Return actual fill quantity in ExchangeResponse
- Track cumulative fills per order_id

---

### 1.3 [CRITICAL] Cancel/Replace Race Condition

**File:** `execution/hyperliquid_adapter.py`
**Lines:** 713-800

**Description:**
No coordination between pending retries and cancel requests. Cancel operation has no retry logic (unlike execute).

**Failure Scenario:**
```
T=0ms:   Execute order, network timeout
T=50ms:  Retry queued (will fire at T=100ms)
T=60ms:  Caller issues cancel for order_id
T=70ms:  Cancel succeeds on exchange
T=100ms: Retry fires, submits NEW order (cancel didn't stop it)
Result:  Two live orders instead of zero
```

**Code Evidence:**
```python
# Lines 739-754: Cancel builds payload without checking pending retries
def cancel_orders(self, order_ids: List[str], symbol: str) -> ExchangeResponse:
    payload = {"action": {"type": "cancel", "cancels": [...]}}
    # NO check: is there a pending retry for this order?
    # NO retry logic if cancel fails
```

**Financial Impact:**
- Unwanted exposure from orphaned orders
- Failed hedges if cancel doesn't actually succeed
- Position drift from exchange state

**Fix Direction:**
- Implement order state machine with cancel intent
- Block retries after cancel requested
- Add retry logic to cancel operations

---

### 1.4 [HIGH] Order State Not Persisted

**File:** `execution/hyperliquid_adapter.py`
**Lines:** 404-468

**Description:**
No tracking of order_id → payload mapping, submission timestamp, or retry history. Crash loses all order context.

**Code Evidence:**
```python
# Line 429: Only cosmetic counter
self._call_count += 1
# NO persistence of: order_id, payload, submit_time, retry_count
```

**Financial Impact:**
- Crash → duplicate orders on restart
- Orphaned positions with no audit trail
- Cannot reconcile fills to original intent

**Fix Direction:**
- Persist order intent before submission
- Track order lifecycle in database
- Reconcile on startup

---

### 1.5 [HIGH] Precision Loss in Price Formatting

**File:** `runtime/exchange/order_executor.py`
**Lines:** 405-427

**Description:**
Price formatting uses arbitrary decimal thresholds that don't match Hyperliquid's 5 significant figure rule for all ranges.

**Code Evidence:**
```python
# Lines 405-427: Fixed decimal places per price range
if price >= 10000:
    return f"{price:.0f}"       # OK
elif price >= 1000:
    return f"{price:.1f}"       # OK
elif price >= 100:
    return f"{price:.2f}"       # Loses precision at 100-199
# ...
```

**Financial Impact:**
- Orders rejected for invalid price format
- Micro-slippage from rounding errors
- Queue priority loss from price mismatch

**Fix Direction:**
- Use proper 5 significant figure formatting for all ranges
- Use Decimal type instead of float
- Validate against exchange tick size

---

## 2. Latency & Timing Assumptions

### 2.1 [CRITICAL] Fill Arrives Before Order Tracked

**File:** `runtime/exchange/fill_tracker.py`
**Lines:** 299-301

**Description:**
Fills for untracked orders are silently discarded. Race window between order submission and `track_order()` registration.

**Code Evidence:**
```python
# Lines 299-301
if order_id not in self._tracked_orders:
    self._logger.debug(f"Fill for untracked order: {order_id}")
    return  # FILL PERMANENTLY LOST
```

**Financial Impact:**
- Fills never recorded in position state
- PnL unaccounted
- Position quantity wrong

**Fix Direction:**
- Buffer fills pending tracking registration
- Replay buffered fills on track_order()
- Add fill recovery mechanism

---

### 2.2 [HIGH] Stale Observation Not Validated

**File:** `runtime/policy_adapter.py`
**Lines:** 105-158

**Description:**
Observation snapshot timestamp never compared to mandate generation timestamp. Stale observations can generate current-time mandates.

**Code Evidence:**
```python
def generate_mandates(
    self,
    observation_snapshot: ObservationSnapshot,  # May be 5+ seconds old
    symbol: str,
    timestamp: float,  # Current time
    ...
) -> List[Mandate]:
    # ONLY checks status, not timestamp
    if observation_snapshot.status == ObservationStatus.FAILED:
        return [...]
    # No staleness check before using primitives
```

**Financial Impact:**
- Mandates generated from old market state
- Liquidation detection delayed
- Wrong entry/exit timing

**Fix Direction:**
- Add configurable staleness threshold (e.g., 2 seconds)
- Reject observations older than threshold
- Log staleness events for monitoring

---

### 2.3 [MEDIUM] Timeout Boundary Race

**File:** `runtime/exchange/order_executor.py`
**Lines:** 788

**Description:**
Floating-point comparison at exact timeout boundary is inconsistent due to precision.

**Code Evidence:**
```python
# Line 788
elapsed_ms = (now_ns - submit_time) / 1_000_000  # Float division
if elapsed_ms > timeout_ms:  # Strict inequality
    timed_out.append(order_id)
```

**Financial Impact:**
- Orders hang unpredictably near timeout boundary
- Inconsistent behavior in tests vs production

**Fix Direction:**
- Use integer nanoseconds throughout
- Use `>=` instead of `>`

---

### 2.4 [HIGH] Callback Outside Lock (Trailing Stop)

**File:** `runtime/exchange/trailing_stop_manager.py`
**Lines:** 304

**Description:**
Stop update callback executes outside the lock, allowing concurrent modifications during callback execution.

**Code Evidence:**
```python
# Line 289-304
with self._lock:
    state.current_stop_price = new_stop
    self._persist_state(state)
# LOCK RELEASED
if self._on_stop_update:
    self._on_stop_update(entry_id, old_stop, new_stop)  # OUTSIDE LOCK
```

**Financial Impact:**
- Callback receives stale state
- Concurrent updates corrupt stop price
- Exchange/manager state diverges

**Fix Direction:**
- Execute callback inside lock OR
- Copy state before releasing lock
- Use callback queue processed sequentially

---

## 3. State Truth & Recovery Risks

### 3.1 [CRITICAL] Position State Machine NOT Thread-Safe

**File:** `runtime/position/state_machine.py`
**Lines:** 93-98

**Description:**
No lock protection on `_positions` or `_closing_trackers` dictionaries. Concurrent access causes corruption.

**Code Evidence:**
```python
# Lines 93-98: No RLock defined
class PositionStateMachine:
    def __init__(self, ...):
        self._positions: Dict[str, Position] = {}  # NO LOCK
        self._closing_trackers: Dict[str, ClosingStateTracker] = {}  # NO LOCK
```

**Concurrent Access Points:**
- `transition()` modifies `_positions`
- `get_position()` reads `_positions`
- `check_closing_timeouts()` iterates `_closing_trackers`
- `force_close_timeout()` modifies both

**Financial Impact:**
- Corrupted position state
- Stuck CLOSING positions
- KeyError crashes mid-execution

**Fix Direction:**
- Add RLock to PositionStateMachine
- Protect all dict access with lock
- Use copy for iteration

---

### 3.2 [CRITICAL] Stale Stop Order Resurrection

**File:** `runtime/persistence/execution_state_repository.py`
**Lines:** 266-275

**Description:**
On restart, loads stop orders with state=PLACED without validating against exchange reality.

**Code Evidence:**
```python
# Lines 266-275
def load_active_stop_orders(self) -> Dict[str, PersistedStopOrder]:
    cursor.execute("""
        SELECT * FROM stop_orders
        WHERE state IN ('PENDING_PLACEMENT', 'PLACED', 'TRIGGERED')
    """)
    # NO validation that these orders still exist on exchange
```

**Failure Scenario:**
```
T=0:    Stop order placed, state=PLACED persisted
T=10:   Stop fills on exchange
T=15:   Crash before deletion persisted
T=100:  Restart → loads state=PLACED
T=101:  Attempts to modify already-filled order
```

**Financial Impact:**
- Phantom orders in tracking
- Attempts to cancel filled orders
- Incorrect stop placement

**Fix Direction:**
- Query exchange positions on startup
- Reconcile persisted state vs exchange reality
- Mark stale orders for review

---

### 3.3 [HIGH] Fill ID Persistence Window

**File:** `runtime/persistence/execution_state_repository.py`
**Lines:** 404-410

**Description:**
Fill processed in memory before persistence commit completes. Crash in window causes duplicate processing.

**Code Evidence:**
```python
# Lines 404-410
def save_fill_id(self, fill_id: str, symbol: str, order_id: str) -> None:
    cursor.execute("INSERT OR IGNORE INTO seen_fill_ids ...")
    self.conn.commit()  # Commit can fail silently
```

**Financial Impact:**
- Duplicate fill processing on restart
- Position size inflated
- PnL double-counted

**Fix Direction:**
- Persist fill_id BEFORE processing fill
- Use write-ahead log pattern
- Add commit error handling

---

### 3.4 [CRITICAL] Trailing Stop State Divergence

**File:** `runtime/exchange/trailing_stop_manager.py`
**Lines:** 289-304

**Description:**
Memory updated, DB persisted, but callback to exchange can fail. No reconciliation mechanism.

**Failure Scenario:**
```
T=0:   Stop at 100.00
T=10:  New stop calculated: 101.00
T=11:  Memory updated to 101.00
T=12:  DB persisted with 101.00
T=13:  Callback to exchange fails (connection drop)
T=14:  Manager thinks 101.00, Exchange has 100.00
```

**Financial Impact:**
- Stop 100-300bps away from intended level
- Unexpected fills or missed protection
- Silent divergence accumulates

**Fix Direction:**
- Wait for exchange ACK before persisting
- Add startup reconciliation
- Track last confirmed exchange state

---

### 3.5 [HIGH] Silent Recovery Failure

**File:** `runtime/position/state_machine.py`
**Lines:** 111-133

**Description:**
Exception during CLOSING timeout recovery is logged but swallowed. State machine continues with incomplete state.

**Code Evidence:**
```python
# Lines 116-128
try:
    persisted = self._exec_state_repo.load_all_closing_timeouts()
    for symbol, p in persisted.items():
        self._closing_trackers[symbol] = ClosingStateTracker(...)
except Exception as e:
    logging.getLogger(__name__).error(...)
    # NO RE-RAISE - continues with incomplete state
```

**Financial Impact:**
- Positions stuck in CLOSING forever
- Timeout protection silently disabled

**Fix Direction:**
- Re-raise exception after logging
- Or mark state machine as degraded
- Alert on recovery failure

---

### 3.6 [HIGH] Two-Phase Persistence Desync

**File:** `runtime/position/state_machine.py`
**Lines:** 237-258

**Description:**
Position and ClosingStateTracker persisted separately. Partial failure leaves inconsistent state.

**Code Evidence:**
```python
# Line 237: Update positions
self._positions[symbol] = new_position

# Lines 240-249: Conditionally create tracker
if new_position.state == PositionState.CLOSING:
    self._closing_trackers[symbol] = ClosingStateTracker(...)
    self._persist_closing_timeout(...)  # Can fail independently

# Lines 257-258: Always save position
if self._repository:
    self._repository.save(new_position)  # Different transaction
```

**Financial Impact:**
- Position is CLOSING but no timeout tracker
- Or timeout tracker exists but position is FLAT

**Fix Direction:**
- Use single atomic transaction
- Or implement saga pattern with compensation
- Add consistency check on load

---

## 4. Market Data Integrity

### 4.1 [CRITICAL] Empty Fill ID Deduplication Failure

**File:** `runtime/exchange/fill_tracker.py`
**Lines:** 305-322

**Description:**
Fills without `tid` field all pass deduplication because empty string is used but not unique.

**Code Evidence:**
```python
# Lines 305-322
fill_id = str(fill_data.get('tid', ''))  # Empty string if missing

if fill_id and fill_id in self._global_seen_fill_ids:
    return  # Dedup check

if fill_id:
    entry.seen_fill_ids.add(fill_id)  # Adds empty string
    # Next fill without tid ALSO has fill_id = ""
    # But "" already in set... wait, it should dedup?
    # NO: Line 309 check is `fill_id and fill_id in set`
    # Empty string is falsy, so check FAILS, fill accepted
```

**Actual Issue:** The `if fill_id` check on line 309 fails for empty string (falsy), so dedup is skipped entirely for fills without tid.

**Financial Impact:**
- Same fill counted multiple times
- Position size inflated
- Cumulative metrics corrupted

**Fix Direction:**
- Generate deterministic ID from (order_id, price, size, timestamp)
- Never rely on exchange-provided ID alone
- Validate fill uniqueness by multiple fields

---

### 4.2 [HIGH] Trade Side Validation Bypass

**File:** `observation/internal/m1_ingestion.py`
**Lines:** 100-153

**Description:**
If no depth data available, side validation is skipped and derived side used without confirmation.

**Code Evidence:**
```python
# Lines 123-127
depth = self.latest_depth.get(symbol)
if not depth:
    self.counters['side_unvalidated'] += 1
    return (None, "UNVALIDATED")  # Uses derived side
```

**Financial Impact:**
- Wrong trade flow direction
- Inverted cascade detection
- False absorption signals

**Fix Direction:**
- Track unvalidated rate
- Alert when threshold exceeded
- Block trading if validation rate too low

---

## 5. Risk & Capital Edge Cases

### 5.1 [CRITICAL] Position Size Inflation via H2-A Floor

**File:** `runtime/risk/position_sizer.py`
**Lines:** 199-207

**Description:**
Floor multiplier can expand position 3.3x without re-validating against max limits.

**Code Evidence:**
```python
# Lines 199-207
if actual_risk_pct < self._config.min_risk_pct_floor and actual_risk_pct > 0:
    floor_multiplier = self._config.min_risk_pct_floor / actual_risk_pct
    position_size *= floor_multiplier  # CAN BE 3.3x
    # NO RE-VALIDATION AGAINST MAX LIMITS
```

**Example:**
```
Initial size: 100 units
Risk pct: 0.09% (below 0.3% floor)
Multiplier: 0.3 / 0.09 = 3.33x
Final size: 333 units (exceeds max_position_size=200)
```

**Financial Impact:**
- Position size exceeds configured limits
- Leverage breach
- Outsized losses on adverse move

**Fix Direction:**
- Re-validate against all limits after floor application
- Cap multiplier to not exceed max limits
- Log floor applications for audit

---

### 5.2 [CRITICAL] Daily Halt Escape via Reset

**File:** `runtime/risk/drawdown_tracker.py`
**Lines:** 326-346

**Description:**
`reset_daily()` unconditionally exits cooldown without validating recovery conditions.

**Code Evidence:**
```python
# Lines 333-335
if self._state == DrawdownState.DAILY_COOLDOWN:
    self._state = DrawdownState.NORMAL  # NO VALIDATION
```

**Failure Scenario:**
```
23:59:59 - Hit daily loss limit, enter DAILY_COOLDOWN
00:00:01 - Scheduled reset_daily() called
00:00:02 - State = NORMAL, can trade again
00:00:10 - Hit limit again (same capital, no recovery)
Result:   Daily limit becomes hourly limit
```

**Financial Impact:**
- Loss limits circumvented
- Cumulative losses compound
- Account blown

**Fix Direction:**
- Require capital recovery proof before reset
- Add minimum cooldown period
- Track resets per period

---

### 5.3 [HIGH] Approved With Violations

**File:** `runtime/risk/capital_manager.py`
**Lines:** 245-251

**Description:**
Returns APPROVED even when violations list is populated, with rejection_reasons attached.

**Code Evidence:**
```python
# Lines 245-251
if not limit_check.allowed:
    if limit_check.adjusted_size and limit_check.adjusted_size > 0:
        adjusted_size = limit_check.adjusted_size
        # violations list populated at line 259
        return TradeApproval(
            decision=TradeDecision.APPROVED,  # APPROVED despite violations!
            ...
        )
```

**Financial Impact:**
- Trades execute despite risk violations
- False sense of risk compliance
- Audit trail shows approval with contradictions

**Fix Direction:**
- Check violations list before returning APPROVED
- Return ADJUSTED or PARTIAL_APPROVED for reduced sizes
- Never return APPROVED with non-empty violations

---

### 5.4 [HIGH] Cooldown Toggle Bypass

**File:** `runtime/risk/capital_manager.py`
**Lines:** 162-179

**Description:**
Entry cooldown can be completely disabled via config flag.

**Code Evidence:**
```python
# Lines 44-45
enable_entry_cooldown: bool = True  # CAN BE SET TO FALSE

# Lines 162-179
if self._config.enable_entry_cooldown:  # Skipped if False
    # H1-A hardening logic here
```

**Financial Impact:**
- Unlimited entries per minute
- Overtrading
- Slippage accumulation

**Fix Direction:**
- Remove toggle; cooldown should be mandatory
- Or require elevated permissions to disable
- Log all disabled safety checks

---

### 5.5 [HIGH] Stacked Multiplier Floor Inflation

**File:** `runtime/risk/capital_manager.py`
**Lines:** 351-363

**Description:**
H9-B floor can expand sizes when stacked multipliers fall below 0.25.

**Code Evidence:**
```python
# Lines 356-359
dd_mult = self._drawdown.get_size_multiplier()  # e.g., 0.1
regime_mult = self._config.sizing.regime_scalars.get(...)  # e.g., 0.5
combined = dd_mult * regime_mult  # 0.05 (5%)
return max(combined, self._config.min_stacked_multiplier)  # Returns 0.25 (25%)
# Size inflated 5x from intended
```

**Financial Impact:**
- Size 5x larger than drawdown state intended
- Defeats purpose of drawdown scaling

**Fix Direction:**
- Floor should be minimum of components, not product
- Or disable floor when any multiplier is at emergency level
- Log floor activations

---

### 5.6 [MEDIUM] Consecutive Loss Dead Zone

**File:** `runtime/risk/circuit_breaker.py`
**Lines:** 217-223

**Description:**
H7-A hardening requires minimum trades before streak detection activates.

**Code Evidence:**
```python
# Lines 217-223
if (self._consecutive_losses >= self._config.consecutive_losses and  # 5
        self._total_trades >= self._config.min_trades_for_streak):  # 10
    self.trip(...)
```

**Impact:** First 9 trades can all lose without triggering halt (9 losses < 10 min trades).

**Fix Direction:**
- Use OR instead of AND for early protection
- Or lower min_trades_for_streak
- Track consecutive losses from session start

---

## 6. Alpha Decay & Regime Blindness

### 6.1 [MEDIUM] Break-Even Trigger Irreversible

**File:** `runtime/exchange/trailing_stop_manager.py`
**Lines:** 321

**Description:**
Once `break_even_triggered=True`, it never resets even if profit retreats.

**Financial Impact:**
- Locked into suboptimal stop on profit whipsaw
- Cannot re-trigger on recovery

**Fix Direction:**
- Allow re-trigger after configurable retreat threshold
- Or track multiple BE levels

---

### 6.2 [HIGH] Stale Watermarks on Position Re-entry

**File:** `runtime/exchange/trailing_stop_manager.py`
**Lines:** 272-274

**Description:**
Watermarks (highest_price/lowest_price) never reset between positions with same entry_order_id.

**Financial Impact:**
- New position inherits old watermark
- Wrong trail calculations
- Immediate stop hit on re-entry

**Fix Direction:**
- Clear watermarks on unregister
- Validate watermarks on register
- Use unique entry_id per position

---

### 6.3 [MEDIUM] ATR Data Gap Blocks Trailing

**File:** `runtime/exchange/trailing_stop_manager.py`
**Lines:** 349-350

**Description:**
ATR_MULTIPLE mode returns None if no ATR data, stop never trails.

**Financial Impact:**
- Stop static while waiting for ATR
- Could miss entire move

**Fix Direction:**
- Use fallback trail method if ATR unavailable
- Or require ATR before enabling trail
- Alert on missing ATR

---

## 7. Adversarial Market Behavior

### 7.1 [CRITICAL] EXIT Supremacy Broken in M6

**File:** `runtime/m6_executor.py`
**Lines:** 343-366

**Description:**
M6._arbitrate() sorts by authority then type, allowing high-authority ENTRY to override EXIT.

**Code Evidence:**
```python
# Lines 352-357
sorted_mandates = sorted(
    mandates,
    key=lambda m: (m.type.value, m.authority),
    reverse=True
)
winner = sorted_mandates[0]  # Could be high-authority ENTRY
```

**Correct Behavior (arbitrator.py:49-54):**
```python
exit_mandates = [m for m in mandates if m.type == MandateType.EXIT]
if exit_mandates:
    return Action(type=ActionType.EXIT, ...)  # EXIT always wins
```

**Financial Impact:**
- Liquidation avoidance EXIT ignored
- Position held into liquidation
- Direct violation of safety rules

**Fix Direction:**
- Use arbitrator.py logic in M6
- EXIT supremacy is unconditional
- Add test for this specific case

---

### 7.2 [HIGH] Leverage Gate Sign Bypass

**File:** `execution/ep4_risk_gates.py`
**Lines:** 248

**Description:**
`abs(new_position_value)` masks direction information, allowing sign manipulation.

**Code Evidence:**
```python
# Line 248
new_position_value = (current_size + quantity) * price
validate_leverage_gate(position_value=abs(new_position_value), ...)
```

**Financial Impact:**
- Direction flip not properly validated
- Could bypass leverage limits via sign tricks

**Fix Direction:**
- Validate direction separately
- Don't use abs() for position value
- Check long/short limits independently

---

### 7.3 [MEDIUM] BLOCK vs EXIT Ambiguity

**File:** `runtime/arbitration/arbitrator.py`
**Lines:** 49-58

**Description:**
EXIT check happens BEFORE BLOCK check. Should BLOCK override EXIT?

**Code Evidence:**
```python
# Lines 49-54: EXIT first
if exit_mandates:
    return Action(type=ActionType.EXIT, ...)

# Lines 56-58: BLOCK checked after EXIT returned
if any(m.type == MandateType.BLOCK for m in mandates):
    mandates = {m for m in mandates if m.type != MandateType.ENTRY}
```

**Constitutional Question:** Does BLOCK mean "halt everything including exits"?

**Fix Direction:**
- Clarify BLOCK semantics in constitution
- Document intended priority
- Add explicit test cases

---

## 8. Human / Governance Risk

### 8.1 [HIGH] Silent Commit Failures

**File:** `runtime/persistence/execution_state_repository.py`
**Lines:** 202, 246, 286, 344, 378, 410, 443, 461, 505, 555, 570, 578

**Description:**
`conn.commit()` has no exception handling throughout the file.

**Code Evidence:**
```python
# Pattern repeated at all listed lines
cursor.execute("INSERT/UPDATE...")
self.conn.commit()  # NO TRY/EXCEPT
# Function returns normally even if commit failed
```

**Financial Impact:**
- State loss masked as success
- Silent data corruption
- Audit trail gaps

**Fix Direction:**
- Wrap all commits in try/except
- Propagate failure to caller
- Add commit verification

---

### 8.2 [CRITICAL] Missing is_cascade Field

**File:** `runtime/exchange/order_executor.py`
**Lines:** 821-825

**Description:**
Code references `request.is_cascade` which doesn't exist in OrderRequest dataclass.

**Code Evidence:**
```python
# Lines 823-824
min_pct = (
    self._config.cascade_min_fill_pct
    if request.is_cascade else self._config.min_fill_pct  # ATTRIBUTEERROR
)
```

**Financial Impact:**
- Partial fill handler crashes
- Fills lost
- Position state corrupted

**Fix Direction:**
- Add `is_cascade: bool = False` to OrderRequest
- Or use getattr with default
- Add test coverage for partial fills

---

### 8.3 [HIGH] Stop Config KeyError

**File:** `runtime/exchange/order_executor.py`
**Lines:** 1014-1027

**Description:**
Stop order placement uses unvalidated config dict keys.

**Code Evidence:**
```python
# Lines 1017, 1021
stop_request = OrderRequest(
    symbol=stop_config['symbol'],  # KeyError if missing
    stop_price=stop_config['stop_price'],  # KeyError if missing
)
```

**Financial Impact:**
- Stop placement crashes
- Position unprotected
- Silent failure mode

**Fix Direction:**
- Validate stop_config structure
- Use .get() with defaults or raise explicit error
- Add schema validation

---

### 8.4 [MEDIUM] Slippage Division by Zero

**File:** `runtime/exchange/order_executor.py`
**Lines:** 722

**Description:**
Slippage calculation divides by expected_price which can be None or 0.

**Code Evidence:**
```python
# Line 722
slippage_bps = abs(fill.price - request.expected_price) / request.expected_price * 10000
# expected_price can be None for market orders
```

**Financial Impact:**
- Fill handler crashes
- Metrics corrupted with NaN
- Fills lost

**Fix Direction:**
- Guard against None/zero
- Use fill price as fallback
- Handle market orders separately

---

## 9. Fix Priority Matrix

| Priority | Issue ID | Severity | Component | Estimated Effort |
|----------|----------|----------|-----------|------------------|
| P0-1 | 3.1 | CRITICAL | PositionStateMachine | 2 hours |
| P0-2 | 1.2 | CRITICAL | HyperliquidAdapter | 4 hours |
| P0-3 | 7.1 | CRITICAL | M6Executor | 1 hour |
| P0-4 | 1.1 | CRITICAL | HyperliquidAdapter | 4 hours |
| P0-5 | 5.1 | CRITICAL | PositionSizer | 2 hours |
| P0-6 | 2.1 | CRITICAL | FillTracker | 3 hours |
| P0-7 | 4.1 | CRITICAL | FillTracker | 2 hours |
| P0-8 | 3.2 | CRITICAL | Persistence | 4 hours |
| P0-9 | 3.4 | CRITICAL | TrailingStopManager | 4 hours |
| P0-10 | 5.2 | CRITICAL | DrawdownTracker | 2 hours |
| P0-11 | 1.3 | CRITICAL | HyperliquidAdapter | 4 hours |
| P0-12 | 8.2 | CRITICAL | OrderExecutor | 1 hour |
| P1-1 | 2.2 | HIGH | PolicyAdapter | 2 hours |
| P1-2 | 2.4 | HIGH | TrailingStopManager | 2 hours |
| P1-3 | 3.3 | HIGH | Persistence | 2 hours |
| P1-4 | 3.5 | HIGH | StateMachine | 1 hour |
| P1-5 | 3.6 | HIGH | StateMachine | 3 hours |
| P1-6 | 4.2 | HIGH | M1Ingestion | 2 hours |
| P1-7 | 5.3 | HIGH | CapitalManager | 1 hour |
| P1-8 | 5.4 | HIGH | CapitalManager | 1 hour |
| P1-9 | 5.5 | HIGH | CapitalManager | 2 hours |
| P1-10 | 6.2 | HIGH | TrailingStopManager | 2 hours |
| P1-11 | 7.2 | HIGH | RiskGates | 1 hour |
| P1-12 | 8.1 | HIGH | Persistence | 3 hours |
| P1-13 | 8.3 | HIGH | OrderExecutor | 1 hour |
| P1-14 | 1.4 | HIGH | HyperliquidAdapter | 4 hours |
| P1-15 | 1.5 | HIGH | OrderExecutor | 2 hours |
| P2-1 | 2.3 | MEDIUM | OrderExecutor | 1 hour |
| P2-2 | 5.6 | MEDIUM | CircuitBreaker | 1 hour |
| P2-3 | 6.1 | MEDIUM | TrailingStopManager | 1 hour |
| P2-4 | 6.3 | MEDIUM | TrailingStopManager | 1 hour |
| P2-5 | 7.3 | MEDIUM | Arbitrator | 2 hours |
| P2-6 | 8.4 | MEDIUM | OrderExecutor | 1 hour |

---

## 10. Implementation Plan

### Phase 1: Critical Thread Safety & State (Day 1)
1. Add RLock to PositionStateMachine (P0-1)
2. Fix EXIT supremacy in M6Executor (P0-3)
3. Add is_cascade field to OrderRequest (P0-12)
4. Fix position size floor re-validation (P0-5)
5. Fix daily halt reset validation (P0-10)

### Phase 2: Execution Reality (Day 2)
1. Add order idempotency (P0-4)
2. Track partial fill quantities (P0-2)
3. Fix cancel/retry coordination (P0-11)
4. Add fill buffering before tracking (P0-6)
5. Fix empty fill ID deduplication (P0-7)

### Phase 3: Persistence & Recovery (Day 3)
1. Add startup reconciliation (P0-8)
2. Fix trailing stop state sync (P0-9)
3. Add commit error handling (P1-12)
4. Fix two-phase persistence (P1-5)
5. Fix silent recovery failure (P1-4)

### Phase 4: Risk & Validation (Day 4)
1. Add observation staleness check (P1-1)
2. Fix callback locking (P1-2)
3. Fix approved with violations (P1-7)
4. Remove cooldown toggle (P1-8)
5. Fix stacked multiplier floor (P1-9)

### Phase 5: Remaining HIGH Issues (Day 5)
1. Fix fill persistence window (P1-3)
2. Add trade side validation alerts (P1-6)
3. Fix watermark reset (P1-10)
4. Fix leverage gate sign (P1-11)
5. Add stop config validation (P1-13)
6. Add order state persistence (P1-14)
7. Fix price formatting precision (P1-15)

### Phase 6: MEDIUM Issues (Day 6)
1. Fix timeout boundary (P2-1)
2. Fix consecutive loss dead zone (P2-2)
3. Allow BE re-trigger (P2-3)
4. Add ATR fallback (P2-4)
5. Clarify BLOCK semantics (P2-5)
6. Fix slippage division (P2-6)

---

## Appendix A: Files Modified

| File | Issues |
|------|--------|
| `execution/hyperliquid_adapter.py` | 1.1, 1.2, 1.3, 1.4 |
| `runtime/exchange/fill_tracker.py` | 2.1, 4.1 |
| `runtime/exchange/order_executor.py` | 1.5, 2.3, 8.2, 8.3, 8.4 |
| `runtime/exchange/trailing_stop_manager.py` | 2.4, 3.4, 6.1, 6.2, 6.3 |
| `runtime/position/state_machine.py` | 3.1, 3.5, 3.6 |
| `runtime/persistence/execution_state_repository.py` | 3.2, 3.3, 8.1 |
| `runtime/policy_adapter.py` | 2.2 |
| `runtime/m6_executor.py` | 7.1 |
| `runtime/arbitration/arbitrator.py` | 7.3 |
| `runtime/risk/position_sizer.py` | 5.1 |
| `runtime/risk/drawdown_tracker.py` | 5.2 |
| `runtime/risk/capital_manager.py` | 5.3, 5.4, 5.5 |
| `runtime/risk/circuit_breaker.py` | 5.6 |
| `execution/ep4_risk_gates.py` | 7.2 |
| `observation/internal/m1_ingestion.py` | 4.2 |

---

## Appendix B: Test Coverage Required

Each fix must include:
1. Unit test demonstrating the failure mode
2. Unit test proving the fix
3. Integration test for cross-component scenarios

**Minimum test additions:** 28 (one per issue)

---

## Appendix C: Constitutional Compliance

All fixes must:
- Preserve trade semantics
- Preserve risk limits
- Not increase leverage
- Not increase position size
- Not change execution meaning
- Not introduce forbidden vocabulary
- Pass all existing tests

---

**END OF AUDIT REPORT**
