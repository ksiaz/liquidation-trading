# SYSTEM TEMPORAL CONTEXT

**Date:** 2026-02-01
**Purpose:** Reconstruct when each subsystem became operational
**Type:** Timeline Reconstruction (Evidence-Based)

---

## TIMELINE (Commit Evidence)

```
2026-01-16: Cascade primitives integrated into M1-M5 observation layer
           commit e81994f
           NOTE: Built BEFORE node adapter existed

2026-01-17: Hyperliquid position indexer added
           commit ee27949
           NOTE: Uses WebSocket API, not node files

2026-01-21: HLP data storage strategy documented
           commit 9ee3e6e
           NOTE: Planning phase, not implementation

2026-01-25: SLBRS and EFFCS strategies added
           commit c1b5051
           NOTE: Built WITHOUT node data source

2026-01-25: Production hardening, real adapter
           commit b657ff8
           NOTE: Still WebSocket-based, not node

2026-01-26: HL oracle price ingestion added to M1/governance
           commit 8ffd5e1
           NOTE: First HL_PRICE event support

2026-01-27: HL_ORDER event routing added
           commit 9cb9bde
           NOTE: Orders routed but no consumer

2026-01-28: Node adapter mode added for Hyperliquid
           commit a8a5bb1
           NOTE: First gRPC client code

2026-01-28: Node liquidation bursts wired to cascade strategy
           commit db87304
           NOTE: Attempted wiring, but cascade primitives still dead

2026-01-28: Timestamp domain mismatch fixed
           commit 0871cb4
           NOTE: Was dropping HL data due to clock issues

2026-01-29: Proximity data wired from node bridge to cascade strategy
           commit ba48ea4
           NOTE: Wiring exists but data source missing

2026-01-29: M2 nodes created from HL liquidations and proximity
           commit fa48ff7
           NOTE: This actually works

2026-01-31: HL liquidations read from node_fills correctly
           commit 29b193e
           NOTE: Liquidation reader fixed

2026-02-01: gRPC server started, data flowing
           (this session)
           NOTE: First time node data actually reaches M1
```

---

## SUBSYSTEM ORDERING

```
[Binance ingestion exists] ← Core system, oldest (pre-2026-01-10)
           │
           ▼
[Strategies implemented] ← SLBRS/EFFCS/Cascade (2026-01-16 to 2026-01-25)
           │
           ▼
[Cascade primitives added] ← Built without data source (2026-01-16)
           │
           ▼
[Node adapter code written] ← gRPC client/server (2026-01-28)
           │
           ▼
[Node files available] ← HL node running (2026-01-26)
           │
           ▼
[Wiring attempted] ← Fixes for timestamp, proximity, etc. (2026-01-28-31)
           │
           ▼
[gRPC server started] ← First actual data flow (2026-02-01)
           │
           ▼
[Prices flowing] ← Verified in this session (2026-02-01)
```

---

## CRITICAL INSIGHT

### Most Code Was Built Before Its Data Source Existed

| Component | Built | Data Source Available | Gap |
|-----------|-------|----------------------|-----|
| Cascade primitives | 2026-01-16 | Never (requires WebSocket) | Still missing |
| SLBRS/EFFCS | 2026-01-25 | 2026-01-28 (node mode) | 3 days |
| Cascade Sniper | 2026-01-16 | Never | Still missing |
| HL_PRICE ingestion | 2026-01-26 | 2026-02-01 (today) | 6 days |
| Node Bridge | 2026-01-28 | 2026-02-01 (today) | 4 days |

**Consequence:** Code was written speculatively. No live verification was possible when it was written.

---

## WHY THINGS ARE BROKEN

### 1. get_latest_prices() Was Never Implemented

The method was referenced in service.py (2026-01-28) and run_paper_trade.py but never implemented in NodeBridge. This suggests:
- Code was written based on expected interface
- Interface was never actually implemented
- No test caught this because node mode was never run

### 2. Cascade Primitives Require HyperliquidCollector

```
Cascade primitives (2026-01-16)
    │
    └── Require: HyperliquidCollector.get_proximity()
                          │
                          └── Requires: WebSocket position tracking
                                              │
                                              └── Status: Connection fails (ping timeout)
```

The cascade primitives were designed around WebSocket collector, not node files. The node files don't contain position data, only fills.

### 3. NodeBridge Uses Different Event Types

| ObservationBridge (old) | NodeBridge (new) |
|------------------------|------------------|
| HL_LIQUIDATION | LIQUIDATION |
| adapter_pb2.MarketPriceEvent | subscriber.PriceEvent |

The old and new bridges use different event types and proto schemas. This creates confusion about which code path is active.

---

## WHAT BECAME OPERATIONAL TODAY

| Component | Status Before | Status Now |
|-----------|---------------|------------|
| gRPC Server | NOT RUNNING | RUNNING (PID 948783) |
| Price Reader | Tested once | ACTIVE (75,000+ prices) |
| Liquidation Reader | Tested once | ACTIVE (0 events, none occurred) |
| NodeSubscriber | Never tested | VERIFIED (570 events/10s) |
| NodeBridge | Never tested | VERIFIED (mock test) |
| ingest_observation(HL_PRICE) | Never received data | VERIFIED (mock test) |

---

## WHAT REMAINS NON-OPERATIONAL

| Component | Reason |
|-----------|--------|
| Paper trade script | Crashes on get_latest_prices() |
| service.py node mode | Crashes on get_latest_prices() |
| Cascade primitives | Require position data from WebSocket |
| HyperliquidCollector | WebSocket connection fails |
| Cascade Sniper strategy | Depends on cascade primitives |
| SLBRS/EFFCS strategies | Regime never enters required state |

---

## CONCLUSION

The system was built speculatively in layers:

1. **Core Binance ingestion** (working) ← oldest
2. **Strategies and primitives** (partial) ← built before data
3. **Node adapter code** (broken) ← written but not tested
4. **gRPC server** (now working) ← just started today
5. **Full integration** (broken) ← missing methods, wrong assumptions

**Key Finding:** The code reflects intent, not reality. Components were written assuming interfaces that were never implemented.

---

*This timeline explains why code exists that cannot run.*

*Generated: 2026-02-01*
