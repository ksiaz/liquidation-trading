# HARD FAILURE MODE SPECIFICATION
**Role:** Epistemic Safety Agent
**Date:** 2026-01-06
**Status:** DESIGN DRAFT

---

## 1. Philosophy: Silence ≠ Failure
In an observational system, "nothing happened" is a valid state. "I don't know what happened" is a failure state.
The system currently treats "I don't know" as "Everything is OK". This must end.

**The Golden Rule:** If the system cannot prove a Metric is coherent, it **MUST NOT** display it.

---

## 2. Invariants & Failure Triggers

The following invariants are **Atomic**. If any single check fails, the entire Observation System enters `CRITICAL_FAILURE` mode.

### Invariant A: Time Monotonicity (The Arrow of Time)
*   **Definition:** Time `T` can never regress. `T_new >= T_current`.
*   **Trigger:** `advance_time(t)` called with `t < current_memory_time`.
*   **Recovery:** Fatal. Requires system restart/reset.
*   **Why:** Replay and baseline calculations break causality if time flows backward.

### Invariant B: Causality (Event Sequence)
*   **Definition:** An event with timestamp `T_event` cannot be ingested if `T_current > T_event + tolerance`.
*   **Trigger:** `ingest_observation` receives ancient history (lag > 30s) without explicit "Backfill Mode".
*   **Recovery:** Rejection (Log Error). If rate > 50%, escalate to Critical Failure.
*   **Why:** Prevents "ghosts from the past" from triggering Real-Time alerts.

### Invariant C: Governance Integrity (The Gate)
*   **Definition:** All queries must pass M5 validation.
*   **Trigger:** Internal code attempts to bypass M5 and read `_internal` state directly.
*   **Recovery:** Exception (Crash).
*   **Why:** Ensures no "secret" unvalidated data paths exist.

### Invariant D: Liveness (The Heartbeat)
*   **Definition:** System time must advance within `max_staleness` seconds of Wall Clock (in Live Mode).
*   **Trigger:** `WallClock - SystemTime > 5.0s`.
*   **Recovery:** `STALE` State.
*   **Why:** Prevents "Zombie UI" where the screen looks healthy but data is 10 minutes old.

---

## 3. Failure States & Display Requirements

The `SystemStatus` enum will replace the boolean `degraded`.

| State | Definition | UI Behavior | Data Access | trigger |
|-------|------------|-------------|-------------|---------|
| **OK** | All invariants hold. | Normal Display. | Full Read | Normal operation. |
| **STALE** | Data is valid but old (>5s lag). | **GRAYSCALE OVERLAY**. Banner: "CONNECTION LOST". Rates = "STALE". | Read Allowed (with warning tag) | Invariant D broken. |
| **SYNCING** | Backfill in progress. | Spinner. Banner: "CATCHING UP". | Read Restricted (Latest only) | Start-up / Reconnect. |
| **FAILED** | Invariant A, B, or C broken. | **RED SCREEN OF DEATH**. Stack Trace. "Run halted." | **BLOCKED**. Returns HTTP 500 / Exception. | Invariant A/B/C broken. |

### Specific UI Mandates
1.  **Rates of "0.0"**: Must be explicitly labeled "Quiet Market" vs "No Data".
    *   If `STALE`: Display "--.--" (Not Zero).
    *   If `OK` and rate is 0: Display "0.0 (Active)".
2.  **Snapshot Loading**:
    *   If `snapshot.json` timestamp is > 10s old: UI MUST display "SNAPSHOT OUTDATED".
    *   Cannot silently display old snapshot as current status.

---

## 4. Implementation Requirements for Phase 5

1.  **Add `ObservationStatus` Class:**
    ```python
    @dataclass
    class ObservationStatus:
        state: State  # OK, STALE, SYNCING, FAILED
        last_tick: float
        failure_reason: Optional[str]
    ```

2.  **Enforce Liveness Check in M5:**
    *   `M5.query()` matches `query_timestamp` vs `system_time`.
    *   If `Status == FAILED`, `query()` raises `SystemHaltedException`.

3.  **UI "Red Screen" Logic:**
    *   Native App must handle `SystemHaltedException` by hiding all panels and showing the Error View.
    *   It must NOT try to "render what it can".

---

## 5. Logging & Audit
*   **FAILED** state events are written to `fatal_error.log` immediately.
*   **STALE** transitions are logged to `latency.log`.
*   Silent failures are eliminated by the `Heartbeat` monitor (external to isolation layer).

**Success Condition:** You can unplug the internet, and within 5 seconds, the UI turns Gray/Red. It does not stay "Green/OK".
