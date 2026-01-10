Replay Harness & Instrumentation Specification v1.0

Version: v1.0
Status: AUTHORIZED
Purpose: Offline validation & behavior discovery

1. Objective

The replay harness exists to answer one question only:

"What does the system actually do when exposed to real market history?"

It is not for optimization, tuning, or learning.

2. Scope of Replay

Replay MUST execute the entire pipeline:

Market Data →
M1 →
M2 →
M3 →
M4 →
M5 →
EP-2 →
M6 →
EP-3 →
EP-4 (NO-EXECUTE MODE)


No shortcuts. No mocks except where explicitly stated.

3. Inputs
Required Inputs

Historical market data (candles, trades, order book updates)

Timestamps preserved exactly

Deterministic ordering guaranteed

Optional Inputs

Multiple symbols

Multiple timeframes (must remain independent)

4. Execution Mode

EP-4 runs in DRY-RUN MODE:

All risk gates evaluated

All exchange constraints checked

No real orders placed

Exchange adapter returns simulated acknowledgements only

5. Instrumentation (Mandatory Logs)

The replay harness MUST record:

Observation Metrics

Primitive outputs per tier

Distribution of zero / non-zero primitives

Proposal Metrics

Proposal count per EP-2 strategy

Proposal co-occurrence (conflicts)

Proposal suppression due to M6 denial

Arbitration Metrics

AUTHORIZED vs NO_ACTION vs REJECTED counts

Reason codes distribution

Execution Metrics

SUCCESS / FAILED_SAFE / NOOP counts

Risk gate failure reasons

Exchange constraint failures

Temporal Metrics

Time between actions

Burst patterns

Extended inactivity windows

6. Forbidden Replay Behaviors

The replay harness MUST NOT:

Modify system state

Cache outputs across runs

Adapt thresholds

Suppress failures

Retry actions

Inject randomness

Replay must be bit-reproducible.

7. Output Artifacts

Each replay run produces:

Structured log file (JSON / Parquet)

Summary report:

Counts

Ratios

Failure modes

Reproducibility hash:

Input data hash

System version hash

Configuration hash

8. Evaluation Philosophy

Replay answers:

When does the system act?

When does it abstain?

Why does it refuse to act?

Replay does not answer:

Whether actions were profitable

Whether signals were "good"

Whether strategy is optimal

PnL analysis comes after structural validation, not before.

9. Success Criteria for Replay

Replay is considered successful if:

System runs end-to-end without mutation

Outputs are deterministic

All failure modes are explicit and explainable

No silent behavior exists

10. Next Authorized Step

Upon successful replay validation:

Enable EP-4 testnet adapter, or

Authorize Tier B-2 Phase 2 (only if replay exposes blind spots)
