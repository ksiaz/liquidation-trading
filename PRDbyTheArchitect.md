Project Requirements Document (PRD)

Project Name: Epistemically-Constrained Execution System
Status: Canonical
Audience: Architect, Verification, Future Implementers
Authority: Epistemic Constitution + Position & Execution Constitution
Revision Policy: Amendments only, no silent drift

1. Problem Statement

Most automated trading systems fail not because of poor models, but because:

Interpretation is mixed with data

Confidence is fabricated from heuristics

Execution logic depends on pre-digested signals

Risk constraints are advisory instead of constitutional

“Strategy” logic leaks across layers

This produces systems that cannot be reasoned about, audited, or proven safe, and that fail silently under stress.

2. Project Purpose

To build a deterministic, auditable, epistemically sound execution system that:

Operates only on raw data

Enforces hard invariants instead of heuristics

Separates observation, decision emission, arbitration, and execution

Prevents semantic interpretation from leaking across boundaries

Makes unsafe or ambiguous behavior structurally impossible

This system is not designed to “predict markets”.
It is designed to execute mandates correctly and safely.

3. Core Design Principles
3.1 Epistemic Discipline

The system may only know what it can prove

Silence is preserved as silence

Absence of data is not information

No confidence, strength, or quality claims exist anywhere

3.2 Raw-Data Exclusivity

Only raw exchange data is admissible at system boundaries

Any derived, aggregated, or interpreted data must:

Remain internal

Die at the boundary

Never influence downstream layers implicitly

3.3 Determinism Over Intelligence

Given the same inputs, the system produces the same outputs

No probabilistic, heuristic, or adaptive behavior is permitted at boundaries

“Smartness” is replaced with explicit structure

3.4 Constitutional Enforcement

Invariants are enforced structurally, not by convention

Violations halt execution

No “best effort”, “fallback”, or “graceful degradation”

4. System Scope (What This Project Is)
4.1 In Scope

The project defines and enforces:

Raw Data Primitives

Trades, liquidations, order book events, timestamps

No indicators, signals, or summaries

Observation Layer

Records facts

Enforces invariants

Exposes only epistemically safe fields

Mandate Emission

Stateless

Rule-driven

Emits intent, not execution

Mandate Arbitration

Symbol-local

Single-cycle

Authority-ordered

Deterministic

Execution Action Contract

ENTRY / EXIT / REDUCE / HOLD / NO_ACTION

Strict compatibility with position state

Position State Machine

Single position per symbol

Deterministic lifecycle

No implicit transitions

Risk & Exposure Invariants

Hard limits

No confidence-based sizing

Liquidation avoidance as invariant, not optimization

Formal Verification Artifacts

Invariant proofs

Adversarial examples

Semantic leak audits

5. Explicit Non-Goals (Out of Scope)

This project explicitly does not include:

Alpha generation

Signal discovery

Indicators (RSI, VWAP, etc.)

Machine learning

Reinforcement learning

Confidence scoring

Probabilistic reasoning

Strategy optimization

Backtesting frameworks

PnL maximization logic

“Smart” execution heuristics

Any of the above, if desired, must live outside this system and interact only via constitutionally valid mandates.

6. Layered Architecture (Conceptual)
RAW DATA
   ↓
OBSERVATION (facts only, invariant-enforced)
   ↓
MANDATE EMISSION (stateless, rule-based)
   ↓
MANDATE ARBITRATION (conflict resolution)
   ↓
EXECUTION ACTION (single action per symbol)
   ↓
POSITION STATE MACHINE
   ↓
EXCHANGE


Each arrow represents a hard epistemic boundary.

7. Safety Guarantees (What This System Guarantees)

If implemented correctly, the system guarantees:

No execution without explicit mandate

No conflicting actions per symbol per cycle

No position reversal without full exit

No exposure growth beyond invariant limits

No semantic interpretation leaks

No hidden state influencing behavior

No silent failures

8. Failure Semantics

Failures are:

Explicit

Terminal

Non-recoverable without restart

The system prefers halting over guessing.

9. Verification Definition (What “Correct” Means)

The system is correct if:

All constitutional invariants hold under all inputs

All forbidden states are unreachable

All adversarial constructions fail safely

All semantic leak audits pass

All layers remain independent and non-interpreting

Determinism holds across runs

Silence is preserved end-to-end

Profitability is not a correctness criterion.

10. Deliverables

This project produces:

Constitutional specifications (.md)

Annexes (raw data, semantic leak rules)

Formal invariants

Adversarial test cases

CI enforcement design

Reference models (optional)

It does not produce a finished trading bot.

11. Project Completion Criteria

The project is considered complete when:

The constitution is frozen

Annexes are complete

Semantic leak audits are exhaustive

Verification artifacts exist

Implementation can be audited against spec line-by-line

Anything beyond this is implementation work, not architecture.

12. Final Statement

This project is not about trading better.
It is about making unsafe, unverifiable trading systems impossible by construction.

Once this PRD is satisfied, the architectural work is complete.

End of PRD