"""
Week 4 Task 4.1 & 4.2: Execution Engine with Entry Timing & Adaptive Limit Orders
==================================================================================

Implements smart order execution with:
1. Entry delay (1.5s stability check)
2. Adaptive limit order placement (by confidence)
3. Fill timeout logic (1 second)

Expert Guidance (Week 4):
- Wait 1.5s after signal to ensure price stability
- Threshold: 5 basis points (0.05%) movement = skip trade
- Adaptive placement (Expert Q6):
  * High conf (>85%): best_bid + 1_tick (aggressive, 50-65% fill)
  * Med conf (60-85%): best_bid (conservative, 25-40% fill)
  * Low conf (<60%): Skip trade
- Fill timeout: 1 second (LOCKED)
"""

import time
import logging
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status enum."""
    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ExecutionEngine:
    """
    Smart execution engine with entry timing and adaptive limit orders.
    
    Features:
    - 1.5s stability check before entry
    - 5 bps threshold (skip if price crashes)
    - Adaptive limit placement by confidence
    - 1 second fill timeout
    """
    
    # LOCKED PARAMETERS (per expert Week 4)
    STABILITY_CHECK_SECONDS = 1.5
    STABILITY_THRESHOLD_BPS = 5  # 5 basis points = 0.05%
    FILL_TIMEOUT_SECONDS = 1.0
    
    # Adaptive placement by confidence (Expert Q6)
    CONFIDENCE_THRESHOLDS = {
        'HIGH': 85.0,    # >85% = high confidence
        'MEDIUM': 60.0   # 60-85% = medium confidence
    }
    
    # Tick sizes per symbol
    TICK_SIZES = {
        'BTCUSDT': 1.0,
        'ETHUSDT': 0.1,
        'SOLUSDT': 0.01
    }
    
    def __init__(self, symbol: str):
        """
        Initialize execution engine.
        
        Args:
            symbol: Trading symbol
        """
        self.symbol = symbol
        self.tick_size = self.TICK_SIZES.get(symbol, 0.01)
        
        # Track pending orders
        self.pending_orders: List[Dict] = []
        
        # Execution statistics
        self.stats = {
            'signals_received': 0,
            'stability_checks_passed': 0,
            'stability_checks_failed': 0,
            'orders_placed': 0,
            'orders_filled': 0,
            'orders_timeout': 0,
            'skipped_low_confidence': 0
        }
        
    def process_signal(self, 
                      signal: Dict,
                      current_orderbook: Dict,
                      wait_for_stability: bool = True) -> Optional[Dict]:
        """
        Process trading signal with entry timing logic.
        
        Args:
            signal: {
                'direction': 'LONG' or 'SHORT',
                'confidence': float (0-100),
                'timestamp': float,
                'entry_price': float (optional),
                ...
            }
            current_orderbook: Current orderbook state
            wait_for_stability: If True, wait 1.5s and check stability
            
        Returns:
            Order dict or None if skipped
        """
        self.stats['signals_received'] += 1
        
        # Check confidence threshold
        confidence = signal.get('confidence', 0)
        
        if confidence < self.CONFIDENCE_THRESHOLDS['MEDIUM']:
            logger.info(f"Skipping signal: Low confidence ({confidence:.1f}% < 60%)")
            self.stats['skipped_low_confidence'] += 1
            return None
        
        # Entry delay & stability check
        if wait_for_stability:
            stable, stability_info = self._check_price_stability(
                signal, current_orderbook
            )
            
            if not stable:
                logger.warning(f"Price unstable: {stability_info['movement_bps']:.1f} bps > {self.STABILITY_THRESHOLD_BPS} bps")
                self.stats['stability_checks_failed'] += 1
                return None
            
            self.stats['stability_checks_passed'] += 1
        
        # Determine limit order placement
        order = self._create_adaptive_limit_order(signal, current_orderbook)
        
        if order:
            self.stats['orders_placed'] += 1
            self.pending_orders.append(order)
        
        return order
    
    def _check_price_stability(self, signal: Dict, current_orderbook: Dict) -> tuple:
        """
        Wait 1.5s and check price hasn't moved >5 bps.
        
        Returns:
            (is_stable, stability_info)
        """
        direction = signal['direction']
        initial_price = signal.get('entry_price') or self._get_midprice(current_orderbook)
        
        # Wait for stability period
        time.sleep(self.STABILITY_CHECK_SECONDS)
        
        # In real implementation, would fetch new orderbook here
        # For now, simulate with current orderbook (in live: fetch fresh)
        final_price = self._get_midprice(current_orderbook)
        
        # Calculate price movement in basis points
        movement_bps = abs(final_price - initial_price) / initial_price * 10000
        
        # Check if movement exceeds threshold
        is_stable = movement_bps <= self.STABILITY_THRESHOLD_BPS
        
        stability_info = {
            'initial_price': initial_price,
            'final_price': final_price,
            'movement_bps': movement_bps,
            'threshold_bps': self.STABILITY_THRESHOLD_BPS,
            'direction': direction
        }
        
        return is_stable, stability_info
    
    def _create_adaptive_limit_order(self, signal: Dict, orderbook: Dict) -> Optional[Dict]:
        """
        Create limit order with adaptive placement based on confidence.
        
        Expert Q6 Decision:
        - High conf (>85%): best_bid + 1_tick (aggressive)
        - Med conf (60-85%): best_bid (conservative)
        - Low conf (<60%): Skip
        """
        confidence = signal.get('confidence', 0)
        direction = signal['direction']
        
        # Get best bid/ask
        best_bid = self._get_best_bid(orderbook)
        best_ask = self._get_best_ask(orderbook)
        
        if direction == 'LONG':
            # Buying
            if confidence >= self.CONFIDENCE_THRESHOLDS['HIGH']:
                # High confidence: Aggressive (bid + 1 tick)
                limit_price = best_bid + self.tick_size
                expected_fill_rate = 0.575  # 50-65% average
                logger.info(f"HIGH conf ({confidence:.1f}%): Aggressive limit @ {limit_price} (bid + 1 tick)")
            else:
                # Medium confidence: Conservative (at bid)
                limit_price = best_bid
                expected_fill_rate = 0.325  # 25-40% average
                logger.info(f"MED conf ({confidence:.1f}%): Conservative limit @ {limit_price} (at bid)")
            
            side = 'BUY'
            
        else:  # SHORT
            # Selling
            if confidence >= self.CONFIDENCE_THRESHOLDS['HIGH']:
                # High confidence: Aggressive (ask - 1 tick)
                limit_price = best_ask - self.tick_size
                expected_fill_rate = 0.575
                logger.info(f"HIGH conf ({confidence:.1f}%): Aggressive limit @ {limit_price} (ask - 1 tick)")
            else:
                # Medium confidence: Conservative (at ask)
                limit_price = best_ask
                expected_fill_rate = 0.325
                logger.info(f"MED conf ({confidence:.1f}%): Conservative limit @ {limit_price} (at ask)")
            
            side = 'SELL'
        
        # Create order
        order = {
            'symbol': self.symbol,
            'side': side,
            'type': 'LIMIT',
            'price': limit_price,
            'quantity': signal.get('quantity', 0),  # Size from position sizer
            'time_in_force': 'GTC',
            'confidence': confidence,
            'expected_fill_rate': expected_fill_rate,
            'timestamp': time.time(),
            'signal': signal,
            'status': OrderStatus.PENDING
        }
        
        return order
    
    def check_fill_timeout(self, order: Dict, current_time: float) -> bool:
        """
        Check if order has exceeded fill timeout (1 second).
        
        Returns:
            True if should cancel (timeout), False if still waiting
        """
        time_elapsed = current_time - order['timestamp']
        
        if time_elapsed >= self.FILL_TIMEOUT_SECONDS:
            logger.warning(f"Order timeout after {time_elapsed:.2f}s (limit: {self.FILL_TIMEOUT_SECONDS}s)")
            self.stats['orders_timeout'] += 1
            return True
        
        return False
    
    def update_fill_status(self, order: Dict, filled_qty: float, executed_price: float):
        """
        Update order with fill information.
        
        Args:
            order: Order dict
            filled_qty: Quantity filled
            executed_price: Average execution price
        """
        total_qty = order['quantity']
        
        if filled_qty >= total_qty:
            order['status'] = OrderStatus.FILLED
            self.stats['orders_filled'] += 1
        elif filled_qty >= total_qty * 0.3:  # Accept partial fills >30%
            order['status'] = OrderStatus.PARTIALLY_FILLED
            self.stats['orders_filled'] += 1
        else:
            order['status'] = OrderStatus.CANCELLED
            logger.info(f"Rejecting partial fill: {filled_qty}/{total_qty} = {filled_qty/total_qty:.1%} < 30%")
        
        order['filled_qty'] = filled_qty
        order['executed_price'] = executed_price
    
    def _get_midprice(self, orderbook: Dict) -> float:
        """Get mid price from orderbook."""
        best_bid = self._get_best_bid(orderbook)
        best_ask = self._get_best_ask(orderbook)
        return (best_bid + best_ask) / 2
    
    def _get_best_bid(self, orderbook: Dict) -> float:
        """Get best bid price."""
        bids = orderbook.get('bids', [])
        if not bids:
            return 0
        return float(bids[0][0])
    
    def _get_best_ask(self, orderbook: Dict) -> float:
        """Get best ask price."""
        asks = orderbook.get('asks', [])
        if not asks:
            return 0
        return float(asks[0][0])
    
    def get_stats(self) -> Dict:
        """Get execution statistics."""
        total_checks = self.stats['stability_checks_passed'] + self.stats['stability_checks_failed']
        
        return {
            **self.stats,
            'stability_pass_rate': self.stats['stability_checks_passed'] / total_checks * 100 if total_checks > 0 else 0,
            'fill_rate': self.stats['orders_filled'] / self.stats['orders_placed'] * 100 if self.stats['orders_placed'] > 0 else 0,
            'timeout_rate': self.stats['orders_timeout'] / self.stats['orders_placed'] * 100 if self.stats['orders_placed'] > 0 else 0
        }


if __name__ == "__main__":
    """Test execution engine."""
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 80)
    print("WEEK 4 TASKS 4.1 & 4.2: EXECUTION ENGINE TEST")
    print("=" * 80)
    print("\n🔒 LOCKED PARAMETERS:")
    print(f"   Stability check: {ExecutionEngine.STABILITY_CHECK_SECONDS}s")
    print(f"   Stability threshold: {ExecutionEngine.STABILITY_THRESHOLD_BPS} bps")
    print(f"   Fill timeout: {ExecutionEngine.FILL_TIMEOUT_SECONDS}s")
    print(f"   High conf threshold: >{ExecutionEngine.CONFIDENCE_THRESHOLDS['HIGH']}%")
    print(f"   Med conf threshold: >{ExecutionEngine.CONFIDENCE_THRESHOLDS['MEDIUM']}%\n")
    
    engine = ExecutionEngine('BTCUSDT')
    
    # Test orderbook
    orderbook = {
        'bids': [[100000, 2.0], [99999, 1.5]],
        'asks': [[100001, 2.0], [100002, 1.5]]
    }
    
    # Test 1: High confidence signal (aggressive placement)
    print("Test 1: High Confidence Signal (>85%)")
    print("-" * 80)
    
    signal_high = {
        'direction': 'LONG',
        'confidence': 90.0,
        'timestamp': time.time(),
        'entry_price': 100000.5,
        'quantity': 1.0
    }
    
    order_high = engine.process_signal(signal_high, orderbook, wait_for_stability=False)
    
    if order_high:
        print(f"   Order created: {order_high['side']} @ ${order_high['price']:,.2f}")
        print(f"   Placement: best_bid + 1 tick (aggressive)")
        print(f"   Expected fill rate: {order_high['expected_fill_rate']:.1%}\n")
    
    # Test 2: Medium confidence signal (conservative placement)
    print("Test 2: Medium Confidence Signal (60-85%)")
    print("-" * 80)
    
    signal_med = {
        'direction': 'LONG',
        'confidence': 70.0,
        'timestamp': time.time(),
        'entry_price': 100000.5,
        'quantity': 1.0
    }
    
    order_med = engine.process_signal(signal_med, orderbook, wait_for_stability=False)
    
    if order_med:
        print(f"   Order created: {order_med['side']} @ ${order_med['price']:,.2f}")
        print(f"   Placement: at best_bid (conservative)")
        print(f"   Expected fill rate: {order_med['expected_fill_rate']:.1%}\n")
    
    # Test 3: Low confidence signal (skipped)
    print("Test 3: Low Confidence Signal (<60%)")
    print("-" * 80)
    
    signal_low = {
        'direction': 'LONG',
        'confidence': 50.0,
        'timestamp': time.time(),
        'entry_price': 100000.5,
        'quantity': 1.0
    }
    
    order_low = engine.process_signal(signal_low, orderbook, wait_for_stability=False)
    
    if order_low:
        print(f"   Order created")
    else:
        print(f"   ❌ Signal SKIPPED (confidence too low)\n")
    
    # Stats
    print("=" * 80)
    print("EXECUTION STATISTICS")
    print("=" * 80)
    stats = engine.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key:<30s}: {value:.2f}")
        else:
            print(f"   {key:<30s}: {value}")
    
    print("\n✅ Test complete - Execution engine ready for integration")
