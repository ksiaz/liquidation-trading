# Production Deployment Plan (Option A)

**Objective:** Deploy the integrated Liquidation Trading System (Observation + M6 Execution) to a live environment for validation.

**Status:** Ready to Deploy
**Target Environment:** Local Workstation with Visualization (Stage 1)

---

## 1. System Components to Deploy

| Component | Role | Status |
|-----------|------|--------|
| **Observation System** | Ingests Binance data, computes M4 primitives | ✅ Production Ready |
| **Collector Service** | Connects to Binance WebSocket | ✅ Production Ready |
| **Policy Adapter** | Generates mandates from primitives | ✅ Integration Tested |
| **Execution Controller** | Processes mandates (Risk + Arbitration) | ✅ Integration Tested |
| **UI Monitor** | Visualizes system state & execution cycles | ✅ Updated for M6 |

---

## 2. Pre-Deployment Checks

- [x] **Code Freeze**: No uncommitted changes in `observation/`, `runtime/`.
- [x] **Tests Passing**: All 44 core tests passing.
- [x] **Scanning**: Semantic leak scanner passing (0 violations).
- [x] **Integration**: `main.py` updated to wire M6 execution layer.

---

## 3. Deployment Instructions

### A. Environment Setup

Ensure Python 3.9+ environment with dependencies:
```bash
pip install PySide6 websockets aiohttp
```

### B. Execution

Run the runtime application:
```bash
python runtime/native_app/main.py
```

### C. Verification (Live Monitor)

1. **Startup Phase (0-10s):**
   - Status: `UNINITIALIZED`
   - Symbols: Increasing count (0 -> 10)
   - Background: Dark Blue

2. **Active Phase (>10s):**
   - Status: `SYSTEM ACTIVE`
   - Background: Dark Green (`#002200`)
   - **Key Metrics to Watch:**
     - `Execution Cycle`: Should update every ~250ms.
     - `Mandates Received`: > 0 implies structural detection.
     - `Actions Executed`: > 0 implies successful arbitration & risk check.
     - `Actions Rejected`: Warnings/Risk blocks (expected in volatile conditions without sufficient margin).

---

## 4. Monitoring & Validation

**Success Criteria:**
1. System stays `ACTIVE` for > 1 hour.
2. `Mandates Received` > 0 within 24 hours (structural events are rare).
3. No `Red Screen of Death` (SystemHaltedException).
4. UI updates smoothly without freezing.

**Logging:**
- Console output will show `UI Error` or critical exceptions.
- `ObservationSystem` logs to internal buffers (viewable via debugger if needed, or implement file logging in Phase 9).

---

## 5. Rollback Plan

If `SYSTEM HALTED` (Red Screen) appears:
1. Close application immediately.
2. Check console log for Exception traceback.
3. Report failure code (e.g., `M6_INVARIANT_BROKEN`).
4. Revert `runtime/native_app/main.py` if wiring is suspected.

---

## 6. Next Actions (Post-Deployment)

- **Monitor**: Run for 24 hours.
- **Analyze**: If mandates are generated, capture screenshots/logs.
- **Refine**: Tune `RiskConfig` if too many valid actions are rejected.
