EXECUTION ACTION CONTRACT

(Minimal, Deterministic, Non-Interpretive)

1. Purpose

The Execution Action Contract defines how an arbitration result is translated into exchange-facing actions.

Execution:

Does not evaluate market data

Does not reinterpret mandates

Does not decide “how good” an action is

Does not modify or enrich intent

Execution is mechanical realization only.

2. Execution Scope Invariants
Invariant E1 — One-to-One Mapping

Each arbitration result maps to at most one execution action per symbol per cycle.

There is no action chaining.

Invariant E2 — No Hidden Decisions

Execution may not:

Choose direction

Choose timing

Choose size beyond allowed bounds

Choose order type beyond mandate constraints

All degrees of freedom must already be resolved upstream.

Invariant E3 — Statelessness

Execution holds no memory:

No knowledge of prior executions

No knowledge of past failures

No retry context

No adaptive behavior

3. Execution Action Primitive

An Execution Action is the only admissible output.

ExecutionAction
{
  symbol
  action_type ∈ { OPEN, CLOSE, REDUCE, NONE }
  direction ∈ { LONG, SHORT } | null
  size
  execution_constraints
}


If action_type = NONE, all other fields must be null.

4. Action-Type Mapping
Mandate Type	Execution Action
ENTRY	OPEN
EXIT	CLOSE
REDUCE	REDUCE
HOLD	NONE
BLOCK	NONE
NO_ACTION	NONE

No other mappings are permitted.

5. Direction Resolution Rule
Invariant E4 — Direction Source

Direction is determined only from:

The mandate (ENTRY)

The current position (EXIT / REDUCE)

Execution may not infer direction from price, flow, or indicators.

6. Size Determination Rules
Invariant E5 — Bounded Size

Execution size must satisfy all active constraints:

Position state machine

Risk & exposure invariants

Leverage constraints

Exchange minimums

Execution may clip, but may not expand, requested size.

Invariant E6 — No Optimization

Execution may not:

Optimize fill

Improve price

Adjust size for expectancy

Split orders strategically

All such logic is forbidden.

7. Execution Constraints Primitive

Execution constraints are pass-through only.

Examples:

Order type (market / limit)

Time-in-force

Reduce-only flag

Execution may not invent constraints.

8. Failure Handling Invariant
Invariant E7 — No Recovery Logic

Execution failure:

Is surfaced as-is

Is not retried

Is not reinterpreted

Does not trigger alternative actions

Failure propagation is mandatory.

9. Partial Execution Semantics

Partial fills:

Are treated as successful execution

Update position state accordingly

Do not trigger re-execution in the same cycle

Execution does not “finish the job”.

10. Execution Idempotence Rule
Invariant E8 — Idempotence

Given the same arbitration output:

Execution produces the same exchange request

Replays do not compound effects

Execution must be replay-safe.

11. Forbidden Execution Behaviors

Execution must never:

Query market data

Read indicators

Access liquidation levels

Access historical positions

Emit mandates

Emit logs with semantic meaning

Execution is blind.

12. Execution Result Primitive

Execution produces a result record:

ExecutionResult
{
  symbol
  action_type
  requested_size
  executed_size
  status ∈ { SUCCESS, PARTIAL, FAILED }
}


No interpretation is attached.

13. Constitutional Separation Invariant
Invariant E9 — Layer Isolation

Execution:

Must not call mandate emitters

Must not call arbitrators

Must not call observation layers

Direction of dependency is one-way.

14. Determinism Guarantee

Invariant E10 — Deterministic Execution

For identical inputs and exchange response:

Execution output is identical

No randomness permitted

15. Constitutional Lock

Any addition of:

Retry logic

Optimization

Adaptive sizing

Semantic error handling

Constitutes a constitutional violation.