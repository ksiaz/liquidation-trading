"""
M3 Temporal Layer (Internal)

Maintains chronological sequence of evidence tokens and derived metrics.
Strictly reacting to external time; determines NOTHING on its own.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import Dict, List, Optional, Tuple
import numpy as np

# Re-define internal dataclasses here (Not part of public API)
@dataclass
class TradeWindow:
    """Aggregated trade data for a time window."""
    window_start: float
    window_end: float
    trade_count: int
    total_volume: float
    mean_price: float
    max_trade_size: float
    symbol: str

@dataclass
class PromotedEventInternal:
    """Internal representation of a promoted event."""
    timestamp: float
    symbol: str
    price: float
    quantity: float
    side: str
    baseline_mean: float
    baseline_stddev: float
    sigma_distance: float

class BaselineCalculator:
    """Rolling baseline calculation (M4 Primitive)."""
    
    def __init__(self, lookback_windows: int = 60):
        self.lookback_windows = lookback_windows
        self.window_sizes: deque = deque(maxlen=lookback_windows)
    
    def update(self, window: TradeWindow):
        if window.trade_count > 0:
            mean_size = window.total_volume / window.trade_count
            self.window_sizes.append(mean_size)
    
    def get_baseline(self) -> Tuple[float, float]:
        if len(self.window_sizes) < 2:
            return (0.0, 0.0)
        return (float(np.mean(self.window_sizes)), float(np.std(self.window_sizes)))
    
    def is_warm(self) -> bool:
        # Enforce 10 window minimum for validity
        return len(self.window_sizes) >= min(10, self.lookback_windows)

class M3TemporalEngine:
    """
    Subsystem responsible for windowing and temporal aggregation.
    No internal clock.
    """
    
    def __init__(self, window_seconds: float = 1.0, baseline_windows: int = 60, threshold_sigma: float = 2.0):
        self._window_seconds = window_seconds
        self._threshold_sigma = threshold_sigma

        # State
        self._current_window_start: Optional[float] = None
        self._current_windows: Dict[str, List[Dict]] = {} # Symbol -> List of raw trades in window

        # OHLC candle state (per symbol)
        self._current_candles: Dict[str, Dict] = {}  # Symbol -> {open, high, low, close, timestamp}

        # Sub-components
        self._baseline = BaselineCalculator(baseline_windows)
        self._promoted_events: List[PromotedEventInternal] = []

        # Counters (Internal M4)
        self.stats = {
            'windows_processed': 0,
            'peak_pressure_events': 0,
            'rejected_count': 0
        }

    def process_trade(self, timestamp: float, symbol: str, price: float, quantity: float, side: str) -> Optional[PromotedEventInternal]:
        """
        Process a single trade event at specific timestamp.
        """
        # 1. Check for Window Rollover (Implicitly driven by event timestamp)
        # Note: In strict mode, we might wait for 'advance_time', but for event-driven
        # windowing, using the event's timestamp to close previous windows is standard M3 behavior.
        self._manage_windows(timestamp)
        
        # 2. Add to current window
        if symbol not in self._current_windows:
            self._current_windows[symbol] = []

        self._current_windows[symbol].append({
            'price': price,
            'quantity': quantity,
            'side': side
        })

        # 2b. Update OHLC candle for this symbol
        self._update_candle(symbol, price, timestamp)
        
        # 3. Check for Immediate Promotion (Instantaneous Pressure)
        # This differs from window-based promotion. The original code promoted *trades* based on baseline.
        # We preserve that logic here.
        
        if self._baseline.is_warm():
            mean, stddev = self._baseline.get_baseline()
            if stddev > 0:
                threshold = mean + (self._threshold_sigma * stddev)
                if quantity > threshold:
                    sigma = (quantity - mean) / stddev
                    # Created Promoted Event
                    event = PromotedEventInternal(
                        timestamp=timestamp,
                        symbol=symbol,
                        price=price,
                        quantity=quantity,
                        side=side,
                        baseline_mean=mean,
                        baseline_stddev=stddev,
                        sigma_distance=sigma
                    )
                    self._promoted_events.append(event)
                    self.stats['peak_pressure_events'] += 1
                    return event
            
            # If warm but not promoted
            self.stats['rejected_count'] += 1
        
        return None

    def advance_time(self, new_timestamp: float) -> None:
        """
        Explicit time tick. Can trigger window closures even without trades.
        """
        self._manage_windows(new_timestamp)

    def _manage_windows(self, current_ts: float):
        """Closes windows that have passed based on current_ts."""
        if self._current_window_start is None:
            self._current_window_start = current_ts
            return

        # Close all completed windows (could be multiple if gap is large)
        while current_ts >= self._current_window_start + self._window_seconds:
            self._close_window()
            self._current_window_start += self._window_seconds
            
            # Optimization: If gap is huge (hours), don't loop millions of times.
            # Reset if gap > 60s
            if current_ts > self._current_window_start + 60:
                self._current_window_start = current_ts
                break

    def _close_window(self):
        """Aggregate current window and update baseline."""
        self.stats['windows_processed'] += 1

        # Aggregate all symbols
        all_trades = []
        for sym_trades in self._current_windows.values():
            all_trades.extend(sym_trades)

        if not all_trades:
            # Empty window, nothing to update baseline with?
            # Or update with 0 volume? Original code skipped empty windows.
            # We skip.
            self._current_windows = {}
            # NOTE: Don't reset candles - they should persist across windows
            # for price_acceptance_ratio computation in M5
            return

        # Calculate metrics
        total_vol = sum(t['quantity'] for t in all_trades)
        weighted_price = sum(t['price'] * t['quantity'] for t in all_trades) / total_vol
        max_size = max(t['quantity'] for t in all_trades)
        count = len(all_trades)
        
        window = TradeWindow(
            window_start=self._current_window_start,
            window_end=self._current_window_start + self._window_seconds,
            trade_count=count,
            total_volume=total_vol,
            mean_price=weighted_price,
            max_trade_size=max_size,
            symbol="ALL" 
        )
        
        # Update Baseline
        self._baseline.update(window)

        # Clear buffer
        self._current_windows = {}
        # NOTE: Don't reset candles - they should persist across windows
        # for price_acceptance_ratio computation in M5

    # Read-Only Accessors
    def get_baseline_status(self) -> Dict:
        mean, std = self._baseline.get_baseline()
        return {
            'mean': mean,
            'stddev': std,
            'is_warm': self._baseline.is_warm()
        }
    
    def get_promoted_events(self) -> List[PromotedEventInternal]:
        return list(self._promoted_events) # Shallow copy
    
    def get_recent_prices(self, symbol: str, max_count: int = 100) -> List[float]:
        """
        Get recent trade prices for a symbol from current window.
        
        Used by M4 primitive computation (zone penetration, traversal velocity).
        Returns empty list if no trades in current window.
        
        Args:
            symbol: Symbol to query
            max_count: Maximum number of prices to return (most recent)
        
        Returns:
            List of prices in chronological order
        """
        if symbol not in self._current_windows:
            return []
        
        trades = self._current_windows[symbol]
        prices = [t['price'] for t in trades]

        # Return most recent max_count prices
        return prices[-max_count:]

    def _update_candle(self, symbol: str, price: float, timestamp: float) -> None:
        """
        Update OHLC candle for symbol with new price.

        Creates new candle if symbol not tracked or window rollover occurred.

        Args:
            symbol: Symbol to update
            price: Trade price
            timestamp: Trade timestamp
        """
        if symbol not in self._current_candles:
            # Initialize new candle
            self._current_candles[symbol] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'timestamp': timestamp
            }
        else:
            candle = self._current_candles[symbol]
            # Update high/low/close
            candle['high'] = max(candle['high'], price)
            candle['low'] = min(candle['low'], price)
            candle['close'] = price
            candle['timestamp'] = timestamp

    def get_current_candle(self, symbol: str) -> Optional[Dict]:
        """
        Get current OHLC candle for symbol.

        Returns:
            Dict with keys: open, high, low, close, timestamp
            None if no candle exists for symbol
        """
        return self._current_candles.get(symbol)
