EXECUTABLE REFERENCE MODEL

Document Class: Normative Reference
Purpose: Define the minimal executable shape of the system
Scope: Raw Data → Observation → Primitives → Mandates → Arbitration → Execution
Audience: Implementers, auditors, reviewers
Non-Goals: Performance, profitability, completeness

0. Model Guarantees

This reference model guarantees:

No semantic interpretation

No hidden state

No learning

No prediction

No feedback loops

No implicit behavior

If an implementation deviates, this model wins.

1. Data Flow Topology (One-Way)
RAW STREAMS
   ↓
Observation Builder
   ↓
Primitive Extractor
   ↓
Mandate Emitter
   ↓
Arbitration
   ↓
Execution (M6)


No arrows go upward.

2. Core Data Types
2.1 Raw Event
RawEvent:
    symbol: str
    event_type: { TRADE, LIQUIDATION, BOOK }
    timestamp: int
    payload: dict

2.2 ObservationSnapshot (External Boundary)
ObservationSnapshot:
    status: { UNINITIALIZED, FAILED }
    timestamp: int | None
    symbols_active: list[str]
    counters: None
    promoted_events: None


Invariant:
No other fields are allowed.

3. Observation System (M1–M5)
3.1 Observation Builder
def build_observation(raw_events) -> ObservationSnapshot:
    if invariant_broken(raw_events):
        return ObservationSnapshot(
            status=FAILED,
            timestamp=None,
            symbols_active=[]
        )

    if raw_events is empty:
        return ObservationSnapshot(
            status=UNINITIALIZED,
            timestamp=None,
            symbols_active=[]
        )

    return ObservationSnapshot(
        status=UNINITIALIZED,
        timestamp=max(e.timestamp for e in raw_events),
        symbols_active=unique_symbols(raw_events)
    )


Notes:

No liveness checks

No freshness logic

No wall clock

UNINITIALIZED does not mean “starting”

4. Primitive Extraction
4.1 Primitive Definition

A primitive is:

Deterministically computable

Raw-derived

Non-semantic

Nullable

Example primitives:

Primitive:
    name: str
    value: number | bool | None

4.2 Example Primitive Extractor
def extract_primitives(raw_events):
    return {
        "last_trade_price": last_trade_price(raw_events) or None,
        "last_trade_size": last_trade_size(raw_events) or None,
        "liquidation_count": count_liquidations(raw_events) or None,
        "price_velocity": abs(p2 - p1) / dt if computable else None
    }


Forbidden:

“Pressure”

“Strength”

“Signal”

“Trend”

“Bias”

5. Memory (Read-Only)
Memory:
    raw_primitives: list[Primitive]


Rules:

Append-only

No mutation

No aggregation

No learning

6. Mandate Emission
6.1 Mandate Structure
Mandate:
    symbol: str
    mandate_type: { ENTRY, EXIT, REDUCE, HOLD, BLOCK }
    authority_rank: int
    expiry_condition: callable
    trigger_id: opaque

6.2 Mandate Emitter Example
def emit_mandates(primitives, position_state):
    mandates = []

    if primitives["liquidation_count"] is not None:
        mandates.append(
            Mandate(
                symbol=primitives.symbol,
                mandate_type=REDUCE,
                authority_rank=2,
                expiry_condition=lambda: False,
                trigger_id="liq_reduce"
            )
        )

    return mandates


Key rule:
Mandates do not decide outcomes — only eligibility.

7. Arbitration
7.1 Authority Order (Fixed)
EXIT
REDUCE
BLOCK
HOLD
ENTRY

7.2 Arbitration Algorithm
def arbitrate(mandates, position_state):
    admissible = filter_by_position_state(mandates, position_state)

    if admissible is empty:
        return NO_ACTION

    highest = max(authority_rank in admissible)

    top = [m for m in admissible if m.authority_rank == highest]

    if multiple_conflict(top):
        return NO_ACTION

    return top[0].mandate_type

7.3 EXIT Supremacy
if any(m.type == EXIT for m in admissible):
    return EXIT


No exceptions.

8. Position Lifecycle
8.1 States
FLAT
ENTERING
OPEN
REDUCING
CLOSING

8.2 Transition Table
Current	Action	Next
FLAT	ENTRY	ENTERING
ENTERING	OPEN	OPEN
OPEN	REDUCE	REDUCING
REDUCING	OPEN	OPEN
OPEN	EXIT	CLOSING
CLOSING	FLAT	FLAT

No other transitions allowed.

9. Execution (M6)
9.1 Minimal Executor
def execute(snapshot, arbitration_result):
    if snapshot.status == FAILED:
        raise SystemHaltedException()

    if snapshot.status == UNINITIALIZED:
        return

    if arbitration_result == NO_ACTION:
        return

    perform_exchange_action(arbitration_result)

9.2 M6 Hard Constraints

Stateless

Event-scoped

No retries

No loops

No logging

No memory

10. Failure Semantics
10.1 Invariant Failure
if invariant_broken:
    snapshot.status = FAILED

10.2 Propagation

FAILED halts everything downstream

No downgrade

No recovery

11. What This Model Deliberately Does NOT Do

No PnL tracking

No strategy evaluation

No confidence scoring

No optimization

No learning

No “edge” logic

Those belong outside this model.

12. Reference Model Usage Rule

An implementation is correct iff:

Its behavior can be mapped to this model without adding logic.

If you need to “explain” behavior → violation.

STATUS: Executable Reference Model COMPLETE