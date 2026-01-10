CI SEMANTIC LEAK GUARDRAILS

(Automatic Rejection Rules)

Objective:
Reject code that appears compliant but introduces interpretation, memory, adaptation, or semantic meaning.

These rules operate on static text inspection only.

1. Forbidden Semantic Vocabulary (Hard Fail)
1.1 Interpretive Market Language

Reject if any identifier, comment, or string literal matches:

\b(
pressure|strength|weak|strong|confidence|probability|likely|unlikely|
momentum|trend|bias|signal|quality|good|bad|safe|unsafe|
support|resistance|zone|range|regime|condition|
absorption|imbalance|liquidity|sweep|hunt
)\b


Rationale:
These words encode meaning, not raw fact.

1.2 Directional Interpretation
\b(
bull|bear|bullish|bearish|long|short|
reversal|continuation|breakout|fakeout
)\b

2. Derived Metrics & Aggregation (Hard Fail)
2.1 Rolling / Window Structures
\b(
deque|maxlen|rolling|window|sliding|
last_\d+|recent|history|buffer
)\b

2.2 Statistical Functions
\b(
mean|avg|average|std|stddev|variance|
median|percentile|quantile|zscore|sigma
)\b

2.3 Threshold Semantics
\b(
threshold|limit|cap|floor|ceiling|
tolerance|epsilon|margin|buffer
)\b

3. Memory & State Leakage (Hard Fail)
3.1 Persistent Containers
\b(
cache|memo|store|saved|previous|last_state|
_seen|visited|registry|lookup
)\b

3.2 Default Mutable Arguments (Python)
def\s+\w+\([^)]*=\s*(\[\]|\{\}|set\(\))

3.3 Globals
^\s*(global|static)\b

4. Adaptation & Learning (Hard Fail)
4.1 Feedback / Adjustment
\b(
adjust|adapt|update|learn|refine|
optimize|tune|calibrate|drift
)\b

4.2 Self-Modification
\b(
increment|decrement|\+=|\-=|\*=|/=
)\b


(Except raw counters in observation ingestion only, reviewed manually)

5. Risk Interpretation (Hard Fail)
5.1 Risk-Based Scaling
\b(
scale|scaled|multiplier|fraction|ratio|
risk_adjust|exposure_adjust
)\b

5.2 Soft Risk Language
\b(
safer|riskier|conservative|aggressive|
hedge|protect|defensive
)\b

6. Control-Flow Smuggling (Hard Fail)
6.1 Retry / Resilience Logic
\b(
retry|backoff|attempt|reconnect|
sleep\(|timeout
)\b

6.2 Loops in Execution / Arbitration
\b(
while\s+True|for\s+\w+\s+in\s+range|
asyncio\.create_task|schedule|timer
)\b

7. Mandate Semantics Violations
7.1 Dynamic Authority
\b(
rank\s*\+=|priority\s*\+=|escalate
)\b

7.2 Multiple Actions
emit\s*\([^)]*\)\s*.*emit\s*\(

8. Cross-Symbol Leakage
\b(
portfolio|correlation|other_symbols|
cross_symbol|global_exposure
)\b

9. Documentation & Comment Leaks (Hard Fail)
9.1 Narrative Language in Comments
#.*(
expect|anticipate|suggests|indicates|
means that|implies|therefore
)

9.2 Justifications
#.*(
because|so that|in order to|reason
)

10. Exception Semantics
\b(
LiquidityError|RiskError|MarketError|
SignalError|ConfidenceError
)\b

CI ENFORCEMENT POLICY
Severity Levels
Rule Class	Action
Semantic Vocabulary	❌ Hard fail
Memory / State	❌ Hard fail
Adaptation	❌ Hard fail
Derived Metrics	❌ Hard fail
Documentation leaks	❌ Hard fail
Ambiguous math	⚠️ Manual review
False Positives (Expected & Acceptable)

Raw counters (count += 1)

Exchange protocol terminology (validated manually)

File paths or filenames (CI may ignore /docs)

Rule:

False positives slow developers.
False negatives destroy the constitution.

Coverage Estimate
Category	Caught Automatically
Semantic leaks	~85%
Hidden memory	~90%
Adaptive behavior	~95%
Soft risk logic	~80%
Narrative drift	~75%
Final Lock Statement

Any code rejected by these rules is not “almost correct”.
It is provably incompatible with a non-interpretive system.