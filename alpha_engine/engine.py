"""
Alpha Engine - Core System
Orchestrates data flow, metric updates, and signal generation.
"""

from typing import Dict, List, Optional, Any
from .metrics import VPINCalculator, OFICalculator
from .factors.microstructure import CascadePredictionFactor, LiquidationAbsorptionFactor
import logging

logger = logging.getLogger(__name__)

class AlphaEngine:
    """
    The central event-driven engine for generating alpha signals.
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        
        # Initialize Metrics
        self.vpin = VPINCalculator(bucket_volume=100, window_size=50) # Tweak bucket size based on asset
        self.ofi = OFICalculator(window_seconds=60)
        
        # Initialize Factors
        self.factors = [
            CascadePredictionFactor(self.vpin),
            LiquidationAbsorptionFactor(self.ofi)
        ]
        
    def on_market_data(self, data: Dict[str, Any]) -> List[Dict]:
        """
        Process incoming market data event.
        Returns list of generated signals (if any).
        """
        event_type = data.get('type')
        signals = []
        
        # 1. Update Metrics based on event type
        if event_type == 'TRADE':
            # Update VPIN
            vol = data.get('value_usd', 0)
            side = data.get('side', 'UNKNOWN')
            self.vpin.update(vol, side)
            
        elif event_type == 'ORDERBOOK_SNAPSHOT':
            # Update OFI
            self.ofi.update(
                bid_price=data.get('best_bid'),
                bid_size=data.get('bid_size'),
                ask_price=data.get('best_ask'),
                ask_size=data.get('ask_size'),
                timestamp=data.get('timestamp')
            )
        
        # 2. Evaluate Factors
        # Note: Factors might need different data subsets, but we pass full event for now
        for factor in self.factors:
            try:
                signal = factor.update(data)
                if signal:
                    # Enrich signal with metadata
                    signal['symbol'] = self.symbol
                    signal['timestamp'] = data.get('timestamp')
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error evaluating factor {factor.name}: {e}")
                
        return signals

    def get_metrics_status(self) -> Dict:
        """Return current values of all quantitative metrics."""
        return {
            'vpin': self.vpin.get_value(),
            'ofi': self.ofi.get_value()
        }
