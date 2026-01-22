ADDITIONAL OBSERVABLE PATTERNS

This document describes observable market conditions beyond basic liquidation mechanics.
All patterns are HYPOTHESES requiring validation before implementation.

---

PATTERN 1: Post-Liquidation Inventory Phase

**Observable conditions:**
- Price stabilizes after liquidation event
- OI has dropped significantly
- Volume remains elevated
- Range compresses

**Mechanical reasoning:**
Participants who absorbed liquidation flow now hold inventory.
Inventory distribution creates selling/buying pressure until cleared.

**HYPOTHESIS (unvalidated):**
Range expansion following post-liquidation compression is tradeable.

**Required validation:**
- Measure frequency of range expansion after OI drops > 10%
- Measure average time between liquidation completion and range expansion
- Document false positive rate

---

PATTERN 2: Failed Liquidation Push

**Observable conditions:**
- Price pushes toward liquidation band
- Depth thins on target side
- But: OI does not collapse
- Price reverses without significant liquidation

**Mechanical reasoning:**
Push was absorbed or defended. Trapped leverage remains.
Initiator may exit, creating opposite flow.

**HYPOTHESIS (unvalidated):**
Failed liquidation pushes lead to faster moves in opposite direction.

**Required validation:**
- Define "failed push" criteria precisely (OI drop < X%, price reversal > Y%)
- Measure continuation vs reversal after failed pushes
- Compare to baseline random price movements

---

PATTERN 3: Funding Rate Mean Reversion

**Observable conditions:**
- Funding rate accelerates aggressively
- Liquidations occur
- OI collapses
- Funding rate decreases faster than price normalizes

**Mechanical reasoning:**
Funding reflects positioning. After liquidations, positioning is reduced.
Funding may normalize before price does.

**HYPOTHESIS (unvalidated):**
Funding rate mean reversion is a leading indicator of price mean reversion.

**Required validation:**
- Measure correlation between funding velocity change and subsequent price change
- Control for baseline funding/price correlation
- Document lag time

---

PATTERN 4: OI Rebuild Failure

**Observable conditions:**
- Price moves in one direction
- OI does not increase proportionally
- Volume decays after initial move

**Mechanical reasoning:**
Price movement without OI increase indicates weak conviction.
No new positions being built to support the move.

**HYPOTHESIS (unvalidated):**
Price moves without OI rebuild are more likely to reverse.

**Required validation:**
- Define "OI rebuild failure" threshold (OI increase < X% while price moves Y%)
- Measure reversal frequency
- Compare to moves with strong OI rebuild

---

PATTERN 5: Orderbook Refill Asymmetry

**Observable conditions:**
- After large price move, orderbook refills
- One side refills faster than the other
- Refill persistence differs (sticky vs ephemeral)

**Mechanical reasoning:**
Fast, persistent refill indicates willingness to provide liquidity.
Slow, ephemeral refill indicates defensive behavior.

**HYPOTHESIS (unvalidated):**
Side with faster, more persistent refill indicates near-term price direction.

**Required validation:**
- Define refill speed and persistence metrics
- Measure predictive value for price direction
- Control for baseline refill patterns

---

PATTERN 6: Cross-Asset Correlation Stress

**Observable conditions:**
- Liquidation occurs on one asset
- Correlated assets show: OI pause, funding hesitation, depth thinning

**Mechanical reasoning:**
Leveraged participants may have positions across assets.
Liquidation on one asset may precede liquidation on correlated assets.

**HYPOTHESIS (unvalidated):**
Liquidation on high-beta asset predicts liquidation risk on correlated assets.

**Required validation:**
- Identify asset correlations
- Measure liquidation cascade frequency
- Document lead time between assets

---

IMPLEMENTATION STATUS

None of these patterns are currently implemented in the system.
They are documented for potential future research and validation.

To implement any pattern:
1. Define precise entry/exit conditions
2. Backtest on historical data
3. Paper trade for validation period
4. Document results with statistical significance
5. Only then consider live implementation

See HLP10 for strategy state machine requirements if implementing.
