"""
Enhanced Signal Generator with All Analytics

Integrates:
- Order Flow Imbalance (OFI)
- Order Toxicity Detection
- Volume Flow Reversal
- VPIN
- Dynamic Confidence (percentage-based)
- Tick Rule Classification
- Liquidation Zones
"""

import time
import logging
from typing import Dict, Optional, List
from dynamic_confidence import DynamicConfidenceCalculator

logger = logging.getLogger(__name__)


class EnhancedSignalGenerator:
    """
    Generate trading signals using all available analytics.
    
    Combines:
    - Orderbook metrics (OFI, weighted imbalance)
    - Volume flow (reversal detection)
    - Order toxicity (informed vs uninformed)
    - VPIN (informed trading probability)
    - Dynamic confidence (9-factor scoring)
    - Liquidation zones
    """
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        
        # Dynamic confidence calculators
        self.confidence_calcs = {s: DynamicConfidenceCalculator(s) for s in symbols}
        
        # Last signal time (prevent spam)
        self.last_signal_time = {s: 0 for s in symbols}
        self.signal_cooldown = 600  # 10 minutes (HIGH QUALITY - prevent spam)
    
    def generate_signal(
        self,
        symbol: str,
        price: float,
        ofi_data: Optional[Dict] = None,
        toxicity_data: Optional[Dict] = None,
        volume_flow_data: Optional[Dict] = None,
        orderbook_data: Optional[Dict] = None,
        zones: Optional[List[Dict]] = None,
        funding_signal: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Generate comprehensive trading signal.
        
        Args:
            symbol: Trading pair
            price: Current price
            ofi_data: OFI metrics from /api/orderbook-metrics
            toxicity_data: Toxicity data from /api/order-toxicity
            volume_flow_data: Volume flow from /api/volume-flow
            orderbook_data: Orderbook snapshot
            zones: Liquidation zones
            funding_signal: Funding rate signal (NEW)
        
        Returns:
            Signal dict or None
        """
        # Check cooldown
        if time.time() - self.last_signal_time[symbol] < self.signal_cooldown:
            logger.debug(f"{symbol}: Signal generation on cooldown")
            return None
        
        logger.info(f"🔍 {symbol}: Starting signal generation check...")
        logger.info(f"  - Price: ${price:.2f}")
        logger.info(f"  - Funding signal: {funding_signal is not None}")
        logger.info(f"  - OFI data: {ofi_data is not None}")
        logger.info(f"  - Toxicity data: {toxicity_data is not None}")
        logger.info(f"  - Volume flow data: {volume_flow_data is not None}")
        logger.info(f"  - Orderbook data: {orderbook_data is not None}")
        
        # Strategy 0: Funding Rate Arbitrage (HIGHEST PRIORITY)
        if funding_signal:
            logger.info(f"  ✓ Checking FUNDING_FADE strategy...")
            signal = self._create_funding_signal(symbol, price, funding_signal, ofi_data, toxicity_data)
            if signal:
                logger.info(f"  ✅ FUNDING_FADE signal generated!")
                return self._finalize_signal(symbol, signal, zones, orderbook_data)
            else:
                logger.info(f"  ✗ FUNDING_FADE conditions not met")
        
        # Strategy 1: V-Bottom Reversal (NEW - 3 entry strategies!)
        # Check if V-bottom tracker has generated a signal
        if orderbook_data and 'v_bottom_signal' in orderbook_data:
            v_signal = orderbook_data['v_bottom_signal']
            if v_signal:
                signal = self._create_v_bottom_signal(symbol, price, v_signal, ofi_data)
                if signal:
                    return self._finalize_signal(symbol, signal, zones, orderbook_data)
        
        # Strategy 2: Volume Flow Reversal
        signal = self._check_volume_flow_reversal(
            symbol, price, volume_flow_data, toxicity_data, ofi_data
        )
        if signal:
            return self._finalize_signal(symbol, signal, zones, orderbook_data)
        
        # Strategy 3: Toxic Flow Following
        signal = self._check_toxic_flow(
            symbol, price, toxicity_data, ofi_data, volume_flow_data
        )
        if signal:
            return self._finalize_signal(symbol, signal, zones, orderbook_data)
        
        # Strategy 4: OFI Breakout
        signal = self._check_ofi_breakout(
            symbol, price, ofi_data, orderbook_data, volume_flow_data
        )
        if signal:
            return self._finalize_signal(symbol, signal, zones, orderbook_data)
        
        logger.info(f"  ❌ {symbol}: No signals generated (no strategies triggered)")
        return None
    
    def _create_funding_signal(
        self,
        symbol: str,
        price: float,
        funding_signal: Dict,
        ofi_data: Optional[Dict],
        toxicity_data: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Create signal from funding rate arbitrage.
        
        High confidence when funding confirms with other analytics.
        """
        direction = funding_signal['direction']
        
        # Set entry/target/stop based on direction
        if direction == 'LONG':
            entry = price
            target = price * 1.015  # 1.5% target
            stop = price * 0.995    # 0.5% stop
        else:  # SHORT
            entry = price
            target = price * 0.985  # 1.5% target
            stop = price * 1.005    # 0.5% stop
        
        # Base confidence and reason
        confidence = funding_signal.get('confidence', 0.85)
        reason = funding_signal.get('reason', f'Funding rate arbitrage: {direction}')
        
        logger.info(f"Funding signal for {symbol}: {reason}")
        
        # Check for confirmations
        if ofi_data and 'ofi' in ofi_data:
            ofi_signal = ofi_data['ofi']['signal']
            logger.debug(f"OFI data for {symbol}: {ofi_signal}")
            if (direction == 'LONG' and 'BULLISH' in ofi_signal) or \
               (direction == 'SHORT' and 'BEARISH' in ofi_signal):
                reason += " + OFI confirms"
                logger.info(f"OFI confirms funding signal for {symbol}")
        
        if toxicity_data and 'signal' in toxicity_data:
            tox_signal = toxicity_data['signal']['signal']
            logger.debug(f"Toxicity data for {symbol}: {tox_signal}")
            if (direction == 'LONG' and 'TOXIC_BUYING' in tox_signal) or \
               (direction == 'SHORT' and 'TOXIC_SELLING' in tox_signal):
                reason += " + Toxic flow confirms"
                logger.info(f"Toxic flow confirms funding signal for {symbol}")
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': 'FUNDING_FADE',
            'direction': direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': confidence,
            'reason': reason,
            'funding_rate': funding_signal.get('funding_rate'),
            'funding_velocity': funding_signal.get('funding_velocity'),
            'details': funding_signal.get('details')
        }
    
    def _create_v_bottom_signal(
        self,
        symbol: str,
        price: float,
        v_signal: Dict,
        ofi_data: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Create V-bottom reversal signal with 3 entry strategies.
        
        Strategy selection based on confidence:
        - Conservative (90%+): 3% from bottom, full position
        - Balanced (85%+): 1.5% from bottom, 75% position
        - Aggressive (75%+): 0.7% from bottom, 50% position
        """
        strategy = v_signal.get('strategy', 'BALANCED')
        confidence = v_signal.get('confidence', 0.75)
        
        # Entry/target/stop based on strategy
        if strategy == 'CONSERVATIVE':
            # Wait for confirmation, enter 3% above current
            entry = price * 1.03
            target = price * 1.08   # 8% target from current
            stop = price * 0.99     # 1% stop
            position_size = 1.0     # Full position
        
        elif strategy == 'BALANCED':
            # Enter near bottom, 1.5% above current
            entry = price * 1.015
            target = price * 1.06   # 6% target
            stop = price * 0.985    # 1.5% stop
            position_size = 0.75    # 75% position
        
        else:  # AGGRESSIVE
            # Immediate entry at current price
            entry = price
            target = price * 1.05   # 5% target
            stop = price * 0.98     # 2% stop
            position_size = 0.5     # 50% position
        
        reason = v_signal.get('reason', 'V-bottom reversal detected')
        
        # Check OFI confirmation
        if ofi_data and 'ofi' in ofi_data:
            ofi_signal = ofi_data['ofi']['signal']
            if 'BULLISH' in ofi_signal:
                reason += " + OFI confirms"
                confidence = min(confidence + 0.05, 0.95)
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': f'V_BOTTOM_{strategy}',
            'direction': 'LONG',  # V-bottoms are always long
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': confidence,
            'reason': reason,
            'position_size': position_size,
            'strategy': strategy,
            'layers_confirmed': v_signal.get('layers_confirmed', 0),
            'drop_pct': v_signal.get('drop_pct', 0)
        }
    
    def _check_spoofing_fade(
        self,
        symbol: str,
        price: float,
        orderbook_data: Optional[Dict],
        ofi_data: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for spoofing fade signal.
        
        Spoofing = fake orders placed to manipulate price, then quickly cancelled.
        Strategy: Fade the spoofed side (trade opposite direction).
        
        High confidence when:
        - Multiple spoofing events detected
        - Large fake orders
        - OFI confirms opposite direction
        """
        if not orderbook_data or 'spoofing_events' not in orderbook_data:
            return None
        
        spoofing_events = orderbook_data['spoofing_events']
        
        # Need multiple events for confidence
        if spoofing_events < 3:
            return None
        
        # Determine spoofed side from orderbook stats
        stats = orderbook_data.get('stats', {})
        walls = stats.get('walls', {})
        
        # Check which side has more fake walls
        bid_walls = walls.get('bid_walls', 0)
        ask_walls = walls.get('ask_walls', 0)
        
        if bid_walls == 0 and ask_walls == 0:
            return None
        
        # Spoofed bids = fake buy pressure = actually bearish
        # Spoofed asks = fake sell pressure = actually bullish
        if bid_walls > ask_walls * 1.5:
            trade_direction = 'SHORT'
            entry = price
            target = price * 0.99    # 1% target
            stop = price * 1.003     # 0.3% stop
            reason = f"Spoofing detected: {spoofing_events} fake bid walls"
        elif ask_walls > bid_walls * 1.5:
            trade_direction = 'LONG'
            entry = price
            target = price * 1.01    # 1% target
            stop = price * 0.997     # 0.3% stop
            reason = f"Spoofing detected: {spoofing_events} fake ask walls"
        else:
            return None  # No clear imbalance
        
        # Check OFI confirmation
        ofi_confirms = False
        if ofi_data and 'ofi' in ofi_data:
            ofi_signal = ofi_data['ofi']['signal']
            if (trade_direction == 'LONG' and 'BULLISH' in ofi_signal) or \
               (trade_direction == 'SHORT' and 'BEARISH' in ofi_signal):
                ofi_confirms = True
                reason += " + OFI confirms"
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        # Base confidence: 70% (moderate - spoofing can be tricky)
        confidence = 0.70
        if ofi_confirms:
            confidence = 0.75  # Higher with confirmation
        
        return {
            'symbol': symbol,
            'type': 'SPOOFING_FADE',
            'direction': trade_direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': confidence,
            'reason': reason,
            'spoofing_events': spoofing_events
        }
    
    def _check_liquidity_breakout(
        self,
        symbol: str,
        price: float,
        orderbook_data: Optional[Dict],
        ofi_data: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for liquidity breakout signal.
        
        Liquidity cliffs = thin orderbook zones where price can accelerate.
        Strategy: Trade breakouts when price approaches thin liquidity.
        
        High confidence when:
        - Price within 0.5% of liquidity cliff
        - OFI confirms direction
        - Cliff is significant (>50% below average)
        """
        if not orderbook_data or 'liquidity_cliffs' not in orderbook_data:
            return None
        
        cliffs = orderbook_data['liquidity_cliffs']
        
        if not cliffs:
            return None
        
        # Find nearest cliff
        nearest_cliff = None
        min_distance = float('inf')
        
        for cliff in cliffs:
            distance_pct = abs(price - cliff['price']) / price * 100
            
            if distance_pct < min_distance and distance_pct < 0.5:  # Within 0.5%
                min_distance = distance_pct
                nearest_cliff = cliff
        
        if not nearest_cliff:
            return None
        
        # Determine direction based on cliff side and price position
        cliff_price = nearest_cliff['price']
        cliff_side = nearest_cliff['side']
        
        # If price approaching ask cliff (resistance) from below = bullish breakout
        # If price approaching bid cliff (support) from above = bearish breakout
        if cliff_side == 'ask' and price < cliff_price:
            trade_direction = 'LONG'
            entry = price
            target = cliff_price * 1.01  # 1% beyond cliff
            stop = price * 0.997         # 0.3% stop
            reason = f"Liquidity cliff breakout: thin asks at ${cliff_price:.2f}"
        elif cliff_side == 'bid' and price > cliff_price:
            trade_direction = 'SHORT'
            entry = price
            target = cliff_price * 0.99  # 1% beyond cliff
            stop = price * 1.003         # 0.3% stop
            reason = f"Liquidity cliff breakout: thin bids at ${cliff_price:.2f}"
        else:
            return None  # Price not positioned correctly
        
        # Check OFI confirmation
        ofi_confirms = False
        if ofi_data and 'ofi' in ofi_data:
            ofi_signal = ofi_data['ofi']['signal']
            if (trade_direction == 'LONG' and 'BULLISH' in ofi_signal) or \
               (trade_direction == 'SHORT' and 'BEARISH' in ofi_signal):
                ofi_confirms = True
                reason += " + OFI confirms"
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        # Base confidence: 65% (moderate - breakouts can fail)
        confidence = 0.65
        if ofi_confirms:
            confidence = 0.72  # Higher with confirmation
        
        # Boost confidence if cliff is very thin
        gap_pct = nearest_cliff.get('gap_pct', 0)
        if gap_pct > 70:  # >70% below average = very thin
            confidence += 0.05
        
        return {
            'symbol': symbol,
            'type': 'LIQUIDITY_BREAKOUT',
            'direction': trade_direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': min(confidence, 0.80),  # Cap at 80%
            'reason': reason,
            'cliff_price': cliff_price,
            'cliff_gap_pct': gap_pct
        }
    
    def _check_mm_unwind(
        self,
        symbol: str,
        price: float,
        orderbook_data: Optional[Dict],
        ofi_data: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for market maker inventory unwind signal.
        
        MM unwinding = strong directional signal (MMs have superior information).
        Strategy: Follow MM flow when they unwind positions.
        
        High confidence when:
        - Clear MM position detected
        - Skew reversing (unwinding)
        - OFI confirms direction
        """
        if not orderbook_data or 'mm_signal' not in orderbook_data:
            return None
        
        mm_signal = orderbook_data['mm_signal']
        
        if not mm_signal or mm_signal.get('type') != 'MM_UNWIND':
            return None
        
        direction = mm_signal['direction']
        confidence = mm_signal['confidence']
        
        # Calculate entry/target/stop
        if direction == 'LONG':
            entry = price
            target = price * 1.015   # 1.5% target
            stop = price * 0.995     # 0.5% stop
        else:  # SHORT
            entry = price
            target = price * 0.985   # 1.5% target
            stop = price * 1.005     # 0.5% stop
        
        reason = mm_signal['reason']
        
        # Check OFI confirmation
        if ofi_data and 'ofi' in ofi_data:
            ofi_signal = ofi_data['ofi']['signal']
            if (direction == 'LONG' and 'BULLISH' in ofi_signal) or \
               (direction == 'SHORT' and 'BEARISH' in ofi_signal):
                reason += " + OFI confirms"
                confidence = min(confidence + 0.05, 0.85)
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': 'MM_UNWIND',
            'direction': direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': confidence,
            'reason': reason,
            'mm_position': mm_signal.get('mm_position'),
            'unwind_strength': mm_signal.get('unwind_strength')
        }
    
    def _check_volume_flow_reversal(
        self,
        symbol: str,
        price: float,
        volume_flow: Optional[Dict],
        toxicity: Optional[Dict],
        ofi: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for volume flow reversal signal.
        
        High confidence when:
        - Multiple windows confirm reversal
        - Toxic flow agrees
        - OFI confirms
        """
        if not volume_flow or 'reversal_signal' not in volume_flow:
            return None
        
        reversal = volume_flow['reversal_signal']
        
        # HIGH QUALITY: Require high confidence AND multiple windows
        if not reversal or reversal['confidence'] < 0.75:
            return None
        
        # Require at least 2 windows confirming
        if len(reversal.get('confirming_windows', [])) < 2:
            return None
        
        # Get direction
        direction = reversal['direction']  # 'BULLISH' or 'BEARISH'
        
        # Check for confirmation from toxicity
        toxicity_confirms = False
        if toxicity and 'signal' in toxicity:
            tox_signal = toxicity['signal']['signal']
            if (direction == 'BULLISH' and 'TOXIC_BUYING' in tox_signal) or \
               (direction == 'BEARISH' and 'TOXIC_SELLING' in tox_signal):
                toxicity_confirms = True
        
        # Check for confirmation from OFI
        ofi_confirms = False
        if ofi and 'ofi' in ofi:
            ofi_signal = ofi['ofi']['signal']
            if (direction == 'BULLISH' and 'BULLISH' in ofi_signal) or \
               (direction == 'BEARISH' and 'BEARISH' in ofi_signal):
                ofi_confirms = True
        
        # Calculate entry/target/stop
        if direction == 'BULLISH':
            entry = price
            target = price * 1.015  # 1.5% target
            stop = price * 0.995    # 0.5% stop
            trade_direction = 'LONG'
        else:
            entry = price
            target = price * 0.985  # 1.5% target
            stop = price * 1.005    # 0.5% stop
            trade_direction = 'SHORT'
        
        # Build reason
        reasons = [f"Volume reversal ({reversal['confirming_windows']} windows)"]
        if toxicity_confirms:
            reasons.append("Toxic flow confirms")
        if ofi_confirms:
            reasons.append("OFI confirms")
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': 'VOLUME_FLOW_REVERSAL',
            'direction': trade_direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': reversal['confidence'],
            'reason': ' + '.join(reasons),
            'strength': reversal['strength'],
            'confirming_windows': reversal['confirming_windows']
        }
    
    def _check_toxic_flow(
        self,
        symbol: str,
        price: float,
        toxicity: Optional[Dict],
        ofi: Optional[Dict],
        volume_flow: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for toxic flow signal (follow informed traders).
        
        High confidence when:
        - High toxicity detected
        - OFI agrees
        - Volume flow agrees
        """
        if not toxicity or 'signal' not in toxicity:
            return None
        
        tox_signal = toxicity['signal']
        
        # HIGH QUALITY: Require very high confidence
        if tox_signal['signal'] == 'NEUTRAL' or tox_signal['confidence'] < 0.80:
            return None
        
        # Determine direction
        if 'TOXIC_BUYING' in tox_signal['signal']:
            trade_direction = 'LONG'
            entry = price
            target = price * 1.01
            stop = price * 0.997
        elif 'TOXIC_SELLING' in tox_signal['signal']:
            trade_direction = 'SHORT'
            entry = price
            target = price * 0.99
            stop = price * 1.003
        else:
            return None  # FADE signals are lower confidence
        
        # Check confirmations
        ofi_confirms = False
        if ofi and 'ofi' in ofi:
            ofi_signal = ofi['ofi']['signal']
            if (trade_direction == 'LONG' and 'BULLISH' in ofi_signal) or \
               (trade_direction == 'SHORT' and 'BEARISH' in ofi_signal):
                ofi_confirms = True
        
        # Build reason
        reasons = [f"Toxic flow: {tox_signal.get('toxic_buys', 0) if trade_direction == 'LONG' else tox_signal.get('toxic_sells', 0)} informed trades"]
        if ofi_confirms:
            reasons.append("OFI confirms")
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': 'TOXIC_FLOW',
            'direction': trade_direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': tox_signal['confidence'],
            'reason': ' + '.join(reasons)
        }
    
    def _check_ofi_breakout(
        self,
        symbol: str,
        price: float,
        ofi: Optional[Dict],
        orderbook: Optional[Dict],
        volume_flow: Optional[Dict]
    ) -> Optional[Dict]:
        """
        Check for OFI breakout signal.
        
        High confidence when:
        - Strong OFI
        - Price coiling (low volatility)
        - Orderbook imbalance agrees
        """
        if not ofi or 'ofi' not in ofi:
            return None
        
        ofi_data = ofi['ofi']
        ofi_signal = ofi_data['signal']
        ofi_value = abs(ofi_data.get('value', 0))
        
        # Require STRONG OFI signal AND value > 10
        if 'STRONG' not in ofi_signal or ofi_value < 10:
            return None  # Only strong OFI with meaningful value
        
        # Determine direction
        if 'BULLISH' in ofi_signal:
            trade_direction = 'LONG'
            entry = price
            target = price * 1.012
            stop = price * 0.996
        elif 'BEARISH' in ofi_signal:
            trade_direction = 'SHORT'
            entry = price
            target = price * 0.988
            stop = price * 1.004
        else:
            return None
        
        # Check orderbook confirmation
        ob_confirms = False
        if orderbook:
            weighted_imb = orderbook.get('weighted_imbalance', 0)
            if (trade_direction == 'LONG' and weighted_imb > 0.1) or \
               (trade_direction == 'SHORT' and weighted_imb < -0.1):
                ob_confirms = True
        
        # Build reason
        reasons = [f"Strong OFI: {ofi_data['value']:.0f}"]
        if ob_confirms:
            reasons.append("Orderbook confirms")
        
        # Calculate R/R
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = reward / risk if risk > 0 else 0
        
        return {
            'symbol': symbol,
            'type': 'OFI_BREAKOUT',
            'direction': trade_direction,
            'entry': entry,
            'target': target,
            'stop': stop,
            'riskReward': rr,
            'confidence': 0.75,  # Increased base confidence for stronger threshold
            'reason': ' + '.join(reasons)
        }
    
    def _apply_orderbook_alpha_confirmations(
        self,
        signal: Dict,
        orderbook_data: Optional[Dict],
        price: float
    ) -> Dict:
        """
        Apply orderbook alpha confirmations to boost signal confidence.
        
        Uses spoofing detection, liquidity structure, and MM alignment
        to enhance confidence scoring on existing signals.
        
        Philosophy: Quality over quantity - use all available information
        to identify the best trading opportunities.
        """
        if not orderbook_data:
            return signal
        
        # 1. Anti-Spoofing Check (reduce confidence if spoofing on signal side)
        signal = self._apply_spoofing_check(signal, orderbook_data)
        
        # 2. Liquidity Confirmation (boost if liquidity supports direction)
        signal = self._apply_liquidity_confirmation(signal, orderbook_data, price)
        
        # 3. MM Alignment (boost if MM position aligns)
        signal = self._apply_mm_alignment(signal, orderbook_data)
        
        # Cap confidence at 95%
        signal['confidence'] = min(signal['confidence'], 0.95)
        
        return signal
    
    def _apply_spoofing_check(self, signal: Dict, orderbook_data: Dict) -> Dict:
        """
        Reduce confidence if spoofing detected on signal side.
        
        Spoofed walls = fake liquidity = signal may be manipulated.
        """
        spoofing_count = orderbook_data.get('spoofing_events', 0)
        if spoofing_count < 3:
            return signal  # Not significant
        
        stats = orderbook_data.get('stats', {})
        walls = stats.get('walls', {})
        bid_walls = walls.get('bid_walls', 0)
        ask_walls = walls.get('ask_walls', 0)
        
        direction = signal['direction']
        
        # If LONG signal but bid walls are spoofed (fake support)
        if direction == 'LONG' and bid_walls > ask_walls * 1.5:
            signal['confidence'] *= 0.85  # Reduce 15%
            signal['reason'] += " [⚠️ Spoofed bids]"
            # logger.info(f"Reduced confidence due to spoofed bid walls: {signal['symbol']}") # Commented out as logger is not defined in this snippet
        
        # If SHORT signal but ask walls are spoofed (fake resistance)
        elif direction == 'SHORT' and ask_walls > bid_walls * 1.5:
            signal['confidence'] *= 0.85  # Reduce 15%
            signal['reason'] += " [⚠️ Spoofed asks]"
            # logger.info(f"Reduced confidence due to spoofed ask walls: {signal['symbol']}") # Commented out as logger is not defined in this snippet
        
        return signal
    
    def _apply_liquidity_confirmation(self, signal: Dict, orderbook_data: Dict, price: float) -> Dict:
        """
        Boost confidence if liquidity supports signal direction.
        
        Thin liquidity in direction = price will accelerate.
        """
        cliffs = orderbook_data.get('liquidity_cliffs', [])
        if not cliffs:
            return signal
        
        direction = signal['direction']
        
        # Find nearest cliff in signal direction
        for cliff in cliffs:
            distance_pct = abs(price - cliff['price']) / price * 100
            
            if distance_pct > 1.0:  # Too far
                continue
            
            # LONG signal + thin asks above = good
            if direction == 'LONG' and cliff['side'] == 'ask' and cliff['price'] > price:
                if cliff['gap_pct'] > 60:  # Very thin
                    signal['confidence'] *= 1.10  # Boost 10%
                    signal['reason'] += f" [✓ Thin asks @${cliff['price']:.0f}]"
                    # logger.info(f"Boosted confidence due to thin asks: {signal['symbol']}") # Commented out as logger is not defined in this snippet
                    break
            
            # SHORT signal + thin bids below = good
            elif direction == 'SHORT' and cliff['side'] == 'bid' and cliff['price'] < price:
                if cliff['gap_pct'] > 60:  # Very thin
                    signal['confidence'] *= 1.10  # Boost 10%
                    signal['reason'] += f" [✓ Thin bids @${cliff['price']:.0f}]"
                    # logger.info(f"Boosted confidence due to thin bids: {signal['symbol']}") # Commented out as logger is not defined in this snippet
                    break
        
        return signal
    
    def _apply_mm_alignment(self, signal: Dict, orderbook_data: Dict) -> Dict:
        """
        Boost confidence if MM position aligns with signal.
        
        MM unwinding = strong directional signal (smart money).
        """
        mm_signal = orderbook_data.get('mm_signal')
        if not mm_signal or mm_signal.get('type') != 'MM_UNWIND':
            return signal
        
        # Check if MM direction matches signal direction
        if mm_signal['direction'] == signal['direction']:
            signal['confidence'] *= 1.15  # Boost 15%
            mm_pos = mm_signal.get('mm_position', 'unknown')
            signal['reason'] += f" [✓ MM unwinding {mm_pos}]"
            # logger.info(f"Boosted confidence due to MM alignment: {signal['symbol']}") # Commented out as logger is not defined in this snippet
        
        return signal
    
    def _finalize_signal(
        self,
        symbol: str,
        signal: Dict,
        zones: Optional[List[Dict]],
        orderbook: Optional[Dict]
    ) -> Dict:
        """
        Finalize signal with dynamic confidence and metadata.
        
        Applies orderbook alpha confirmations to boost confidence.
        """
        if not signal:
            return None
        
        # Get entry price for orderbook alpha confirmations
        entry_price = signal.get('entry', 0)
        
        # Apply orderbook alpha confirmations (NEW!)
        # Uses spoofing detection, liquidity structure, and MM alignment
        # to enhance confidence scoring
        if entry_price > 0:
            signal = self._apply_orderbook_alpha_confirmations(
                signal, orderbook, entry_price
            )
        
        # Calculate dynamic confidence
        confidence_calc = self.confidence_calcs.get(symbol)
        if confidence_calc:
            confidence_data = confidence_calc.get_confidence(signal['direction'])
            
            # Blend base confidence with dynamic confidence
            # Give more weight to base confidence (strategy-specific)
            base_conf = signal['confidence']
            dynamic_conf = confidence_data['confidence_pct'] / 100
            signal['confidence'] = (base_conf * 0.85) + (dynamic_conf * 0.15)  # 85/15 split instead of 70/30
        
        # Add metadata
        signal['timestamp'] = time.time()
        signal['regime'] = confidence_data['regime'] if confidence_calc else 'UNKNOWN'
        
        # Add zone info if available (metadata only, not in reason)
        if zones:
            nearby_zones = [
                z for z in zones
                if abs(z.get('distance_pct', 100)) < 2
            ]
            if nearby_zones:
                signal['nearby_zones'] = len(nearby_zones)
                # Removed: signal['reason'] += f" | {len(nearby_zones)} zones nearby"

        
        # Update last signal time
        self.last_signal_time[symbol] = time.time()
        
        return signal


if __name__ == "__main__":
    """Test enhanced signal generator."""
    
    logging.basicConfig(level=logging.INFO)
    
    generator = EnhancedSignalGenerator(['BTCUSDT'])
    
    # Simulate data
    volume_flow = {
        'reversal_signal': {
            'direction': 'BULLISH',
            'confidence': 0.75,
            'strength': 0.3,
            'confirming_windows': 3
        }
    }
    
    toxicity = {
        'signal': {
            'signal': 'FOLLOW_TOXIC_BUYING',
            'confidence': 0.82,
            'toxic_buys': 15
        }
    }
    
    ofi = {
        'ofi': {
            'value': 850,
            'signal': 'STRONG_BULLISH'
        }
    }
    
    signal = generator.generate_signal(
        'BTCUSDT',
        100000,
        ofi_data=ofi,
        toxicity_data=toxicity,
        volume_flow_data=volume_flow
    )
    
    if signal:
        print("="*60)
        print("ENHANCED SIGNAL GENERATED")
        print("="*60)
        for key, value in signal.items():
            print(f"{key}: {value}")
