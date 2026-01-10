"""
Dynamic Signal Confidence System

Calculates percentage-based confidence scores (0-100%) for trading signals.
Uses 9 weighted factors and adapts to market conditions in real-time.
"""

import time
import logging
from typing import Dict, List, Optional
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class DynamicConfidenceCalculator:
    """
    Calculate dynamic percentage-based confidence scores.
    
    Features:
    - 9-factor weighted scoring (0-100 points)
    - Market regime detection (TRENDING/VOLATILE/CALM/CRISIS/RANGING)
    - Real-time volatility adjustment
    - Pre-calculated scores (event-driven, <0.1ms lookup)
    """
    
    def __init__(self, symbol: str):
        """
        Initialize confidence calculator.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        
        # Pre-calculated scores (updated continuously)
        self.scores = {
            'clusters': 0,
            'ofi': 0,
            'vpin': 0,
            'funding': 0,
            'kyle': 0,
            'intensity': 0,
            'orderbook': 0,
            'institutional': 0,
            'alignment': 0
        }
        
        # Market regime
        self.current_regime = 'CALM'
        self.regime_multiplier = 1.1
        
        # Volatility adjustment
        self.vol_adjustment = 1.0
        
        # Price history for regime detection
        self.price_history = deque(maxlen=3600)  # Last hour
        self.volatility_samples = deque(maxlen=8640)  # 30 days @ 5min
        
        # Liquidation tracking for regime
        self.recent_liquidations = deque(maxlen=300)  # Last 5 minutes
        
    def get_confidence(self, signal_direction: str) -> Dict:
        """
        Get instant confidence score (pre-calculated).
        
        Args:
            signal_direction: 'LONG' or 'SHORT'
        
        Returns:
            Dict with confidence_pct and breakdown
        """
        # 1. Sum pre-calculated base scores
        base_score = sum(self.scores.values())
        
        # 2. Apply regime multiplier
        # 3. Apply volatility adjustment
        confidence = base_score * self.regime_multiplier * self.vol_adjustment
        
        # 4. Clamp to [0, 100]
        confidence = max(0, min(100, confidence))
        
        return {
            'confidence_pct': round(confidence, 1),
            'base_score': round(base_score, 1),
            'regime': self.current_regime,
            'regime_multiplier': self.regime_multiplier,
            'volatility_adjustment': self.vol_adjustment,
            'breakdown': self.scores.copy()
        }
    
    # ============================================
    # EVENT HANDLERS (called from live streams)
    # ============================================
    
    def on_liquidation(self, liq_event: Dict, zones: List[Dict]):
        """
        Update scores when liquidation occurs.
        
        Args:
            liq_event: Liquidation event data
            zones: Current liquidation zones
        """
        # Update cluster proximity score
        self.scores['clusters'] = self._score_clusters(zones, liq_event['price'])
        
        # Track for regime detection
        self.recent_liquidations.append({
            'timestamp': time.time(),
            'value_usd': liq_event['value_usd']
        })
        
        # Update regime
        self._update_regime()
    
    def on_orderbook_update(self, orderbook: Dict, ofi_value: float, ofi_momentum: float):
        """
        Update scores from orderbook.
        
        Args:
            orderbook: Orderbook data
            ofi_value: Order flow imbalance
            ofi_momentum: OFI momentum
        """
        # Update OFI score
        self.scores['ofi'] = self._score_ofi(ofi_value, ofi_momentum)
        
        # Update orderbook imbalance score
        self.scores['orderbook'] = self._score_orderbook_imbalance(orderbook)
        
        # Update price history
        if 'best_bid' in orderbook and 'best_ask' in orderbook:
            mid_price = (orderbook['best_bid'] + orderbook['best_ask']) / 2
            self.price_history.append((time.time(), mid_price))
        
        # Update regime
        self._update_regime()
    
    def on_vpin_update(self, vpin_value: float):
        """Update VPIN score."""
        self.scores['vpin'] = self._score_vpin(vpin_value)
    
    def on_funding_update(self, funding_rate: float, funding_velocity: float):
        """Update funding rate score."""
        self.scores['funding'] = self._score_funding(funding_rate, funding_velocity)
    
    def on_kyle_update(self, kyle_lambda: float, kyle_percentile: float):
        """Update Kyle's lambda score."""
        self.scores['kyle'] = self._score_kyle(kyle_lambda, kyle_percentile)
    
    def on_intensity_update(self, intensity: float, acceleration: float):
        """Update liquidation intensity score."""
        self.scores['intensity'] = self._score_intensity(intensity, acceleration)
    
    def on_institutional_activity(self, inst_summary: Dict):
        """Update institutional activity score."""
        self.scores['institutional'] = self._score_institutional(inst_summary)
    
    def on_volatility_sample(self, vol_value: float):
        """Store volatility sample (called every 5 minutes)."""
        self.volatility_samples.append(vol_value)
    
    # ============================================
    # SCORING FUNCTIONS
    # ============================================
    
    def _score_clusters(self, zones: List[Dict], current_price: float) -> float:
        """Score liquidation cluster proximity (0-20 points)."""
        if not zones or not current_price:
            return 0
        
        # Find nearest zone
        nearest = min(zones, key=lambda z: abs(z.get('distance_pct', 100)))
        
        distance_pct = abs(nearest.get('distance_pct', 100))
        value_usd = nearest.get('value_usd', 0)
        
        # Distance scoring
        if distance_pct < 0.5:
            distance_score = 10
        elif distance_pct < 1.0:
            distance_score = 8
        elif distance_pct < 2.0:
            distance_score = 5
        elif distance_pct < 3.0:
            distance_score = 3
        else:
            distance_score = 0
        
        # Size scoring
        if value_usd > 10_000_000:
            size_score = 10
        elif value_usd > 5_000_000:
            size_score = 7
        elif value_usd > 2_000_000:
            size_score = 5
        elif value_usd > 1_000_000:
            size_score = 3
        else:
            size_score = 1
        
        return min(distance_score + size_score, 20)
    
    def _score_ofi(self, ofi_value: float, ofi_momentum: float) -> float:
        """Score order flow imbalance (0-15 points)."""
        score = 0
        
        # OFI magnitude (0-10 points)
        ofi_abs = abs(ofi_value)
        if ofi_abs > 1000:
            score += 10
        elif ofi_abs > 500:
            score += 7
        elif ofi_abs > 200:
            score += 5
        elif ofi_abs > 100:
            score += 3
        else:
            score += 1
        
        # OFI momentum (0-5 points)
        if abs(ofi_momentum) > 500:
            score += 5
        elif abs(ofi_momentum) > 200:
            score += 3
        elif abs(ofi_momentum) > 50:
            score += 1
        
        return min(score, 15)
    
    def _score_vpin(self, vpin_value: float) -> float:
        """Score VPIN toxicity (0-15 points)."""
        if vpin_value > 0.8:
            return 15
        elif vpin_value > 0.6:
            return 12
        elif vpin_value > 0.4:
            return 8
        elif vpin_value > 0.2:
            return 4
        else:
            return 1
    
    def _score_funding(self, funding_rate: float, funding_velocity: float) -> float:
        """Score funding rate extremity (0-10 points)."""
        score = 0
        
        # Magnitude (0-7 points)
        funding_abs = abs(funding_rate)
        if funding_abs > 0.05:
            score += 7
        elif funding_abs > 0.03:
            score += 5
        elif funding_abs > 0.01:
            score += 3
        elif funding_abs > 0.005:
            score += 1
        
        # Velocity (0-3 points)
        velocity_abs = abs(funding_velocity)
        if velocity_abs > 0.001:
            score += 3
        elif velocity_abs > 0.0005:
            score += 2
        elif velocity_abs > 0.0001:
            score += 1
        
        return min(score, 10)
    
    def _score_kyle(self, kyle_lambda: float, kyle_percentile: float) -> float:
        """Score Kyle's lambda (0-10 points)."""
        score = 0
        
        # Percentile (0-7 points)
        if kyle_percentile > 90:
            score += 7
        elif kyle_percentile > 75:
            score += 5
        elif kyle_percentile > 50:
            score += 3
        else:
            score += 1
        
        # Magnitude (0-3 points)
        if kyle_lambda > 0.001:
            score += 3
        elif kyle_lambda > 0.0005:
            score += 2
        elif kyle_lambda > 0.0001:
            score += 1
        
        return min(score, 10)
    
    def _score_intensity(self, intensity: float, acceleration: float) -> float:
        """Score liquidation intensity (0-10 points)."""
        score = 0
        
        # Current intensity (0-6 points)
        if intensity > 5.0:
            score += 6
        elif intensity > 3.0:
            score += 4
        elif intensity > 1.0:
            score += 2
        
        # Acceleration (0-4 points)
        if acceleration > 2.0:
            score += 4
        elif acceleration > 1.0:
            score += 2
        elif acceleration > 0:
            score += 1
        
        return min(score, 10)
    
    def _score_orderbook_imbalance(self, orderbook: Dict) -> float:
        """Score orderbook imbalance (0-10 points)."""
        bid_size = orderbook.get('bid_size', 0)
        ask_size = orderbook.get('ask_size', 0)
        
        if bid_size + ask_size == 0:
            return 0
        
        imbalance = (bid_size - ask_size) / (bid_size + ask_size)
        imb_abs = abs(imbalance)
        
        # Magnitude (0-10 points)
        if imb_abs > 0.3:
            return 10
        elif imb_abs > 0.2:
            return 7
        elif imb_abs > 0.1:
            return 5
        elif imb_abs > 0.05:
            return 3
        else:
            return 1
    
    def _score_institutional(self, inst_summary: Dict) -> float:
        """Score institutional activity (0-5 points)."""
        score = 0
        
        if inst_summary.get('spoofing_detected'):
            score += 2
        if inst_summary.get('stop_hunting_detected'):
            score += 2
        if inst_summary.get('large_absorption'):
            score += 1
        
        return min(score, 5)
    
    # ============================================
    # REGIME DETECTION
    # ============================================
    
    def _update_regime(self):
        """Update market regime and multipliers."""
        if len(self.price_history) < 60:
            return  # Not enough data
        
        # Calculate trend strength
        trend_strength = self._calculate_trend_strength()
        
        # Calculate volatility percentile
        current_vol = self._calculate_current_volatility()
        vol_percentile = self._get_volatility_percentile(current_vol)
        
        # Calculate liquidation rate
        liq_rate = self._get_liquidation_rate()
        
        # Classify regime
        if vol_percentile > 95 and liq_rate > 10:
            self.current_regime = 'CRISIS'
            self.regime_multiplier = 0.5
        elif vol_percentile > 80:
            self.current_regime = 'VOLATILE'
            self.regime_multiplier = 0.7
        elif trend_strength > 25 and vol_percentile < 50:
            self.current_regime = 'TRENDING'
            self.regime_multiplier = 1.3
        elif trend_strength < 15 and vol_percentile < 30:
            self.current_regime = 'RANGING'
            self.regime_multiplier = 0.9
        else:
            self.current_regime = 'CALM'
            self.regime_multiplier = 1.1
        
        # Update volatility adjustment
        self.vol_adjustment = self._calculate_volatility_adjustment(current_vol)
    
    def _calculate_trend_strength(self) -> float:
        """Calculate trend strength (0-100)."""
        if len(self.price_history) < 60:
            return 0
        
        # Get last 60 price changes
        prices = list(self.price_history)[-60:]
        price_changes = [
            (prices[i][1] - prices[i-1][1]) / prices[i-1][1]
            for i in range(1, len(prices))
        ]
        
        # Directional movement
        positive_moves = [max(0, c) for c in price_changes]
        negative_moves = [abs(min(0, c)) for c in price_changes]
        
        avg_pos = sum(positive_moves) / len(positive_moves) if positive_moves else 0
        avg_neg = sum(negative_moves) / len(negative_moves) if negative_moves else 0
        
        total = avg_pos + avg_neg
        if total == 0:
            return 0
        
        trend_strength = (abs(avg_pos - avg_neg) / total) * 100
        return trend_strength
    
    def _calculate_current_volatility(self) -> float:
        """Calculate current realized volatility."""
        if len(self.price_history) < 300:
            return 0
        
        # Get last 5 minutes of prices
        prices = list(self.price_history)[-300:]
        returns = [
            np.log(prices[i][1] / prices[i-1][1])
            for i in range(1, len(prices))
        ]
        
        # Realized volatility (annualized)
        vol = np.std(returns) * np.sqrt(252 * 24 * 60)  # Annualize
        return vol
    
    def _get_volatility_percentile(self, current_vol: float) -> float:
        """Get volatility percentile vs historical."""
        if len(self.volatility_samples) < 100:
            return 50  # Default to median
        
        samples = list(self.volatility_samples)
        count_below = sum(1 for v in samples if v < current_vol)
        percentile = (count_below / len(samples)) * 100
        
        return percentile
    
    def _get_liquidation_rate(self) -> float:
        """Get liquidation rate (events per minute)."""
        current_time = time.time()
        
        # Count liquidations in last 5 minutes
        recent = [
            liq for liq in self.recent_liquidations
            if current_time - liq['timestamp'] < 300
        ]
        
        liq_rate = len(recent) / 5  # Per minute
        return liq_rate
    
    def _calculate_volatility_adjustment(self, current_vol: float) -> float:
        """Calculate volatility adjustment multiplier (0.7-1.3)."""
        if len(self.volatility_samples) < 100:
            return 1.0
        
        # Calculate baseline volatility
        baseline_vol = np.mean(list(self.volatility_samples))
        
        if baseline_vol == 0:
            return 1.0
        
        vol_ratio = current_vol / baseline_vol
        
        # Adjustment logic
        if vol_ratio > 2.0:
            return 0.7  # High volatility spike
        elif vol_ratio > 1.5:
            return 0.85
        elif vol_ratio < 0.5:
            return 1.2  # Volatility compression
        elif vol_ratio < 0.7:
            return 1.1
        else:
            return 1.0  # Normal


if __name__ == "__main__":
    """Test dynamic confidence calculator."""
    
    logging.basicConfig(level=logging.INFO)
    
    # Create calculator
    calc = DynamicConfidenceCalculator('BTCUSDT')
    
    # Simulate some updates
    calc.on_vpin_update(0.75)
    calc.on_funding_update(0.02, 0.001)
    calc.on_intensity_update(3.5, 1.2)
    
    # Get confidence
    result = calc.get_confidence('LONG')
    
    print("=" * 60)
    print("DYNAMIC CONFIDENCE TEST")
    print("=" * 60)
    print(f"\nConfidence: {result['confidence_pct']}%")
    print(f"Base Score: {result['base_score']}/100")
    print(f"Regime: {result['regime']} ({result['regime_multiplier']}x)")
    print(f"Vol Adjustment: {result['volatility_adjustment']}x")
    print(f"\nBreakdown:")
    for factor, score in result['breakdown'].items():
        print(f"  {factor}: {score}")
