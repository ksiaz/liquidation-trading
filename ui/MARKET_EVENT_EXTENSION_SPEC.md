# Market Event Stream Extension - Specification

**Date:** 2026-01-05  
**Purpose:** Hypothesis testing via raw market observation  
**Authority:** System v1.0 Freeze, Epistemic Discipline

---

## Objective

Extend Live-Run Observability UI to test hypothesis:

> **"At the peak of a move, there should be observable events such as liquidations or large orders."**

**Critical:** UI must be capable of **falsifying** this hypothesis, not just confirming it.

---

## Data Sources to Add

### 1. Market Event Streams (Raw)

**Trades:**
```typescript
{
  timestamp: number;
  price: number;
  quantity: number;
  side: "BUY" | "SELL";
  symbol: string;
}
```

**Order Book Updates:**
```typescript
{
  timestamp: number;
  symbol: string;
  bids_changed: number;  // Count of levels changed
  asks_changed: number;
  best_bid_delta: number;
  best_ask_delta: number;
}
```

**Liquidations (if available):**
```typescript
{
  timestamp: number;
  symbol: string;
  side: "BUY" | "SELL";
  price: number;
  quantity: number;
}
```

---

## New UI Panels

### Panel D: Correlation View (Non-Interpretive)

**Purpose:** Show co-occurrence without causality

**For selected timestamp ± N seconds window:**

Display counts ONLY:
- Number of trades
- Total traded volume
- Number of book updates  
- Number of liquidations
- Number of system proposals
- Number of ghost executions

**No ratios. No labels. No thresholds.**

### Panel F: Market Event Timeline

**Parallel to System Event Timeline**

Each row:
- Timestamp
- Event type (TRADE / BOOK_UPDATE / LIQUIDATION)
- Price (if applicable)
- Size
- Side

**No aggregation. No bucketing. No highlighting.**

---

## Explicitly Forbidden

❌ Peak detection  
❌ "Large order" highlighting  
❌ Anomaly detection  
❌ Z-scores, percentiles  
❌ Any chart-derived signals  

**If an event is "large", human observer decides, not UI.**

---

## Hypothesis Testing Requirements

UI must enable answering both:

1. ✓ When price peaks, do market events increase?
2. ✓ Are there peaks with NO unusual events?

**If hypothesis is false, UI should make that obvious.**

---

## Acceptance Criteria

✓ Can observe peak with zero trades nearby  
✓ Can observe peak with many trades nearby  
✓ Can observe liquidations with no price reversal  
✓ UI does not editorialize outcomes  
✓ "No events" is valid steady state  

---

## Next Steps

1. Add Binance WebSocket feeds (trades, liquidations, book)
2. Create market event storage/replay
3. Build correlation view panel
4. Extend API server with market event endpoints
5. Test with real data: find peaks, check event counts
