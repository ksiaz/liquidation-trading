"""
Alpha Engine - Quantitative Metrics
Core calculators for VPIN and OFI.
"""

from collections import deque
import math
import logging

logger = logging.getLogger(__name__)

class VPINCalculator:
    """
    Volume-Synchronized Probability of Informed Trading (VPIN)
    
    Measures order flow toxicity by analyzing volume imbalance in 
    volume-synchronized buckets (rather than time bars).
    """
    
    def __init__(self, bucket_volume=100000, window_size=50):
        """
        Args:
            bucket_volume (float): Volume required to complete a bucket (in USD).
            window_size (int): Number of buckets involved in VPIN calculation.
        """
        self.bucket_volume = bucket_volume
        self.window_size = window_size
        
        # Current bucket state
        self.current_buy_vol = 0.0
        self.current_sell_vol = 0.0
        
        # History of completed buckets: (buy_vol, sell_vol)
        self.buckets = deque(maxlen=window_size)
        
        # Cached VPIN value
        self.current_vpin = 0.0
        self.is_ready = False
        
    def update(self, volume_usd: float, side: str):
        """
        Update with a new trade.
        
        Args:
            volume_usd: Trade size in USD.
            side: 'BUY' or 'SELL'.
        """
        remaining_vol = volume_usd
        
        # Fill buckets
        while remaining_vol > 0:
            current_total = self.current_buy_vol + self.current_sell_vol
            space_in_bucket = self.bucket_volume - current_total
            
            fill_amt = min(remaining_vol, space_in_bucket)
            
            if side.upper() == 'BUY':
                self.current_buy_vol += fill_amt
            else:
                self.current_sell_vol += fill_amt
                
            remaining_vol -= fill_amt
            
            # Check if bucket is full
            if (self.current_buy_vol + self.current_sell_vol) >= self.bucket_volume:
                self._finalize_bucket()
                logger.debug(f"VPIN Bucket Filled. New VPIN: {self.current_vpin:.4f}")  # Changed to DEBUG
                
    def _finalize_bucket(self):
        """Push current bucket to history and reset."""
        self.buckets.append((self.current_buy_vol, self.current_sell_vol))
        
        # Reset
        self.current_buy_vol = 0.0
        self.current_sell_vol = 0.0
        
        # Update VPIN if we have enough data
        if len(self.buckets) == self.window_size:
            self._recalc_vpin()
            self.is_ready = True
            
    def _recalc_vpin(self):
        """
        Calculate VPIN = sum(|buy - sell|) / sum(buy + sell) over the window.
        """
        total_imbalance = 0.0
        total_volume = 0.0
        
        for b_buy, b_sell in self.buckets:
            total_imbalance += abs(b_buy - b_sell)
            total_volume += (b_buy + b_sell)
            
        if total_volume > 0:
            self.current_vpin = total_imbalance / total_volume
        else:
            self.current_vpin = 0.0

    def get_value(self) -> float:
        """Return current VPIN metric (0.0 to 1.0)."""
        return self.current_vpin


class OFICalculator:
    """
    Order Flow Imbalance (OFI) Calculator
    
    Measures the imbalance of supply/demand updates at the Best Bid/Ask.
    Positive OFI = Buying Pressure
    Negative OFI = Selling Pressure
    """
    
    def __init__(self, window_seconds=60):
        self.window_seconds = window_seconds
        self.prev_best_bid = None # (price, size)
        self.prev_best_ask = None # (price, size)
        
        # Rolling sum
        self.ofi_samples = deque() # (timestamp, ofi_value)
        self.current_ofi_sum = 0.0
        
    def update(self, bid_price, bid_size, ask_price, ask_size, timestamp):
        """
        Update with new L2 Best Bid/Ask snapshot.
        """
        ofi_delta = 0.0
        
        # Bid Side Impact
        if self.prev_best_bid:
            p_bid_t, q_bid_t = bid_price, bid_size
            p_bid_prev, q_bid_prev = self.prev_best_bid
            
            if p_bid_t > p_bid_prev:
                ofi_delta += q_bid_t
            elif p_bid_t < p_bid_prev:
                ofi_delta -= q_bid_prev
            else: # Price unchanged
                ofi_delta += (q_bid_t - q_bid_prev)
                
        # Ask Side Impact
        if self.prev_best_ask:
            p_ask_t, q_ask_t = ask_price, ask_size
            p_ask_prev, q_ask_prev = self.prev_best_ask
            
            if p_ask_t > p_ask_prev:
                # Price moved up, supply removed at lower price
                ofi_delta += q_ask_prev
            elif p_ask_t < p_ask_prev:
                # Price moved down, supply added at lower price
                ofi_delta -= q_ask_t
            else: # Price unchanged
                # Decrease in size = supply removal (bullish) -> OFI +
                # Increase in size = supply addition (bearish) -> OFI -
                ofi_delta -= (q_ask_t - q_ask_prev)
        
        # Save state
        self.prev_best_bid = (bid_price, bid_size)
        self.prev_best_ask = (ask_price, ask_size)
        
        # Add to window
        self.ofi_samples.append((timestamp, ofi_delta))
        self.current_ofi_sum += ofi_delta
        
        # Prune old samples
        while self.ofi_samples and (timestamp - self.ofi_samples[0][0]) > self.window_seconds:
            old_ts, old_val = self.ofi_samples.popleft()
            self.current_ofi_sum -= old_val
            
    def get_value(self) -> float:
        """Return cumulative OFI over the window."""
        return self.current_ofi_sum
