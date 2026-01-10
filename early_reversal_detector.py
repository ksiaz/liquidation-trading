"""
Early Reversal Detection System

Detects orderbook preparation signals BEFORE price reversal completes.
Uses scaling exit: 50% at 0.5%, 50% runner until pivot.

Key Innovation: Don't wait for sharp move + recovery (lag).
Instead: Detect preparation and enter early (no lag).
"""

import logging
from collections import deque
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class EarlyReversalDetector:
    """
    Detect reversals early using orderbook preparation signals.
    Uses MULTI-TIMEFRAME analysis to adapt to changing conditions.
    Target: 0.5-1% profit with 75%+ win rate.
    """
    
    def __init__(self, max_lookback_seconds: int = 300, 
                 predictor=None, impact_calc=None, snr_threshold: float = 0.15):
        """
        Initialize with maximum lookback (keeps all data).
        We'll analyze multiple timeframes simultaneously.
        
        Args:
            max_lookback_seconds: Maximum history to keep
            predictor: Optional LiquidationPredictor for funding rate
            impact_calc: Optional MarketImpactCalculator for liquidity asymmetry
            snr_threshold: Minimum signal-to-noise ratio (default 0.15, was 0.3)
        """
        self.max_lookback_seconds = max_lookback_seconds
        
        # Tier 1 enrichment (optional)
        self.predictor = predictor
        self.impact_calc = impact_calc
        
        # History buffers (keep 5 minutes of data)
        self.price_history = deque(maxlen=max_lookback_seconds)
        self.imbalance_history = deque(maxlen=max_lookback_seconds)
        self.bid_depth_history = deque(maxlen=max_lookback_seconds)
        self.ask_depth_history = deque(maxlen=max_lookback_seconds)
        self.spread_history = deque(maxlen=max_lookback_seconds)
        self.volume_history = deque(maxlen=max_lookback_seconds)
        self.timestamp_history = deque(maxlen=max_lookback_seconds)
        
        # Multi-timeframe windows (in seconds)
        self.timeframes = [10, 30, 60, 120, 180]  # 10s, 30s, 1m, 2m, 3m
        
        # Adaptive thresholds (FIXED: raised from permissive defaults)
        self.min_signals_required = 3  # Need 3+ signals for entry (was 2)
        self.snr_threshold = max(snr_threshold, 1.0)  # Force minimum 1.0 SNR (was 0.15)
        
        # Cache for API calls (to avoid repeated calls)
        self.last_funding_check = 0
        self.cached_funding_rate = None
        self.symbol = None  # Will be set from orderbook data
        
        # Signal consolidation
        self.last_signal_time = 0
        self.last_signal_direction = None
        self.last_signal_price = 0
        self.signal_cooldown = 60  # 60 seconds cooldown for same setup
        
        # Wave Trend Analyzer (Regime Filter)
        # 0.1% threshold for swings, enough to catch micro-structure
        self.wave_analyzer = WaveTrendAnalyzer(price_change_threshold=0.001)
        
    def _is_choppy_market(self) -> bool:
        """
        Detect if market is choppy (range-bound) vs trending.
        Returns True if choppy (should skip trading).
        
        ZERO-LAG APPROACH using orderbook microstructure:
        - Imbalance persistence (trending = sustained imbalance)
        - Liquidity symmetry (choppy = walls on both sides)
        - Price volatility context (avoid false positives in low-vol)
        """
        if len(self.price_history) < 60:  # Need at least 1 minute of data
            return False
        
        # Get recent data (last 60 seconds)
        recent_prices = list(self.price_history)[-60:]
        recent_imbalances = list(self.imbalance_history)[-60:]
        recent_bid_depth = list(self.bid_depth_history)[-60:]
        recent_ask_depth = list(self.ask_depth_history)[-60:]
        
        # ========== METRIC 1: IMBALANCE PERSISTENCE ==========
        # Trending: Imbalance stays on one side (persistent)
        # Choppy: Imbalance flips back and forth (no persistence)
        
        sign_changes = 0
        for i in range(1, len(recent_imbalances)):
            if (recent_imbalances[i] > 0) != (recent_imbalances[i-1] > 0):
                sign_changes += 1
        
        # Normalize: 0 changes = 100% persistence, 60 changes = 0% persistence
        imbalance_persistence = 1.0 - (sign_changes / 60.0)
        
        # ========== METRIC 2: LIQUIDITY SYMMETRY ==========
        # Trending: Imbalanced liquidity (thin on one side)
        # Choppy: Symmetric liquidity (walls on both sides)
        
        avg_bid_depth = sum(recent_bid_depth) / len(recent_bid_depth)
        avg_ask_depth = sum(recent_ask_depth) / len(recent_ask_depth)
        
        if avg_bid_depth > 0 and avg_ask_depth > 0:
            # Symmetry: 1.0 = perfectly balanced, 0.0 = completely imbalanced
            liquidity_symmetry = min(avg_bid_depth, avg_ask_depth) / max(avg_bid_depth, avg_ask_depth)
        else:
            liquidity_symmetry = 0.5  # Default to neutral
        
        # ========== METRIC 3: PRICE MOVEMENT CONTEXT ==========
        # Avoid false positives during low-volatility stable periods
        
        total_range = max(recent_prices) - min(recent_prices)
        directional_move = abs(recent_prices[-1] - recent_prices[0])
        
        # If price barely moving at all, don't call it choppy - just stable
        if total_range < 0.0001:  # Less than 0.01% range
            return False  # Let SNR filter handle quality
        
        # Calculate range efficiency (directional move / total range)
        range_efficiency = directional_move / total_range if total_range > 0 else 1.0
        
        # ========== DECISION LOGIC ==========
        # Choppy if ANY TWO of these conditions are met:
        # VERSION 2 PARAMETERS (Best Performance: 76 trades, 55.3% win, +1.408% P&L):
        # 1. Low imbalance persistence (< 0.6 = flipping frequently)
        # 2. High liquidity symmetry (> 0.6 = balanced walls)
        # 3. Low range efficiency (< 0.5 = lots of back-and-forth)
        
        choppy_signals = 0
        
        if imbalance_persistence < 0.6:  # Imbalance flipping
            choppy_signals += 1
        
        if liquidity_symmetry > 0.6:  # Balanced liquidity
            choppy_signals += 1
        
        if range_efficiency < 0.5:  # Price chopping
            choppy_signals += 1
        
        is_choppy = choppy_signals >= 2  # Need 2 out of 3 conditions
        
        if is_choppy:
            logger.debug(
                f"Choppy market detected ({choppy_signals}/3 conditions): "
                f"imb_persist={imbalance_persistence:.2f}, "
                f"liq_sym={liquidity_symmetry:.2f}, "
                f"range_eff={range_efficiency:.2f}"
            )
            return True
        
        # All checks passed - market is trending
        return False
    
    def update(self, orderbook_data: Dict) -> Optional[Dict]:
        """
        Update with new orderbook data and check for reversal signals.
        Analyzes MULTIPLE timeframes simultaneously.
        
        Returns signal dict if reversal preparation detected, None otherwise.
        """
        # Extract data
        price = (orderbook_data['best_bid'] + orderbook_data['best_ask']) / 2
        imbalance = orderbook_data['imbalance']
        bid_depth = orderbook_data['bid_volume_10']
        ask_depth = orderbook_data['ask_volume_10']
        spread = orderbook_data['spread_pct']
        volume = bid_depth + ask_depth  # Total volume as proxy
        
        # Cache symbol for API calls
        if 'symbol' in orderbook_data and not self.symbol:
            self.symbol = orderbook_data['symbol']
        
        # Update histories
        self.price_history.append(price)
        self.imbalance_history.append(imbalance)
        self.bid_depth_history.append(bid_depth)
        self.ask_depth_history.append(ask_depth)
        self.spread_history.append(spread)
        self.volume_history.append(volume)
        self.timestamp_history.append(orderbook_data.get('timestamp', datetime.now()))
        
        # Need minimum data
        if len(self.price_history) < 30:
            return None
        
        # Update Wave Analyzer
        timestamp = orderbook_data.get('timestamp', datetime.now())
        wave_state = self.wave_analyzer.update(price, volume, timestamp)
        
        # Analyze ALL timeframes and pick best signal
        best_signal = None
        best_snr = 0
        
        for tf in self.timeframes:
            if len(self.price_history) >= tf:
                signal = self._detect_reversal_at_timeframe(tf)
                
                # Check against Wave Trend (Counter-trend filtering)
                if signal:
                    slope_bias = wave_state['bias'] if wave_state else 'NEUTRAL'
                    
                    # If trying to go LONG
                    if signal['direction'] == 'LONG':
                        # If bias is BEARISH (Counter-trend), need huge confirmation
                        if slope_bias == 'BEARISH':
                             if signal['confidence'] < 90 or signal['snr'] < 2.0:  # FIXED: AND -> OR
                                logger.debug(f"Signal rejected by WaveTrend: LONG but bias {slope_bias}")
                                continue
                        # If bias is NEUTRAL (Breakout?), permissive
                        # (Allow normal thresholds to applying)
                            
                    # If trying to go SHORT
                    if signal['direction'] == 'SHORT':
                        # If bias is BULLISH (Counter-trend), need huge confirmation
                        if slope_bias == 'BULLISH':
                             if signal['confidence'] < 90 or signal['snr'] < 2.0:  # FIXED: AND -> OR
                                logger.debug(f"Signal rejected by WaveTrend: SHORT but bias {slope_bias}")
                                continue
                        # If bias is NEUTRAL (Breakout?), permissive
                            
                    if signal and signal.get('snr', 0) > best_snr:
                        best_signal = signal
                        best_snr = signal['snr']
        
        # Check signal consolidation (prevent spam)
        if best_signal:
            # CHOP FILTER: Check market conditions (FIXED: removed bypass loophole)
            if self._is_choppy_market():
                logger.debug(f"Signal rejected by CHOP filter (market is choppy)")
                return None
            
            # Check cooldown
            if self._should_suppress_signal(best_signal):
                # Don't log cooldown rejections as they spam
                return None
                
            # Update last signal info
            self.last_signal_time = best_signal['timestamp'].timestamp()
            self.last_signal_direction = best_signal['direction']
            self.last_signal_price = best_signal['entry_price']
            
        return best_signal
        
    def _should_suppress_signal(self, signal: Dict) -> bool:
        """
        Check if signal should be suppressed (duplicate/spam).
        Returns True if signal should be skipped.
        """
        current_time = signal['timestamp'].timestamp()
        
        # 1. Minimum cooldown
        if current_time - self.last_signal_time < self.signal_cooldown:
            # Same direction?
            if signal['direction'] == self.last_signal_direction:
                # Same price area? (within 0.1%)
                price_diff_pct = abs(signal['entry_price'] - self.last_signal_price) / self.last_signal_price
                if price_diff_pct < 0.001:
                    return True
        
        return False
    
    def _detect_reversal_at_timeframe(self, timeframe_seconds: int) -> Optional[Dict]:
        """
        Detect reversal signals at a specific timeframe.
        Returns signal with SNR (signal-to-noise ratio) for quality assessment.
        """
        # Get data for this timeframe
        data_points = min(timeframe_seconds, len(self.price_history))
        
        # Split into "before" (earlier 2/3) and "after" (recent 1/3)
        split_point = int(data_points * 2 / 3)
        
        # Price direction (from earlier data)
        earlier_prices = list(self.price_history)[-data_points:-split_point] if split_point > 0 else []
        recent_prices = list(self.price_history)[-split_point:]
        
        if len(earlier_prices) < 5 or len(recent_prices) < 5:
            return None
        
        earlier_avg = sum(earlier_prices) / len(earlier_prices)
        recent_avg = sum(recent_prices) / len(recent_prices)
        
        price_change_pct = (recent_avg - earlier_avg) / earlier_avg
        
        # Determine price direction (FIXED: raised from 0.05% to 0.2%)
        if price_change_pct > 0.002:  # 0.2% threshold (was 0.05%)
            price_direction = 'UP'
        elif price_change_pct < -0.002:
            price_direction = 'DOWN'
        else:
            price_direction = 'FLAT'
        
        if price_direction == 'FLAT':
            return None
        
        # Check preparation signals with SNR calculation
        signals = {}
        signal_strengths = {}
        
        # Signal 1: Imbalance divergence
        imb_signal, imb_snr = self._check_imbalance_divergence_with_snr(
            price_direction, data_points, split_point
        )
        signals['imbalance_divergence'] = imb_signal
        signal_strengths['imbalance_divergence'] = imb_snr
        
        # Signal 2: Depth building
        depth_signal, depth_snr = self._check_depth_building_with_snr(
            price_direction, data_points, split_point
        )
        signals['depth_building'] = depth_signal
        signal_strengths['depth_building'] = depth_snr
        
        # Signal 3: Spread contraction
        spread_signal, spread_snr = self._check_spread_contraction_with_snr(
            data_points, split_point
        )
        signals['spread_contraction'] = spread_signal
        signal_strengths['spread_contraction'] = spread_snr
        
        # Signal 4: Volume exhaustion
        vol_signal, vol_snr = self._check_volume_exhaustion_with_snr(
            price_direction, data_points, split_point
        )
        signals['volume_exhaustion'] = vol_signal
        signal_strengths['volume_exhaustion'] = vol_snr
        
        # Determine trade direction (opposite of price move) - needed for Tier 1
        trade_direction = 'LONG' if price_direction == 'DOWN' else 'SHORT'
        
        # ========== TIER 1 ENRICHMENT ==========
        
        # Signal 5: Funding divergence (if predictor available)
        if self.predictor and self.symbol:
            funding_signal, funding_snr = self._check_funding_divergence_with_snr(
                price_direction
            )
            signals['funding_divergence'] = funding_signal
            signal_strengths['funding_divergence'] = funding_snr
        
        # Signal 6: Liquidity confirmation (if impact_calc available)
        if self.impact_calc and self.symbol:
            liq_signal, liq_snr = self._check_liquidity_confirmation_with_snr(
                trade_direction
            )
            signals['liquidity_confirmation'] = liq_signal
            signal_strengths['liquidity_confirmation'] = liq_snr
        
        # Count confirmed signals
        confirmed_signals = sum(signals.values())
        
        # Calculate overall SNR (average of active signals)
        active_snrs = [snr for sig, snr in signal_strengths.items() if signals[sig]]
        overall_snr = sum(active_snrs) / len(active_snrs) if active_snrs else 0
        
        # Need minimum signals AND good SNR
        if confirmed_signals < self.min_signals_required or overall_snr < self.snr_threshold:
            return None
        
        # Calculate confidence
        confidence = min(confirmed_signals * 25 + int(overall_snr * 20), 100)
        
        logger.info(f"Early reversal detected at {timeframe_seconds}s timeframe: "
                   f"{trade_direction} with {confirmed_signals} signals (SNR: {overall_snr:.2f})")
        
        return {
            'type': 'EARLY_REVERSAL',
            'direction': trade_direction,
            'confidence': confidence,
            'entry_price': self.price_history[-1],
            'signals': signals,
            'signals_confirmed': confirmed_signals,
            'timestamp': self.timestamp_history[-1],
            'timeframe': timeframe_seconds,
            'snr': overall_snr,  # Signal-to-noise ratio
            'signal_strengths': signal_strengths
        }
    
    def _get_price_direction(self) -> str:
        """Determine if price is moving up, down, or flat."""
        if len(self.price_history) < 10:
            return 'FLAT'
        
        # Compare recent prices to earlier prices
        recent_avg = sum(list(self.price_history)[-10:]) / 10
        earlier_avg = sum(list(self.price_history)[-30:-20]) / 10
        
        change_pct = (recent_avg - earlier_avg) / earlier_avg
        
        if change_pct > 0.001:  # 0.1% threshold
            return 'UP'
        elif change_pct < -0.001:
            return 'DOWN'
        else:
            return 'FLAT'
    
    def _check_imbalance_divergence(self, price_direction: str) -> bool:
        """
        Check if imbalance is diverging from price direction.
        Price down but imbalance improving = bullish divergence.
        Price up but imbalance weakening = bearish divergence.
        """
        if len(self.imbalance_history) < 20:
            return False
        
        # Get recent and earlier imbalance
        recent_imb = list(self.imbalance_history)[-10:]
        earlier_imb = list(self.imbalance_history)[-30:-20]
        
        recent_avg = sum(recent_imb) / len(recent_imb)
        earlier_avg = sum(earlier_imb) / len(earlier_imb)
        
        imb_change = recent_avg - earlier_avg
        
        if price_direction == 'DOWN':
            # Price falling, but imbalance improving (getting less negative)
            return imb_change > 0.1
        elif price_direction == 'UP':
            # Price rising, but imbalance weakening (getting less positive)
            return imb_change < -0.1
        
        return False
    
    def _check_depth_building(self, price_direction: str) -> bool:
        """
        Check if depth is building on the opposite side.
        Price down but bids building = accumulation.
        Price up but asks building = distribution.
        """
        if len(self.bid_depth_history) < 20:
            return False
        
        # Get recent and earlier depth
        recent_bids = list(self.bid_depth_history)[-10:]
        earlier_bids = list(self.bid_depth_history)[-30:-20]
        recent_asks = list(self.ask_depth_history)[-10:]
        earlier_asks = list(self.ask_depth_history)[-30:-20]
        
        bid_growth = (sum(recent_bids) / len(recent_bids)) / (sum(earlier_bids) / len(earlier_bids))
        ask_growth = (sum(recent_asks) / len(recent_asks)) / (sum(earlier_asks) / len(earlier_asks))
        
        if price_direction == 'DOWN':
            # Price falling, but bids building (smart money accumulating)
            return bid_growth > 1.15  # 15% increase
        elif price_direction == 'UP':
            # Price rising, but asks building (smart money distributing)
            return ask_growth > 1.15
        
        return False
    
    def _check_spread_contraction(self) -> bool:
        """
        Check if spread is contracting (liquidity returning).
        Tightening spread = market makers returning = reversal near.
        """
        if len(self.spread_history) < 20:
            return False
        
        recent_spread = sum(list(self.spread_history)[-10:]) / 10
        earlier_spread = sum(list(self.spread_history)[-30:-20]) / 10
        
        # Spread contracting by 20%+
        return recent_spread < earlier_spread * 0.8
    
    def _check_volume_exhaustion(self, price_direction: str) -> bool:
        """
        Check if volume is declining (momentum fading).
        Declining volume = move exhausting = reversal near.
        """
        if len(self.volume_history) < 20:
            return False
        
        recent_vol = sum(list(self.volume_history)[-10:]) / 10
        earlier_vol = sum(list(self.volume_history)[-30:-20]) / 10
        
        # Volume declining by 20%+
        return recent_vol < earlier_vol * 0.8
    
    # ========== SNR-BASED METHODS (Multi-timeframe) ==========
    
    def _check_imbalance_divergence_with_snr(self, price_direction: str, 
                                              data_points: int, split_point: int) -> tuple:
        """
        Check imbalance divergence with SNR calculation.
        Returns (signal_detected: bool, snr: float)
        """
        import numpy as np
        
        # Get data for this timeframe
        imb_data = list(self.imbalance_history)[-data_points:]
        
        if len(imb_data) < data_points:
            return (False, 0.0)
        
        # Split into earlier and recent
        earlier_imb = imb_data[:split_point]
        recent_imb = imb_data[split_point:]
        
        if len(earlier_imb) < 5 or len(recent_imb) < 5:
            return (False, 0.0)
        
        # Calculate averages
        earlier_avg = np.mean(earlier_imb)
        recent_avg = np.mean(recent_imb)
        
        # Calculate flip (signal)
        flip = recent_avg - earlier_avg
        
        # Calculate noise (std dev)
        noise = (np.std(earlier_imb) + np.std(recent_imb)) / 2
        
        # Calculate SNR
        snr = abs(flip) / noise if noise > 0 else 0
        
        # Check for divergence
        # For price DOWN → expect BIDS to improve (divergence)
        # FIXED: raised from 0.15 to 0.30 (30% improvement required)
        if price_direction == 'DOWN':
            if flip > 0.30:  # Imbalance improved (was 0.15)
                return (True, snr)
        
        # For price UP → expect ASKS to improve (divergence)
        # FIXED: raised from 0.15 to 0.30
        elif price_direction == 'UP':
            if flip < -0.30:  # Imbalance weakening (was -0.15)
                return (True, snr)
        else:
            signal = False
        
        return (signal, snr)
    
    def _check_depth_building_with_snr(self, price_direction: str,
                                        data_points: int, split_point: int) -> tuple:
        """
        Check depth building with SNR calculation.
        Returns (signal_detected: bool, snr: float)
        """
        import numpy as np
        
        # Get data
        bid_data = list(self.bid_depth_history)[-data_points:]
        ask_data = list(self.ask_depth_history)[-data_points:]
        
        if len(bid_data) < data_points or len(ask_data) < data_points:
            return (False, 0.0)
        
        # Split
        earlier_bids = bid_data[:split_point]
        recent_bids = bid_data[split_point:]
        earlier_asks = ask_data[:split_point]
        recent_asks = ask_data[split_point:]
        
        if len(earlier_bids) < 5 or len(recent_bids) < 5:
            return (False, 0.0)
        
        # Calculate growth
        bid_earlier_avg = np.mean(earlier_bids)
        bid_recent_avg = np.mean(recent_bids)
        ask_earlier_avg = np.mean(earlier_asks)
        ask_recent_avg = np.mean(recent_asks)
        
        bid_growth = (bid_recent_avg / bid_earlier_avg - 1) if bid_earlier_avg > 0 else 0
        ask_growth = (ask_recent_avg / ask_earlier_avg - 1) if ask_earlier_avg > 0 else 0
        
        # Calculate noise
        bid_noise = (np.std(earlier_bids) + np.std(recent_bids)) / 2
        ask_noise = (np.std(earlier_asks) + np.std(recent_asks)) / 2
        
        # Calculate SNR
        bid_snr = abs(bid_growth * bid_earlier_avg) / bid_noise if bid_noise > 0 else 0
        ask_snr = abs(ask_growth * ask_earlier_avg) / ask_noise if ask_noise > 0 else 0
        
        # Check for building
        # For price DOWN → expect BIDS to grow (accumulation)
        # FIXED: raised from 1.15 to 1.30 (30% growth required)
        if price_direction == 'DOWN':
            if bid_growth > 1.30:  # Bids grew 30%+ (was 1.15)
                return (True, bid_snr)
        
        # For price UP → expect ASKS to grow (distribution)
        # FIXED: raised from 1.15 to 1.30
        elif price_direction == 'UP':
            if ask_growth > 1.30:  # Asks grew 30%+ (was 1.15)
                return (True, ask_snr)
        else:
            signal = False
            snr = 0.0
        
        return (signal, snr)
    
    def _check_spread_contraction_with_snr(self, data_points: int, split_point: int) -> tuple:
        """
        Check spread contraction with SNR calculation.
        Returns (signal_detected: bool, snr: float)
        """
        import numpy as np
        
        # Get data
        spread_data = list(self.spread_history)[-data_points:]
        
        if len(spread_data) < data_points:
            return (False, 0.0)
        
        # Split
        earlier_spread = spread_data[:split_point]
        recent_spread = spread_data[split_point:]
        
        if len(earlier_spread) < 5 or len(recent_spread) < 5:
            return (False, 0.0)
        
        # Calculate averages
        earlier_avg = np.mean(earlier_spread)
        recent_avg = np.mean(recent_spread)
        
        # Calculate contraction
        contraction = (earlier_avg - recent_avg) / earlier_avg if earlier_avg > 0 else 0
        
        # Calculate noise
        noise = (np.std(earlier_spread) + np.std(recent_spread)) / 2
        
        # Calculate SNR
        snr = abs(contraction * earlier_avg) / noise if noise > 0 else 0
        # Spread tightening = liquidity returning
        # FIXED: raised from 0.2 to 0.35 (35% contraction required)
        if contraction > 0.35:  # 35% contraction (was 0.2)
            return (True, snr)
        
        return (False, snr)
    
    def _check_volume_exhaustion_with_snr(self, price_direction: str,
                                           data_points: int, split_point: int) -> tuple:
        """
        Check volume exhaustion with SNR calculation.
        Returns (signal_detected: bool, snr: float)
        """
        import numpy as np
        
        # Get data
        vol_data = list(self.volume_history)[-data_points:]
        
        if len(vol_data) < data_points:
            return (False, 0.0)
        
        # Split
        earlier_vol = vol_data[:split_point]
        recent_vol = vol_data[split_point:]
        
        if len(earlier_vol) < 5 or len(recent_vol) < 5:
            return (False, 0.0)
        
        # Calculate averages
        earlier_avg = np.mean(earlier_vol)
        recent_avg = np.mean(recent_vol)
        
        # Calculate decline
        decline = (earlier_avg - recent_avg) / earlier_avg if earlier_avg > 0 else 0
        
        # Calculate noise
        noise = (np.std(earlier_vol) + np.std(recent_vol)) / 2
        
        # Calculate SNR
        snr = abs(decline * earlier_avg) / noise if noise > 0 else 0
        
        # Volume declining = momentum fading
        # FIXED: raised from 0.2 to 0.35 (35% decline required)
        if decline > 0.35:  # 35% decline (was 0.2)
            return (True, snr)
        
        return (False, snr)
    
    def _check_funding_divergence_with_snr(self, price_direction: str) -> tuple:
        """
        Check if funding rate diverges from price direction.
        Returns (signal_detected: bool, snr: float)
        
        Funding rate shows market sentiment:
        - Positive = longs paying shorts (too many longs)
        - Negative = shorts paying longs (too many shorts)
        """
        import time
        
        # Cache funding rate (only check every 60 seconds)
        current_time = time.time()
        if current_time - self.last_funding_check < 60:
            if self.cached_funding_rate is None:
                return (False, 0.0)
            funding_rate = self.cached_funding_rate
        else:
            try:
                funding_rate = self.predictor.get_funding_rate(self.symbol)
                self.cached_funding_rate = funding_rate
                self.last_funding_check = current_time
            except Exception as e:
                logger.warning(f"Failed to get funding rate: {e}")
                return (False, 0.0)
        
        if funding_rate is None:
            return (False, 0.0)
        
        # Calculate SNR based on funding rate magnitude
        # Typical funding: -0.0005 to +0.0005 (0.05%)
        # Extreme funding: > 0.001 (0.1%)
        snr = abs(funding_rate) / 0.0005  # Normalize to typical range
        
        # Check for divergence
        signal = False
        
        if price_direction == 'UP' and funding_rate > 0.0003:
            # Price rising, longs overextended → bearish divergence
            signal = True
        elif price_direction == 'DOWN' and funding_rate < -0.0003:
            # Price falling, shorts overextended → bullish divergence
            signal = True
        
        return (signal, snr)
    
    def _check_liquidity_confirmation_with_snr(self, trade_direction: str) -> tuple:
        """
        Check if liquidity asymmetry confirms trade direction.
        Returns (signal_detected: bool, snr: float)
        
        If easier to move in trade direction = confirmation
        """
        try:
            # Calculate impact for 0.25% move
            impact = self.impact_calc.calculate_impact_for_move(self.symbol, 0.25)
            
            if 'error' in impact:
                return (False, 0.0)
            
            # Get asymmetry
            asymmetry = impact['liquidity_asymmetry']
            
            # Determine easier direction
            easier_down = impact['value_down_usd'] < impact['value_up_usd']
            
            # Calculate SNR from asymmetry
            # Asymmetry > 0.3 = significant imbalance
            snr = asymmetry / 0.3
            
            # Check confirmation
            signal = False
            
            if trade_direction == 'SHORT' and easier_down and asymmetry > 0.2:
                # Easier to move down confirms SHORT
                signal = True
            elif trade_direction == 'LONG' and not easier_down and asymmetry > 0.2:
                # Easier to move up confirms LONG
                signal = True
            
            return (signal, snr)
            
        except Exception as e:
            logger.warning(f"Failed to check liquidity: {e}")
            return (False, 0.0)




        return (signal, snr)


class WaveTrendAnalyzer:
    """
    Analyzes price waves to determine trend strength and volume support.
    Used to filter out weak counter-trend signals.
    """
    
    def __init__(self, price_change_threshold=0.001):
        """
        Args:
            price_change_threshold: Min change (0.1%) to confirm a new wave
        """
        self.threshold = price_change_threshold
        
        # Wave tracking
        self.current_wave_type = None  # 'UP' or 'DOWN'
        self.wave_start_price = None
        self.wave_start_time = None
        self.current_extreme_price = None
        
        self.current_wave_volume = 0
        self.current_wave_count = 0
        
        # History
        self.completed_waves = deque(maxlen=10) # Store last 10 waves
        
    def update(self, price: float, volume: float, timestamp):
        """
        Update with new price/volume data.
        Returns trend state dict if wave completes.
        """
        if self.current_wave_type is None:
            # Initialize
            self.current_wave_type = 'FLAT'
            self.wave_start_price = price
            self.current_extreme_price = price
            self.wave_start_time = timestamp
            return None
            
        # Update current accumulator
        self.current_wave_volume += volume
        self.current_wave_count += 1
        
        # Check for reversal (New Wave)
        if self.current_wave_type == 'UP':
            # We are in UP wave, look for drop from high
            if price > self.current_extreme_price:
                self.current_extreme_price = price
            
            # Reversal criteria: Drop from high > threshold
            drop_pct = (self.current_extreme_price - price) / self.current_extreme_price
            if drop_pct > self.threshold:
                self._complete_wave(timestamp)
                self._start_new_wave('DOWN', self.current_extreme_price, timestamp)
                
        elif self.current_wave_type == 'DOWN':
            # We are in DOWN wave, look for rise from low
            if price < self.current_extreme_price:
                self.current_extreme_price = price
                
            # Reversal criteria: Rise from low > threshold
            rise_pct = (price - self.current_extreme_price) / self.current_extreme_price
            if rise_pct > self.threshold:
                self._complete_wave(timestamp)
                self._start_new_wave('UP', self.current_extreme_price, timestamp)
                
        else: # FLAT
            change = (price - self.wave_start_price) / self.wave_start_price
            if change > self.threshold:
                self._start_new_wave('UP', self.wave_start_price, timestamp)
            elif change < -self.threshold:
                self._start_new_wave('DOWN', self.wave_start_price, timestamp)
                
        return self.get_trend_state()
        
    def _complete_wave(self, timestamp):
        """Store completed wave"""
        duration = (timestamp - self.wave_start_time).total_seconds() \
                   if isinstance(timestamp, datetime) else 0
                   
        wave = {
            'type': self.current_wave_type,
            'start_price': self.wave_start_price,
            'end_price': self.current_extreme_price,
            'price_change': abs(self.current_extreme_price - self.wave_start_price),
            'total_volume': self.current_wave_volume,
            'avg_volume': self.current_wave_volume / max(self.current_wave_count, 1),
            'duration': duration
        }
        self.completed_waves.append(wave)
        
    def _start_new_wave(self, direction, start_price, timestamp):
        """Start tracking new wave"""
        self.current_wave_type = direction
        self.wave_start_price = start_price
        self.current_extreme_price = start_price
        self.wave_start_time = timestamp
        self.current_wave_volume = 0
        self.current_wave_count = 0
        
    def get_trend_state(self) -> Dict:
        """Analyze waves to determine stronger side using Volume + Structure"""
        if len(self.completed_waves) < 2:
            return {'bias': 'NEUTRAL', 'strength': 0}
            
        # Get averages for UP and DOWN waves
        up_waves = [w for w in self.completed_waves if w['type'] == 'UP']
        down_waves = [w for w in self.completed_waves if w['type'] == 'DOWN']
        
        if not up_waves or not down_waves:
            return {'bias': 'NEUTRAL', 'strength': 0}
            
        # 1. Volume Analysis
        avg_up_vol = sum(w['avg_volume'] for w in up_waves) / len(up_waves)
        avg_down_vol = sum(w['avg_volume'] for w in down_waves) / len(down_waves)
        
        vol_bias = 'NEUTRAL'
        if avg_up_vol > avg_down_vol * 1.05: # 5% diff
            vol_bias = 'BULLISH'
        elif avg_down_vol > avg_up_vol * 1.05:
            vol_bias = 'BEARISH'
            
        # 2. Market Structure Analysis (Highs and Lows)
        # Get last 2 peaks and valleys
        peaks = [w['end_price'] for w in up_waves][-2:]
        valleys = [w['end_price'] for w in down_waves][-2:]
        
        structure_bias = 'NEUTRAL'
        
        # Check Highs (Peaks)
        if len(peaks) >= 2:
            if peaks[1] < peaks[0]: # Lower High
                structure_bias = 'BEARISH'
            elif peaks[1] > peaks[0]: # Higher High
                structure_bias = 'BULLISH'
                
        # Check Lows (Valleys) - confirms trend
        if len(valleys) >= 2:
            if valleys[1] < valleys[0]: # Lower Low
                if structure_bias == 'BEARISH': 
                    structure_bias = 'STRONGLY_BEARISH'
                elif structure_bias == 'NEUTRAL':
                    structure_bias = 'BEARISH'
            elif valleys[1] > valleys[0]: # Higher Low
                if structure_bias == 'BULLISH':
                    structure_bias = 'STRONGLY_BULLISH'
                elif structure_bias == 'NEUTRAL':
                    structure_bias = 'BULLISH'
                    
        # 3. Combine Signals
        final_bias = 'NEUTRAL'
        
        if 'BEARISH' in structure_bias:
            if vol_bias != 'BULLISH': # Structure is King, unless Volume screams opposite
                final_bias = 'BEARISH'
        elif 'BULLISH' in structure_bias:
            if vol_bias != 'BEARISH':
                final_bias = 'BULLISH'
        else:
            final_bias = vol_bias
            
        return {
            'bias': final_bias,
            'structure': structure_bias,
            'volume_bias': vol_bias
        }


class PivotDetector:
    """
    Detect pivot points for exiting runner positions.
    Looks for OPPOSITE signals from entry.
    """
    
    def __init__(self, entry_direction: str, lookback_seconds: int = 20):
        self.entry_direction = entry_direction
        self.lookback_seconds = lookback_seconds
        
        # History buffers
        self.imbalance_history = deque(maxlen=lookback_seconds)
        self.bid_depth_history = deque(maxlen=lookback_seconds)
        self.ask_depth_history = deque(maxlen=lookback_seconds)
        self.spread_history = deque(maxlen=lookback_seconds)
        self.volume_history = deque(maxlen=lookback_seconds)
        
    def update(self, orderbook_data: Dict) -> bool:
        """
        Update with new data and check for pivot.
        Returns True if pivot detected.
        """
        # Extract data
        imbalance = orderbook_data['imbalance']
        bid_depth = orderbook_data['bid_volume_10']
        ask_depth = orderbook_data['ask_volume_10']
        spread = orderbook_data['spread_pct']
        volume = bid_depth + ask_depth
        
        # Update histories
        self.imbalance_history.append(imbalance)
        self.bid_depth_history.append(bid_depth)
        self.ask_depth_history.append(ask_depth)
        self.spread_history.append(spread)
        self.volume_history.append(volume)
        
        # Need enough data
        if len(self.imbalance_history) < self.lookback_seconds:
            return False
        
        # Detect pivot
        return self._detect_pivot()
    
    def _detect_pivot(self) -> bool:
        """
        Detect pivot using opposite signals from entry direction.
        """
        signals = {}
        
        if self.entry_direction == 'LONG':
            # Entered long, look for top signals
            signals['imbalance_weakening'] = self._check_imbalance_weakening()
            signals['ask_depth_building'] = self._check_ask_depth_building()
            signals['spread_widening'] = self._check_spread_widening()
            
        else:  # SHORT
            # Entered short, look for bottom signals
            signals['imbalance_improving'] = self._check_imbalance_improving()
            signals['bid_depth_building'] = self._check_bid_depth_building()
            signals['spread_tightening'] = self._check_spread_tightening()
        
        # Need 2+ opposite signals for pivot
        return sum(signals.values()) >= 2
    
    def _check_imbalance_weakening(self) -> bool:
        """Check if imbalance is weakening (for LONG exit)."""
        if len(self.imbalance_history) < 15:
            return False
        
        recent = sum(list(self.imbalance_history)[-5:]) / 5
        earlier = sum(list(self.imbalance_history)[-15:-10]) / 5
        
        # Imbalance declining (lowered threshold based on real data)
        return recent < earlier - 0.10
    
    def _check_imbalance_improving(self) -> bool:
        """Check if imbalance is improving (for SHORT exit)."""
        if len(self.imbalance_history) < 15:
            return False
        
        recent = sum(list(self.imbalance_history)[-5:]) / 5
        earlier = sum(list(self.imbalance_history)[-15:-10]) / 5
        
        # Imbalance rising (lowered threshold based on real data)
        return recent > earlier + 0.10
    
    def _check_ask_depth_building(self) -> bool:
        """Check if asks building (for LONG exit)."""
        if len(self.ask_depth_history) < 15:
            return False
        
        recent = sum(list(self.ask_depth_history)[-5:]) / 5
        earlier = sum(list(self.ask_depth_history)[-15:-10]) / 5
        
        return recent > earlier * 1.2
    
    def _check_bid_depth_building(self) -> bool:
        """Check if bids building (for SHORT exit)."""
        if len(self.bid_depth_history) < 15:
            return False
        
        recent = sum(list(self.bid_depth_history)[-5:]) / 5
        earlier = sum(list(self.bid_depth_history)[-15:-10]) / 5
        
        return recent > earlier * 1.2
    
    def _check_spread_widening(self) -> bool:
        """Check if spread widening (for LONG exit)."""
        if len(self.spread_history) < 15:
            return False
        
        recent = sum(list(self.spread_history)[-5:]) / 5
        earlier = sum(list(self.spread_history)[-15:-10]) / 5
        
        return recent > earlier * 1.2
    
    def _check_spread_tightening(self) -> bool:
        """Check if spread tightening (for SHORT exit)."""
        if len(self.spread_history) < 15:
            return False
        
        recent = sum(list(self.spread_history)[-5:]) / 5
        earlier = sum(list(self.spread_history)[-15:-10]) / 5
        
        return recent < earlier * 0.8


class ScalingExitManager:
    """
    Manage scaling exits: 50% at 0.5%, 50% runner until pivot.
    """
    
    def __init__(self, entry_price: float, direction: str, symbol: str):
        self.entry_price = entry_price
        self.direction = direction
        self.symbol = symbol
        
        # Targets (adjusted for BTC volatility)
        if direction == 'LONG':
            self.target_1 = entry_price * 1.0025  # +0.25%
            self.initial_stop = entry_price * 0.9975  # -0.25%
        else:  # SHORT
            self.target_1 = entry_price * 0.9975  # -0.25%
            self.initial_stop = entry_price * 1.0025  # +0.25%
        
        # State
        self.position_remaining = 100  # Percentage
        self.target_1_hit = False
        self.stop_loss = self.initial_stop
        self.pivot_detector = None
        
        logger.info(f"Scaling exit manager created: {direction} {symbol} @ ${entry_price:.2f}")
        logger.info(f"  Target 1: ${self.target_1:.2f} (0.25%)")
        logger.info(f"  Stop: ${self.stop_loss:.2f} (-0.25%)")

    
    def update(self, current_price: float, orderbook_data: Dict) -> Optional[Dict]:
        """
        Update position based on current price and orderbook.
        Returns action dict if action needed, None otherwise.
        """
        # Check stop loss
        if self._check_stop(current_price):
            logger.warning(f"Stop loss hit at ${current_price:.2f}")
            return {
                'action': 'CLOSE_ALL',
                'reason': 'STOP_LOSS',
                'price': current_price,
                'pnl_pct': self._calculate_pnl(current_price)
            }
        
        # Check first target
        if not self.target_1_hit and self._check_target_1(current_price):
            self.target_1_hit = True
            self.position_remaining = 50
            self.stop_loss = self.entry_price  # Move to breakeven
            
            # Initialize pivot detector for runner
            self.pivot_detector = PivotDetector(self.direction)
            
            logger.info(f"Target 1 hit at ${current_price:.2f}! Closing 50%, moving stop to breakeven")
            
            return {
                'action': 'CLOSE_50%',
                'reason': 'TARGET_1_HIT',
                'price': current_price,
                'pnl_pct': 0.25,  # 0.25% on 50% position
                'remaining': 50
            }

        
        # Check pivot exit (for runner)
        if self.target_1_hit and self.pivot_detector:
            if self.pivot_detector.update(orderbook_data):
                pnl = self._calculate_pnl(current_price)
                logger.info(f"Pivot detected at ${current_price:.2f}! Closing runner (PnL: {pnl:.2f}%)")
                
                return {
                    'action': 'CLOSE_50%',
                    'reason': 'PIVOT_DETECTED',
                    'price': current_price,
                    'pnl_pct': pnl,
                    'remaining': 0
                }
        
        return None
    
    def _check_target_1(self, price: float) -> bool:
        """Check if first target hit."""
        if self.direction == 'LONG':
            return price >= self.target_1
        else:
            return price <= self.target_1
    
    def _check_stop(self, price: float) -> bool:
        """Check if stop loss hit."""
        if self.direction == 'LONG':
            return price <= self.stop_loss
        else:
            return price >= self.stop_loss
    
    def _calculate_pnl(self, current_price: float) -> float:
        """Calculate PnL percentage."""
        if self.direction == 'LONG':
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - current_price) / self.entry_price) * 100
