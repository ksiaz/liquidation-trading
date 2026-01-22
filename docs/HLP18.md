ORDER EXECUTION PROTOCOLS
From Trading Decision to Filled Order

Order execution is where theory meets reality.

Perfect strategy + perfect timing + bad execution = loss.

This document defines exactly how orders are submitted, monitored, and managed on Hyperliquid.

Every scenario is covered.
Every edge case is handled.
No ambiguity.

---

PART 1: ORDER TYPES

Hyperliquid Order Types:

Market Order:
  - Executes immediately at best available price
  - Crosses spread
  - Accepts slippage
  - Guaranteed fill (in liquid markets)

Limit Order:
  - Executes only at specified price or better
  - May not fill
  - No slippage beyond limit
  - Can provide liquidity (maker)

Stop Market:
  - Triggers at stop price
  - Becomes market order when triggered
  - Used for stops

Stop Limit:
  - Triggers at stop price
  - Becomes limit order when triggered
  - May not fill if price gaps

Post-Only:
  - Limit order that must be maker
  - Rejected if would take liquidity
  - Earns maker rebate

IOC (Immediate or Cancel):
  - Fill immediately or cancel
  - Partial fills allowed
  - Remainder canceled

---

STRATEGY ORDER TYPE SELECTION

Entry Orders:

For liquidation cascade:
  - Use: Market order
  - Reason: Speed critical, entry window narrow
  - Acceptable slippage: Up to 0.5%

For failed hunt:
  - Use: Limit order (post-only if available)
  - Reason: Can wait for reversal fill
  - Price: At invalidation level

For funding snapback:
  - Use: Limit order
  - Reason: Gradual move, can be patient
  - Price: Current market + buffer

Default Entry Type: Market (prioritize execution)

Exit Orders (Stops):

Always use: Stop Market
  - Guaranteed execution
  - Accepts slippage to close
  - Cannot afford to hold losing position

Never use: Stop Limit
  - May not fill if gaps
  - Unacceptable risk

Exit Orders (Targets):

Use: Limit Order
  - Want to get target price
  - Can wait for fill
  - If not filled, manage manually

---

PART 2: SLIPPAGE HANDLING

Acceptable Slippage Thresholds:

Entry orders:
  - Normal: 0.2% (20 bps)
  - Aggressive: 0.5% (50 bps)
  - Maximum: 1.0% (100 bps)

Exit orders (market):
  - No limit on stops (get out at any price)
  - Target fills: 0% slippage (limit order)

Pre-Trade Slippage Estimation:

available_liquidity = sum_orderbook_depth(entry_price, max_slippage)

if position_size > available_liquidity:
  estimated_slippage = calculate_impact(position_size, orderbook)
  
  if estimated_slippage > threshold:
    - Reduce position size, or
    - Reject trade, or
    - Split into multiple orders

Post-Trade Slippage Measurement:

actual_slippage = (fill_price - expected_price) / expected_price

if actual_slippage > threshold:
  - Log warning
  - Investigate orderbook state
  - Adjust future estimates

Slippage Accounting:

Include slippage in PnL calculation:
  - Expected PnL (at mid price)
  - Actual PnL (at fill price)
  - Slippage cost = difference

Track slippage costs separately:
  - Total slippage paid
  - Average slippage per trade
  - Slippage as % of PnL

---

PART 3: PARTIAL FILL HANDLING

Scenario: Order partially filled

Example:
  Ordered: 1.0 BTC
  Filled: 0.7 BTC
  Remaining: 0.3 BTC

Decision Tree:

If filled >= 80% of order:
  - Accept partial fill
  - Cancel remaining
  - Adjust stop for actual position size
  - Continue

If filled < 80% of order:
  - Cancel remaining
  - Close partial position immediately
  - Reason: Position too small, risk/reward broken
  - Re-evaluate entry

Special Case: Entry During Cascade

If liquidation cascade:
  - Accept any partial fill > 50%
  - Cannot wait, window closing
  - Adjust stop proportionally

If failed hunt:
  - Require 90% fill minimum
  - Precision matters for reversal
  - Cancel if insufficient

---

PART 4: FILL MONITORING

Order Lifecycle:

1. SUBMITTED
   - Order sent to exchange
   - Awaiting acknowledgment

2. ACKNOWLEDGED
   - Exchange confirmed receipt
   - Order is active

3. PARTIAL
   - Some fills received
   - Order still active

4. FILLED
   - Completely filled
   - Order complete

5. CANCELED
   - Order canceled (by us or exchange)
   - No further fills

6. REJECTED
   - Exchange rejected order
   - Did not execute

Fill Detection Methods:

Method 1: WebSocket Order Updates (Primary)
  - Subscribe to order updates
  - Receive fill notifications in real-time
  - Latency: < 100ms

Method 2: Polling (Fallback)
  - Poll order status every 500ms
  - Use if WebSocket unavailable
  - Latency: 500ms average

Method 3: Position Monitoring (Validation)
  - Monitor position changes
  - Cross-check with order fills
  - Detect discrepancies

Use all three concurrently:
  - WebSocket for speed
  - Polling for reliability
  - Position for validation

---

Fill Timeout Handling:

For Market Orders:

if time_since_submission > 5 seconds AND status != FILLED:
  - Log error "Market order timeout"
  - Query order status
  - If still open:
    * Cancel order
    * Resubmit if still valid
  - If filled:
    * Update records
    * Possible notification delay

For Limit Orders:

if time_since_submission > 60 seconds AND fills == 0:
  - Acceptable (may not fill immediately)
  - Continue monitoring
  
if time_since_submission > 300 seconds AND fills == 0:
  - Cancel order
  - Re-evaluate if still want position

---

PART 5: ORDER AMENDMENTS

When to Amend:

Scenario 1: Price Moved Away from Limit Order
  - Limit order not filling
  - Price moved 0.5% away
  - Decision:
    * If entry window closing: Cancel, submit market order
    * If patient: Amend limit price closer
    * If invalidated: Cancel

Scenario 2: Stop Price Needs Adjustment
  - Position moved in favor
  - Want to trail stop
  - Decision:
    * Cancel existing stop
    * Submit new stop at trailing price

Amendment Race Conditions:

Problem: Order amends while being filled

Solution:
  1. Cancel existing order
  2. Wait for cancel confirmation
  3. Submit new order
  4. Handle fills during window:
     - If filled before cancel: Accept
     - If cancel confirms: Proceed with new order
     - If both happen: Reconcile positions

---

PART 6: EXECUTION LATENCY TARGETS

End-to-End Latency Budget:

From strategy decision to order acknowledged:

Decision made:                    T+0ms
Position reservation:             T+10μs
Order construction:               T+20μs
Slippage check:                   T+50μs
Risk validation:                  T+100μs
Order submission (network):       T+500μs
Exchange processing:              T+200μs
Acknowledgment received:          T+1ms

Total Target: < 2ms

Component Breakdown:

Internal processing: < 200μs
  - Strategy logic: 50μs
  - Position sizing: 50μs
  - Risk checks: 50μs
  - Order formatting: 50μs

Network latency: < 1ms
  - Node to exchange: 500μs
  - Exchange ACK back: 500μs

Exchange processing: < 1ms
  - Order validation: 500μs
  - Matching: 500μs

Alerting Thresholds:

If latency > 5ms: Warning
If latency > 10ms: Critical
If latency > 50ms: Emergency (something broken)

---

PART 7: ORDER SUBMISSION FLOW

Pre-Submission Checklist:

[ ] Position size calculated
[ ] Risk limits checked
[ ] Slippage estimated
[ ] Orderbook depth verified
[ ] Position slot reserved
[ ] Event lifecycle validated
[ ] Capital available

Submission Procedure:

1. Construct order:
   order = {
     "symbol": symbol,
     "side": "BUY" | "SELL",
     "size": position_size,
     "type": "MARKET" | "LIMIT",
     "price": limit_price (if limit),
     "reduce_only": false (for entries),
   }

2. Validate order:
   - All required fields present
   - Size > minimum
   - Size < maximum
   - Price within bounds (if limit)

3. Submit via API:
   response = exchange.submit_order(order)

4. Handle response:
   if response.status == "SUCCESS":
     order_id = response.order_id
     track_order(order_id)
     
   elif response.status == "REJECTED":
     reason = response.reason
     log_error(f"Order rejected: {reason}")
     release_position_reservation()
     
   else:
     log_error(" Unknown response")
     retry_or_abort()

5. Monitor for fill:
   Start fill monitoring (see Part 4)

---

PART 8: STOP LOSS EXECUTION

Stop Placement:

Immediately after entry fill:

1. Calculate stop price:
   if direction == LONG:
     stop_price = entry_price - stop_distance
   else:
     stop_price = entry_price + stop_distance

2. Submit stop order:
   stop_order = {
     "symbol": symbol,
     "side": opposite(entry_side),
     "size": position_size,
     "type": "STOP_MARKET",
     "stop_price": stop_price,
     "reduce_only": true,
   }

3. Verify stop active:
   - Query stop order status
   - Confirm stop price correct
   - Link to position

Time Constraint:

Stop must be placed within 1 second of entry fill.

If stop placement fails:
  - Alert operator immediately
  - Close position at market manually
  - Investigate failure

Stop Management:

Monitor stop order:
  - Ensure it remains active
  - Detect if canceled accidentally
  - Re-submit if missing

Trailing Stops (Optional):

If position moves favorably:
  - Cancel existing stop
  - Submit new stop at trailing price
  - Maintain minimum distance (e.g., 1%)

Never move stop unfavorably (widen loss).

---

PART 9: TARGET EXIT EXECUTION

Target Placement:

After entry fill + stop placed:

1. Calculate target price:
   target_price = entry_price ± (target_distance)
   
2. Submit limit order:
   target_order = {
     "symbol": symbol,
     "side": opposite(entry_side),
     "size": position_size,
     "type": "LIMIT",
     "price": target_price,
     "reduce_only": true,
     "post_only": true (if available),
   }

3. Monitor for fill

Target Not Filled:

If target not hit within expected time:
  - Check event lifecycle
  - If event COMPLETED: Close at market
  - If event ACTIVE: Continue monitoring
  - If invalidated: Close at market

Manual Target Management:

If price approaches target but doesn't fill:
  - Option 1: Amend limit closer (within 0.1%)
  - Option 2: Cancel, close at market
  - Option 3: Scale out (partial fills)

---

PART 10: POSITION RECONCILIATION

Why Needed:

Orders may:
  - Fill without notification
  - Partially fill
  - Get canceled by exchange
  - Experience communication delays

Reconciliation ensures actual position matches expected.

Reconciliation Frequency:

- After every order event (fill, cancel)
- Every 5 seconds (periodic check)
- On reconnection
- On error detection

Reconciliation Procedure:

1. Query actual position from exchange:
   actual_position = exchange.get_position(symbol)

2. Compare to internal records:
   expected_position = position_manager.get_position(symbol)

3. If mismatch, execute reconciliation algorithm:

RECONCILIATION ALGORITHM:

def reconcile_position(symbol):
    actual = exchange.get_position(symbol)
    expected = local_state.get_position(symbol)

    if actual == expected:
        return  # No action needed

    log_discrepancy(symbol, expected, actual)

    # Case 1: Exchange has position, we don't
    if actual != 0 and expected == 0:
        # CRITICAL: We have exposure we didn't track
        # Could be: missed fill notification, manual trade, system restart
        action = "EMERGENCY_CLOSE"
        reason = "Unknown position detected - close immediately"
        close_position_at_market(symbol)
        alert_operator(reason)
        return

    # Case 2: We think we have position, exchange says no
    if actual == 0 and expected != 0:
        # CRITICAL: Position was closed without our knowledge
        # Could be: liquidation, stop triggered but missed, manual close
        action = "RESET_LOCAL_STATE"
        reason = "Position closed externally - resetting state"
        local_state.clear_position(symbol)
        cancel_associated_orders(symbol)  # Cancel orphan stops/targets
        alert_operator(reason)
        return

    # Case 3: Both have position but sizes differ
    if actual != 0 and expected != 0 and actual != expected:
        # Size mismatch - trust exchange as source of truth
        action = "SYNC_TO_EXCHANGE"
        reason = f"Size mismatch: local={expected}, exchange={actual}"
        local_state.set_position(symbol, actual)

        # Adjust stop order size to match actual position
        update_stop_order_size(symbol, actual)

        # If actual > expected: missed fill (investigate)
        # If actual < expected: partial close (investigate)
        alert_operator(reason)
        return

RECONCILIATION RULES:

1. Exchange is ALWAYS source of truth for position size
2. After reconciliation, local state MUST match exchange
3. All mismatches trigger operator alert
4. Stop orders must be adjusted to match actual position
5. Never attempt to "fix" exchange position - only sync local state

---

PART 11: ERROR SCENARIOS

Error Scenario 1: Order Rejection

Possible Reasons:
  - Insufficient margin
  - Invalid price
  - Size too small
  - Rate limit exceeded
  - Symbol not tradable

Response:
  1. Log rejection reason
  2. Release position reservation
  3. If rate limit: Back off, retry later
  4. If invalid params: Fix and resubmit
  5. If account issue: Alert operator, halt trading

---

Error Scenario 2: Fill Price Far from Expected

Detection:
  fill_slippage = abs(fill_price - expected_price) / expected_price
  
  if fill_slippage > 2%:  # Extreme slippage
    log_error("Extreme slippage detected")

Possible Causes:
  - Flash crash
  - Orderbook temporarily thin
  - Large position size
  - Exchange execution issue

Response:
  1. Accept fill (cannot reverse)
  2. Adjust stop accordingly
  3. Flag for investigation
  4. Review sizing algorithms
  5. If systematic: Reduce position sizes

---

Error Scenario 3: Order Stuck

Detection:
  if order_status == "SUBMITTED" AND time_elapsed > 10s:
    log_error("Order stuck")

Response:
  1. Query order status manually
  2. If truly stuck:
     - Cancel order
     - Resubmit if still valid
  3. If filled but notification missed:
     - Update records
     - Reconcile position

Prevention:
  - Implement order timeouts
  - Active monitoring
  - Fallback to polling

---

Error Scenario 4: Stop Not Triggered When Expected

Detection:
  if price_crossed_stop AND position_still_open:
    log_critical("Stop failed to trigger")

Possible Causes:
  - Stop order canceled
  - Exchange malfunction
  - Price gap (stop limit instead of stop market)

Response:
  1. Close position immediately at market
  2. Investigate why stop didn't trigger
  3. Verify stop orders active
  4. Alert operator

Prevention:
  - Always use stop market (not stop limit)
  - Monitor stop order status
  - Redundant position monitoring

---

PART 12: ORDER EXECUTION LOGGING

Every order must be logged:

Order Submitted:
{
  "timestamp": nanoseconds,
  "order_id": "12345",
  "symbol": "BTC-PERP",
  "side": "BUY",
  "size": 0.5,
  "type": "MARKET",
  "expected_price": 50000,
  "strategy": "geometry",
  "event_id": "cascade_BTC_...",
}

Order Filled:
{
  "timestamp": nanoseconds,
  "order_id": "12345",
  "fill_price": 50025,
  "fill_size": 0.5,
  "slippage_bps": 5,
  "fill_latency_ms": 1.2,
}

Order Rejected:
{
  "timestamp": nanoseconds,
  "order_id": "12345",
  "reason": "INSUFFICIENT_MARGIN",
  "details": {...},
}

Stop Triggered:
{
  "timestamp": nanoseconds,
  "stop_order_id": "67890",
  "trigger_price": 49500,
  "fill_price": 49475,
  "position_closed": true,
}

---

PART 13: TESTING ORDER EXECUTION

Unit Tests:

[ ] Test order construction
[ ] Test slippage calculation
[ ] Test partial fill handling
[ ] Test stop placement
[ ] Test target placement
[ ] Test position reconciliation
[ ] Test error handling

Integration Tests:

[ ] Submit market order on testnet
[ ] Verify fill notification
[ ] Submit stop order
[ ] Verify stop triggers correctly
[ ] Test order cancellation
[ ] Test amendment race conditions

Paper Trading Tests:

[ ] Run full trading loop
[ ] Verify all orders execute correctly
[ ] Measure latency
[ ] Test under various market conditions
[ ] Validate reconciliation works

---

PART 14: EXECUTION PERFORMANCE METRICS

Track:

Order Submission Success Rate:
  - Orders submitted / orders attempted
  - Target: > 99%

Fill Rate:
  - Orders filled / orders submitted
  - Market orders: > 99.9%
  - Limit orders: varies

Average Slippage:
  - Track by order type
  - Market orders: < 0.1%
  - Exits: varies

Fill Latency:
  - Decision to fill confirmation
  - Target: < 5ms p50, < 20ms p99

Stop Execution Rate:
  - Stops triggered / stops expected
  - Target: 100%

Position Reconciliation Discrepancies:
  - Mismatches detected
  - Target: < 0.1%

---

IMPLEMENTATION CHECKLIST

[ ] Implement order construction logic
[ ] Implement order submission via API
[ ] Implement fill monitoring (WebSocket + polling)
[ ] Implement partial fill handling
[ ] Implement stop placement
[ ] Implement target placement
[ ] Implement position reconciliation
[ ] Implement slippage tracking
[ ] Implement error handling
[ ] Add execution logging
[ ] Build execution metrics dashboard
[ ] Write execution tests
[ ] Test on paper trading

---

BOTTOM LINE

Order execution is NOT:
  - "Just submit the order"
  - One-size-fits-all
  - Set and forget

Order execution IS:
  - Careful order type selection
  - Slippage management
  - Continuous monitoring
  - Error handling
  - Position reconciliation
  - Latency optimization

Perfect strategy + bad execution = loss.

Execution matters as much as the strategy.

Every latency improvement is profit.
Every slippage reduction is profit.
Every error prevented is capital preserved.

Build execution infrastructure with the same rigor as strategy logic.
