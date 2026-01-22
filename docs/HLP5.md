LIQUIDATION ENGINE BEHAVIOR

This document separates FACTS about Hyperliquid's liquidation engine from HYPOTHESES about trading implications.

---

PART 1: FACTS (VERIFIABLE)

**FACT 1: Liquidations Always Execute**
Hyperliquid's internal liquidation engine completes all liquidations.
Unlike some exchanges, liquidations do not fail, stall, or partially fill.
The engine crosses the spread and consumes whatever depth is needed.

**FACT 2: Liquidations Are Forced Market Orders**
When a position is liquidated, a market order is executed.
This order is price-insensitive - it executes regardless of slippage.

**FACT 3: Liquidations Reduce OI**
After liquidation, open interest decreases by the liquidated position size.
The liquidated wallet exits users_with_positions.

**FACT 4: Liquidation Completion Is Observable**
Observable indicators of liquidation completion:
- Sudden OI drop
- Volume spike without price extension
- Position disappearance from users_with_positions

---

PART 2: HYPOTHESES (REQUIRE VALIDATION)

**HYPOTHESIS 1: Liquidation Timing Is Predictable**

Claim: You can detect when a liquidation is "inevitable" before it occurs.

Required conditions (proposed):
- Remaining depth < estimated liquidation size
- Price approaching liquidation band
- Depth thinning on one side

**Problems with this hypothesis:**
- "Estimated liquidation size" requires knowing which positions will liquidate
- Position liquidation prices are not directly observable
- New depth can appear, invalidating "inevitability"

**Validation required:**
- Define precise "inevitability" criteria
- Measure how often "inevitable" liquidations actually occur
- Measure false positive rate

---

**HYPOTHESIS 2: Post-Liquidation Reversal Is Tradeable**

Claim: Price reverses after liquidation completion, creating a trading opportunity.

**Problems with this hypothesis:**
- "Reversal" is undefined (how much? how fast?)
- Not all liquidations lead to reversals
- Entry timing is unspecified
- Risk/reward is unquantified

**Validation required:**
- Define "reversal" precisely (X% move within Y time)
- Measure reversal frequency after liquidation events
- Compare to baseline (random entries after volume spikes)
- Calculate win rate and expected value

---

**HYPOTHESIS 3: Node Data Provides Timing Advantage**

Claim: Node data allows earlier detection of liquidation conditions than public APIs.

**Problems with this hypothesis:**
- Latency advantage is unquantified
- May be milliseconds (not actionable) or seconds (potentially actionable)
- Depends on public API latency, which varies

**Validation required:**
- Measure actual latency difference between node and public API
- Determine if latency is sufficient for trade execution
- Document under what conditions advantage exists

---

PART 3: WHAT IS ACTUALLY KNOWN

**Known:**
- Liquidations are forced flow events
- Forced flow ends when liquidation completes
- OI decreases after liquidation

**Unknown:**
- Whether this creates profitable trading opportunity
- Optimal entry/exit timing
- Expected win rate
- Risk-adjusted returns

---

PART 4: HONEST ASSESSMENT

The liquidation engine's behavior is mechanical and observable.
The claim that this creates "mechanical certainty edge" conflates:
- Engine mechanics (certain)
- Trading profitability (uncertain)

The engine will execute liquidations. Whether you can profit from this is a separate question that requires empirical validation.

Do not confuse understanding how something works with knowing how to profit from it.

---

PART 5: IMPLEMENTATION IMPLICATIONS

If implementing liquidation-based strategies:

1. **Define precise entry conditions** - not "liquidation looks inevitable" but specific thresholds
2. **Define precise exit conditions** - not "after reversal" but specific targets/stops
3. **Backtest with realistic assumptions** - include slippage, latency, partial fills
4. **Paper trade before live** - validate in real market conditions
5. **Track all trades** - build evidence base for whether hypothesis holds

Without validation data, any liquidation-based strategy is speculative.
