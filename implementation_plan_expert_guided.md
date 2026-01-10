# Expert-Guided Implementation Plan
**90-Day Roadmap to Protect and Enhance Trading Alpha**

**Date Created**: 2026-01-01  
**Last Updated**: 2026-01-01 (Expert responses received - All decisions final)  
**Based On**: Expert Consultations #1, #2, #3 (documented in `expert_consultations.md`)  
**Final Decisions**: See `expert_response_final_decisions.md` for complete implementation details  
**Quick Reference**: See `QUICK_REFERENCE_EXPERT_DECISIONS.md` for locked parameters

---

## 🎯 **Core Philosophy**

> **"You already have real alpha, but it is conditional alpha. The market will punish you unless you: (1) Stop believing the orderbook, (2) Confirm pressure with trades, (3) Respect time as a decay variable."** — Expert #2

**Translation**: Don't rebuild the system. Protect what works by fixing execution, filtering, and timing.

---

## 🚨 **Critical Reality Check: The Cost Problem**

### Current Backtest Performance
- **Win Rate**: 52.4% (42 signals / 8 hours)
- **Gross Profit**: +3.29% per session
- **Profit per Trade**: ~0.08%

### Hidden Cost Reality
| Cost Component | Per Trade | Impact |
|----------------|-----------|--------|
| Binance Taker Fee | 0.04% | Fixed |
| Spread (normal) | 0.01-0.02% | Variable |
| Spread (during drain) | 0.05-0.10% | **Killer** |
| **Total Cost** | **0.06-0.14%** | **75-175% of edge** |

**Conclusion**: Current system is likely **breakeven or losing** after real costs.

---

## 📋 **90-Day Implementation Roadmap**

### **Phase 1: Survival (Weeks 1-4) - Microstructure Hygiene**
**Goal**: Stop leaking profit. Fix execution and filtering.  
**Expected Impact**: +6-10 percentage points win rate, +3-5% per session from cost savings

### **Phase 2: Optimization (Weeks 5-8) - Execution Quality**
**Goal**: Improve entry timing and exit discipline.  
**Expected Impact**: +0.5-1.5% per session from better fills and time-based exits

### **Phase 3: Adaptation (Weeks 9-12) - Regime Awareness**
**Goal**: Prevent weeks 2-4 degradation (predicted failure mode).  
**Expected Impact**: Stability, reduced drawdown clustering, protection against volatility spikes

---

## 🔧 **PHASE 1: SURVIVAL (Weeks 1-4)**

### **Week 1: Cost Validation & Measurement**

#### **Objective**: Understand true costs with real data, establish baseline

#### **Tasks**

**1.1 Enhanced Cost Backtesting** 
- [ ] File: `backtest_realistic.py` (enhance existing)
- [ ] Load actual spread data from `orderbook_snapshots` table
- [ ] Model spread widening during drains using stored `best_bid`/`best_ask`
- [ ] Calculate costs using correlation: `depth_ratio < 0.95 → spread × 1.2`, `< 0.90 → spread × 1.5`
- [ ] Add fee modeling: 0.02% maker, 0.04% taker
- [ ] Output: Cost-adjusted PnL (expect it to be negative or near-zero)

**1.2 Signal Half-Life Measurement**
- [ ] File: `signal_performance_tracker.py` (enhance existing)
- [ ] Add time-based metrics:
  - `t_peak_MFE` (time to max favorable excursion)
  - `t_reversion_50%` (50% PnL retracement time)
  - `t_zero_PnL` (time back to breakeven)
- [ ] Calculate median half-life by: `(symbol, session, volatility_regime)`
- [ ] Expected ranges (Expert #2):
  - BTC: 20-90 seconds
  - ETH: 30-120 seconds
  - SOL: 10-40 seconds
- [ ] Output: Half-life tables for each bucket

**1.3 Signal Density Analysis**
- [ ] Script: `analyze_signal_distribution.py` (new)
- [ ] Calculate signals per hour by:
  - Time of day (UTC hourly buckets)
  - Volatility regime (ATR-based: low/med/high)
  - Day of week
- [ ] Identify "toxic" periods (high signal count + low win rate)
- [ ] Output: Heatmap of signal density vs profitability

**Deliverable**: Cost validation report showing real profitability (likely negative)

---

### **Week 2: Toxicity Filtering - "Stop Believing the Orderbook"**

#### **Objective**: Filter fake liquidity (spoofs) from depth calculations

#### **Tasks**

**2.1 Survival-Weighted Depth Calculation**
- [ ] File: `order_toxicity.py` (enhance existing)
- [ ] Implement context-aware decay weighting:
  ```python
  weight_i = exp(-λ_final × age_i)
  λ_final = base_λ × spread_factor × volatility_factor × level_factor
  ```
- [ ] Starting parameters (Expert #2):
  - `base_λ = 0.08`
  - `α (spread) = 0.5`
  - `β (volatility) = 0.6`
  - `γ (level distance) = 1.2`
- [ ] Apply weights in `orderbook_storage.py` when calculating `bid_volume_10`, `ask_volume_10`
- [ ] Track: Original depth vs weighted depth ratio

**2.2 Cancel-to-Trade Ratio (CTR) Calculation**
- [ ] File: `order_toxicity.py`
- [ ] Infer cancellations from L2 snapshots:
  - If `depth[level]` decreases AND no trade at that level → cancelled volume
  - Calculate rolling 10-20s window: `CTR = cancelled_vol / (executed_vol + ε)`
  - Flag levels with `CTR > 4.0` as toxic
- [ ] Apply toxicity discount:
  ```python
  effective_depth = Σ depth_i × exp(-α × CTR_i)
  ```
- [ ] Track: Percentage of depth flagged as toxic

**2.3 Ghost Order Filter**
- [ ] File: `order_toxicity.py`
- [ ] Detect ghost patterns:
  - Large order appears (>5× median level size)
  - Sits for <10 seconds
  - Disappears without trade
- [ ] Action: Discount that price level by 0.15× weight for next 60 seconds
- [ ] Track repeat offenders (same price level ghosts multiple times)

**2.4 Integration into Signal Generator**
- [ ] File: `liquidity_drain_detector.py`
- [ ] Replace raw depth with toxicity-adjusted depth:
  ```python
  # OLD: bid_volume_10 (raw)
  # NEW: weighted_bid_volume_10 (toxicity-adjusted)
  ```
- [ ] Expected impact: Signal count ↓20-35%, Win rate ↑4-8 points

**Deliverable**: Toxicity metrics dashboard showing filtered vs unfiltered signals

---

### **Week 3: Active Pressure Confirmation - "Trades Are Truth"**

#### **Objective**: Distinguish passive drains (spoofs) from active drains (real pressure)

#### **Tasks**

**3.1 Passive vs Active Drain Classification**
- [ ] File: `liquidity_drain_detector.py` (major enhancement)
- [ ] Integrate `trade_stream.py` and `volume_flow_detector.py` data
- [ ] Calculate over 10-second window:
  ```python
  passive_drain = cancelled_bid_volume
  active_drain = taker_sell_volume_at_bid
  absorption_efficiency = executed / (executed + cancelled)
  ```
- [ ] Define 4 regimes:

| Regime | Passive | Active | Trade? |
|--------|---------|--------|--------|
| Spoof cleanup | High (>2.5× median) | Low | ❌ SKIP |
| Real pressure | Low | High (>1.8× buy) | ✅ TRADE |
| Panic | High | High | ⚠️ Conditional (conf>85%) |
| Noise | Low | Low | ❌ SKIP |

**3.2 Signal Gate Implementation**
- [ ] File: `liquidity_drain_detector.py`
- [ ] Add new signal filter:
  ```python
  if regime == 'SPOOF_CLEANUP':
      return None  # Skip signal
  elif regime == 'REAL_PRESSURE':
      if absorption_efficiency > 0.7:
          return signal  # High quality
  elif regime == 'PANIC':
      if signal['confidence'] > 85 and spread_not_widening():
          return signal  # Risky but tradeable
  else:
      return None  # Noise
  ```

**3.3 Backtest Validation**
- [ ] Script: `backtest_with_regimes.py` (new)
- [ ] Re-run backtest with regime filtering
- [ ] Compare:
  - Signal count before/after
  - Win rate before/after
  - Drawdown clustering
- [ ] Expected: Fewer signals (30-40% reduction), higher WR (+5-8 points)

**Deliverable**: Regime-filtered signal performance report

---

### **Week 4: Entry Timing - "Don't Catch the Falling Knife"**

#### **Objective**: Add 1.5s stability confirmation before entry

#### **Tasks**

**4.1 Entry Delay Logic**
- [ ] File: `execution_engine.py` (new)
- [ ] Implement delay confirmation:
  ```python
  # Signal fires at t=0 (drain detected)
  price_signal = get_midprice()
  
  # Wait 1.5 seconds
  time.sleep(1.5)
  
  # Stability check (5 basis points threshold)
  price_now = get_midprice()
  if price_now >= price_signal - (price_signal * 0.0005):
      return True  # Stable, proceed
  else:
      log("Price instability - drain was real selling, skip")
      return False
  ```

**4.2 Limit Order Placement**
- [ ] File: `execution_engine.py`
- [ ] Never use market orders (paying 0.04% taker + spread)
- [ ] Always place at best bid for longs:
  ```python
  best_bid_price = orderbook['bids'][0][0]
  order = place_limit_order(
      side='BUY',
      price=best_bid_price,  # Maker pricing
      quantity=position_size,
      time_in_force='GTC'
  )
  ```

**4.3 Fill Timeout & Fallback**
- [ ] Wait 1 second for fill
- [ ] If unfilled → cancel order and skip signal
- [ ] Accept 50-60% fill rate (Quality > Quantity)
- [ ] Accept partial fills (30%+ of intended size)

**4.4 Backtest with Execution Model**
- [ ] Script: `backtest_limit_order_simulation.py` (new)
- [ ] Simulate fill probability based on orderbook state:
  - If price moves away from limit → no fill
  - If price touches limit → assume fill (conservative)
- [ ] Model costs:
  - Filled: 0.02% maker fee + spread/2 (got good entry)
  - Unfilled: 0% (no trade)
- [ ] Expected: 42 signals → 25 signals, but +3.5% cost savings

**Deliverable**: Execution strategy with simulated fill rates and cost savings

---

## 🎯 **PHASE 2: OPTIMIZATION (Weeks 5-8)**

### **Week 5: Time-Based Exits**

#### **Objective**: Exit based on signal half-life, not just price targets

**Tasks**
- [ ] File: `signal_performance_tracker.py`
- [ ] Implement time-decayed confidence:
  ```python
  effective_conf = raw_conf × exp(-t / half_life[symbol])
  ```
- [ ] Exit rules:
  - After `t > half_life`: Move stop to breakeven
  - After `t > 1.2 × half_life` AND MFE stagnates: Exit at market
- [ ] MFE stagnation: No new peak for `max(10s, 0.5 × half_life)`
- [ ] Backtest impact: Expect +0.3-0.8% from not holding past edge decay

### **Week 6: Dynamic Position Sizing**

**Tasks**
- [ ] File: `risk_manager.py` (new)
- [ ] Start conservative:
  - Week 1-2: 0.1% per trade
  - Week 3-4: 0.25% per trade
  - Week 5+: 0.5% per trade (if metrics stable)
- [ ] Max concurrent exposure: 1.0% (3 positions max)
- [ ] Drawdown adjustment: After 2 consecutive losses → reduce size by 50%

### **Week 7: Order Book Imbalance (OBI) Velocity**

**Tasks**
- [ ] File: `order_toxicity.py`
- [ ] Implement OBI change tracking:
  ```python
  OBI = (bid_vol - ask_vol) / (bid_vol + ask_vol)
  OBI_change = abs(OBI[t] - OBI[t-2s])
  ```
- [ ] Flag high churn: `OBI_change > 2 × rolling_std`
- [ ] Use as additional signal confirmation (not primary)

### **Week 8: VPIN (Volume-Synchronized Probability of Informed Trading)**

**Tasks**
- [ ] File: `vpin_calculator.py` (new)
- [ ] Bucket by equal volume (e.g., every 100 BTC traded)
- [ ] Calculate per bucket: `|buy_volume - sell_volume|`
- [ ] High VPIN (>95th percentile) → Toxic flow, skip long entries
- [ ] Use as circuit breaker, not signal filter

**Phase 2 Deliverable**: Optimized execution with time-based exits and toxic flow filters

---

## 🛡️ **PHASE 3: ADAPTATION (Weeks 9-12)**

### **Week 9: Volatility-Scaled Thresholds**

**Tasks**
- [ ] File: `liquidity_drain_detector.py`
- [ ] Replace static thresholds with dynamic:
  ```python
  # OLD: depth_ratio < 0.96 (always)
  # NEW: depth_ratio < (base_threshold × vol_scale)
  
  vol_ratio = current_vol / rolling_5min_vol
  vol_scale = 1 + β × clamp(log(vol_ratio), 0, 1)
  ```
- [ ] β ∈ [0.4, 0.8] per Expert #2

### **Week 10: Session-Aware Parameters**

**Tasks**
- [ ] Detect session: Asia (low vol), Europe (medium), US (high vol)
- [ ] Per-session thresholds:
  - Asia: Stricter (fewer signals, higher quality)
  - US: Relaxed (more signals, expect chop)
- [ ] Track: Signal distribution vs profitability by session

### **Week 11: Cross-Asset Propagation (BTC → ETH/SOL)**

**Tasks**
- [ ] File: `cross_asset_detector.py` (new)
- [ ] If BTC drain detected → set flag for 5 seconds
- [ ] During flag: Lower ETH/SOL confidence threshold (80% → 60%)
- [ ] Captures BTC-led market moves (95%+ correlation)

### **Week 12: Circuit Breakers**

**Tasks**
- [ ] File: `risk_manager.py`
- [ ] Auto-disable if:
  - Signal count >2× baseline (choppy market)
  - Rolling 20-trade WR <45%
  - Daily drawdown >3%
- [ ] Action sequence:
  1. Tighten CTR filters
  2. Reduce position size 50%
  3. Pause trading (last resort)

**Phase 3 Deliverable**: Adaptive system that survives regime changes

---

## 📊 **Success Metrics & Validation**

### **Week 1 Validation Checkpoints**

| Metric | Target | Action if Failed |
|--------|--------|------------------|
| Cost-adjusted PnL | >0% daily | Fix execution before proceeding |
| Fill rate (limit orders) | >50% | Adjust placement or accept lower count |
| Signal half-life measured | Yes | Need this for time-based exits |

### **Month 1 Validation (After Phase 1)**

| Metric | Target | Red Flag |
|--------|--------|----------|
| Win Rate (toxicity-filtered) | >55% | <50% |
| Signals per day | 15-25 | >40 (overtrading) |
| Cost per trade | <0.04% | >0.08% |
| Max consecutive losses | <6 | >8 |

### **Month 3 Validation (Pre Live Deployment)**

| Metric | Target | Go/No-Go |
|--------|--------|----------|
| Paper trading (real API, $0 size) | 2 weeks profitable | REQUIRED |
| Sharpe ratio | >1.0 | >0.5 minimum |
| Real PnL (cost-adjusted) | >0.5% daily | >0% minimum |
| Drawdown clustering | Minimal | No 5+ loss streaks |

---

## 🔥 **Critical Implementation Rules**

### **Do NOT Do (Yet)**

❌ LSTM on raw orderbooks (too fragile pre-hygiene)  
❌ Online RL (dangerous live feedback loops)  
❌ Full L3 infrastructure (overkill)  
❌ Complex cross-exchange arbitrage  
❌ Optimize for Sharpe ratio (optimize for survival first)

### **Week 1 Priority (Non-Negotiable)**

✅ Update backtest with **real spread data** from DB  
✅ Measure signal half-life (need this for exits)  
✅ Run cost-adjusted backtest  
✅ If PnL <0 → DO NOT PROCEED until execution fixed

---

## ✅ **EXPERT RESPONSES RECEIVED - ALL DECISIONS FINAL**

**Status**: All 7 follow-up questions answered (2026-01-01)  
**Document**: See `expert_response_final_decisions.md` for complete implementation guidance  

### **Key Decisions Summary**

**Q1 (Lambda Calibration)**: ✅ LOCKED  
- Use fixed heuristic: `base_λ=0.08, α=0.5, β=0.6, γ=1.2`  
- DO NOT optimize on PnL in Phase 1-2  
- Validate directional impact only (signal ↓20-35%, WR ↑4-8pts)  
- Revisit only after 30+ live sessions if broken  

**Q2 (Ghost Filter)**: ✅ FORWARD-ONLY  
- No retroactive signal invalidation  
- Track absolute price buckets (not relative levels)  
- Discount factor: 0.15× for 60 seconds  
- Increase λ locally for repeat offender buckets  

**Q3 (CTR Window)**: ✅ FIXED 10s  
- Start with fixed 10-second window  
- Upgrade to volatility-scaled only if CTR explodes/flatlines  
- Epsilon per symbol: BTC=0.001, ETH=0.01, SOL=1.0  
- Threshold: CTR > 4.0 (fixed)  

**Q4 (Active Drain Window)**: ✅ HYBRID  
- PRIMARY: Concurrent 30s window with depth decline  
- SECONDARY: Trailing 1.5s sanity check (non-zero taker_sell)  
- Confirms causality, not continuation  
- Skip if selling happened earlier (edge already gone)  

**Q5 (OBI StdDev Period)**: ✅ ROLLING 5min  
- Rolling 300-sample window (5 minutes @ 1/sec)  
- Minimum sample guard: ≥100 samples required  
- If insufficient: Use precomputed historical baseline  
- Upgrade to regime-based only in Phase 3  

**Q6 (Fill Rate Targeting)**: ✅ ADAPTIVE (Your instinct was correct!)  
- High confidence (>85%): `best_bid + 1_tick` (50-65% fill)  
- Medium confidence (60-85%): `best_bid` (25-40% fill)  
- Low confidence (<60%): Skip trade  
- NEVER cross more than 1 tick  
- Backtest correction: Assume mid-queue, not last  

**Q7 (Circuit Breakers)**: ✅ PER-SESSION NOW  
- Phase 1-2: Per-session baselines (Asia: 30, Europe: 70, US: 120)  
- Phase 3: Add Z-score (z>2.0 AND drawdown accelerating)  
- Multi-metric: Require 2 of 3 breaches to trigger  
- Single-metric triggers are "too twitchy"  

---

## 🎯 **ORIGINAL QUESTIONS (ARCHIVED)**

*The following questions were sent to experts and are now answered above. Archived for reference.*

### **For Expert #2: Toxicity Implementation Details**

**Q1: Lambda (λ) Calibration Strategy** (ANSWERED)

You provided parameter ranges:
- `base_λ ∈ [0.05, 0.12]`, start at 0.08
- `α (spread) ∈ [0.3, 0.7]`, start at 0.5
- `β (volatility) ∈ [0.4, 0.8]`, start at 0.6
- `γ (level distance) ∈ [0.8, 1.5]`, start at 1.2

**Question**: How do we calibrate these without overfitting?

**Proposed approach**:
1. Fix λ heuristically at starting values (0.08, 0.5, 0.6, 1.2)
2. Run backtest, measure:
   - Win rate improvement
   - Signal count reduction
3. Only then regress λ vs context variables
4. Use forward-walk validation (not in-sample)

**Is this the right sequence?** Or should we grid search on out-of-sample data from day 1?

---

**Q2: Ghost Filter Retroactive Discounting**

You said: "If large order appears, no trades at level, then disappears → assign near-zero weight retroactively."

**Question**: How far back should we retroactively adjust?

**Scenario**:
- `t=0s`: 1000 BTC appears at $87,850 bid
- `t=5s`: Still there, no trades
- `t=8s`: Disappears (ghost confirmed)

**Do we**:
- Option A: Zero out that **price level** ($87,850) for next 60s going forward
- Option B: Retroactively recalculate **depth metrics** for past 30s (re-run signal detection?)
- Option C: Just flag it, don't retroactively adjust

**My assumption**: Option A (forward-looking only), since retroactive is computationally expensive. Confirm?

---

**Q3: CTR Time Window Definition**

You said: "Use rolling 10-20s window for CTR."

**Question**: Should this window be:
- **Fixed time**: Always last 10 seconds
- **Adaptive**: Shorter (5s) in high volatility, longer (20s) in low volatility
- **Volume-based**: Last 100 BTC traded (regardless of time)

**Context**: In high volatility, 10 seconds might contain 500 trades. In low volatility, only 20 trades. Which normalizes better?

---

### **For Expert #3: Execution Mechanics**

**Q4: Active Drain Confirmation Window**

You said: "Require `taker_sell > 1.8× taker_buy` to confirm active drain."

**Question**: Over what exact time window?

**Options**:
- Option A: **Concurrent with drain** (same 30s window as depth decline)
- Option B: **During 1.5s delay** (only confirm in stability check period)
- Option C: **Rolling 10s** (independent of drain timing)

**My assumption**: Option A (concurrent), so we're confirming the drain was accompanied by aggressive selling. Correct?

---

**Q5: OBI Velocity StdDev Calculation**

You suggested: `OBI_Change > 2 × StdDev` as "high churn" threshold.

**Question**: Calculate StdDev over what period?

**Options**:
- Option A: **Rolling 5 minutes** (300 snapshots at 1s frequency)
- Option B: **Entire session** (Asia/Europe/US separately)
- Option C: **Per volatility regime** (low/med/high buckets)

**Context**: If we use rolling 5min, StdDev will be noisy. If we use session-wide, it won't adapt to intra-session volatility changes. Which is more robust?

---

**Q6: Limit Order Fill Rate Targeting**

You said: "Accept 50% fill rate for limit orders."

**Question**: If we're only achieving 30% fills in testing, should we:

**Option A**: Place more aggressively (`bid + 1 tick`) to increase fills  
**Option B**: Stay strict (`bid` only) and accept fewer signals  
**Option C**: Adaptive placement based on signal confidence:
```python
if confidence > 85%:
    place_at(bid + 1_tick)  # Aggressive
else:
    place_at(bid)  # Conservative
```

**My concern**: Option A increases costs (partially crosses spread). Option B might miss too many edges. Leaning toward Option C. Your recommendation?

---

**Q7: Circuit Breaker Granularity**

You said: "If `signal_count > 60` (1.5× normal) → reduce position size 50%."

**Question**: Should this threshold be:

**Option A**: **Per-session** (Asia/Europe/US have different baselines)  
**Option B**: **Rolling 8-hour window** (regardless of session)  
**Option C**: **Z-score based** (`signal_count > mean + 2σ`)

**Context**:
- Asia session baseline: ~15 signals / 8h (normal)
- US session baseline: ~60 signals / 8h (normal)

If we use fixed threshold (60), it would never trigger in US session (normal behavior) but always trigger in Asia (false alarm). Should we use **per-session Z-score** instead?

---

## 🎯 **Summary: Critical Path**

### **Can Start Immediately (No Expert Confirmation Needed)**
1. ✅ Week 1 cost validation (use stored spread data)
2. ✅ Week 1 signal half-life measurement
3. ✅ Week 4 limit order logic (place at bid, 1s timeout)

### **Needs Expert Clarification Before Implementation**
1. ⏸️ Week 2 lambda calibration (Q1 - calibration strategy)
2. ⏸️ Week 2 ghost filter (Q2 - retroactive scope)
3. ⏸️ Week 3 active drain window (Q4 - time synchronization)
4. ⏸️ Week 7 OBI velocity (Q5 - StdDev period)

### **Recommended Approach**
- **Start Week 1 tasks immediately** (pure measurement, no trading impact)
- **Send follow-up questions to experts** while Week 1 runs
- **Proceed to Week 2-4** once expert clarifications received
- **Do NOT go live** until Month 3 validation passes

---

## 📝 **Next Steps**

1. **Immediate**: Start Week 1 cost validation
2. **Day 2**: Send follow-up questions to experts (this document, questions section)
3. **Week 1 End**: Review cost validation results
   - If PnL <0: Fix execution before proceeding
   - If PnL >0: Continue to Week 2
4. **Month 1 End**: Paper trading with implemented Phase 1 filters
5. **Month 3 End**: Final validation before live deployment (real API, $0.1% position sizes)

**Target Go-Live**: End of Month 3 (if all validation passes)  
**Minimum Capital**: $10,000 (for 0.25-0.5% position sizes)

---

**Document Status**: Implementation plan ready. Awaiting expert clarifications on questions Q1-Q7 before proceeding past Week 1.
