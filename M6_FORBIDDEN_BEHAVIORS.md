# M6: FORBIDDEN BEHAVIORS & NON-ASSUMPTIONS (EXHAUSTIVE)

**Status:** Negative Capability Certification  
**Purpose:** Enumeration of prohibited M6 behaviors  
**Authority:** M6_CONSUMPTION_CONTRACT.md, EPISTEMIC_CONSTITUTION.md

---

## SECTION 1: FORBIDDEN READS

### Fields M6 Must Treat as Unknowable (Even if Technically Accessible)

**ObservationSnapshot fields:**
- `counters.windows_processed` - does not prove data processing occurred
- `counters.peak_pressure_events` - does not prove events are significant
- `counters.dropped_events` - does not prove complete drop tracking
- `promoted_events` list - does not prove baseline warmth or event meaningfulness
- Any field that returns None - does not distinguish "not implemented" from "not available"

**M1 Internal State:**
- `raw_trades` buffer length - does not prove market activity level
- `raw_liquidations` buffer length - does not prove market conditions
- `counters['trades']` - does not prove data completeness
- `counters['liquidations']` - does not prove observation health
- `counters['errors']` - does not prove error severity or cause

**M3 Internal State:**
- `_baseline.window_sizes` deque - does not prove baseline is warm
- `stats['windows_processed']` - does not prove windows contained data
- `stats['peak_pressure_events']` - does not prove statistical significance
- `stats['rejected_count']` - does not prove filter correctness
- `_current_windows` contents - does not prove window completeness
- `_current_window_start` - does not prove time coverage

**M5 Internal State:**
- `_system_time` - does not prove data freshness
- `_failure_reason` text - does not prove failure is recoverable
- `_allowed_symbols` - does not prove symbols have data

---

## SECTION 2: FORBIDDEN INFERENCES

### From Silence (UNINITIALIZED, empty buffers, empty lists)

M6 must never infer:
- Market is quiet
- No opportunities exist
- System is starting up
- Data will arrive soon
- Waiting is appropriate
- Initialization is in progress
- System is healthy but idle
- Observation is functional
- Absence of events means absence of market activity

### From UNINITIALIZED Status

M6 must never infer:
- System is booting
- System will become operational
- Temporary state
- Data is being fetched
- Synchronization is happening
- Warm-up period
- Calibration phase
- Safe to wait
- Safe to proceed with defaults

### From Timestamp Advancement

M6 must never infer:
- Data is flowing
- Observation is operational
- System is healthy
- Clock is synchronized
- Data is fresh
- Observation is processing
- Windows are being analyzed
- Market time is advancing
- Safe to assume liveness

### From Counters (If Reintroduced)

M6 must never infer:
- Counter increment means meaningful activity
- Counter value correlates with data quality
- High counter means system is working well
- Low counter means system is broken
- Counter ratio indicates health
- Counter trend indicates performance
- Zero counter means absence of data
- Non-zero counter means presence of valid data

### From Absence of FAILED Status

M6 must never infer:
- Observation is healthy
- Observation is operational
- Observation is trustworthy
- Safe to proceed
- Data is reliable
- System is ready
- Invariants are satisfied
- No errors exist

---

## SECTION 3: FORBIDDEN STATE TRANSITIONS

### When Observation is UNINITIALIZED

M6 must never:
- Initiate new execution actions
- Assume observation will transition to usable state
- Use cached observation data
- Use default values as substitutes
- Continue with "safe" assumptions
- Operate in degraded mode claiming functionality
- Assert readiness to external systems
- Claim capability
- Wait with expectation of data arrival
- Retry queries expecting different result

### When Observation is FAILED

M6 must never:
- Continue any execution operations
- Attempt to restart observation
- Attempt to recover observation state
- Bypass observation requirement
- Operate on last known state
- Downgrade failure to warning
- Suppress failure propagation
- Convert exception to boolean or enum
- Log "working around observation failure"
- Enter "safe mode" claiming continued functionality
- Wait for observation recovery
- Retry queries
- Assume failure is transient
- Assume failure is recoverable

### When Observation is Silent (Empty Buffers/Lists)

M6 must never:
- Substitute cached values
- Substitute default values
- Substitute derived values
- Proceed assuming "no news is good news"
- Interpret silence as market condition
- Use previous non-silent state as current
- Interpolate missing data
- Extrapolate from historical data
- Continue operations claiming data availability

---

## SECTION 4: FORBIDDEN LANGUAGE

### Prohibited Variable Names

- `observation_health`
- `observation_ready`
- `observation_ok`
- `data_quality`
- `baseline_ready`
- `baseline_warm`
- `data_fresh`
- `data_valid`
- `system_operational`
- `liveness`
- `uptime`
- `confidence`
- `strength`
- `edge`
- `signal`
- `opportunity`
- `setup`
- `bias`
- `market_regime`
- `market_condition`
- `pressure_level`
- `significance`
- `quality_score`
- `reliability`
- `trustworthiness`

### Prohibited Log Messages

- "Observation is healthy"
- "Observation is ready"
- "Data quality is good"
- "Baseline is warm"
- "System is operational"
- "Data is fresh"
- "Liveness confirmed"
- "Health check passed"
- "All systems go"
- "Ready to trade"
- "Confidence is high"
- "Strong signal detected"
- "Good opportunity"
- "Market conditions favorable"
- "Observation validated"
- "Data looks good"
- "Everything working normally"
- "No issues detected"

### Prohibited Comments

- "// observation is reliable here"
- "// baseline must be warm by now"
- "// data is fresh enough"
- "// safe to assume observation is working"
- "// this counter indicates good data"
- "// high events means strong signal"
- "// observation health verified"
- "// ready to proceed"
- "// market is active"
- "// valid opportunity detected"

### Prohibited Function Names

- `check_observation_health()`
- `verify_data_quality()`
- `assess_baseline_readiness()`
- `confirm_liveness()`
- `validate_observation()`
- `is_observation_ready()`
- `is_data_fresh()`
- `get_confidence_level()`
- `calculate_signal_strength()`
- `assess_opportunity_quality()`
- `evaluate_market_regime()`
- `check_system_health()`

### Prohibited Documentation Terms

- "observation validation"
- "data quality assurance"
- "health monitoring"
- "liveness detection"
- "readiness checking"
- "confidence scoring"
- "signal strength"
- "opportunity assessment"
- "market regime detection"
- "baseline verification"
- "system reliability"
- "observation uptime"
- "data freshness guarantee"

### Prohibited Metric Names

- `observation_health_score`
- `data_quality_percentage`
- `baseline_warmth_indicator`
- `liveness_status`
- `observation_uptime`
- `confidence_level`
- `signal_strength`
- `opportunity_score`
- `reliability_metric`

### Prohibited Error Messages

- "Observation degraded, continuing in safe mode"
- "Observation temporarily unavailable, using cached data"
- "Data quality low, reducing position size"
- "Baseline not ready, waiting for warm-up"
- "Observation unstable, proceeding cautiously"

### Prohibited Status Enums (for M6)

- `OBSERVATION_HEALTHY`
- `OBSERVATION_DEGRADED`
- `OBSERVATION_RECOVERING`
- `DATA_FRESH`
- `DATA_STALE`
- `BASELINE_WARM`
- `BASELINE_COLD`

---

## EXHAUSTIVENESS COMMITMENT

This enumeration is not complete.

Any term, phrase, variable, function, comment, or assertion that:
- Implies observation health
- Implies observation readiness
- Implies data quality
- Implies data freshness
- Implies baseline state
- Implies confidence
- Implies understanding
- Implies interpretation
- Implies market conditions
- Implies opportunity quality

Is forbidden, whether enumerated above or not.

When in doubt, the term is forbidden.

---

**END OF FORBIDDEN BEHAVIORS & NON-ASSUMPTIONS**

M6 is a consumer of structural input.
M6 is not an interpreter of meaning.
M6 is not an assessor of quality.
M6 is not a detector of readiness.
