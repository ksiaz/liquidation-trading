# INTEGRATION DECISION

**Date:** 2026-02-01
**Purpose:** Decide whether a dedicated Node Adapter is needed
**Type:** Architecture Decision Record

---

## THE QUESTION

> Do we need a dedicated Node Adapter (RPC / gRPC / WS) layer, or is the current bridge sufficient?

---

## ANSWER: NO, the current bridge is sufficient.

---

## JUSTIFICATION

### What Already Exists

1. **File-based readers** (`~/.hl-node-adapter/readers/`)
   - `price_reader.py` — Reads SetGlobalAction from replica_cmds
   - `liquidation_reader.py` — Reads fills from node_fills/hourly
   - Both are VERIFIED working (tested 2026-02-01)

2. **gRPC Server** (`~/.hl-node-adapter/grpc_server.py`)
   - Broadcasts PriceEvent, LiquidationEvent, SyncStatus
   - Proto schema defined (events.proto)
   - Server code complete, just not running

3. **NodeBridge** (`runtime/node_client/bridge.py`)
   - Connects to gRPC server on localhost:50051
   - Normalizes HL events to M1 canonical format
   - LONG→SELL, SHORT→BUY conversion implemented
   - Metrics tracking built in

4. **NodeSubscriber** (`runtime/node_client/subscriber.py`)
   - gRPC client with callbacks
   - Handles price, liquidation, status, disconnect events

### What Problem Would a New Adapter Solve?

| Problem | Already Solved By |
|---------|-------------------|
| Reading HL node files | `price_reader.py`, `liquidation_reader.py` |
| Streaming events | gRPC server + NodeSubscriber |
| Normalizing to M1 | NodeBridge._handle_price/liquidation |
| Error handling | Bridge has _errors counter, diagnostics |
| Reconnection | Subscriber has disconnect callback |

**A new adapter would duplicate existing functionality.**

### What's Actually Missing

The problem is not architecture. The problem is:

1. **The gRPC server is not running**
2. **The collector service is not running**
3. **No process is consuming the data that exists**

This is an **operational gap**, not an **architectural gap**.

---

## WHAT THE CURRENT BRIDGE ENFORCES

### Contracts

1. **Event Type Normalization**
   - HL_PRICE → separate buffer (not Binance equivalent)
   - HL LIQUIDATION → canonical LIQUIDATION (LONG→SELL, SHORT→BUY)

2. **Timestamp Handling**
   - Uses wall clock for governance freshness (bridge.py:77)
   - Preserves original timestamp in payload (bridge.py:88)

3. **Schema Compliance**
   - Binance-compatible payload format for normalize_liquidation
   - HL-specific metadata preserved but not processed

### What It Must NOT Do

- Make trading decisions
- Interpret market conditions
- Filter events based on strategy
- Buffer/batch events (real-time only)

**The current bridge already enforces these constraints.**

---

## RISKS OF ADDING A NEW ADAPTER

| Risk | Impact |
|------|--------|
| Code duplication | Two paths for same data = inconsistency |
| Interface divergence | New adapter might use different schema |
| Testing burden | Two adapters to maintain |
| Complexity | More code = more bugs |
| Temporal confusion | Which adapter is "the one"? |

---

## RECOMMENDATION

### Do NOT create a new adapter.

### Instead:

1. **Start the gRPC server** — It exists, just isn't running
2. **Start the collector service** — It exists, just isn't running
3. **Verify data flows** — Using existing diagnostics

### The architecture is complete. The operation is incomplete.

---

## DECISION MATRIX

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Create new adapter | Fresh start | Duplicates existing code, risk of divergence | REJECT |
| Modify existing bridge | Leverage existing work | May need bug fixes | ACCEPT with caution |
| Start existing components | Zero code changes | May expose latent bugs | **PREFERRED** |

---

## VERIFICATION PLAN

Before concluding the bridge is sufficient, verify:

1. **gRPC server can start** — `python ~/.hl-node-adapter/server.py`
2. **NodeSubscriber can connect** — Check for handshake
3. **Events flow to M1** — Watch for ingest_observation calls
4. **Diagnostics fire correctly** — `DIAG_PRINT=1`

If any of these fail, document the failure. Do not create a new adapter without evidence that the current one is fundamentally broken.

---

## FINAL ANSWER

**NO, we do not need a dedicated Node Adapter layer.**

The current bridge (`runtime/node_client/bridge.py`) is architecturally sufficient. The gap is operational (processes not running), not architectural (missing components).

**Adding a new adapter would increase complexity and risk without solving the actual problem.**

---

*This decision can be revisited if the current bridge proves fundamentally broken during verification.*

*Generated: 2026-02-01*
