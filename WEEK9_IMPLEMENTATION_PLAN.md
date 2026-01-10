# Week 9 Implementation Plan
## Adaptive Signal Thresholds

**Phase**: 3 (Weeks 9-12) - Adaptive Strategies  
**Status**: 📋 Planning  
**Dependencies**: Weeks 1-8 complete

---

## 🎯 Objective

Make liquidity drain detection **adaptive** to market conditions instead of using fixed thresholds. Adjust detection sensitivity based on:
1. **Volatility**: Higher volatility → Higher drain threshold
2. **Symbol**: BTC/ETH/SOL have different liquidity profiles
3. **Session**: Asia/Europe/US have different characteristics
4. **Regime**: Trending/Ranging/Volatile markets

**Goal**: Maintain signal quality across varying market conditions while avoiding over-sensitivity in choppy markets or under-sensitivity in calm markets.

---

## 📊 Current State (Fixed Thresholds)

### Existing Liquidity Drain Detector
Currently uses **fixed threshold** for all conditions:
```python
LIQUIDITY_DRAIN_THRESHOLD = 0.25  # 25% depth reduction
```

**Problems**:
- Too sensitive in high volatility (false positives)
- Too insensitive in low volatility (missed signals)
- Doesn't account for symbol-specific liquidity depth
- Treats all sessions equally (ignores liquidity differences)

---

## 🧠 Adaptive Threshold Design

### 1. Volatility Scaling

**Concept**: Scale threshold proportionally to recent volatility

**Formula**:
```python
vol_ratio = current_volatility / baseline_volatility
adaptive_threshold = base_threshold × (1 + β × (vol_ratio - 1))
```

**Where**:
- `base_threshold = 0.25` (current fixed value)
- `β = 0.6` (**LOCKED** - volatility sensitivity parameter)
- `current_volatility` = 5-min rolling std of mid-price returns
- `baseline_volatility` = session-specific median volatility

**Example**:
```
If vol_ratio = 2.0 (market 2× more volatile):
  adaptive_threshold = 0.25 × (1 + 0.6 × (2.0 - 1.0))
                     = 0.25 × 1.6
                     = 0.40  (40% drain required, vs 25% normally)

If vol_ratio = 0.5 (market 50% less volatile):
  adaptive_threshold = 0.25 × (1 + 0.6 × (0.5 - 1.0))
                     = 0.25 × 0.7
                     = 0.175 (17.5% drain required, more sensitive)
```

**Rationale**:
- High volatility → Orderbook naturally more unstable → Require larger drain
- Low volatility → Smaller drains are more significant → Lower threshold

---

### 2. Symbol-Specific Calibration

**Concept**: Each symbol has different baseline liquidity depth

**Approach**:
- Calculate historical median depth at best bid for each symbol
- Use relative depth change instead of absolute
- Apply symbol-specific multipliers

**Parameters** (**LOCKED** from historical data):
```python
SYMBOL_DEPTH_MULTIPLIER = {
    'BTCUSDT': 1.0,   # Baseline (most liquid)
    'ETHUSDT': 1.15,  # Slightly less liquid, easier to drain
    'SOLUSDT': 1.35,  # Much thinner, drains more common
}
```

**Adjusted Formula**:
```python
symbol_adjusted_threshold = adaptive_threshold × SYMBOL_DEPTH_MULTIPLIER[symbol]
```

**Example for SOL**:
```
Base threshold: 0.25
Vol-adjusted: 0.25 × 1.6 = 0.40 (high vol period)
Symbol-adjusted: 0.40 × 1.35 = 0.54 (54% drain required for SOL in high vol)
```

**Rationale**:
- SOL drains more frequently due to thinner books
- Need higher threshold to maintain similar FPR across symbols

---

### 3. Session-Aware Baselines

**Concept**: Liquidity depth and volatility differ by session

**Sessions**:
- **Asia**: 00:00-08:00 UTC (thinner liquidity, lower vol)
- **Europe**: 08:00-16:00 UTC (moderate)
- **US**: 16:00-00:00 UTC (highest liquidity, highest vol)

**Parameters** (**LOCKED** from Week 1 data):
```python
SESSION_BASELINE_VOL = {
    'ASIA': {
        'BTCUSDT': 0.00045,  # 4.5 bps/min
        'ETHUSDT': 0.00052,
        'SOLUSDT': 0.00068,
    },
    'EUROPE': {
        'BTCUSDT': 0.00055,
        'ETHUSDT': 0.00063,
        'SOLUSDT': 0.00081,
    },
    'US': {
        'BTCUSDT': 0.00062,
        'ETHUSDT': 0.00071,
        'SOLUSDT': 0.00093,
    },
}
```

**Usage**:
```python
session = get_current_session(timestamp)
baseline_vol = SESSION_BASELINE_VOL[session][symbol]
vol_ratio = current_vol / baseline_vol
```

---

### 4. Regime-Aware Adjustment (Phase 3 Enhancement)

**Concept**: Different market regimes require different sensitivity

**Regime Classification** (to be implemented Week 11):
- **Trending**: Strong directional move, sustained volume
- **Ranging**: Oscillating within bounds, mean-reverting
- **Volatile**: High churn, no clear direction

**Preliminary Multipliers** (**TO BE CALIBRATED**):
```python
REGIME_MULTIPLIER = {
    'TRENDING': 0.85,   # More sensitive (drains likely real)
    'RANGING': 1.0,     # Baseline
    'VOLATILE': 1.25,   # Less sensitive (lots of noise)
}
```

**Note**: Full regime detection comes in Week 11. For Week 9, use simple volatility-based proxy.

---

## 🔧 Implementation Plan

### Task 9.1: Volatility Calculator

**File**: `volatility_calculator.py`

**Class**: `VolatilityCalculator`

**Methods**:
```python
def __init__(self, symbol: str, window_seconds: int = 300):
    """
    Args:
        symbol: Trading pair
        window_seconds: Rolling window (5min = 300s LOCKED)
    """

def update_price(self, timestamp: float, price: float):
    """Update with new mid-price observation"""

def get_current_volatility(self) -> float:
    """Return rolling std of returns"""

def get_session_baseline(self, session: str) -> float:
    """Return session-specific baseline volatility"""

def get_volatility_ratio(self, session: str) -> float:
    """Return current_vol / baseline_vol"""
```

**🔒 LOCKED Parameters**:
- **Window**: 300 seconds (5 minutes)
- **Baseline volatilities**: Per session, per symbol (from Week 1 data)
- **Min samples**: 60 (1 minute of data before calculating)

---

### Task 9.2: Adaptive Threshold Manager

**File**: `adaptive_threshold_manager.py`

**Class**: `AdaptiveThresholdManager`

**Methods**:
```python
def __init__(self):
    """Initialize with locked parameters"""

def calculate_threshold(
    self,
    symbol: str,
    volatility_ratio: float,
    session: str,
) -> float:
    """
    Calculate adaptive threshold for liquidity drain detection
    
    Returns:
        Adaptive threshold (e.g., 0.175 to 0.60)
    """

def get_symbol_multiplier(self, symbol: str) -> float:
    """Return symbol-specific depth multiplier"""

def get_base_threshold(self) -> float:
    """Return base threshold (0.25 LOCKED)"""
```

**🔒 LOCKED Parameters**:
```python
BASE_THRESHOLD = 0.25
BETA_VOLATILITY = 0.6  # Volatility sensitivity
SYMBOL_MULTIPLIERS = {
    'BTCUSDT': 1.0,
    'ETHUSDT': 1.15,
    'SOLUSDT': 1.35,
}
MAX_THRESHOLD = 0.60  # Cap at 60% to avoid missing major drains
MIN_THRESHOLD = 0.10  # Floor at 10% to avoid excessive noise
```

---

### Task 9.3: Integration with Liquidity Drain Detector

**Modify**: `toxicity_aware_detector.py`

**Changes**:
1. Add `AdaptiveThresholdManager` instance
2. Add `VolatilityCalculator` instance
3. Replace fixed threshold logic with adaptive calculation
4. Track threshold values for each signal (for analysis)

**Before** (fixed):
```python
if depth_change >= 0.25:  # Fixed threshold
    signal = True
```

**After** (adaptive):
```python
vol_ratio = self.vol_calc.get_volatility_ratio(session)
threshold = self.threshold_mgr.calculate_threshold(
    symbol=self.symbol,
    volatility_ratio=vol_ratio,
    session=session,
)
if depth_change >= threshold:
    signal = True
    signal_metadata['adaptive_threshold'] = threshold
```

---

### Task 9.4: Validation & Analysis

**File**: `week9_adaptive_threshold_analysis.py`

**Purpose**: Validate adaptive thresholds improve performance

**Analysis**:
1. **Before/After Comparison**:
   - Signal count by regime (high vol vs low vol)
   - Win rate by regime
   - False positive rate by regime

2. **Threshold Distribution**:
   - Histogram of applied thresholds
   - By session, by symbol
   - Correlation with volatility

3. **Expected Improvements**:
   - Signal count: ±0% (rebalanced, not reduced)
   - Win rate: +1-2 points (better quality across regimes)
   - WR in high vol: +3-4 points (fewer false positives)
   - WR in low vol: No degradation (maintain sensitivity)

4. **Metrics to Track**:
   - `signals_per_hour` by vol regime
   - `win_rate` by vol regime
   - `avg_threshold_applied` by session
   - `threshold_utilization` (% time at min/max caps)

---

## 📈 Expected Impact

### Signal Quality
- **High Volatility Periods**: 
  - Signals: ↓30-40% (filter noise)
  - WR: ↑3-4 points (fewer false positives)
- **Low Volatility Periods**:
  - Signals: ↑15-20% (more sensitive)
  - WR: Maintained or +1 point (catch subtle drains)
- **Overall**:
  - Signals: ±0-5% (rebalanced)
  - WR: +1-2 points (better regime fit)

### Session Consistency
- More consistent signal quality across Asia/Europe/US
- Reduced session-specific bias
- Smoother performance attribution

### Symbol Performance
- SOL: Fewer noise signals (currently over-firing)
- BTC: Maintained baseline (most liquid, stable)
- ETH: Slight improvement (middle ground)

---

## 🧪 Testing Plan

### Unit Tests
```python
# Test volatility calculation
def test_volatility_calculator():
    # Edge cases: insufficient data, zero vol, extreme vol
    
# Test threshold calculation
def test_adaptive_threshold_manager():
    # Verify: vol scaling, symbol multipliers, min/max caps
    
# Test integration
def test_toxicity_detector_adaptive():
    # Compare fixed vs adaptive on same data
```

### Integration Tests
```python
# Test with historical data
def test_week9_backtest():
    # Run Phase 1-2 backtest with adaptive thresholds
    # Compare metrics before/after
```

### Validation Criteria
- ✅ Win rate improvement: +1-2 points overall
- ✅ High-vol WR: +3-4 points
- ✅ Signal count: No excessive increase/decrease
- ✅ Threshold distribution: Well-distributed (not stuck at caps)

---

## 🔄 Integration Architecture

```
[Orderbook Snapshots] → [VolatilityCalculator]
                              ↓
                      [Current Vol Ratio]
                              ↓
[Session Detector] → [AdaptiveThresholdManager]
                              ↓
                      [Adaptive Threshold]
                              ↓
[ToxicityAwareDetector] (use adaptive threshold)
                              ↓
                      [Signal with metadata]
```

---

## 📝 Deliverables

### Code Artifacts
1. ✅ `volatility_calculator.py` (~300 lines)
2. ✅ `adaptive_threshold_manager.py` (~250 lines)
3. ✅ Modified `toxicity_aware_detector.py` (add adaptive logic)
4. ✅ `week9_adaptive_threshold_analysis.py` (~350 lines)

### Documentation
1. ✅ This implementation plan
2. ✅ Week 9 completion summary
3. ✅ Test results and validation report
4. ✅ Updated system architecture diagram

### Data Artifacts
1. ✅ Session baseline volatilities (from Week 1 data)
2. ✅ Threshold distribution analysis
3. ✅ Before/after performance comparison

---

## 🔒 Locked Parameters Summary

| Parameter | Value | Source |
|-----------|-------|--------|
| `base_threshold` | 0.25 | Current baseline |
| `β (volatility)` | 0.6 | Expert guidance |
| `window_seconds` | 300 | 5-min standard |
| `min_samples` | 60 | 1-min safety |
| `max_threshold` | 0.60 | Expert cap |
| `min_threshold` | 0.10 | Expert floor |
| `BTCUSDT multiplier` | 1.0 | Baseline |
| `ETHUSDT multiplier` | 1.15 | Historical data |
| `SOLUSDT multiplier` | 1.35 | Historical data |

**Expert Compliance**: All parameters derived from Week 1 empirical data or expert guidance. NO optimization.

---

## ⏭️ Next Steps (Execution)

1. ✅ **Create `volatility_calculator.py`**
   - Rolling window calculation
   - Session baseline lookup
   - Ratio computation

2. ✅ **Create `adaptive_threshold_manager.py`**
   - Threshold calculation logic
   - Symbol/session multipliers
   - Min/max capping

3. ✅ **Integrate with detector**
   - Modify `toxicity_aware_detector.py`
   - Add metadata tracking
   - Test with simulated data

4. ✅ **Validation analysis**
   - Run backtest comparison
   - Generate performance report
   - Validate improvement expectations

5. ✅ **Documentation**
   - Week 9 completion summary
   - Update task checklist
   - Prepare for Week 10

---

**Status**: 📋 Plan complete, ready for execution

**Confidence**: **High** - Clear design, locked parameters, builds on established foundation

**Risk**: **Low** - Additive change, doesn't break existing logic, can revert to fixed threshold if needed
