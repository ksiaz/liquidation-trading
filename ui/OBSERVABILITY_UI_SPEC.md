# Live-Run Observability UI - Implementation Specification

**Date:** 2026-01-05  
**Purpose:** Human observability interface for Phase V1-LIVE  
**Authority:** Empirical Pressure Testing Requirements

---

## Objective

Create a **strictly observational** UI that reveals:
- What the system sees
- What the system proposes
- What is permitted/rejected
- What would have executed (ghost)
- Why nothing happened

**Critical:** This UI does NOT control the system. It renders truth.

---

## Hard Prohibitions

❌ No control buttons  
❌ No strategy toggles  
❌ No parameter editing  
❌ No "execute", "pause", or "override"  
❌ No semantics ("good trade", "bad trade")  

---

## Data Sources (Read-Only)

### 1. Audit Events
```typescript
interface AuditEvent {
  trace_id: string;
  timestamp: number;
  strategy_id: string;
  decision_code: "AUTHORIZED_ACTION" | "NO_ACTION" | "REJECTED_ACTION";
  action_type?: string;
  execution_result?: "SUCCESS" | "NOOP" | "FAILED_SAFE" | "REJECTED";
  reason_code: string;
  symbol: string;
}
```

### 2. Ghost Execution Records
```typescript
interface GhostExecutionRecord {
  trace_id: string;
  execution_mode: "GHOST_LIVE" | "SNAPSHOT";
  orderbook_snapshot_id: string;
  best_bid: number;
  best_ask: number;
  spread: number;
  would_execute: boolean;
  fill_estimate: "FULL" | "PARTIAL" | "NONE";
  reject_reason?: string;
}
```

### 3. Snapshot Metadata
```typescript
interface SnapshotMetadata {
  snapshot_id: string;
  symbol: string;
  timestamp: number;
}
```

---

## UI Sections (Exact Implementation)

### 1. Live Status Header
**Purpose:** Situational awareness

**Displays:**
- System mode (LIVE GHOST / SNAPSHOT REPLAY)
- Symbols monitored
- Current time vs snapshot time
- Event throughput (events/min)
- Last activity timestamp

**No controls. Display only.**

### 2. Strategy Activity Panel
**Purpose:** Is the system thinking?

**For each EP-2 strategy:**
- Strategy ID
- Proposals attempted (count)
- Proposals emitted (count)
- Last proposal timestamp
- Abstention count
- % time silent

**Prevents false assumption: "System is broken" when it's correctly abstaining.**

### 3. Decision Timeline (Core View)
**Purpose:** Event history

**Scrollable, append-only timeline. Each row:**
- Timestamp
- Trace ID
- Strategy ID
- Decision Code
- Reason Code
- Action Type (if any)

**Color rules (strict, non-semantic):**
- Gray → NO_ACTION
- Yellow → AUTHORIZED_ACTION
- Red → REJECTED_ACTION
- Blue → FAILED_SAFE

### 4. Ghost Execution Detail Drawer
**Purpose:** Market reality inspection

**Clicking timeline row opens drawer showing:**
- Order type (LIMIT / MARKET)
- Quantity
- Price (if limit)
- Best bid / ask
- Spread
- Fill estimate
- Reject reason (if any)
- Snapshot ID

**This is where market realism becomes visible.**

### 5. Metrics Panel
**Purpose:** Structural pressure insight

**Displays (aggregates only):**
- Proposal frequency per strategy
- Authorization rate
- Execution feasibility rate
- Partial-fill frequency
- Rest-in-book frequency
- Risk-gate failure counts
- Cooldown violations

**All metrics are counts, ratios, histograms. No averages that imply optimization.**

### 6. Snapshot Replay Selector
**Purpose:** Deterministic analysis

**Allows:**
- Selecting snapshot by ID or time
- Replaying exact ghost execution outcomes
- Comparing LIVE vs SNAPSHOT outcomes

**Replay mode:**
- Disables live streaming
- Locks UI state
- Clearly displays "REPLAY MODE"

### 7. History Browser
**Purpose:** Forensic analysis

**Features:**
- Filter by symbol
- Filter by strategy
- Filter by decision_code
- Filter by execution_result
- Export raw JSON (no transformation)

---

## Technical Stack

**Frontend:** React + TypeScript  
**State:** Event-driven (no mutation)  
**Charts:** Simple histograms/counters  
**Backend:** WebSocket (live) + REST (history)  
**Styling:** Neutral, grayscale, no "trading colors"

---

## Non-Functional Requirements

✓ Must handle hours/days of data  
✓ Must not crash if nothing happens  
✓ Must not assume execution ever occurs  
✓ Must tolerate very low signal density  
✓ Must not infer meaning  

---

## Design Philosophy

> This UI exists to reveal pressure, not success.  
> Silence is a valid outcome.  
> Abstention is information.  
> Reality is allowed to disagree.

---

## Implementation Priority

1. **Phase 1:** Decision timeline + Live status (core observability)
2. **Phase 2:** Strategy activity + Metrics (structural insight)
3. **Phase 3:** Ghost execution drawer (market reality)
4. **Phase 4:** Snapshot replay + History browser (analysis)

---

## File Structure

```
ui/
  src/
    components/
      LiveStatusHeader.tsx
      StrategyActivityPanel.tsx
      DecisionTimeline.tsx
      GhostExecutionDrawer.tsx
      MetricsPanel.tsx
      SnapshotReplaySelector.tsx
      HistoryBrowser.tsx
    hooks/
      useAuditEvents.ts
      useGhostRecords.ts
      useSnapshots.ts
    types/
      events.ts
      metrics.ts
    App.tsx
  backend/
    api_server.py  # REST + WebSocket server
```

---

**Next:** Begin UI implementation
