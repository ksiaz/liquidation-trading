LIQUIDATION MECHANICS

1. What Liquidations Are (Mechanically)

Liquidations are:
- Forced market orders
- Price-insensitive (must execute regardless of slippage)
- Liquidity-consuming (take from orderbook, do not provide)
- Position-removing (reduce OI on one side)

When liquidations execute:
1. Forced sell/buy order enters market
2. Order consumes resting liquidity at available prices
3. Position is closed
4. OI decreases
5. Forced flow ends

---

2. Observable Conditions Before Liquidations

**Condition Set A (Structural):**
- OI elevated relative to 15-minute baseline
- Funding persistently skewed (positive or negative)
- Price range compressed despite OI increase

**Condition Set B (Localization):**
- Price approaches round number levels
- Repeated tests of same price level
- Depth asymmetry near specific prices

**Condition Set C (Microstructure):**
- Passive liquidity cancellations ahead of price
- Depth thinning on one side
- Market orders that do not extend price (absorption testing)

---

3. Observable Conditions During Liquidations

When liquidation flow is active:
- Volume spikes
- Price moves in bursts, not smooth progression
- OI decreases
- Aggressive orders on one side dominate

---

4. Observable Conditions After Liquidations

When liquidation flow completes:
- Large volume with no further price extension
- OI has dropped significantly
- Funding velocity decreases
- Aggressive order flow changes direction or stops

---

5. Why Price Often Reverses After Liquidations

Mechanical reasons:
1. Forced flow has ended (no more price-insensitive orders)
2. OI on liquidated side is reduced (less selling/buying pressure)
3. Participants who absorbed liquidation flow hold inventory they may unwind

**HYPOTHESIS (requires validation):**
Post-liquidation price reversal is more common than continuation.

To validate:
- Collect historical data on price action after OI drops > X%
- Measure reversal vs continuation frequency
- Document edge cases where continuation occurs

---

6. Conditions That Invalidate Liquidation Logic

Do not apply liquidation-based reasoning when:
- OI is low (no leverage to liquidate)
- Funding is neutral (no positioning skew)
- Depth is thick on both sides (no liquidity vacuum)
- Price movement is smooth and continuous (organic flow, not forced)

These conditions indicate directional flow, not liquidation-driven movement.

---

7. Timing Considerations

**HYPOTHESIS (requires validation):**
Entry after liquidation exhaustion (OI drop + volume spike + no price extension) has better risk/reward than entry during liquidation flow.

Risks of early entry (before exhaustion):
- Liquidation flow continues
- Price extends further against position
- Stop triggered before reversal

Risks of late entry (after reversal begins):
- Miss initial move
- Chase extended price
- Worse entry price

---

8. What This Document Does Not Specify

This document describes mechanics, not strategy.

Not specified:
- Entry price calculation
- Position sizing
- Stop placement
- Exit criteria
- Risk limits

See HLP10 (Strategy State Machines) and HLP17 (Capital Management) for those specifications.
