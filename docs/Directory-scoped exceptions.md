Design principle (explicit)

Default: forbidden everywhere

Exception: explicitly allowed only in whitelisted directories

No implicit allowances

Fail closed

Directory Policy Matrix (hard-coded)
Directory	Allowed
observation/internal/m1_ingestion/	counters, buffers, raw accumulation
observation/internal/m3_temporal/	windows, deques, rolling
observation/governance.py	NONE
arbitration/	NONE
mandate/	NONE
execution/	NONE
runtime/	NONE

No other directories receive exemptions.

GitHub Actions Workflow (Scoped)

Copy-paste exactly as is

# .github/workflows/semantic-constitution-ci.yml

name: Semantic Constitution Enforcement (Scoped)

on:
  pull_request:
  push:
    branches: [ main, master ]

jobs:
  semantic-guardrails:
    name: Semantic Leak Guardrails
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Semantic Leak Scan (Scoped)
        shell: bash
        run: |
          set -e

          echo "Running semantic constitution checks (scoped)..."

          # -------------------------------
          # Directory allowlists
          # -------------------------------
          INGEST_ALLOW="observation/internal/m1_ingestion"
          TEMPORAL_ALLOW="observation/internal/m3_temporal"

          # All scanned source files
          FILES=$(find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.rs" \))

          fail() {
            echo "::error::$1"
            exit 1
          }

          scan_global() {
            local pattern="$1"
            local message="$2"

            if grep -RInE "$pattern" $FILES; then
              fail "$message"
            fi
          }

          scan_except() {
            local pattern="$1"
            local except_dir="$2"
            local message="$3"

            if grep -RInE "$pattern" $FILES \
              | grep -v "$except_dir"; then
              fail "$message"
            fi
          }

          # =================================================
          # 1. Interpretive / semantic vocabulary (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(pressure|strength|weak|strong|confidence|probability|likely|unlikely|momentum|trend|bias|signal|quality|good|bad|safe|unsafe|support|resistance|zone|range|regime|absorption|imbalance|liquidity|sweep|hunt)\b' \
                      "Interpretive semantic vocabulary detected"

          scan_global '\b(bull|bear|bullish|bearish|long|short|reversal|continuation|breakout|fakeout)\b' \
                      "Directional interpretation detected"

          # =================================================
          # 2. Rolling / accumulation (ONLY allowed in ingestion & temporal)
          # =================================================
          scan_except '\b(deque|maxlen|rolling|window|sliding|buffer|history|recent)\b' \
                      "$INGEST_ALLOW\|$TEMPORAL_ALLOW" \
                      "Rolling or buffered state detected outside ingestion/temporal"

          scan_except '\b(mean|avg|average|std|stddev|variance|median|percentile|quantile|zscore|sigma)\b' \
                      "$TEMPORAL_ALLOW" \
                      "Statistical aggregation detected outside temporal layer"

          # =================================================
          # 3. Memory / persistence (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(cache|memo|saved|persist|registry|lookup|global_state|shared_state)\b' \
                      "Persistent memory semantics detected"

          scan_global 'def\s+\w+\([^)]*=\s*(\[\]|\{\}|set\(\))' \
                      "Default mutable argument detected"

          scan_global '^\s*(global|static)\b' \
                      "Global or static state detected"

          # =================================================
          # 4. Adaptation / learning (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(adapt|learn|optimize|tune|calibrate|refine|drift)\b' \
                      "Adaptive or learning behavior detected"

          scan_global '\+=|\-=|\*=|/=' \
                      "Self-modifying state detected"

          # =================================================
          # 5. Risk interpretation (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(scale|scaled|multiplier|fraction|ratio|risk_adjust|exposure_adjust)\b' \
                      "Risk-based scaling detected"

          scan_global '\b(safer|riskier|conservative|aggressive|hedge|protect|defensive)\b' \
                      "Soft risk interpretation detected"

          # =================================================
          # 6. Control-flow smuggling (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(retry|backoff|attempt|reconnect|timeout|sleep\()\b' \
                      "Retry or resilience logic detected"

          scan_global '\b(while\s+True|asyncio\.create_task|schedule|timer)\b' \
                      "Forbidden execution loop detected"

          # =================================================
          # 7. Mandate violations (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(rank\s*\+=|priority\s*\+=|escalate)\b' \
                      "Dynamic authority escalation detected"

          scan_global 'emit\s*\([^)]*\).*\n.*emit\s*\(' \
                      "Multiple action emissions detected"

          # =================================================
          # 8. Cross-symbol leakage (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(portfolio|correlation|other_symbols|cross_symbol|global_exposure)\b' \
                      "Cross-symbol semantic leakage detected"

          # =================================================
          # 9. Documentation semantic leaks (NO EXCEPTIONS)
          # =================================================
          scan_global '#.*(expect|anticipate|suggests|indicates|means that|implies|therefore|because|so that|reason)\b' \
                      "Narrative inference detected in comments"

          # =================================================
          # 10. Exception semantics (NO EXCEPTIONS)
          # =================================================
          scan_global '\b(LiquidityError|RiskError|MarketError|SignalError|ConfidenceError)\b' \
                      "Interpretive exception type detected"

          echo "Semantic constitution checks passed (scoped)."

Why this is constitutionally correct

Observation ingestion is allowed to accumulate raw facts

Temporal layer is allowed to window facts

No other layer may

No layer may interpret

No layer may adapt

No layer may infer

No layer may smooth

This preserves the architecture:

Raw → Structural → Mandates → Arbitration → Execution
with zero semantic leakage between layers