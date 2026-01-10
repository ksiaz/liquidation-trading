ADVERSARIAL CODE EXAMPLES

(Almost Passes — Must Be Rejected)

Purpose:
Demonstrate how semantic leakage, interpretation, or adaptation can be smuggled in under “clean-looking” code.

Each example includes:

❌ Why it must be rejected

⚠️ Why it is tempting

🔒 Which constitutional rule it violates

A1. Rolling Count Disguised as a Counter
class TradeCounter:
    def __init__(self):
        self.count = 0

    def ingest(self, trade):
        self.count += 1
        if self.count > 100:
            self.count = 100


❌ Why Reject
Implicit saturation creates a hidden window and introduces interpretation (“enough trades”).

⚠️ Why Tempting
Looks like a harmless cap to avoid overflow.

🔒 Violates

Raw-data purity

No implicit windows

No derived thresholds

A2. Boolean Condition with Hidden Threshold Semantics
def large_trade(trade):
    return trade.size > 500


❌ Why Reject
The numeric threshold embeds semantic classification (“large”).

⚠️ Why Tempting
Returns a boolean; no scores, no floats.

🔒 Violates

No semantic labeling

No interpretation of magnitude

A3. Zone Detection Masquerading as Equality
if abs(price - level) < 0.5:
    emit(ENTRY)


❌ Why Reject
Tolerance introduces a zone (interpreted spatial concept).

⚠️ Why Tempting
Looks like numerical stability handling.

🔒 Violates

No zones

No spatial interpretation

No fuzzy equality

A4. Memory via Default Arguments
def emit_if_repeat(event, seen=set()):
    if event in seen:
        emit(BLOCK)
    seen.add(event)


❌ Why Reject
Hidden persistent memory across cycles.

⚠️ Why Tempting
Pure Python trick, no explicit state object.

🔒 Violates

Stateless mandate emission

No historical context

A5. Soft Risk Adjustment
size = base_size * 0.5 if exposure > limit else base_size


❌ Why Reject
Risk layer is modulating, not vetoing.

⚠️ Why Tempting
Still “risk-aware”, not aggressive.

🔒 Violates

Risk may only block, not adjust

No adaptive exposure

A6. Confidence Hidden as Count
if confirmations >= 3:
    emit(ENTRY)


❌ Why Reject
Confirmation count is equivalent to confidence accumulation.

⚠️ Why Tempting
No floats, no probabilities.

🔒 Violates

No accumulation

No multi-hit validation

A7. Exit Justification Leak
if drawdown > max_dd:
    emit(EXIT)  # safety exit


❌ Why Reject
“Safety” implies evaluative reasoning; drawdown is derived.

⚠️ Why Tempting
Industry-standard practice.

🔒 Violates

No quality assessment

No outcome-based interpretation

A8. Execution Retry with Backoff
for i in range(3):
    try:
        place_order()
        break
    except:
        sleep(2 ** i)


❌ Why Reject
Retry policy encodes belief about future success.

⚠️ Why Tempting
Looks like robustness.

🔒 Violates

No retries

No adaptive behavior

Event-scoped execution only

A9. Adaptive Threshold Drift
threshold = max(threshold, recent_avg)


❌ Why Reject
Introduces learning / adaptation.

⚠️ Why Tempting
Self-correcting logic feels “safe”.

🔒 Violates

No learning

No feedback loops

A10. Semantic Renaming Without Logic Change
pressure = trade.size


❌ Why Reject
Semantic leak through naming alone.

⚠️ Why Tempting
“Just a variable name”.

🔒 Violates

Semantic neutrality

Leak via language

A11. Window Without Time
last_trades = deque(maxlen=50)


❌ Why Reject
Implicit temporal window.

⚠️ Why Tempting
No timestamps involved.

🔒 Violates

No windows

No bounded memory

A12. Aggregation Masquerading as Metadata
snapshot = {
    "trade_count": len(trades),
    "unique_prices": len(set(p.price for p in trades))
}


❌ Why Reject
Derived metrics, not raw facts.

⚠️ Why Tempting
Looks informational, not interpretive.

🔒 Violates

Observation purity

No derived structure

A13. Conditional Mandate Priority
if mandate.type == ENTRY and urgency > 1:
    mandate.rank += 1


❌ Why Reject
Dynamic authority ranking.

⚠️ Why Tempting
“Edge case handling”.

🔒 Violates

Static authority ordering

Determinism

A14. Silent Default Action
action = action or HOLD


❌ Why Reject
Injects behavior where silence is required.

⚠️ Why Tempting
Prevents null handling bugs.

🔒 Violates

Silence preservation

No fabricated intent

A15. Cross-Symbol Awareness
if any(symbol in positions for symbol in correlated_set):
    emit(BLOCK)


❌ Why Reject
Breaks symbol-locality.

⚠️ Why Tempting
“Portfolio-aware risk”.

🔒 Violates

Symbol-local invariants

No cross-symbol reasoning

A16. Partial Exit Justification Logic
if price_near_zone:
    emit(REDUCE)
else:
    emit(EXIT)


❌ Why Reject
Interprets why a reduction vs exit is appropriate.

⚠️ Why Tempting
Matches discretionary trading intuition.

🔒 Violates

No scenario interpretation

No context-based choice

A17. Implicit Direction Inference
direction = BUY if price > vwap else SELL


❌ Why Reject
VWAP is derived; direction inferred.

⚠️ Why Tempting
Common TA idiom.

🔒 Violates

Raw data only

No indicators

A18. Comment-Level Semantic Leak
# Strong rejection here → expect reversal


❌ Why Reject
Documentation itself leaks interpretation.

⚠️ Why Tempting
“Just comments”.

🔒 Violates

Semantic containment

Human-facing leak rules

A19. Exception-Based Interpretation
except LiquidityError:
    emit(EXIT)


❌ Why Reject
Exception name encodes interpretation.

⚠️ Why Tempting
Clean error handling.

🔒 Violates

No causal interpretation

No inferred market state

A20. “Almost Stateless” Cache
_last_snapshot = None

def evaluate(snapshot):
    global _last_snapshot
    _last_snapshot = snapshot


❌ Why Reject
Memory without usage is still memory.

⚠️ Why Tempting
“Not used yet”.

🔒 Violates

Statelessness

Future semantic leak risk

SUMMARY RULE

If code answers any of the following implicitly, it must be rejected:

Is this significant?

Is this enough?

Is this safe?

Is this better?

Is this likely?

Those are interpretations, not facts.

Final Enforcement Clause

Any code that almost works by relying on intuition, convention, or trader experience
is precisely the code this system exists to forbid.