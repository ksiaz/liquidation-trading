# Week 10 Implementation Plan
## Session-Aware Parameters

**Phase**: 3 (Weeks 9-12) - Adaptive Strategies  
**Status**: 📋 Planning  
**Dependencies**: Weeks 1-9 complete

---

## 🎯 Objective

Optimize system performance across different trading sessions (Asia/Europe/US) by applying session-specific parameters. Different sessions have distinct characteristics:
- **Liquidity depth**: Varies significantly
- **Volatility patterns**: Different baselines
- **Participant mix**: Regional traders, HFTs, institutions
- **Signal quality**: Session-dependent win rates

**Goal**: Consistent performance across all time zones instead of optimizing for one session at the expense of others.

---

## 📊 Current State (Session-Agnostic)

### Existing Approach
- Uses same parameters 24/7
- Volatility baselines vary by session (implemented Week 9)
- But thresholds, risk limits, and circuit breakers are session-agnostic

**Problems**:
- Asia: Over-trading (low liquidity → more false drains)
- US: Under-trading (high liquidity → miss subtle drains)
- Europe: Reasonable (middle ground)
- Inconsistent WR and drawdown patterns by session

---

## 🧠 Session-Aware Design

### 1. Session Detection & Classification

**Sessions** (from Week 1 data):
```python
ASIA:   00:00-08:00 UTC    # Tokyo, Singapore, Hong Kong
EUROPE: 08:00-16:00 UTC    # London, Frankfurt, Zurich  
US:     16:00-00:00 UTC    # New York, Chicago
```

**Characteristics** (from Week 1 analysis):

| Session | Avg Signals/8h | Baseline Vol (BTC) | Liquidity Depth | Typical WR |
|---------|----------------|-------------------|-----------------|------------|
| Asia | 15 | 0.00045 (lowest) | Thinnest | 52-54% |
| Europe | 35 | 0.00055 (medium) | Medium | 56-58% |
| US | 60 | 0.00062 (highest) | Deepest | 54-56% |

**Insights**:
- Asia: Fewer signals, lower vol, thinner books → Need higher quality bar
- US: Many signals, higher vol, deeper books → More aggressive thresholds
- Europe: Balanced, best baseline for parameter tuning

---

### 2. Session-Specific Circuit Breakers

**Current** (from Week 8):
- Fixed session limit: 25 signals
- Problem: Too high for Asia (normal = 15), too low for US (normal = 60)

**New Approach** (per Expert Q7):
```python
SESSION_SIGNAL_LIMITS = {
    'ASIA': {
        'normal': 15,
        'threshold': 30,  # 2× normal
    },
    'EUROPE': {
        'normal': 35,
        'threshold': 70,  # 2× normal
    },
    'US': {
        'normal': 60,
        'threshold': 120,  # 2× normal
    },
}
```

**🔒 LOCKED**: Thresholds are 2× empirical normal from Week 1 data

**Logic**:
- If signals > threshold for session → Trigger circuit breaker
- Prevents overtrading relative to **session baseline**, not global average

---

### 3. Session-Specific Threshold Adjustments

**Beyond Volatility Scaling** (Week 9):
- Week 9: Adjusts for volatility changes **within** a session
- Week 10: Adjusts base threshold **between** sessions

**Approach**:
```python
# Week 9: Volatility-based
adaptive_threshold = base × vol_scaling × symbol_mult

# Week 10: Add session multiplier
session_threshold = base × vol_scaling × symbol_mult × SESSION_MULT[session]
```

**Session Multipliers** (**TO BE CALIBRATED** from backtests):
```python
SESSION_MULTIPLIERS = {
    'ASIA': 1.10,    # 10% higher (thinner books, more false drains)
    'EUROPE': 1.00,  # Baseline
    'US': 0.95,      # 5% lower (deeper books, can be more aggressive)
}
```

**Rationale**:
- Asia: Harder to distinguish real vs fake drains → Higher bar
- US: More liquidity → Can catch smaller drains
- Europe: Standard baseline

---

### 4. Session-Aware Risk Limits

**Position Sizing by Session**:
```python
SESSION_RISK_MULTIPLIERS = {
    'ASIA': 0.8,     # Reduce size 20% (lower confidence)
    'EUROPE': 1.0,   # Standard
    'US': 1.0,       # Standard (volume compensates)
}
```

**Max Concurrent Positions** (from Week 6):
- Current: 1.0% max exposure (3 positions @ 0.33% each)
- New: Adjust by session expected signal count

```python
SESSION_MAX_POSITIONS = {
    'ASIA': 2,       # Fewer signals → Fewer concurrent
    'EUROPE': 3,     # Standard
    'US': 3,         # More signals but same limit
}
```

**🔒 LOCKED**: Based on empirical signal distributions

---

### 5. Session Performance Tracking

**Metrics by Session**:
- Win rate deviation from baseline
- Avg PnL per trade
- Max drawdown
- Signal quality score
- Fill rate

**Purpose**:
- Identify which sessions underperform
- Detect regime shifts within sessions
- Validate session-specific parameters working

---

## 🔧 Implementation Plan

### Task 10.1: Session Manager

**File**: `session_manager.py`

**Class**: `SessionManager`

**Methods**:
```python
def __init__(self):
    """Initialize session parameters"""

def get_current_session(self, timestamp: float) -> str:
    """Return ASIA, EUROPE, or US"""

def get_session_parameters(self, session: str) -> dict:
    """
    Return session-specific config:
    - signal_limit_normal
    - signal_limit_threshold
    - threshold_multiplier
    - risk_multiplier
    - max_concurrent_positions
    """

def get_circuit_breaker_limit(self, session: str) -> int:
    """Return signal limit for session"""

def get_threshold_multiplier(self, session: str) -> float:
    """Return threshold adjustment factor"""
```

**🔒 LOCKED Parameters**:
```python
SESSION_DEFINITIONS = {
    'ASIA': (0, 8),       # 00:00-08:00 UTC
    'EUROPE': (8, 16),    # 08:00-16:00 UTC
    'US': (16, 24),       # 16:00-00:00 UTC
}

SESSION_SIGNAL_LIMITS = {
    'ASIA': {'normal': 15, 'threshold': 30},
    'EUROPE': {'normal': 35, 'threshold': 70},
    'US': {'normal': 60, 'threshold': 120},
}

SESSION_THRESHOLD_MULTIPLIERS = {
    'ASIA': 1.10,
    'EUROPE': 1.00,
    'US': 0.95,
}

SESSION_RISK_MULTIPLIERS = {
    'ASIA': 0.8,
    'EUROPE': 1.0,
    'US': 1.0,
}
```

---

### Task 10.2: Integrate Session Manager

**Modify**: Multiple modules to use session awareness

**Changes**:

1. **`adaptive_threshold_manager.py`**:
```python
# Add session multiplier to threshold calculation
def calculate_threshold(
    self,
    symbol: str,
    volatility_ratio: float,
    session: str,  # NEW
) -> float:
    vol_scaling = 1.0 + BETA × (volatility_ratio - 1.0)
    session_mult = SESSION_MANAGER.get_threshold_multiplier(session)
    threshold = BASE × vol_scaling × SYMBOL_MULT × session_mult
    return clamp(threshold, MIN, MAX)
```

2. **`vpin_circuit_breaker.py`**:
```python
# Use session-specific signal limits
def __init__(self, session_manager: SessionManager):
    self.session_mgr = session_manager
    
def check_signal(self, timestamp: float) -> dict:
    session = self.session_mgr.get_current_session(timestamp)
    limit = self.session_mgr.get_circuit_breaker_limit(session)
    
    if self.signal_count >= limit:
        return {'allowed': False, 'reason': f'Session limit ({session})'}
```

3. **`dynamic_position_sizer.py`**:
```python
# Apply session risk multiplier
def calculate_size(
    self,
    confidence: float,
    session: str,  # NEW
) -> float:
    base_size = self._get_base_size(confidence)
    risk_mult = SESSION_MANAGER.get_risk_multiplier(session)
    return base_size × risk_mult
```

---

### Task 10.3: Session Performance Tracker

**File**: `session_performance_tracker.py`

**Purpose**: Monitor and compare performance across sessions

**Metrics**:
```python
SESSION_METRICS = {
    'ASIA': {
        'signals': 0,
        'wins': 0,
        'losses': 0,
        'total_pnl': 0.0,
        'max_drawdown': 0.0,
        'avg_hold_time': 0.0,
    },
    # ... same for EUROPE, US
}
```

**Methods**:
```python
def record_signal(self, session: str, result: dict):
    """Record signal outcome by session"""

def get_session_win_rate(self, session: str) -> float:
    """Calculate win rate for session"""

def get_session_comparison(self) -> dict:
    """Compare all sessions side-by-side"""

def detect_session_degradation(self, session: str) -> bool:
    """Alert if session underperforming"""
```

---

### Task 10.4: Validation & Analysis

**File**: `week10_session_analysis.py`

**Purpose**: Validate session-aware parameters improve consistency

**Analysis**:
1. **Before/After Comparison**:
   - WR variance across sessions (before vs after)
   - Signal count distribution
   - Drawdown by session

2. **Session Heatmap**:
   - Hourly performance breakdown
   - Identify toxic hours within sessions
   - Visualize improvements

3. **Expected Improvements**:
   - WR variance: ↓40-50% (more consistent)
   - Asia WR: +2-3 points (better filtering)
   - US WR: +1-2 points (more aggressive)
   - Overall WR: +1 point (better session fit)

4. **Metrics to Track**:
   - `session_wr_std_dev` (should decrease)
   - `signals_per_session` (should match baselines)
   - `session_specific_sharpe`
   - `cross_session_drawdown_correlation`

---

## 📈 Expected Impact

### Session Consistency
**Problem**: Current system optimized for Europe, degrades in Asia/US
- Asia: 52% WR (vs 56% Europe)
- US: 54% WR (vs 56% Europe)
- Variance: 4 percentage points

**Solution**: Session-specific parameters
- Asia: 54-55% WR (+2-3 points from better filtering)
- Europe: 56-57% WR (slight improvement)
- US: 55-56% WR (+1-2 points from aggression)
- Variance: <2 percentage points (↓50%)

### Circuit Breaker Effectiveness
- Asia: Prevent 30-signal days (was triggering at 25)
- US: Allow 120 signals before pause (was capping at 25)
- Result: Better risk control **relative to normal**

### Risk-Adjusted Returns
- Asia: Smaller positions → Better risk/reward
- US: Maintain positions → Capture volume opportunities
- Overall Sharpe: +0.05 to +0.10 (from consistency)

---

## 🧪 Testing Plan

### Unit Tests
```python
# Test session detection
def test_session_manager():
    # Edge cases: midnight boundaries, DST, etc.
    
# Test parameter lookup
def test_session_parameters():
    # Verify correct multipliers returned
    
# Test integration
def test_session_aware_thresholds():
    # Compare Asia vs US thresholds for same vol
```

### Integration Tests
```python
# Test with historical data by session
def test_week10_session_backtest():
    # Run separate backtests for each session
    # Compare metrics before/after
```

### Validation Criteria
- ✅ WR variance: ↓40-50%
- ✅ Asia WR: +2-3 points
- ✅ US WR: +1-2 points
- ✅ Circuit breakers: Session-appropriate
- ✅ No regression in Europe performance

---

## 🔄 Integration Architecture

```
[Timestamp] → [SessionManager]
                    ↓
           [Session: ASIA/EUROPE/US]
                    ↓
    ┌───────────────┴───────────────┐
    ↓                               ↓
[Threshold Multiplier]    [Circuit Breaker Limit]
    ↓                               ↓
[Adaptive Threshold]      [Session Signal Count]
    ↓                               ↓
[Toxicity Detector]       [Risk Manager]
    ↓                               ↓
[Signal Generation]       [Position Sizing]
                    ↓
           [Session-Aware Trading]
```

---

## 📝 Deliverables

### Code Artifacts
1. ✅ `session_manager.py` (~300 lines)
2. ✅ `session_performance_tracker.py` (~350 lines)
3. ✅ Modified `adaptive_threshold_manager.py` (add session param)
4. ✅ Modified `vpin_circuit_breaker.py` (session-aware limits)
5. ✅ Modified `dynamic_position_sizer.py` (session risk mult)
6. ✅ `week10_session_analysis.py` (~400 lines)

### Documentation
1. ✅ This implementation plan
2. ✅ Week 10 completion summary
3. ✅ Session comparison report
4. ✅ Updated system architecture

### Data Artifacts
1. ✅ Session performance baselines
2. ✅ WR variance analysis
3. ✅ Before/after comparison charts

---

## 🔒 Locked Parameters Summary

| Parameter | Value | Source |
|-----------|-------|--------|
| Asia hours | 00:00-08:00 UTC | Standard definition |
| Europe hours | 08:00-16:00 UTC | Standard definition |
| US hours | 16:00-00:00 UTC | Standard definition |
| Asia signal limit | 30 (2× normal 15) | Week 1 data + Expert Q7 |
| Europe signal limit | 70 (2× normal 35) | Week 1 data + Expert Q7 |
| US signal limit | 120 (2× normal 60) | Week 1 data + Expert Q7 |
| Asia threshold mult | 1.10 | To be validated |
| Europe threshold mult | 1.00 | Baseline |
| US threshold mult | 0.95 | To be validated |
| Asia risk mult | 0.8 | Conservative approach |
| Europe risk mult | 1.0 | Baseline |
| US risk mult | 1.0 | Baseline |

**Expert Compliance**: 100% - Circuit breaker limits from Week 1 empirical data per Expert Q7

---

## ⏭️ Next Steps (Execution)

1. ✅ **Create `session_manager.py`**
   - Session detection logic
   - Parameter lookup
   - Integration helpers

2. ✅ **Create `session_performance_tracker.py`**
   - Metrics by session
   - Comparison reports
   - Degradation alerts

3. ✅ **Integrate into existing modules**
   - Modify threshold manager
   - Modify circuit breaker
   - Modify position sizer

4. ✅ **Validation analysis**
   - Run session-specific backtests
   - Generate comparison report
   - Validate improvements

5. ✅ **Documentation**
   - Week 10 completion summary
   - Update task checklist
   - Prepare for Week 11

---

**Status**: 📋 Plan complete, ready for execution

**Confidence**: **High** - Clear session boundaries, empirical baselines from Week 1, expert-validated approach

**Risk**: **Low** - Additive feature, can revert to session-agnostic if needed

**Expected Timeline**: Week 10 tasks (same as previous weeks)
