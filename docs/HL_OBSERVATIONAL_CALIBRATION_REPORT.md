# HL Observational Calibration Report

**Date:** 2026-02-01
**Mode:** Observation Only (No Trading, No Optimization)
**Purpose:** Measure empirical distributions of HL node signals

---

## System Configuration

| Setting | Value | Status |
|---------|-------|--------|
| Hyperliquid Node | localhost:50051 | **ENABLED** |
| Binance Ingestion | N/A | **DISABLED** |
| Live Execution | N/A | **DISABLED** |
| Strategy Evaluation | Observation mode | **ENABLED** |
| Order Submission | N/A | **DISABLED** |

**Data Source:** `~/hl/data/node_fills/hourly/` (ground truth liquidations)

**Time Window:** 2026-01-31 to 2026-02-01 (approximately 24 hours)

---

## Observation Windows Defined

### Time-Based Windows
| Window | Duration | Use Case |
|--------|----------|----------|
| 1s | 1 second | Immediate cascade detection |
| 5s | 5 seconds | Cascade grouping (configured) |
| 30s | 30 seconds | Extended cascade boundary |
| 5m | 5 minutes | Post-cascade observation |

### Event-Based Windows
| Window | Trigger | Description |
|--------|---------|-------------|
| per liquidation | Each HL_LIQUIDATION | Raw event capture |
| per cascade | Cascade start | Group events by 5s gap |
| per cascade completion | 5s gap detected | End of cascade window |

---

## Data Collected

### Raw Event Summary

| Metric | Value |
|--------|-------|
| Total Fills with Liquidation | 10,164 |
| Unique Liquidation Events | ~5,000 (estimated, each has 2+ fills) |
| Liquidated User Fills | 15,302 (corrected count) |
| Total Cascades | 704 |
| Symbols Observed | 118 |
| Time Span | ~4 days (20260128-20260201) |
| Total Value Liquidated | $119,630,117 |

### Symbol Distribution (Top 10)

| Symbol | Liquidations | % of Total |
|--------|-------------|------------|
| BTC | 3,822 | 37.6% |
| HYPE | 1,318 | 13.0% |
| ETH | 1,302 | 12.8% |
| MEGA | 660 | 6.5% |
| SOL | 510 | 5.0% |
| XRP | 198 | 1.9% |
| ASTER | 186 | 1.8% |
| PUMP | 154 | 1.5% |
| FARTCOIN | 120 | 1.2% |
| VVV | 116 | 1.1% |

**Observation:** BTC dominates with 37.6% of all liquidations. Top 5 symbols account for 75% of activity.

### Side Distribution (CORRECTED)

**Initial Issue:** Raw parsing counted BOTH liquidated user AND liquidators.
**Correction:** Only count fills where `wallet == liquidation.liquidatedUser`.

| Side | Count | % | Total Value |
|------|-------|---|-------------|
| LONG | 8,655 | 56.6% | $90,821,776 |
| SHORT | 6,647 | 43.4% | $28,808,341 |

**Long/Short Ratio:** 1.30 by count, 3.15 by value

**Observation:** Slight LONG bias overall. Value ratio (3:1) shows LONG liquidations are larger on average.

#### Hourly Variation (Top 10 by Activity)

| Hour | Total | LONG % | Interpretation |
|------|-------|--------|----------------|
| 20260129/2 | 2,621 | 95.8% | Price crash |
| 20260128/23 | 1,138 | 5.4% | Price rally |
| 20260130/20 | 962 | 94.0% | Price crash |
| 20260131/23 | 903 | 1.2% | Price rally |
| 20260201/7 | 786 | 99.5% | Price crash |
| 20260129/1 | 690 | 99.3% | Price crash |
| 20260201/0 | 644 | 18.0% | Mixed/rally |
| 20260131/21 | 584 | 4.5% | Price rally |

**Observation:** Liquidation side strongly correlated with price direction. Cascade events cluster in directional moves.

### Liquidation Method

| Method | Count | % |
|--------|-------|---|
| market | 10,164 | 100% |
| backstop | 0 | 0% |

**Observation:** All observed liquidations used market method. No backstop liquidations in sample period.

---

## Empirical Distributions

### Quote Quantity (USD Value per Liquidation)

| Statistic | Value |
|-----------|-------|
| Count | 10,164 |
| Minimum | $0.01 |
| Maximum | $150,165.81 |
| Mean | $2,802.03 |
| Median | $419.19 |
| Std Dev | $8,628.96 |
| P5 | $10.17 |
| P25 | $65.38 |
| P50 | $419.19 |
| P75 | $1,569.26 |
| P95 | $13,161.29 |

**Observations:**
1. Heavy right skew (mean >> median)
2. Typical liquidation: ~$400
3. Large liquidations (P95+): >$13,000
4. Extreme outliers: >$150,000

### Time Between Liquidations Within Cascade (ms)

| Statistic | Value |
|-----------|-------|
| Count | 154 (within-cascade only) |
| Minimum | -692,720 ms |
| Maximum | 4,719 ms |
| Mean | -16,857 ms |
| Median | 3,036 ms |
| P25 | 2,784 ms |
| P75 | 3,328 ms |
| P95 | 4,546 ms |

**Observations:**
1. Typical gap: ~3 seconds (3,036 ms median)
2. Negative values indicate timestamp ordering issue
3. Most cascade liquidations occur 2.7-3.3 seconds apart

**Data Quality Issue:** Negative time differences detected. This suggests:
- Timestamps not strictly ordered within cascade
- Or file read order doesn't match event order

---

## Cascade Size Distribution

| Cascade Size | Count | Cumulative % |
|--------------|-------|--------------|
| 2 | 326 | 46.3% |
| 4 | 108 | 61.6% |
| 6 | 62 | 70.5% |
| 8 | 34 | 75.3% |
| 10-20 | 85 | 87.4% |
| 20-50 | 44 | 93.6% |
| 50-100 | 20 | 96.4% |
| 100+ | 8 | 100% |

**Observations:**
1. Most cascades are small (2-4 liquidations)
2. 46% of cascades have only 2 liquidations
3. Large cascades (50+) are rare but significant

### Largest Cascades Observed

| Cascade ID | Liquidations | Total Value | Duration | Symbol |
|------------|--------------|-------------|----------|--------|
| BTC_cascade_425 | 516 | $811,121 | 19.5s | BTC |
| BTC_cascade_437 | 262 | $407,906 | * | BTC |
| MEGA_cascade_112 | 216 | $51,576 | ~0s | MEGA |
| BTC_cascade_258 | 132 | $714,717 | 7.1s | BTC |
| ASTER_cascade_68 | 110 | $90,966 | ~0s | ASTER |

*Duration marked with * or ~0s indicates data ordering issue

**Observations:**
1. BTC has the largest cascades by both count and value
2. Cascade velocity: 516 liquidations in 19.5s = 26.5/second
3. Some "cascades" appear to be single-block events (0s duration)

---

## Coverage Report

### Completeness

| Metric | Status |
|--------|--------|
| HL Node Data | ✅ Available |
| Liquidation Events | ✅ 10,164 collected |
| Cascade Detection | ⚠️ Working but timestamp issues |
| M4 Primitives | ❌ Not computed (historical only) |
| Strategy Proposals | ❌ Not computed (historical only) |

### Missing Data

| Data Type | Status | Reason |
|-----------|--------|--------|
| M4 Primitives | Not collected | Requires live observation loop |
| Strategy Proposals | Not collected | Requires PolicyAdapter integration |
| Arbitration Outcomes | Not collected | Requires full pipeline |
| Price Context | Not collected | PriceReader not integrated |

---

## Data Quality Issues

### 1. Timestamp Ordering
**Issue:** Negative time differences detected within cascades
**Evidence:** P5 of time_between_liqs = -144,462 ms
**Impact:** Cascade detection may group incorrectly
**Mitigation:** Sort events by timestamp before cascade detection

### 2. Side Parsing (RESOLVED)
**Issue:** Initial parsing counted both liquidated AND liquidator fills
**Resolution:** Filter to only count fills where `wallet == liquidation.liquidatedUser`
**Corrected Result:** 56.6% LONG / 43.4% SHORT (realistic market distribution)
**Impact:** None - issue resolved

### 3. Zero-Duration Cascades
**Issue:** Some cascades show 0s duration with many events
**Evidence:** MEGA_cascade_112 has 216 events in "0s"
**Impact:** These are likely single-block batch liquidations
**Mitigation:** Treat as special case in cascade analysis

---

## What This Data Does NOT Tell Us

### Cannot Be Concluded Yet

1. **Profitability** - No trades executed, no PnL observed
2. **Directional Edge** - No price direction correlation analyzed
3. **Optimal Entry Timing** - No entry/exit simulation performed
4. **Risk-Adjusted Returns** - No capital allocation tested
5. **Correct Threshold Values** - No optimization performed
6. **Cascade Predictability** - No forward-looking analysis done
7. **Strategy Performance** - No proposals evaluated against outcomes

### Open Questions (For Future Phases)

1. What is the price movement after cascade events?
2. How quickly do cascades exhaust?
3. Is there a detectable cascade acceleration pattern?
4. Do large cascades cluster in time?
5. What is the cross-symbol cascade correlation?

---

## Output Artifacts

| File | Description | Records |
|------|-------------|---------|
| `liquidations_20260201_103324.jsonl` | Raw liquidation events | 10,164 |
| `primitives_20260201_103324.jsonl` | M4 primitive snapshots | 0 |
| `proposals_20260201_103324.jsonl` | Strategy proposals | 0 |
| `distributions_20260201_103324.json` | Distribution statistics | 2 metrics |
| `coverage_20260201_103324.json` | Coverage summary | Full |

---

## Recommendations for Next Phase

### Before Proceeding to Threshold Tuning

1. **Fix timestamp ordering** in cascade detection
2. **Verify side parsing** to resolve 50/50 anomaly
3. **Integrate PriceReader** to add price context
4. **Run live observation** to capture M4 primitives
5. **Collect at minimum 7 days** of continuous data

### Minimum Data Requirements for Phase 2

| Requirement | Current | Target |
|-------------|---------|--------|
| Liquidation events | 10,164 | 50,000+ |
| Cascade events | 704 | 5,000+ |
| Time span | ~36 hours | 7+ days |
| M4 primitives | 0 | 10,000+ |
| Symbols | 118 | All available |

---

## Conclusion

This calibration phase successfully collected raw liquidation data from the Hyperliquid node, revealing:

1. **Cascade patterns exist** - 704 cascades detected with clear size distribution
2. **BTC dominates** - 37.6% of all liquidations
3. **Typical liquidation size** - Median $419, heavily right-skewed
4. **Cascade velocity** - Up to 26+ liquidations per second in large cascades
5. **Directional clustering** - Hours with 95%+ LONG or 95%+ SHORT liquidations
6. **Value asymmetry** - LONG liquidations 3x larger than SHORT by value
7. **Total value observed** - $119.6M liquidated over 4 days

**Data quality issues** (timestamp ordering) must be resolved before proceeding to threshold discovery. Side parsing issue was resolved during this phase.

**This report contains measurements only. No performance claims are made.**

---

*Generated: 2026-02-01 10:33 UTC*
*Mode: Observational Calibration (No Trading)*
*Data Range: 2026-01-28 to 2026-02-01*
