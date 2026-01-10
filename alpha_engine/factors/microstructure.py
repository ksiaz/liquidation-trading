"""
Alpha Engine - Microstructure Factors
Logic that combines quantitative metrics into actionable signals.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from ..metrics import VPINCalculator, OFICalculator
import logging

logger = logging.getLogger(__name__)

class AlphaFactor(ABC):
    """Base class for all alpha factors."""
    
    def __init__(self, name: str):
        self.name = name
        
    @abstractmethod
    def update(self, data: Dict[str, Any]) -> Optional[Dict]:
        """
        Process new data and return a signal if generated.
        Args:
            data: Dictionary containing event data (L2, Trade, Liq, etc.)
        Returns:
            Signal dict or None
        """
        pass

class CascadePredictionFactor(AlphaFactor):
    """
    Predicts price cascades (crashes) by combining Toxicity (VPIN) with Liquidity Thinness.
    
    Logic:
    - If VPIN > threshold (Toxic Flow)
    - AND Bid Depth < threshold (Thin Liquidity)
    - THEN Signal: CASCADE_RISK_HIGH
    """
    
    def __init__(self, vpin_calc: VPINCalculator, depth_threshold_usd=500000, vpin_threshold=0.7):
        super().__init__("CascadePrediction")
        self.vpin_calc = vpin_calc
        self.depth_threshold = depth_threshold_usd
        self.vpin_threshold = vpin_threshold
        
    def update(self, data: Dict[str, Any]) -> Optional[Dict]:
        # We need Order Book snapshots
        if data.get('type') != 'ORDERBOOK_SNAPSHOT':
            return None
            
        current_vpin = self.vpin_calc.get_value()
        bid_depth_1pct = data.get('bid_depth_1pct', 0)
        price = data.get('price', 0)
        
        # Check conditions
        if current_vpin > self.vpin_threshold and bid_depth_1pct < self.depth_threshold:
            return {
                'factor': self.name,
                'signal_type': 'MARKET_CRASH_RISK',
                'direction': 'SHORT',
                'confidence': 0.85 + (current_vpin - self.vpin_threshold), # Scale confidence
                'score': current_vpin,
                'reason': f"High Toxicity (VPIN={current_vpin:.2f}) + Thin Liquidity (${bid_depth_1pct:,.0f})",
                'price': price
            }
            
        return None

class LiquidationAbsorptionFactor(AlphaFactor):
    """
    Detects absorption of liquidation cascades.
    
    Logic:
    - If Large Liquidation Sell Volume detected
    - BUT OFI is Positive or Neutral (Buying Pressure)
    - THEN Signal: ABSORPTION_BUY
    """
    
    def __init__(self, ofi_calc: OFICalculator, min_liq_vol=100000):
        super().__init__("LiquidationAbsorption")
        self.ofi_calc = ofi_calc
        self.min_liq_vol = min_liq_vol
        
    def update(self, data: Dict[str, Any]) -> Optional[Dict]:
        # We process 'LIQUIDATION' events here
        if data.get('type') != 'LIQUIDATION':
            return None
            
        liq_side = data.get('side') # 'SELL' or 'BUY' (This is the maker side? No, Liq is Taker)
        # Usually liq data: side=SELL means forced sell.
        
        vol_usd = data.get('value_usd', 0)
        price = data.get('price', 0)
        
        if vol_usd < self.min_liq_vol:
            return None
            
        current_ofi = self.ofi_calc.get_value()
        
        # Case 1: Forced Selling (Price should drop) but OFI is Positive (Buying Pressure)
        if liq_side == 'SELL' and current_ofi > 0:
            return {
                'factor': self.name,
                'signal_type': 'ABSORPTION_REVERSAL',
                'direction': 'LONG',
                'confidence': 0.9,
                'score': current_ofi,
                'reason': f"Large Sell Liq (${vol_usd:,.0f}) absorbed by Buying Pressure (OFI={current_ofi:,.0f})",
                'price': price
            }
            
        # Case 2: Forced Buying (Price should pop) but OFI is Negative (Selling Pressure)
        if liq_side == 'BUY' and current_ofi < 0:
             return {
                'factor': self.name,
                'signal_type': 'ABSORPTION_REVERSAL',
                'direction': 'SHORT',
                'confidence': 0.9,
                'score': abs(current_ofi),
                'reason': f"Large Buy Liq (${vol_usd:,.0f}) absorbed by Selling Pressure (OFI={current_ofi:,.0f})",
                'price': price
            }
            
        return None
