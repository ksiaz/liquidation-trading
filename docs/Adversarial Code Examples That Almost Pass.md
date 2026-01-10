# Adversarial Code Examples That Almost Pass
(Formal Negative-Specification Catalogue)

## Status
CONSTITUTIONAL SAFETY ANNEX  
Normative, non-executable

---

## 1. Purpose

This document enumerates **adversarial code patterns** that appear compliant under
superficial review but **must be rejected** under constitutional interpretation.

These examples define the **boundary of correctness by counterexample**.

> If a reviewer hesitates on any example below, the system is already compromised.

---

## 2. Threat Model

The adversary is **not malicious**.

The adversary is:
- Competent
- Well-intentioned
- Optimizing for convenience
- Familiar with the Constitution but tempted by shortcuts

Therefore, these examples are *plausible*, not contrived.

---

## 3. Observation Layer Adversarial Patterns

### 3.1 Silent Semantic Field Leak

```python
@dataclass(frozen=True)
class ObservationSnapshot:
    status: ObservationStatus
    timestamp: float
    symbols_active: list[str]
    volatility_hint: Optional[float]  # "Just informational"

Why it almost passes

    Optional

    Nullable

    “Hint” sounds harmless

Why it must be rejected

    Encodes derived meaning

    Invites interpretation

    Violates epistemic ceiling even if always None

3.2 Neutral-Sounding Derived Metric

internal_pressure_score = compute_score(events)

Used only internally.

Why it almost passes

    Internal variable

    Never exposed directly

Why it must be rejected

    Semantic aggregation without scoped exception

    May influence downstream logic implicitly

Allowed only inside declared exception directories.
3.3 Timestamp Arithmetic as Liveness Proxy

if now - last_event_ts > 5:
    status = UNINITIALIZED

Why it almost passes

    No “STALE” language

    Uses only timestamps

Why it must be rejected

    Temporal inference

    Encodes freshness semantics

    Violates silence rule

4. Mandate Emission Adversarial Patterns
4.1 “Weak” Mandate with Soft Language

emit_mandate(
    type=HOLD,
    reason="uncertain conditions"
)

Why it almost passes

    HOLD is allowed

    Reason is informational

Why it must be rejected

    “Uncertain” is epistemic interpretation

    Reasons are externalizable semantics

Mandates may not justify themselves.
4.2 Confidence-Weighted Mandates

if confidence > 0.7:
    emit(ENTRY)

Why it almost passes

    Confidence never exposed

    ENTRY itself is valid

Why it must be rejected

    Confidence is a hidden semantic scalar

    Arbitration must not consume strength, confidence, or scores

4.3 Multiple Mandates with Intentional Priority

emit(REDUCE)
emit(EXIT)  # "EXIT will win anyway"

Why it almost passes

    Arbitration resolves conflicts

    EXIT supremacy exists

Why it must be rejected

    Violates single-action invariant

    Emission phase must not rely on arbitration side-effects

5. Arbitration Adversarial Patterns
5.1 Tie-Breaking by Heuristic

selected = max(mandates, key=lambda m: m.confidence)

Why it almost passes

    Deterministic

    Local decision

Why it must be rejected

    Introduces semantic ranking

    Authority is the only legal ordering

5.2 Remembering Last Cycle’s Mandate

if last_cycle_action == EXIT:
    suppress_entry()

Why it almost passes

    Appears defensive

    Improves “stability”

Why it must be rejected

    Cross-cycle memory

    Violates stateless arbitration invariant

6. Execution Layer Adversarial Patterns
6.1 “Safety” Auto-Reduction

if unrealized_loss > threshold:
    reduce_position()

Why it almost passes

    Risk-aware

    Protective

Why it must be rejected

    Execution interpreting PnL

    Mandate-free action

    Violates separation of concerns

6.2 Implicit Direction Flip

if short_signal and long_position:
    close_and_reverse()

Why it almost passes

    Single function call

    Efficient

Why it must be rejected

    Collapses EXIT + ENTRY

    Violates lifecycle and direction invariance

7. Logging & Telemetry Adversarial Patterns
7.1 Neutralized Logging Language

logger.info("state advanced")

Why it almost passes

    Vague

    No quality words

Why it must be rejected

    Implies progress

    External speech about system behavior

7.2 Numeric Telemetry Leak

metrics.emit("mandates_emitted", count)

Why it almost passes

    Purely numeric

    No interpretation

Why it must be rejected

    Activity assertion

    Enables external inference

8. Configuration-Based Backdoors
8.1 Feature Flag Execution

if config.enable_m6:
    execute(snapshot)

Why it almost passes

    Explicit

    Configurable

Why it must be rejected

    Configuration-based invocation

    Bypasses architectural wiring discipline

9. Test Code That Must Be Scrutinized
9.1 Golden-Path Tests Only

assert action == ENTRY

Why it almost passes

    Tests correctness

    Clean

Why it must be rejected

    Does not test forbidden paths

    Masks invariant violations

Tests must include rejection assertions.
10. Meta-Violation: “We Know What We’re Doing”

Any argument of the form:

    “This is internal”

    “It won’t be used”

    “We’ll remove it later”

    “It’s just for debugging”

Is automatically invalid.
11. Completeness Statement

This list is not exhaustive.

It is:

    Representative

    Adversarial

    Grounded in real failure modes

Any code that feels similar to the above must be treated as suspect.
12. Constitutional Lock

This document defines rejection precedents.

Future designs must prove they are not equivalent to any pattern above.

END OF DOCUMENT