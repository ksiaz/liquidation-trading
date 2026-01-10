EP-4 Execution Policy Layer

Design Specification v1.0

Status: Draft (Pending Freeze)
Scope: Deterministic execution of authorized actions
Authority: EP-3 Arbitration Output + M6 Permission
Market Context: Crypto perpetual futures (e.g., Binance)
Semantic Policy: ZERO market interpretation

1. Purpose & Non-Goals
1.1 Purpose

EP-4 is the only layer permitted to cause external side effects.

Its role is to:

deterministically execute authorized actions,

enforce hard risk and safety constraints,

remain mechanically correct under exchange conditions,

produce auditable execution traces.

EP-4 answers only:

"Given this authorized action, how do we carry it out safely?"

1.2 Explicit Non-Goals

EP-4 does NOT:

decide whether to act (EP-3)

decide what to do (EP-2)

decide why to do it (external policy)

evaluate profitability, edge, expectancy

adapt, learn, or optimize

infer intent from market data

2. Inputs & Outputs
2.1 Required Inputs

Mandatory (all immutable):

PolicyDecision (from EP-3)

ExecutionContext

exchange identifier (e.g., BINANCE_PERP)

symbol

timestamp

account_id (opaque)

ExecutionConfig

risk ceilings

execution mode

exchange constraints snapshot

EP-4 never queries M1–M6.

2.2 Outputs

One of:

ExecutionResult.SUCCESS

ExecutionResult.NOOP

ExecutionResult.REJECTED

ExecutionResult.FAILED_SAFE

All outputs must include:

trace_id

decision_id

timestamp

reason_code

3. Action Grammar (v1.0)

Actions are mechanical instructions, not strategies.

3.1 Allowed Action Types
ACTION_OPEN_POSITION
ACTION_CLOSE_POSITION
ACTION_ADJUST_POSITION
ACTION_CANCEL_OPEN_ORDERS
ACTION_NOOP


No other action types are permitted in v1.0.

3.2 Action Schemas
ACTION_OPEN_POSITION
OpenPositionAction:
    action_id: str
    symbol: str
    side: LONG | SHORT
    quantity: float
    order_type: MARKET | LIMIT
    limit_price: Optional[float]
    reduce_only: False
    time_in_force: GTC | IOC


Constraints:

quantity > 0

limit_price required iff LIMIT

reduce_only == False

ACTION_CLOSE_POSITION
ClosePositionAction:
    action_id: str
    symbol: str
    quantity: Optional[float]  # None = full close
    order_type: MARKET
    reduce_only: True

ACTION_ADJUST_POSITION
AdjustPositionAction:
    action_id: str
    symbol: str
    delta_quantity: float


Positive = increase, negative = decrease.
Must not violate risk gates.

ACTION_CANCEL_OPEN_ORDERS
CancelOrdersAction:
    action_id: str
    symbol: Optional[str]  # None = all symbols

ACTION_NOOP

Explicit do-nothing instruction.
Always succeeds.

4. Execution Rules (Deterministic)

Execution proceeds in strict sequence.

Rule 1 — Authorization Gate (Absolute)

If:

PolicyDecision.decision_code != AUTHORIZED_ACTION

→ NOOP, return ExecutionResult.NOOP

Rule 2 — Schema Validation

If:

action schema invalid

required fields missing

forbidden combinations present

→ REJECTED

No attempt is made to "fix" inputs.

Rule 3 — Risk Gate Evaluation (Pre-Execution)

All gates evaluated before touching exchange.

Failure of any gate → FAILED_SAFE

Rule 4 — Exchange Constraint Alignment

Validate:

min/max order size

step size

tick size

margin mode compatibility

leverage bounds

No rounding heuristics allowed:

If incompatible → FAILED_SAFE

Rule 5 — Execution Attempt

Exactly one exchange call per action

No retries in v1.0

No partial execution handling (delegated to exchange)

Rule 6 — Post-Execution Verification

Verify:

order acknowledged

rejection reason (if any)

timestamp consistency

If ambiguous → FAILED_SAFE

5. Risk Gates (Hard, Non-Negotiable)

Risk is binary, not optimized.

5.1 Exposure Gates

Max absolute position size

Max notional exposure

Max leverage per symbol

Max concurrent open positions

5.2 Temporal Gates

Minimum time between executions

Cooldown after FAILED_SAFE

Optional trading session windows

5.3 Action Frequency Gates

Max actions per minute

Max opens per symbol

Max cancels per window

5.4 Exchange Health Gates

API latency threshold

Order rejection rate threshold

Margin availability check

6. Failure Modes & Safe Behavior
6.1 FAIL-SAFE is the Default

When uncertain → do nothing.

6.2 Enumerated Failure Modes
Failure	Result
Schema invalid	REJECTED
Risk gate violation	FAILED_SAFE
Exchange rejection	FAILED_SAFE
Timeout / no ack	FAILED_SAFE
Duplicate execution	NOOP
Ambiguous state	FAILED_SAFE
6.3 Post-Failure Behavior

After FAILED_SAFE:

Optional forced ACTION_CANCEL_OPEN_ORDERS

Enforced cooldown

No automatic retries

Requires fresh authorization

7. Binance-Specific Considerations (Abstracted)

EP-4 must account for, but not embed semantics about:

Partial fills

Funding rate side effects

Liquidation engine behavior

Reduce-only enforcement

Margin mode mismatches (cross vs isolated)

These are treated as mechanical constraints, not strategy signals.

8. Determinism & Auditability
8.1 Determinism

Identical inputs ⇒ identical decisions.

No clocks except provided timestamps.
No randomness.
No stateful memory beyond explicit context.

8.2 Audit Log (Mandatory)

Each execution emits:

{
  "trace_id": "...",
  "policy_decision_id": "...",
  "action_id": "...",
  "execution_result": "...",
  "timestamp": "...",
  "reason_code": "...",
  "exchange_response": "opaque"
}

9. Versioning & Extension Policy

v1.0: Single-shot execution only

No retries

No batching

No dynamic sizing

No adaptive logic

All extensions require:

new version

explicit authorization

regression certification

10. Design Summary (Why This Fits Your System)

Separates causality from interpretation

Preserves epistemic firewall

Compatible with Binance perps reality

Fails safe under uncertainty

Auditable, deterministic, minimal

This is not a trading system.

It is a structurally correct actuator.
