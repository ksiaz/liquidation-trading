"""
Week 8: VPIN Calculator & Circuit Breakers
==========================================

Implements Volume-Synchronized Probability of Informed Trading (VPIN)
and circuit breakers for risk control.

VPIN Overview:
- Measures toxic flow (informed trading)
- Based on volume buckets (not time-based)
- High VPIN = adverse selection risk
- Use to pause trading during toxic conditions

Circuit Breakers:
1. **Per-Session Limit**: Max signals per session (from Week 1)
2. **Z-Score Threshold**: Pause if signal rate >> normal
3. **VPIN Threshold**: Pause if market toxicity high

Expert Context:
- VPIN >95th percentile = toxic market
- Circuit breakers prevent overtrading
- Protect capital during adverse conditions
"""

import logging
from typing import Dict, Optional, List, Tuple
from collections import deque
import numpy as np
import time

logger = logging.getLogger(__name__)


class VPINCalculator:
    """
    Calculate Volume-Synchronized Probability of Informed Trading (VPIN).
    
    VPIN measures the probability that next trade is informed (toxic).
    High VPIN = high adverse selection risk.
    
    Algorithm:
    1. Accumulate trades into volume buckets (e.g., 100 BTC each)
    2. For each bucket, calculate |buy_volume - sell_volume|
    3. VPIN = average(|buy - sell|) / total_volume over N buckets
    """
    
    # LOCKED PARAMETERS
    VOLUME_BUCKET_SIZE = 100.0  # BTC per bucket
    NUM_BUCKETS = 50            # Rolling window of buckets
    
    # VPIN thresholds (will be calibrated from data)
    VPIN_HIGH_THRESHOLD = 0.5   # 95th percentile (placeholder)
    VPIN_EXTREME_THRESHOLD = 0.7  # 99th percentile (placeholder)
    
    def __init__(self, symbol: str = 'BTCUSDT', bucket_size: float = None):
        """
        Initialize VPIN calculator.
        
        Args:
            symbol: Trading symbol
            bucket_size: Volume bucket size (overrides default)
        """
        self.symbol = symbol
        self.bucket_size = bucket_size or self.VOLUME_BUCKET_SIZE
        
        # Current bucket accumulation
        self.current_bucket_buy = 0.0
        self.current_bucket_sell = 0.0
        self.current_bucket_total = 0.0
        
        # Historical buckets (rolling window)
        self.bucket_imbalances: deque = deque(maxlen=self.NUM_BUCKETS)
        
        # Statistics
        self.stats = {
            'total_trades_processed': 0,
            'buckets_completed': 0,
            'current_vpin': 0.0,
            'vpin_readings': []
        }
        
        logger.info(f"VPINCalculator initialized for {symbol}")
        logger.info(f"  Bucket size: {self.bucket_size} BTC")
        logger.info(f"  Window: {self.NUM_BUCKETS} buckets")
    
    def update_trade(self, trade: Dict):
        """
        Update VPIN with new trade.
        
        Args:
            trade: {
                'quantity': float (in BTC),
                'is_buyer_maker': bool (True = sell, False = buy)
            }
        """
        self.stats['total_trades_processed'] += 1
        
        quantity = trade.get('quantity', 0)
        is_buyer_maker = trade.get('is_buyer_maker', False)
        
        # Classify as buy or sell
        # is_buyer_maker=True means buyer provided liquidity (passive buy = market sell hit the bid)
        if is_buyer_maker:
            # Market sell (aggressive seller)
            self.current_bucket_sell += quantity
        else:
            # Market buy (aggressive buyer)
            self.current_bucket_buy += quantity
        
        self.current_bucket_total += quantity
        
        # Check if bucket is complete
        if self.current_bucket_total >= self.bucket_size:
            self._complete_bucket()
    
    def _complete_bucket(self):
        """Complete current bucket and calculate imbalance."""
        # Calculate absolute imbalance
        imbalance = abs(self.current_bucket_buy - self.current_bucket_sell)
        
        # Store imbalance
        self.bucket_imbalances.append(imbalance)
        
        self.stats['buckets_completed'] += 1
        
        # Reset current bucket
        self.current_bucket_buy = 0.0
        self.current_bucket_sell = 0.0
        self.current_bucket_total = 0.0
    
    def calculate_vpin(self) -> Optional[Dict]:
        """
        Calculate current VPIN.
        
        Returns:
            {
                'vpin': float,
                'buckets_used': int,
                'is_valid': bool,
                'toxicity_level': str
            }
            or None if insufficient data
        """
        if len(self.bucket_imbalances) < 10:  # Need minimum buckets
            return None
        
        # Calculate VPIN
        total_imbalance = sum(self.bucket_imbalances)
        total_volume = len(self.bucket_imbalances) * self.bucket_size
        
        vpin = total_imbalance / total_volume if total_volume > 0 else 0
        
        # Classify toxicity
        if vpin >= self.VPIN_EXTREME_THRESHOLD:
            toxicity = 'EXTREME'
        elif vpin >= self.VPIN_HIGH_THRESHOLD:
            toxicity = 'HIGH'
        else:
            toxicity = 'NORMAL'
        
        self.stats['current_vpin'] = vpin
        self.stats['vpin_readings'].append(vpin)
        
        return {
            'vpin': vpin,
            'buckets_used': len(self.bucket_imbalances),
            'is_valid': True,
            'toxicity_level': toxicity
        }
    
    def is_market_toxic(self) -> bool:
        """Check if market is currently toxic (high VPIN)."""
        vpin_result = self.calculate_vpin()
        
        if vpin_result is None:
            return False
        
        return vpin_result['vpin'] >= self.VPIN_HIGH_THRESHOLD
    
    def get_stats(self) -> Dict:
        """Get VPIN statistics."""
        vpin_readings = self.stats['vpin_readings']
        
        return {
            **self.stats,
            'vpin_mean': np.mean(vpin_readings) if vpin_readings else 0,
            'vpin_std': np.std(vpin_readings) if vpin_readings else 0,
            'vpin_95pct': np.percentile(vpin_readings, 95) if len(vpin_readings) > 20 else 0
        }


class CircuitBreaker:
    """
    Circuit breakers for risk control.
    
    Monitors:
    1. Signals per session (from Week 1 data)
    2. Signal rate Z-score
    3. VPIN toxicity
    
    Triggers:
    - Pause trading when limits exceeded
    - Resume after cooldown period
    """
    
    # LOCKED PARAMETERS (from Week 1)
    SIGNALS_PER_SESSION_TARGET = (15, 25)  # (min, max) from Month 1 checkpoint
    SESSION_DURATION_HOURS = 8  # 3 sessions per 24h
    
    # Z-score threshold
    ZSCORE_THRESHOLD = 2.5  # >2.5 std devs = anomalous
    
    # Cooldown periods
    COOLDOWN_SESSION_LIMIT = 300  # 5 minutes
    COOLDOWN_ZSCORE = 600         # 10 minutes
    COOLDOWN_VPIN = 900          # 15 minutes
    
    def __init__(self, vpin_calculator: Optional[VPINCalculator] = None):
        """
        Initialize circuit breaker.
        
        Args:
            vpin_calculator: Optional VPIN calculator for toxicity monitoring
        """
        self.vpin_calculator = vpin_calculator
        
        # Signal tracking
        self.session_signals = 0
        self.session_start_time = time.time()
        
        # Historical signal rates (for Z-score)
        self.hourly_signal_counts: deque = deque(maxlen=24)  # Last 24 hours
        
        # Breaker state
        self.is_paused = False
        self.pause_reason = None
        self.pause_start_time = None
        self.resume_time = None
        
        # Statistics
        self.stats = {
            'total_signals': 0,
            'sessions_completed': 0,
            'circuit_breaks_session': 0,
            'circuit_breaks_zscore': 0,
            'circuit_breaks_vpin': 0,
            'total_pause_time': 0
        }
        
        logger.info("CircuitBreaker initialized")
        logger.info(f"  Target signals/session: {self.SIGNALS_PER_SESSION_TARGET}")
        logger.info(f"  Z-score threshold: {self.ZSCORE_THRESHOLD}")
    
    def check_signal(self) -> Dict:
        """
        Check if signal should be allowed through circuit breaker.
        
        Returns:
            {
                'allowed': bool,
                'reason': str,
                'pause_remaining': float (seconds)
            }
        """
        # Check if currently paused
        if self.is_paused:
            time_remaining = self.resume_time - time.time()
            
            if time_remaining <= 0:
                # Cooldown complete
                self._resume()
            else:
                return {
                    'allowed': False,
                    'reason': f'Paused: {self.pause_reason}',
                    'pause_remaining': time_remaining
                }
        
        # Check session limit
        if self.session_signals >= self.SIGNALS_PER_SESSION_TARGET[1]:
            self._trigger_break('SESSION_LIMIT', self.COOLDOWN_SESSION_LIMIT)
            self.stats['circuit_breaks_session'] += 1
            return {
                'allowed': False,
                'reason': f'Session limit reached ({self.session_signals} signals)',
                'pause_remaining': self.COOLDOWN_SESSION_LIMIT
            }
        
        # Check Z-score
        zscore = self._calculate_signal_rate_zscore()
        if zscore is not None and zscore > self.ZSCORE_THRESHOLD:
            self._trigger_break('ZSCORE_ANOMALY', self.COOLDOWN_ZSCORE)
            self.stats['circuit_breaks_zscore'] += 1
            return {
                'allowed': False,
                'reason': f'Signal rate anomaly (Z={zscore:.2f})',
                'pause_remaining': self.COOLDOWN_ZSCORE
            }
        
        # Check VPIN toxicity
        if self.vpin_calculator and self.vpin_calculator.is_market_toxic():
            self._trigger_break('VPIN_TOXIC', self.COOLDOWN_VPIN)
            self.stats['circuit_breaks_vpin'] += 1
            return {
                'allowed': False,
                'reason': 'Market toxicity high (VPIN)',
                'pause_remaining': self.COOLDOWN_VPIN
            }
        
        # All checks passed
        self.session_signals += 1
        self.stats['total_signals'] += 1
        
        return {
            'allowed': True,
            'reason': 'All checks passed',
            'pause_remaining': 0
        }
    
    def _trigger_break(self, reason: str, duration: float):
        """Trigger circuit breaker."""
        self.is_paused = True
        self.pause_reason = reason
        self.pause_start_time = time.time()
        self.resume_time = self.pause_start_time + duration
        
        logger.warning(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        logger.warning(f"  Pausing for {duration}s")
    
    def _resume(self):
        """Resume trading after cooldown."""
        pause_duration = time.time() - self.pause_start_time
        self.stats['total_pause_time'] += pause_duration
        
        logger.info(f"CIRCUIT BREAKER RESUMED after {pause_duration:.0f}s")
        
        self.is_paused = False
        self.pause_reason = None
        self.pause_start_time = None
        self.resume_time = None
    
    def _calculate_signal_rate_zscore(self) -> Optional[float]:
        """Calculate Z-score of current signal rate."""
        if len(self.hourly_signal_counts) < 3:
            return None
        
        # Current rate (signals per hour)
        elapsed_hours = (time.time() - self.session_start_time) / 3600
        current_rate = self.session_signals / elapsed_hours if elapsed_hours > 0 else 0
        
        # Historical stats
        mean_rate = np.mean(self.hourly_signal_counts)
        std_rate = np.std(self.hourly_signal_counts)
        
        if std_rate == 0:
            return 0
        
        zscore = (current_rate - mean_rate) / std_rate
        
        return zscore
    
    def end_session(self):
        """Mark end of session and reset counters."""
        # Record hourly rate
        elapsed_hours = (time.time() - self.session_start_time) / 3600
        rate = self.session_signals / elapsed_hours if elapsed_hours > 0 else 0
        self.hourly_signal_counts.append(rate)
        
        self.stats['sessions_completed'] += 1
        
        # Reset session
        self.session_signals = 0
        self.session_start_time = time.time()
    
    def get_stats(self) -> Dict:
        """Get circuit breaker statistics."""
        total_breaks = (self.stats['circuit_breaks_session'] + 
                       self.stats['circuit_breaks_zscore'] + 
                       self.stats['circuit_breaks_vpin'])
        
        return {
            **self.stats,
            'total_circuit_breaks': total_breaks,
            'is_paused': self.is_paused,
            'current_session_signals': self.session_signals
        }


if __name__ == "__main__":
    """Test VPIN calculator and circuit breakers."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 8: VPIN & CIRCUIT BREAKERS TEST")
    print("=" * 80)
    print(f"\n🔒 LOCKED PARAMETERS:")
    print(f"   VPIN bucket size: {VPINCalculator.VOLUME_BUCKET_SIZE} BTC")
    print(f"   VPIN window: {VPINCalculator.NUM_BUCKETS} buckets")
    print(f"   Session limit: {CircuitBreaker.SIGNALS_PER_SESSION_TARGET}")
    print(f"   Z-score threshold: {CircuitBreaker.ZSCORE_THRESHOLD}\n")
    
    # Test VPIN
    print("Test 1: VPIN Calculation")
    print("-" * 80)
    
    vpin_calc = VPINCalculator('BTCUSDT')
    
    # Simulate 50 buckets of trades (5000 BTC total)
    for i in range(500):
        # Simulate imbalanced flow (70% buys, 30% sells)
        is_buy = np.random.random() < 0.7
        
        trade = {
            'quantity': 10.0,
            'is_buyer_maker': not is_buy  # Inverse for our convention
        }
        
        vpin_calc.update_trade(trade)
    
    vpin_result = vpin_calc.calculate_vpin()
    
    if vpin_result:
        print(f"   VPIN: {vpin_result['vpin']:.4f}")
        print(f"   Buckets: {vpin_result['buckets_used']}")
        print(f"   Toxicity: {vpin_result['toxicity_level']}")
        print(f"   Is toxic: {vpin_calc.is_market_toxic()}\n")
    
    # Test Circuit Breaker
    print("Test 2: Circuit Breaker - Session Limit")
    print("-" * 80)
    
    breaker = CircuitBreaker(vpin_calc)
    
    # Simulate signals up to limit
    for i in range(26):
        result = breaker.check_signal()
        
        if not result['allowed']:
            print(f"   Signal {i+1}: BLOCKED - {result['reason']}")
            break
        else:
            if i < 3 or i >= 23:
                print(f"   Signal {i+1}: ALLOWED")
    
    print(f"\n✅ Test complete - VPIN & Circuit Breakers ready")
    print("\n📊 Expected Impact:")
    print("   - Avoid toxic markets (VPIN > threshold)")
    print("   - Prevent overtrading (session limits)")
    print("   - Detect anomalies (Z-score) ")
    print("   - Protect capital during adverse conditions")
