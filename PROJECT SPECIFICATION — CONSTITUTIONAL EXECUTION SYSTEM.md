PROJECT SPECIFICATION — CONSTITUTIONAL EXECUTION SYSTEM
0. Purpose of This Document

This document is the authoritative project-level specification for the system. It consolidates scope, intent, guarantees, constraints, and remaining work. It is not a design doc for a single module, but a contract for the entire repository.

This document answers four questions definitively:

What this system is

What this system is not

What is constitutionally locked

What work remains before the system is complete

1. System Definition
1.1 What the System Is

The system is a constitutionally governed execution engine whose sole purpose is:

To transform raw market event streams into execution actions without interpretation, prediction, confidence, or semantic leakage.

It operates through:

Raw data ingestion

Stateless mandate emission

Deterministic mandate arbitration

Constitutionally constrained execution

The system does not attempt to understand the market. It only enforces rules.

1.2 What the System Is Not

The system is explicitly not:

A signal generator

A prediction engine

A statistical model

A confidence-based decision system

A strategy optimizer

A learning system

A discretionary framework

Any attempt to add these properties violates the constitution.

2. Architectural Layers (Locked)
2.1 Observation Layer

Purpose: Record facts and enforce epistemic boundaries.

Properties:

Consumes only raw data streams

Performs no interpretation

Exposes only constitutionally allowed fields

Enforces silence when truth cannot be proven

Forbidden:

Indicators

Baselines as signals

Scores, strengths, probabilities

Health or quality claims

2.2 Mandate Layer

Purpose: Emit stateless, expiring intent primitives.

Properties:

Stateless

Non-persistent

Symbol-local

Emitted per evaluation cycle

Mandate Types (Closed Set):

ENTRY

EXIT

REDUCE

HOLD

BLOCK

No other mandate types are permitted.

2.3 Arbitration Layer

Purpose: Resolve conflicting mandates deterministically.

Properties:

Single-cycle

Stateless

Symbol-local

At most one action per symbol per cycle

EXIT Supremacy: EXIT overrides all other mandates.

2.4 Execution Layer

Purpose: Enforce position lifecycle invariants.

Properties:

Enforces Position State Machine

Deterministic

No interpretation

No retries, recovery, or degradation

Execution is the only layer allowed to interact with exchanges.

3. Position Lifecycle (Locked)

The Position State Machine is fully specified and closed:

FLAT → ENTERING → OPEN → REDUCING → CLOSING → FLAT

No additional states, shortcuts, or inferred transitions are allowed.

4. Risk & Exposure Model (Partially Complete)
4.1 Locked Invariants

One position per symbol

No directional reversal without EXIT

Exposure must be bounded

REDUCE does not change direction

4.2 Incomplete (Work Remaining)

Formal leverage constraint

Liquidation avoidance invariant

Exposure aggregation rules

Partial vs full exit resolution under stress

5. Epistemic Constitution (Locked)
5.1 Core Principle

The system may only claim what can be proven directly from raw data.

If truth cannot be proven, the system must remain silent.

5.2 Raw Data Requirement

Only the following are constitutionally compliant inputs:

Trades

Order book updates

Liquidations

Funding updates

Exchange timestamps

Any pre-interpreted data source is forbidden.

6. Semantic Leak Control (In Progress)
6.1 Definition

A semantic leak occurs when internal meaning, interpretation, or implication crosses an external boundary.

6.2 Current State

Completed:

Boundary definition

Directory-scoped exception model

Incomplete:

Exhaustive leak catalog

Leak → rule mapping

Proof of closure

7. Enforcement & Tooling (In Progress)
7.1 Planned Enforcement

CI regex-based semantic scanning

Directory-scoped rule application

Diff-only scanning for performance

Pre-commit mirror of CI

7.2 Not Yet Complete

Full regex taxonomy

Adversarial examples

Required-status enforcement wiring

8. Formal Verification (Not Started)

Required but not yet completed:

Formal invariant proofs

Counterexample impossibility proofs

Executable reference model

Machine-verifiable spec (TLA⁺ / Alloy)

9. Project Status Summary
Complete & Locked

Constitutional architecture

Observation boundaries

Mandate model

Arbitration

Position lifecycle

M6 execution constraints

In Progress

Semantic leak audit

Enforcement design

Not Started

Formal proofs

Complete risk mathematics

10. Completion Criteria

The project is considered complete only when:

All semantic leaks are exhaustively cataloged

CI enforcement blocks all known leak patterns

Risk & exposure invariants are fully formalized

Formal proofs exist for all core invariants

Until then, the system is correct but incomplete.

11. Amendment Rule

Any change to:

Mandate types

State machine

Observation exposure

Execution semantics

Requires a constitutional amendment and cannot be implemented ad hoc.

End of Project Specification

Here is where we are, precisely, without drift or embellishment.

Current Project Condition (Authoritative)
What is complete and locked

You have successfully completed and frozen:

Epistemic Constitution

Observation speaks facts only

Silence over ambiguity

Raw-data primacy (now explicitly recognized)

No health, readiness, quality, or interpretation claims

Position & Execution Constitution

Position State Machine (FLAT → ENTERING → OPEN → REDUCING → CLOSING)

Deterministic transitions

Single-position, single-direction invariants

EXIT terminality

No implicit or inferred transitions

Mandate System (Core)

Mandate types (ENTRY / EXIT / REDUCE / HOLD / BLOCK)

Stateless, expiring mandates

Symbol-local, single-cycle evaluation

Authority ordering

Arbitration determinism

Single-action invariant

M6 Execution Constraints

Event-scoped, stateless execution

Hard dependency on observation

No retries, no background execution

Explicit failure propagation

No interpretation or exposure

These are done. Continuing to re-specify them would be duplication.

What you correctly discovered (critical insight)

You are not wrong about pre-interpreted data.

Any data that has already been algorithmically interpreted is constitutionally suspect.

This is a real architectural inflection point, not a minor addendum.

What this implies:

Indicators

Aggregated metrics

“Zones” computed elsewhere

Statistical labels

Any upstream “signal”

are not automatically admissible, even if widely used in trading systems.

This does not mean computation is forbidden.
It means epistemic claims must remain internal and never cross boundaries.

You correctly triggered the need for:

Annex A: Raw-Data Exclusivity

Semantic Leak Audits

Enforcement tooling

This was the right time to surface that concern.

What is in progress (and where work remains)

The remaining work is structural and defensive, not conceptual strategy design.

1. Semantic Leak Control (Major Remaining Block)

Still needed:

Exhaustive semantic leak catalog

Formal taxonomy of leak types

Directory-scoped exception framework (you started this)

Adversarial “almost valid” code examples

Explicit boundary proofs

This is not optional.
Without it, future contributors will unknowingly violate the constitution.

2. Enforcement Architecture (Design Stage)

Still needed:

CI rule taxonomy (regex + structural)

Mapping: violation → detection

Required status checks definition

Pre-commit parity model

Diff-only scanning strategy

You explicitly requested design only, not production code — correct.

3. Risk & Exposure Mathematics (Incomplete)

You have principles, but not yet:

Formal leverage bounds

Liquidation-avoidance invariant

Exposure aggregation logic

Partial vs full exit resolution under conflicting pressures

This is where your earlier research (liquidation cascades, absorption, memory zones) will feed in — as constraints, not signals.

4. Formal Verification Layer (Not Started)

Still outstanding:

Formal invariant proofs

Counterexample impossibility proofs

Executable reference model

Machine-verifiable spec (TLA⁺ / Alloy)

This comes last, after enforcement is designed.

What I just produced

I created an authoritative Project Specification document in the repository that:

Consolidates everything already completed

Clearly marks what is locked vs incomplete

Prevents future scope confusion

Gives you a stable anchor for future work

This document is not extra — it is a control surface for the project.

Recommended Next Steps (Strict Order)

To progress without duplication or drift, the next steps should be:

Semantic Leak Exhaustive Audit

Catalog every possible leak class

Include “looks harmless but isn’t” cases

Directory-Scoped Exception Framework

Where certain primitives are allowed internally

Explicit, minimal, auditable

Adversarial Code Examples

Code that almost passes

Used to validate enforcement design

CI / Tooling Design

Regex taxonomy

Mapping rules to violations

Required status checks

Only after those are done should you return to:

Risk math

Formal proofs