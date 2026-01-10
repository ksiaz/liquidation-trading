"""
V-Bottom Tracker - Bulletproof Reversal Detection

Detects sharp selloff reversals (V-bottoms) using 7-layer confirmation:
1. Orderbook microstructure (bid refill, spread, skew)
2. Order Flow Imbalance (OFI flip)
3. Volume profile (capitulation, buy/sell ratio)
4. Market maker behavior
5. Price action (wick, recovery)
6. Multi-timeframe support
7. False positive filters

State Machine: NORMAL → SELLOFF → CAPITULATION → REVERSAL

Three Entry Strategies:
- Conservative: 90%+ confidence, 3% from bottom
- Balanced: 85%+ confidence, 1.5% from bottom
- Aggressive: 75%+ confidence, 0.7% from bottom
"""

import time
import logging
import numpy as np
from typing import Dict, Optional, List
from collections import deque

logger = logging.getLogger(__name__)


class VBottomTracker:
    """
    Tracks market state and detects V-bottom reversals.
    
    Uses 7-layer confirmation system for bulletproof signals.
    """
    
    def __init__(self, symbol: str):
        """
        Initialize V-bottom tracker.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
        """
        self.symbol = symbol
        
        # State machine (BIDIRECTIONAL!)
        # Downward: NORMAL → SELLOFF → CAPITULATION → REVERSAL (LONG)
        # Upward:   NORMAL → RALLY → RALLY_EXHAUSTION → REVERSAL (SHORT)
        self.state = 'NORMAL'
        self.state_entry_time = time.time()
        
        # History tracking (for all layers)
        self.ofi_history = deque(maxlen=20)
        self.spread_history = deque(maxlen=20)
        self.bid_depth_history = deque(maxlen=20)
        self.ask_depth_history = deque(maxlen=20)
        self.skew_history = deque(maxlen=20)
        self.volume_history = deque(maxlen=60)  # 60 seconds
        self.price_history = deque(maxlen=20)
        
        # Enhancement tracking
        self.liquidation_history = deque(maxlen=10)  # Recent liquidations
        self.bid_pressure_gradient = deque(maxlen=10)  # Pressure acceleration
        self.toxicity_history = deque(maxlen=20)  # Toxicity signals
        
        # Capitulation/Exhaustion metrics (bidirectional)
        self.selloff_start_price = None
        self.capitulation_price = None
        self.rally_start_price = None  # NEW
        self.exhaustion_price = None   # NEW
        self.max_spread_seen = 0
        self.min_bid_depth_seen = float('inf')
        self.min_ask_depth_seen = float('inf')  # NEW
        
        # BTC correlation (for ETH/SOL)
        self.btc_state = None  # Will be set externally
        
        # Thresholds (FIXED - was -0.7, way too strict!)
        # Real V-formations have 5-10% orderbook skew, not 70%!
        self.SELLOFF_THRESHOLD = -0.08  # -8% skew (was -0.7 = -70%!)
        self.RALLY_THRESHOLD = 0.08     # +8% skew (was 0.7 = +70%!)
        self.CAPITULATION_SPREAD = 0.002  # 0.2% spread
        self.BID_REFILL_THRESHOLD = 0.5  # 50% increase
        self.ASK_REFILL_THRESHOLD = 0.5  # 50% increase
        self.OFI_FLIP_THRESHOLD = 0  # OFI > 0
        
    def update(self, orderbook: Dict, price: float, volume: float = 0, 
               liquidation_data: Optional[Dict] = None,
               toxicity_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Update tracker with new market data.
        
        Args:
            orderbook: 20-level orderbook
            price: Current price
            volume: Recent volume
            liquidation_data: Recent liquidations for cascade detection
            toxicity_data: Toxicity signals for flip detection
            
        Returns:
            Signal dict if reversal detected, None otherwise
        """
        try:
            # Calculate metrics
            metrics = self._calculate_metrics(orderbook, price, volume)
            
            # Store history
            self._update_history(metrics)
            
            # Store liquidation data
            if liquidation_data:
                self.liquidation_history.append(liquidation_data)
            
            # Store toxicity data
            if toxicity_data:
                self.toxicity_history.append(toxicity_data)
            
            # State machine (BIDIRECTIONAL)
            if self.state == 'NORMAL':
                # Check for selloff (downward)
                if self._detect_selloff(metrics):
                    self._enter_selloff(price)
                # Check for rally (upward) - NEW!
                elif self._detect_rally(metrics):
                    self._enter_rally(price)
            
            elif self.state == 'SELLOFF':
                if self._detect_capitulation(metrics):
                    self._enter_capitulation(price)
            
            elif self.state == 'RALLY':  # NEW!
                if self._detect_rally_exhaustion(metrics):
                    self._enter_rally_exhaustion(price)
            
            elif self.state == 'CAPITULATION':
                signal = self._detect_reversal(metrics, price, liquidation_data, toxicity_data, direction='LONG')
                if signal:
                    self._enter_reversal()
                    return signal
            
            elif self.state == 'RALLY_EXHAUSTION':  # NEW!
                signal = self._detect_reversal(metrics, price, liquidation_data, toxicity_data, direction='SHORT')
                if signal:
                    self._enter_reversal()
                    return signal
            
            return None
            
        except Exception as e:
            logger.error(f"Error in V-bottom tracker for {self.symbol}: {e}")
            return None
    
    def _calculate_metrics(self, orderbook: Dict, price: float, volume: float) -> Dict:
        """Calculate all metrics for 7-layer system."""
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks or len(bids) < 20 or len(asks) < 20:
            return {}
        
        # Layer 1: Orderbook microstructure
        bid_depth_L1 = sum(float(qty) for _, qty in bids[:5])
        bid_depth_L2 = sum(float(qty) for _, qty in bids[5:10])
        bid_depth_total = sum(float(qty) for _, qty in bids[:20])
        
        ask_depth_L1 = sum(float(qty) for _, qty in asks[:5])
        ask_depth_total = sum(float(qty) for _, qty in asks[:20])
        
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread_pct = (best_ask - best_bid) / best_bid * 100
        
        # Orderbook skew
        total_depth = bid_depth_total + ask_depth_total
        skew = (bid_depth_total - ask_depth_total) / total_depth if total_depth > 0 else 0
        
        return {
            'bid_depth_L1': bid_depth_L1,
            'bid_depth_L2': bid_depth_L2,
            'bid_depth_total': bid_depth_total,
            'ask_depth_total': ask_depth_total,
            'spread_pct': spread_pct,
            'skew': skew,
            'price': price,
            'volume': volume
        }
    
    def _update_history(self, metrics: Dict):
        """Update all history deques."""
        if not metrics:
            return
        
        self.bid_depth_history.append(metrics.get('bid_depth_total', 0))
        self.ask_depth_history.append(metrics.get('ask_depth_total', 0))
        self.spread_history.append(metrics.get('spread_pct', 0))
        self.skew_history.append(metrics.get('skew', 0))
        self.price_history.append(metrics.get('price', 0))
        self.volume_history.append(metrics.get('volume', 0))
    
    def _detect_selloff(self, metrics: Dict) -> bool:
        """Detect start of selloff (NORMAL → SELLOFF)."""
        if not metrics or len(self.skew_history) < 5:
            return False
        
        skew = metrics.get('skew', 0)
        spread = metrics.get('spread_pct', 0)
        
        # Selloff: extreme negative skew + widening spread
        if skew < self.SELLOFF_THRESHOLD and spread > 0.1:
            logger.info(f"{self.symbol}: SELLOFF detected (skew: {skew:.2f}, spread: {spread:.3f}%)")
            return True
        
        return False
    
    def _enter_selloff(self, price: float):
        """Enter SELLOFF state."""
        self.state = 'SELLOFF'
        self.state_entry_time = time.time()
        self.selloff_start_price = price
        self.max_spread_seen = 0
        self.min_bid_depth_seen = float('inf')
        logger.info(f"{self.symbol}: Entered SELLOFF state at ${price:.2f}")
    
    def _detect_capitulation(self, metrics: Dict) -> bool:
        """Detect capitulation point (SELLOFF → CAPITULATION)."""
        if not metrics:
            return False
        
        spread = metrics.get('spread_pct', 0)
        bid_depth = metrics.get('bid_depth_total', 0)
        
        # Track extremes
        self.max_spread_seen = max(self.max_spread_seen, spread)
        if bid_depth > 0:
            self.min_bid_depth_seen = min(self.min_bid_depth_seen, bid_depth)
        
        # Capitulation: spread explosion + bid depth collapse
        if spread > self.CAPITULATION_SPREAD and bid_depth < self.min_bid_depth_seen * 1.2:
            logger.info(f"{self.symbol}: CAPITULATION detected (spread: {spread:.3f}%, bid_depth: {bid_depth:.2f})")
            return True
        
        return False
    
    def _enter_capitulation(self, price: float):
        """Enter CAPITULATION state."""
        self.state = 'CAPITULATION'
        self.state_entry_time = time.time()
        self.capitulation_price = price
        logger.info(f"{self.symbol}: Entered CAPITULATION state at ${price:.2f}")
    
    def _detect_rally(self, metrics: Dict) -> bool:
        """Detect start of rally (NORMAL → RALLY) - MIRROR of selloff."""
        if not metrics or len(self.skew_history) < 5:
            return False
        
        skew = metrics.get('skew', 0)
        spread = metrics.get('spread_pct', 0)
        
        # Rally: extreme positive skew + widening spread
        if skew > self.RALLY_THRESHOLD and spread > 0.1:
            logger.info(f"{self.symbol}: RALLY detected (skew: {skew:.2f}, spread: {spread:.3f}%)")
            return True
        
        return False
    
    def _enter_rally(self, price: float):
        """Enter RALLY state."""
        self.state = 'RALLY'
        self.state_entry_time = time.time()
        self.rally_start_price = price
        self.max_spread_seen = 0
        self.min_ask_depth_seen = float('inf')
        logger.info(f"{self.symbol}: Entered RALLY state at ${price:.2f}")
    
    def _detect_rally_exhaustion(self, metrics: Dict) -> bool:
        """Detect exhaustion point (RALLY → RALLY_EXHAUSTION) - MIRROR of capitulation."""
        if not metrics:
            return False
        
        spread = metrics.get('spread_pct', 0)
        ask_depth = metrics.get('ask_depth_total', 0)
        
        # Track extremes
        self.max_spread_seen = max(self.max_spread_seen, spread)
        if ask_depth > 0:
            self.min_ask_depth_seen = min(self.min_ask_depth_seen, ask_depth)
        
        # Exhaustion: spread explosion + ask depth collapse
        if spread > self.CAPITULATION_SPREAD and ask_depth < self.min_ask_depth_seen * 1.2:
            logger.info(f"{self.symbol}: RALLY EXHAUSTION detected (spread: {spread:.3f}%, ask_depth: {ask_depth:.2f})")
            return True
        
        return False
    
    def _enter_rally_exhaustion(self, price: float):
        """Enter RALLY_EXHAUSTION state."""
        self.state = 'RALLY_EXHAUSTION'
        self.state_entry_time = time.time()
        self.exhaustion_price = price
        logger.info(f"{self.symbol}: Entered RALLY_EXHAUSTION state at ${price:.2f}")
    
    def _detect_reversal(self, metrics: Dict, price: float,
                        liquidation_data: Optional[Dict] = None,
                        toxicity_data: Optional[Dict] = None,
                        direction: str = 'LONG') -> Optional[Dict]:
        """
        Detect reversal using enhanced 12-layer confirmation.
        
        BIDIRECTIONAL:
        - direction='LONG': V-bottom (selloff reversal)
        - direction='SHORT': V-top (rally reversal)
        
        Original 7 layers + 5 enhancements:
        8. Liquidation cascade detection
        9. Orderbook pressure buildup
        10. Volume profile microstructure
        11. Toxicity flip detection
        12. BTC correlation
        
        Returns signal dict with enhanced confidence score.
        """
        if not metrics or len(self.bid_depth_history) < 10:
            return None
        
        # Layer 1: Orderbook microstructure
        layer1_score = self._check_layer1_orderbook(metrics)
        
        # Layer 2: OFI (if available)
        layer2_score = self._check_layer2_ofi()
        
        # Layer 3: Volume profile
        layer3_score = self._check_layer3_volume()
        
        # Layer 4: Market maker behavior
        layer4_score = self._check_layer4_mm(metrics)
        
        # Layer 5: Price action
        layer5_score = self._check_layer5_price(price)
        
        # Layer 6: Multi-timeframe (simplified)
        layer6_score = self._check_layer6_timeframe(price)
        
        # ENHANCEMENT LAYERS (8-12)
        cascade_result = self._detect_liquidation_cascade()
        layer8_score = cascade_result.get('score', 0.0)
        
        pressure_result = self._track_orderbook_pressure_buildup()
        layer9_score = pressure_result.get('score', 0.0)
        
        volume_result = self._analyze_volume_profile_shape()
        layer10_score = volume_result.get('score', 0.0)
        
        toxicity_result = self._detect_toxicity_flip()
        layer11_score = toxicity_result.get('score', 0.0)
        
        btc_result = self._check_btc_correlation()
        layer12_score = btc_result.get('score', 0.0)
        
        # Calculate enhanced confidence (12 layers total!)
        confidence = 0.5
        confidence += layer1_score  # Max +0.40
        confidence += layer2_score  # Max +0.20
        confidence += layer3_score  # Max +0.15
        confidence += layer4_score  # Max +0.10
        confidence += layer5_score  # Max +0.10
        confidence += layer6_score  # Max +0.05
        confidence += layer8_score  # Max +0.25
        confidence += layer9_score  # Max +0.20
        confidence += layer10_score # Max +0.15
        confidence += layer11_score # Max +0.20
        confidence += layer12_score # Max +0.15
        
        # Layer 7: False positive filters (penalties)
        confidence = self._apply_layer7_filters(confidence, metrics, price)
        
        # Determine strategy based on enhanced confidence
        if confidence >= 0.95:
            strategy = 'ULTRA_PRECISE'
        elif confidence >= 0.90:
            strategy = 'CONSERVATIVE'
        elif confidence >= 0.85:
            strategy = 'BALANCED'
        elif confidence >= 0.75:
            strategy = 'AGGRESSIVE'
        else:
            return None  # Not confident enough
        
        # Count confirmed layers
        layers_confirmed = sum([
            layer1_score > 0, layer2_score > 0, layer3_score > 0,
            layer4_score > 0, layer5_score > 0, layer6_score > 0,
            layer8_score > 0, layer9_score > 0, layer10_score > 0,
            layer11_score > 0, layer12_score > 0
        ])
        
        # Build comprehensive reason (bidirectional)
        pattern_name = "V-bottom" if direction == 'LONG' else "V-top"
        reason = f"{pattern_name} ({strategy.lower()}): "
        reasons = []
        if layer1_score > 0.2: reasons.append("bid refill" if direction == 'LONG' else "ask refill")
        if layer2_score > 0.1: reasons.append("OFI flip")
        if layer3_score > 0.1: reasons.append("volume spike")
        if layer4_score > 0: reasons.append("MM return")
        if layer5_score > 0: reasons.append("wick")
        if layer8_score > 0:
            if cascade_result.get('pattern') == 'STRONG_CASCADE':
                reasons.append(f"CASCADE({cascade_result.get('cascade_size')})")
            else:
                reasons.append("cascade")
        if layer9_score > 0: reasons.append("pressure buildup")
        if layer10_score > 0: reasons.append("exhaustion")
        if layer11_score > 0: reasons.append("toxic flip")
        if layer12_score > 0: reasons.append("BTC lead")
        
        reason += ", ".join(reasons)
        
        # Calculate drop/rally percentage
        if direction == 'LONG':
            price_move_pct = ((self.selloff_start_price - self.capitulation_price) / self.selloff_start_price * 100) if self.selloff_start_price else 0
            base_price = self.capitulation_price
        else:  # SHORT
            price_move_pct = ((self.exhaustion_price - self.rally_start_price) / self.rally_start_price * 100) if self.rally_start_price else 0
            base_price = self.exhaustion_price
        
        return {
            'type': 'V_BOTTOM' if direction == 'LONG' else 'V_TOP',
            'direction': direction,
            'strategy': strategy,
            'confidence': min(confidence, 0.95),
            'reason': reason,
            'layers_confirmed': layers_confirmed,
            'capitulation_price': base_price,
            'price_move_pct': price_move_pct
        }
    
    def _check_layer1_orderbook(self, metrics: Dict) -> float:
        """Layer 1: Orderbook microstructure (40% weight)."""
        score = 0.0
        
        # 1.1 Bid refill detection
        if len(self.bid_depth_history) >= 2:
            current_bid = metrics.get('bid_depth_total', 0)
            prev_bid = self.bid_depth_history[-2]
            
            if prev_bid > 0:
                refill_pct = (current_bid - prev_bid) / prev_bid
                if refill_pct > self.BID_REFILL_THRESHOLD:
                    score += 0.15  # Strong bid refill
                elif refill_pct > 0.25:
                    score += 0.08  # Moderate bid refill
        
        # 1.2 Spread contraction
        if len(self.spread_history) >= 2:
            current_spread = metrics.get('spread_pct', 0)
            prev_spread = self.spread_history[-2]
            
            if prev_spread > 0 and current_spread < prev_spread * 0.7:
                score += 0.10  # Spread contracting
        
        # 1.3 Skew recovery
        if len(self.skew_history) >= 2:
            current_skew = metrics.get('skew', 0)
            if current_skew > -0.3:  # Recovering from extreme
                score += 0.05
        
        # 1.4 Ask consumption (simplified - check if asks decreasing)
        if len(self.ask_depth_history) >= 2:
            current_ask = metrics.get('ask_depth_total', 0)
            prev_ask = self.ask_depth_history[-2]
            
            if prev_ask > 0 and current_ask < prev_ask * 0.8:
                score += 0.10  # Asks being consumed
        
        return min(score, 0.40)
    
    def _check_layer2_ofi(self) -> float:
        """Layer 2: OFI flip (20% weight)."""
        # Simplified - would use actual OFI from orderbook analyzer
        # For now, use skew as proxy
        if len(self.skew_history) < 5:
            return 0.0
        
        recent_skew = list(self.skew_history)[-5:]
        min_skew = min(recent_skew)
        current_skew = recent_skew[-1]
        
        # OFI flip: was very negative, now recovering
        if min_skew < -0.7 and current_skew > min_skew * 0.5:
            return 0.20
        elif min_skew < -0.5 and current_skew > -0.2:
            return 0.10
        
        return 0.0
    
    def _check_layer3_volume(self) -> float:
        """Layer 3: Volume profile (15% weight)."""
        if len(self.volume_history) < 20:
            return 0.0
        
        recent_volume = sum(list(self.volume_history)[-10:])
        normal_volume = sum(list(self.volume_history)[-60:-10]) / 50 * 10
        
        # Volume spike during selloff
        if normal_volume > 0 and recent_volume > normal_volume * 2:
            return 0.15
        elif normal_volume > 0 and recent_volume > normal_volume * 1.5:
            return 0.08
        
        return 0.0
    
    def _check_layer4_mm(self, metrics: Dict) -> float:
        """Layer 4: Market maker behavior (10% weight)."""
        # Simplified - check if spread is tightening (MM confidence)
        if len(self.spread_history) >= 3:
            recent_spreads = list(self.spread_history)[-3:]
            if all(recent_spreads[i] > recent_spreads[i+1] for i in range(len(recent_spreads)-1)):
                return 0.10  # Spread consistently tightening
        
        return 0.0
    
    def _check_layer5_price(self, price: float) -> float:
        """Layer 5: Price action (10% weight)."""
        if not self.capitulation_price or len(self.price_history) < 5:
            return 0.0
        
        # Check for wick (price recovered from low)
        recent_low = min(list(self.price_history)[-5:])
        wick_size = (price - recent_low) / recent_low * 100
        
        if wick_size > 2.0:
            return 0.10
        elif wick_size > 1.0:
            return 0.05
        
        return 0.0
    
    def _check_layer6_timeframe(self, price: float) -> float:
        """Layer 6: Multi-timeframe support (5% weight)."""
        # Simplified - check if price is above capitulation
        if self.capitulation_price and price > self.capitulation_price * 1.005:
            return 0.05
        
        return 0.0
    
    def _apply_layer7_filters(self, confidence: float, metrics: Dict, price: float) -> float:
        """Layer 7: False positive filters (penalties)."""
        
        # Filter 1: Weak recovery (price not recovering enough)
        if self.capitulation_price:
            recovery_pct = (price - self.capitulation_price) / self.capitulation_price * 100
            if recovery_pct < 0.5:  # Less than 0.5% recovery
                confidence *= 0.80
        
        # Filter 2: Still high spread (lack of confidence)
        current_spread = metrics.get('spread_pct', 0)
        if current_spread > 0.15:  # Still > 0.15%
            confidence *= 0.85
        
        return confidence
    
    def _enter_reversal(self):
        """Enter REVERSAL state."""
        self.state = 'REVERSAL'
        logger.info(f"{self.symbol}: Entered REVERSAL state")
        
        # Reset after some time
        # (In practice, would reset after signal is consumed)
    
    def reset(self):
        """Reset tracker to NORMAL state."""
        self.state = 'NORMAL'
        self.selloff_start_price = None
        self.capitulation_price = None
        self.max_spread_seen = 0
        self.min_bid_depth_seen = float('inf')
    
    # ============================================
    # ENHANCEMENT METHODS (Precision Layers 8-12)
    # ============================================
    
    def _detect_liquidation_cascade(self) -> Dict:
        """
        Enhancement Layer 8: Liquidation cascade detection.
        
        Detects when liquidations trigger more liquidations (cascade effect).
        Strong capitulation signal.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.liquidation_history) < 3:
            return {'score': 0.0}
        
        recent_liqs = list(self.liquidation_history)[-5:]
        
        # Extract liquidation data
        try:
            sides = [liq.get('side') for liq in recent_liqs if 'side' in liq]
            sizes = [liq.get('value_usd', 0) for liq in recent_liqs if 'value_usd' in liq]
            timestamps = [liq.get('timestamp', 0) for liq in recent_liqs if 'timestamp' in liq]
            
            if len(sides) < 3 or len(sizes) < 3 or len(timestamps) < 3:
                return {'score': 0.0}
            
            # Check for cascade pattern
            # 1. All same side (panic in one direction)
            if len(set(sides)) == 1:
                # 2. Increasing size (snowball effect)
                size_increasing = sum(1 for i in range(len(sizes)-1) if sizes[i] < sizes[i+1])
                
                # 3. Rapid succession (< 5 seconds between)
                time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                rapid_succession = sum(1 for diff in time_diffs if diff < 5)
                
                # Strong cascade if both conditions met
                if size_increasing >= 2 and rapid_succession >= 2:
                    logger.info(f"{self.symbol}: STRONG CASCADE detected ({len(recent_liqs)} liquidations, ${sum(sizes):,.0f})")
                    return {
                        'score': 0.25,
                        'pattern': 'STRONG_CASCADE',
                        'cascade_size': len(recent_liqs),
                        'total_value': sum(sizes)
                    }
                elif size_increasing >= 1 or rapid_succession >= 1:
                    logger.info(f"{self.symbol}: Moderate cascade detected")
                    return {
                        'score': 0.15,
                        'pattern': 'MODERATE_CASCADE',
                        'cascade_size': len(recent_liqs)
                    }
            
            return {'score': 0.0}
            
        except Exception as e:
            logger.debug(f"Error detecting liquidation cascade: {e}")
            return {'score': 0.0}
    
    def _track_orderbook_pressure_buildup(self) -> Dict:
        """
        Enhancement Layer 9: Orderbook pressure buildup tracking.
        
        Tracks acceleration of bid refills (not just refill).
        Detects institutional buying.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.bid_depth_history) < 10:
            return {'score': 0.0}
        
        # Calculate pressure gradient (rate of change)
        bid_changes = []
        for i in range(1, len(self.bid_depth_history)):
            change = self.bid_depth_history[i] - self.bid_depth_history[i-1]
            bid_changes.append(change)
        
        if len(bid_changes) < 5:
            return {'score': 0.0}
        
        # Check for acceleration (gradient of gradient)
        recent_changes = bid_changes[-5:]
        
        # Accelerating bid refill (each change larger than previous)
        accelerating = sum(1 for i in range(len(recent_changes)-1) 
                          if recent_changes[i] > 0 and recent_changes[i+1] > recent_changes[i])
        
        if accelerating >= 3:
            logger.info(f"{self.symbol}: Accelerating bid refill detected")
            return {
                'score': 0.20,
                'pattern': 'ACCELERATING_BID_REFILL',
                'strength': recent_changes[-1] / (recent_changes[0] + 1)
            }
        elif accelerating >= 2:
            return {
                'score': 0.10,
                'pattern': 'MODERATE_BID_ACCELERATION'
            }
        
        return {'score': 0.0}
    
    def _analyze_volume_profile_shape(self) -> Dict:
        """
        Enhancement Layer 10: Volume profile microstructure.
        
        Analyzes volume distribution during selloff.
        Perfect V-bottom has volume spike at exact low, then declining.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.volume_history) < 30:
            return {'score': 0.0}
        
        volumes = list(self.volume_history)[-30:]
        
        # Find volume peak
        max_vol = max(volumes)
        peak_idx = volumes.index(max_vol)
        
        # Check if peak is recent (within last 10 ticks)
        if peak_idx > len(volumes) - 10:
            # Volume declining after peak (exhaustion)
            post_peak = volumes[peak_idx:]
            
            if len(post_peak) >= 3:
                # Check if declining
                declining = sum(1 for i in range(len(post_peak)-1) 
                               if post_peak[i] > post_peak[i+1])
                
                if declining >= len(post_peak) - 1:  # All declining
                    logger.info(f"{self.symbol}: Volume exhaustion detected")
                    return {
                        'score': 0.15,
                        'pattern': 'CAPITULATION_EXHAUSTION',
                        'peak_volume': max_vol,
                        'decline_rate': (post_peak[0] - post_peak[-1]) / (post_peak[0] + 1)
                    }
                elif declining >= (len(post_peak) - 1) // 2:  # Mostly declining
                    return {
                        'score': 0.08,
                        'pattern': 'MODERATE_EXHAUSTION'
                    }
        
        return {'score': 0.0}
    
    def _detect_toxicity_flip(self) -> Dict:
        """
        Enhancement Layer 11: Toxicity flip detection.
        
        Detects when toxic (informed) flow reverses direction.
        Informed traders reversing = strong signal.
        
        Returns:
            Dict with score and pattern info
        """
        if len(self.toxicity_history) < 2:
            return {'score': 0.0}
        
        try:
            current_tox = self.toxicity_history[-1]
            
            if not current_tox or 'signal' not in current_tox:
                return {'score': 0.0}
            
            signal = current_tox.get('signal', {})
            
            # During CAPITULATION state, look for toxic buying
            if self.state == 'CAPITULATION':
                toxic_signal = signal.get('signal', '')
                
                if 'TOXIC_BUYING' in toxic_signal:
                    # Strong toxic buying during capitulation
                    avg_toxicity = signal.get('avg_toxicity', 0)
                    
                    if avg_toxicity > 0.7:
                        logger.info(f"{self.symbol}: Strong toxic buying detected")
                        return {
                            'score': 0.20,
                            'pattern': 'STRONG_TOXIC_BUYING',
                            'toxicity': avg_toxicity
                        }
                    elif avg_toxicity > 0.5:
                        return {
                            'score': 0.10,
                            'pattern': 'MODERATE_TOXIC_BUYING',
                            'toxicity': avg_toxicity
                        }
            
            return {'score': 0.0}
            
        except Exception as e:
            logger.debug(f"Error detecting toxicity flip: {e}")
            return {'score': 0.0}
    
    def _check_btc_correlation(self) -> Dict:
        """
        Enhancement Layer 12: BTC correlation.
        
        Uses BTC as leading indicator for ETH/SOL.
        If BTC reversed first, ETH/SOL likely to follow.
        
        Returns:
            Dict with score and pattern info
        """
        # Only applies to ETH/SOL
        if self.symbol not in ['ETHUSDT', 'SOLUSDT']:
            return {'score': 0.0}
        
        # Check if BTC is in REVERSAL state
        if self.btc_state == 'REVERSAL' and self.state == 'CAPITULATION':
            logger.info(f"{self.symbol}: BTC leading reversal detected")
            return {
                'score': 0.15,
                'pattern': 'BTC_LEADING_REVERSAL'
            }
        elif self.btc_state == 'CAPITULATION' and self.state == 'CAPITULATION':
            return {
                'score': 0.08,
                'pattern': 'BTC_CORRELATED_CAPITULATION'
            }
        
        return {'score': 0.0}
    
    def set_btc_state(self, btc_state: str):

        """Set BTC state for correlation analysis."""
        self.btc_state = btc_state
    
    def get_state(self) -> Dict:
        """Get current tracker state."""
        return {
            'symbol': self.symbol,
            'state': self.state,
            'time_in_state': time.time() - self.state_entry_time,
            'selloff_start_price': self.selloff_start_price,
            'capitulation_price': self.capitulation_price
        }


if __name__ == "__main__":
    """Test V-bottom tracker."""
    
    logging.basicConfig(level=logging.INFO)
    
    tracker = VBottomTracker('BTCUSDT')
    
    print("=" * 60)
    print("V-BOTTOM TRACKER TEST")
    print("=" * 60)
    
    # Simulate selloff
    print("\n1. Simulating SELLOFF...")
    for i in range(10):
        orderbook = {
            'bids': [[100000 - i*100, 1.0 - i*0.05] for _ in range(20)],
            'asks': [[100100 - i*100, 5.0] for _ in range(20)]
        }
        price = 100000 - i*100
        tracker.update(orderbook, price, volume=100)
        time.sleep(0.1)
    
    print(f"State: {tracker.get_state()}")
    
    # Simulate capitulation
    print("\n2. Simulating CAPITULATION...")
    for i in range(5):
        orderbook = {
            'bids': [[99000, 0.2], [98900, 0.1]] + [[98800 - i*10, 0.1] for _ in range(18)],
            'asks': [[99500, 50.0]] + [[99600 + i*10, 20.0] for _ in range(19)]
        }
        price = 99000 - i*50
        tracker.update(orderbook, price, volume=500)
        time.sleep(0.1)
    
    print(f"State: {tracker.get_state()}")
    
    # Simulate reversal
    print("\n3. Simulating REVERSAL...")
    for i in range(10):
        orderbook = {
            'bids': [[98800 + i*50, 5.0 + i*0.5] for _ in range(20)],
            'asks': [[98900 + i*50, 2.0 - i*0.1] for _ in range(20)]
        }
        price = 98800 + i*50
        signal = tracker.update(orderbook, price, volume=200)
        
        if signal:
            print(f"\n🎯 SIGNAL GENERATED!")
            print(f"Strategy: {signal['strategy']}")
            print(f"Confidence: {signal['confidence']:.0%}")
            print(f"Reason: {signal['reason']}")
            print(f"Layers Confirmed: {signal['layers_confirmed']}/6")
            print(f"Drop: {signal['drop_pct']:.1f}%")
            break
        
        time.sleep(0.1)
