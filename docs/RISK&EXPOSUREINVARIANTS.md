RISK & EXPOSURE INVARIANTS

(Symbol-Local, Account-Bounded, Non-Interpretive)

1. Scope

Risk & Exposure Invariants define hard limits on:

Capital at risk

Leverage usage

Liquidation proximity

Aggregate exposure

Position sizing bounds

These invariants:

Apply before execution

Are enforced per symbol and per account

Are independent of strategy

Cannot be overridden by mandates, confidence, or opportunity

2. Definitions

Let:

Equity = current account equity

Balance = account balance

MarginUsed = total margin currently allocated

FreeMargin = Equity − MarginUsed

PositionNotional(symbol) = |position_size × price|

Leverage(symbol) = PositionNotional / AllocatedMargin

LiquidationPrice(symbol) = exchange-defined liquidation threshold

EntryPrice(symbol) = average entry price

MarkPrice(symbol) = current mark price

3. Maximum Risk Per Position (Hard Ceiling)

Invariant R1 — Per-Position Risk Cap

For any ENTRY action:

MaxLoss(symbol) ≤ RiskFraction × Equity


Where:

RiskFraction is a fixed constant (e.g., 1%)

MaxLoss is defined strictly by stop-distance to liquidation or forced exit

Violation → ENTRY is forbidden.

4. Leverage Ceiling Invariant

Invariant R2 — Absolute Leverage Cap

For any OPEN or ENTERING state:

Leverage(symbol) ≤ MaxLeverage


Where MaxLeverage is a fixed system constant.

No dynamic leverage escalation

No conditional leverage exceptions

Violation → ENTRY forbidden or EXIT forced.

5. Liquidation Distance Invariant

Invariant R3 — Liquidation Safety Margin

At all times:

DistanceToLiquidation(symbol) ≥ MinLiquidationBuffer


Where:

DistanceToLiquidation = |MarkPrice − LiquidationPrice| / MarkPrice


If violated:

ENTRY forbidden

REDUCE required

EXIT mandatory if REDUCE cannot restore compliance

6. Exposure-Aware Leverage Constraint

Invariant R4 — Exposure-Scaled Leverage

Leverage must monotonically decrease as exposure increases:

d(Leverage) / d(PositionNotional) ≤ 0


Meaning:

Increasing size cannot increase leverage

Scaling in must reduce effective leverage or hold it constant

7. Aggregate Exposure Ceiling

Invariant R5 — Account-Wide Exposure Cap

Σ PositionNotional(all symbols) ≤ ExposureCap × Equity


Violation → New ENTRY forbidden across all symbols.

8. Symbol Concentration Limit

Invariant R6 — Single-Symbol Exposure Limit

PositionNotional(symbol) ≤ SymbolExposureCap × Equity


Prevents:

Single-symbol dominance

Hidden correlated risk via leverage

9. Directional Exposure Symmetry

Invariant R7 — Direction Neutrality

Risk limits apply identically to:

Long

Short

No directional bias is permitted at the risk layer.

10. Entry Size Determinism

Invariant R8 — Deterministic Sizing

Given:

Equity

RiskFraction

StopDistance

LeverageCap

Position size must be uniquely determined.

No discretionary sizing.
No confidence scaling.
No adaptive overrides.

11. Reduction Priority Rule

Invariant R9 — Risk-First Reduction

When risk invariants are violated while OPEN or REDUCING:

REDUCE must be attempted first

EXIT only if REDUCE cannot restore invariants

Strategy intent is irrelevant.

12. No Risk Inference

Invariant R10 — No Implicit Risk Estimation

Risk must be computed from:

Prices

Margin

Equity

Exchange liquidation rules

Forbidden:

Volatility estimates

Model-based risk

Probabilistic drawdown forecasts

13. No Temporal Assumptions

Invariant R11 — Time-Agnostic Risk

Risk constraints do not relax based on:

Holding duration

Time in profit

Time since entry

14. Partial Exit Safety

Invariant R12 — Partial Exit Validity

Partial exits are permitted only if:

Post-Reduce state satisfies all invariants R1–R7


Otherwise:

Partial exit forbidden

Full EXIT required

15. No Averaging Down Invariant

Invariant R13 — No Risk-Increasing Additions

Additional ENTRY-like exposure is forbidden if it:

Increases MaxLoss

Reduces liquidation buffer

Increases leverage beyond pre-entry state

16. Margin Exhaustion Prohibition

Invariant R14 — Free Margin Floor

At all times:

FreeMargin ≥ MinFreeMargin


Violation → Immediate EXIT.

17. Exchange Constraint Supremacy

Invariant R15 — Exchange Rules Dominate

If exchange-imposed constraints are stricter than internal ones:

Exchange rules override

No attempt to bypass or approximate

18. Failure Semantics

If risk checks cannot be evaluated due to missing data:

ENTRY forbidden

REDUCE forbidden

EXIT permitted

Silence ≠ permission.

19. Observability Requirement

All quantities used in invariants must be:

Explicit

Measurable

Auditable

No hidden variables.

20. Completeness Statement

These invariants:

Fully bound exposure

Prevent liquidation-driven failure

Are strategy-independent

Are non-negotiable

21. Constitutional Lock

Any modification to:

RiskFraction

Leverage caps

Exposure caps

Liquidation buffers

Requires constitutional amendment, not runtime configuration.