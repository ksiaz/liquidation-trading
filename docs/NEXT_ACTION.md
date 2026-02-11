# NEXT ACTION

**Date:** 2026-02-01
**Purpose:** Define one minimal integration step
**Type:** Action Specification (Not Roadmap)

---

## COMPLETED ACTION ✅

### Start the gRPC server and verify data flows to NodeBridge

**Status:** COMPLETED (2026-02-01 11:35)

**Evidence:**
- gRPC server running (PID 948783)
- Port 50051 listening
- 72,200+ prices broadcast
- 570 prices received by NodeSubscriber in 10s test
- 570 prices ingested via NodeBridge
- Liquidation parsing verified (5 historical events)

See: `docs/SYSTEM_BOOTSTRAP_REPORT.md`

---

## THE ONE NEXT ACTION

### Connect NodeBridge to paper trading loop

---

## SPECIFICATION

### What

Integrate NodeBridge into the paper trading runtime so HL node price data feeds the observation system during live operation.

### Where

The integration point is in `scripts/run_paper_trade.py` or equivalent entry point.

### Changes Required

1. Import NodeBridge: `from runtime.node_client.bridge import NodeBridge`
2. Create bridge instance with observation system reference
3. Start bridge before main loop: `bridge.start()`
4. Stop bridge on shutdown: `bridge.stop()`

### Expected Outcome

1. Paper trading loop starts normally
2. NodeBridge connects to gRPC server on :50051
3. HL_PRICE events flow into observation system
4. M1 buffers receive HL oracle prices
5. Diagnostics show "HL_PRICE" event type in logs

---

## OBSERVABILITY

### Success Criteria

| Check | How to Verify |
|-------|---------------|
| Bridge connected | Log: `[NodeBridge] Started, connected to localhost:50051` |
| Prices flowing | Bridge metrics: `prices_ingested > 0` |
| M1 receiving | Diagnostic: HL_PRICE events in ingest log |
| No errors | Bridge metrics: `errors == 0` |

### Failure Criteria

| Symptom | Meaning |
|---------|---------|
| "Connection refused" | gRPC server not running |
| `prices_ingested == 0` | No price data flowing |
| `errors > 0` | Event processing failures |

---

## WHY THIS ACTION

### It Is The Next Logical Step

- gRPC server is running (verified)
- NodeBridge works in isolation (tested)
- Now we integrate it with the actual runtime

### It Is Observable

- Bridge has metrics (`get_metrics()`)
- Observation system has diagnostics
- Connection status is logged

### It Is Reversible

- Remove bridge.start() call
- No persistent changes
- System returns to Binance-only mode

### It Is Minimal

- Adds one import
- Adds 3 lines of code
- No architectural changes

---

## WHAT THIS ACTION DOES NOT DO

| Out of Scope | Why |
|--------------|-----|
| Replace Binance data | HL_PRICE is separate from Binance prices |
| Generate mandates | Requires full observation system |
| Execute trades | Requires mandates |
| Fix dead components | Separate issue (requires position data) |

---

## DEPENDENCIES

### Required Before This Action

1. gRPC server running — ✅ VERIFIED (PID 948783)
2. Port 50051 listening — ✅ VERIFIED
3. NodeBridge tested — ✅ VERIFIED (570 events ingested)

### Nothing Else Required

---

## ROLLBACK PROCEDURE

```bash
# Remove bridge integration from paper trading script
# Kill gRPC server if needed
pkill -f "python.*server.py"
```

---

## NEXT STEP AFTER SUCCESS

**IF** NodeBridge integration works:

→ Run paper trading loop with DIAG_PRINT=1 to observe HL_PRICE events

```bash
cd /media/ksiaz/D/liquidation-trading
DIAG_PRINT=1 python scripts/run_paper_trade.py
```

But that is the NEXT next action. One step at a time.

---

## SUMMARY

| Attribute | Value |
|-----------|-------|
| **Previous Action** | Start gRPC server (✅ COMPLETED) |
| **Current Action** | Connect NodeBridge to paper trading loop |
| **Location** | `scripts/run_paper_trade.py` |
| **Lines of Code** | ~3 new lines |
| **Reversible** | Yes |
| **Observable** | Yes (metrics, logs) |
| **Dependencies** | gRPC server running (verified) |
| **Risk** | Low |

---

*This is one action, not a roadmap. Complete this before proposing the next.*

*Updated: 2026-02-01*
