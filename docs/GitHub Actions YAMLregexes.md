# .github/workflows/semantic-constitution-ci.yml

name: Semantic Constitution Enforcement

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

      - name: Semantic Leak Scan
        shell: bash
        run: |
          set -e

          echo "Running semantic constitution checks..."

          TARGET_DIRS="observation runtime execution arbitration mandate"

          # If directories don't exist, skip them silently
          FILES=$(find $TARGET_DIRS -type f \( -name "*.py" -o -name "*.ts" -o -name "*.rs" \) 2>/dev/null || true)

          if [ -z "$FILES" ]; then
            echo "No target source files found. Skipping scan."
            exit 0
          fi

          fail() {
            echo "::error::$1"
            exit 1
          }

          scan() {
            local pattern="$1"
            local message="$2"

            if grep -RInE "$pattern" $FILES; then
              fail "$message"
            fi
          }

          # -------------------------------------------------
          # 1. Interpretive / semantic vocabulary
          # -------------------------------------------------
          scan '\b(pressure|strength|weak|strong|confidence|probability|likely|unlikely|momentum|trend|bias|signal|quality|good|bad|safe|unsafe|support|resistance|zone|range|regime|condition|absorption|imbalance|liquidity|sweep|hunt)\b' \
               "Interpretive semantic vocabulary detected"

          scan '\b(bull|bear|bullish|bearish|long|short|reversal|continuation|breakout|fakeout)\b' \
               "Directional interpretation detected"

          # -------------------------------------------------
          # 2. Derived metrics / aggregation
          # -------------------------------------------------
          scan '\b(deque|maxlen|rolling|window|sliding|recent|history|buffer|last_[0-9]+)\b' \
               "Rolling / historical aggregation detected"

          scan '\b(mean|avg|average|std|stddev|variance|median|percentile|quantile|zscore|sigma)\b' \
               "Statistical aggregation detected"

          scan '\b(threshold|limit|cap|floor|ceiling|tolerance|epsilon|margin|buffer)\b' \
               "Threshold semantics detected"

          # -------------------------------------------------
          # 3. Memory & state leakage
          # -------------------------------------------------
          scan '\b(cache|memo|store|saved|previous|last_state|_seen|visited|registry|lookup)\b' \
               "Persistent memory semantics detected"

          scan 'def\s+\w+\([^)]*=\s*(\[\]|\{\}|set\(\))' \
               "Default mutable argument detected"

          scan '^\s*(global|static)\b' \
               "Global or static state detected"

          # -------------------------------------------------
          # 4. Adaptation / learning
          # -------------------------------------------------
          scan '\b(adjust|adapt|update|learn|refine|optimize|tune|calibrate|drift)\b' \
               "Adaptive or learning behavior detected"

          scan '\+=|\-=|\*=|/=' \
               "Self-modifying state detected"

          # -------------------------------------------------
          # 5. Risk interpretation
          # -------------------------------------------------
          scan '\b(scale|scaled|multiplier|fraction|ratio|risk_adjust|exposure_adjust)\b' \
               "Risk-based scaling detected"

          scan '\b(safer|riskier|conservative|aggressive|hedge|protect|defensive)\b' \
               "Soft risk interpretation detected"

          # -------------------------------------------------
          # 6. Control-flow smuggling
          # -------------------------------------------------
          scan '\b(retry|backoff|attempt|reconnect|timeout|sleep\()\b' \
               "Retry or resilience logic detected"

          scan '\b(while\s+True|for\s+\w+\s+in\s+range|asyncio\.create_task|schedule|timer)\b' \
               "Forbidden execution loop detected"

          # -------------------------------------------------
          # 7. Mandate violations
          # -------------------------------------------------
          scan '\b(rank\s*\+=|priority\s*\+=|escalate)\b' \
               "Dynamic authority escalation detected"

          scan 'emit\s*\([^)]*\).*\n.*emit\s*\(' \
               "Multiple action emissions detected"

          # -------------------------------------------------
          # 8. Cross-symbol leakage
          # -------------------------------------------------
          scan '\b(portfolio|correlation|other_symbols|cross_symbol|global_exposure)\b' \
               "Cross-symbol semantic leakage detected"

          # -------------------------------------------------
          # 9. Documentation semantic leaks
          # -------------------------------------------------
          scan '#.*(expect|anticipate|suggests|indicates|means that|implies|therefore)' \
               "Narrative inference detected in comments"

          scan '#.*(because|so that|in order to|reason)' \
               "Justification language detected in comments"

          # -------------------------------------------------
          # 10. Exception semantics
          # -------------------------------------------------
          scan '\b(LiquidityError|RiskError|MarketError|SignalError|ConfidenceError)\b' \
               "Interpretive exception type detected"

          echo "Semantic constitution checks passed."

How this behaves in practice

    ❌ Any single violation fails the PR

    ❌ No partial acceptance

    ❌ No warnings

    ✅ Fast (<1s on most repos)

    ✅ Language-agnostic (Python / TS / Rust)

    ✅ Zero runtime dependencies

What this does not do (by design)

    ❌ It does not understand intent

    ❌ It does not parse ASTs

    ❌ It does not allow “almost compliant” code

    ❌ It does not try to be clever

This is constitutional enforcement, not linting.