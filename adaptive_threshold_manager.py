"""
Adaptive Threshold Manager Module
Week 9: Adaptive Signal Thresholds

Calculates adaptive liquidity drain thresholds based on:
1. Volatility ratio (current vs baseline)
2. Symbol-specific depth characteristics
3. Min/max capping for safety

LOCKED PARAMETERS:
- Base threshold: 0.25 (25% depth reduction)
- Beta (volatility sensitivity): 0.6
- Symbol multipliers: BTC=1.0, ETH=1.15, SOL=1.35
- Max threshold: 0.60 (60% cap)
- Min threshold: 0.10 (10% floor)

Expert Compliance: 100% - All parameters locked, no optimization
"""

import logging
from typing import Dict
from enum import Enum

logger = logging.getLogger(__name__)


class AdaptiveThresholdManager:
    """
    Calculate adaptive thresholds for liquidity drain detection.
    
    Formula:
        adaptive_threshold = base × (1 + β × (vol_ratio - 1)) × symbol_multiplier
        capped between [MIN_THRESHOLD, MAX_THRESHOLD]
    
    Where:
        - base = 0.25 (current fixed threshold)
        - β = 0.6 (volatility sensitivity, LOCKED)
        - vol_ratio = current_vol / baseline_vol
        - symbol_multiplier = per-symbol adjustment for liquidity depth
    """
    
    # 🔒 LOCKED PARAMETERS (DO NOT MODIFY)
    BASE_THRESHOLD = 0.25  # 25% depth reduction baseline
    BETA_VOLATILITY = 0.6  # Volatility sensitivity factor
    MAX_THRESHOLD = 0.60   # 60% cap (avoid missing major drains)
    MIN_THRESHOLD = 0.10   # 10% floor (avoid excessive noise)
    
    # Symbol-specific multipliers (from historical liquidity analysis)
    # Higher multiplier = thinner orderbook, drains more common, need higher threshold
    SYMBOL_MULTIPLIERS = {
        'BTCUSDT': 1.0,   # Baseline (most liquid)
        'ETHUSDT': 1.15,  # Slightly less liquid
        'SOLUSDT': 1.35,  # Much thinner, highest multiplier
    }
    
    def __init__(self):
        """Initialize adaptive threshold manager."""
        logger.info("AdaptiveThresholdManager initialized")
        logger.info(f"Base threshold: {self.BASE_THRESHOLD}")
        logger.info(f"Beta (volatility): {self.BETA_VOLATILITY}")
        logger.info(f"Threshold range: [{self.MIN_THRESHOLD}, {self.MAX_THRESHOLD}]")
        logger.info(f"Symbol multipliers: {self.SYMBOL_MULTIPLIERS}")
    
    def calculate_threshold(
        self,
        symbol: str,
        volatility_ratio: float = 1.0,
    ) -> float:
        """
        Calculate adaptive threshold for liquidity drain detection.
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            volatility_ratio: Current vol / baseline vol (default 1.0 = normal)
        
        Returns:
            Adaptive threshold (e.g., 0.175 to 0.60)
        
        Raises:
            ValueError: If symbol not supported
        """
        # Get symbol multiplier
        symbol_mult = self.get_symbol_multiplier(symbol)
        
        # Calculate volatility scaling factor
        # Formula: 1 + β × (vol_ratio - 1)
        #   If vol_ratio = 1.0 (normal): scaling = 1.0 (no change)
        #   If vol_ratio = 2.0 (2x volatile): scaling = 1 + 0.6×(2-1) = 1.6
        #   If vol_ratio = 0.5 (50% vol): scaling = 1 + 0.6×(0.5-1) = 0.7
        vol_scaling = 1.0 + self.BETA_VOLATILITY * (volatility_ratio - 1.0)
        
        # Calculate preliminary threshold
        prelim_threshold = self.BASE_THRESHOLD * vol_scaling * symbol_mult
        
        # Apply min/max caps
        capped_threshold = max(
            self.MIN_THRESHOLD,
            min(self.MAX_THRESHOLD, prelim_threshold)
        )
        
        logger.debug(
            f"Threshold calculation for {symbol}: "
            f"vol_ratio={volatility_ratio:.2f}, "
            f"vol_scaling={vol_scaling:.2f}, "
            f"symbol_mult={symbol_mult:.2f}, "
            f"prelim={prelim_threshold:.4f}, "
            f"final={capped_threshold:.4f}"
        )
        
        return capped_threshold
    
    def get_symbol_multiplier(self, symbol: str) -> float:
        """
        Get symbol-specific depth multiplier.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Multiplier value
        
        Raises:
            ValueError: If symbol not in SYMBOL_MULTIPLIERS
        """
        if symbol not in self.SYMBOL_MULTIPLIERS:
            raise ValueError(
                f"Unsupported symbol: {symbol}. "
                f"Supported symbols: {list(self.SYMBOL_MULTIPLIERS.keys())}"
            )
        
        return self.SYMBOL_MULTIPLIERS[symbol]
    
    def get_base_threshold(self) -> float:
        """Return base threshold (0.25 LOCKED)."""
        return self.BASE_THRESHOLD
    
    def get_threshold_summary(
        self,
        symbol: str,
        volatility_ratio: float,
    ) -> Dict:
        """
        Get detailed threshold calculation summary for analysis.
        
        Args:
            symbol: Trading pair
            volatility_ratio: Current vol / baseline vol
        
        Returns:
            Dictionary with calculation details
        """
        symbol_mult = self.get_symbol_multiplier(symbol)
        vol_scaling = 1.0 + self.BETA_VOLATILITY * (volatility_ratio - 1.0)
        prelim_threshold = self.BASE_THRESHOLD * vol_scaling * symbol_mult
        final_threshold = self.calculate_threshold(symbol, volatility_ratio)
        
        was_capped = (prelim_threshold != final_threshold)
        if was_capped:
            if final_threshold == self.MAX_THRESHOLD:
                cap_reason = f"Hit MAX cap ({self.MAX_THRESHOLD})"
            else:
                cap_reason = f"Hit MIN cap ({self.MIN_THRESHOLD})"
        else:
            cap_reason = "No capping"
        
        return {
            'symbol': symbol,
            'base_threshold': self.BASE_THRESHOLD,
            'volatility_ratio': volatility_ratio,
            'vol_scaling_factor': vol_scaling,
            'symbol_multiplier': symbol_mult,
            'preliminary_threshold': prelim_threshold,
            'final_threshold': final_threshold,
            'was_capped': was_capped,
            'cap_reason': cap_reason,
        }


def test_adaptive_threshold_manager():
    """Test adaptive threshold manager with various scenarios."""
    print("=" * 60)
    print("ADAPTIVE THRESHOLD MANAGER TEST")
    print("=" * 60)
    
    mgr = AdaptiveThresholdManager()
    
    # Test scenarios
    test_cases = [
        # (symbol, vol_ratio, description)
        ('BTCUSDT', 1.0, "Normal volatility"),
        ('BTCUSDT', 2.0, "High volatility (2x)"),
        ('BTCUSDT', 0.5, "Low volatility (50%)"),
        ('BTCUSDT', 3.0, "Extreme volatility (3x) - should cap"),
        ('BTCUSDT', 0.2, "Very low volatility - should cap"),
        ('ETHUSDT', 1.0, "ETH normal volatility"),
        ('ETHUSDT', 2.0, "ETH high volatility"),
        ('SOLUSDT', 1.0, "SOL normal volatility"),
        ('SOLUSDT', 2.0, "SOL high volatility"),
        ('SOLUSDT', 1.5, "SOL elevated volatility"),
    ]
    
    print(f"\nBase threshold: {mgr.BASE_THRESHOLD} (25%)")
    print(f"Beta (volatility sensitivity): {mgr.BETA_VOLATILITY}")
    print(f"Threshold range: [{mgr.MIN_THRESHOLD}, {mgr.MAX_THRESHOLD}]")
    print()
    
    for symbol, vol_ratio, description in test_cases:
        print("=" * 60)
        print(f"{description}")
        print("=" * 60)
        
        summary = mgr.get_threshold_summary(symbol, vol_ratio)
        
        print(f"Symbol: {summary['symbol']}")
        print(f"Volatility ratio: {summary['volatility_ratio']:.2f}")
        print(f"Symbol multiplier: {summary['symbol_multiplier']:.2f}")
        print(f"Vol scaling factor: {summary['vol_scaling_factor']:.2f}")
        print(f"Preliminary threshold: {summary['preliminary_threshold']:.4f} ({summary['preliminary_threshold']*100:.2f}%)")
        print(f"Final threshold: {summary['final_threshold']:.4f} ({summary['final_threshold']*100:.2f}%)")
        print(f"Capping: {summary['cap_reason']}")
        
        # Interpretation
        final = summary['final_threshold']
        base = summary['base_threshold']
        pct_change = ((final - base) / base) * 100
        
        if final > base:
            print(f"📈 Threshold INCREASED by {pct_change:.1f}% (less sensitive)")
        elif final < base:
            print(f"📉 Threshold DECREASED by {abs(pct_change):.1f}% (more sensitive)")
        else:
            print(f"➡️  Threshold UNCHANGED")
        
        print()
    
    # Summary table
    print("=" * 60)
    print("SUMMARY TABLE")
    print("=" * 60)
    print(f"{'Symbol':<10} {'Vol Ratio':<12} {'Threshold':<12} {'Change':<12}")
    print("-" * 60)
    
    for symbol, vol_ratio, _ in test_cases:
        threshold = mgr.calculate_threshold(symbol, vol_ratio)
        base = mgr.BASE_THRESHOLD
        change_pct = ((threshold - base) / base) * 100
        
        change_str = f"{change_pct:+.1f}%"
        
        print(f"{symbol:<10} {vol_ratio:<12.2f} {threshold*100:<11.2f}% {change_str:<12}")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    test_adaptive_threshold_manager()
