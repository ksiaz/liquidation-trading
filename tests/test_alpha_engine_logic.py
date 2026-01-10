"""
Test Alpha Engine Logic
"""

import unittest
from alpha_engine.metrics import VPINCalculator, OFICalculator
from alpha_engine.factors.microstructure import CascadePredictionFactor, LiquidationAbsorptionFactor
from alpha_engine.engine import AlphaEngine

class TestAlphaMetrics(unittest.TestCase):
    
    def test_vpin_calculation(self):
        # Bucket size = 100
        vpin = VPINCalculator(bucket_volume=100, window_size=2)
        
        # Fill bucket 1: 50 Buy, 50 Sell -> Imbalance 0. Toxic? No.
        vpin.update(50, 'BUY')
        vpin.update(50, 'SELL')
        # Bucket 1 closed. Imbalance=0. Total=100.
        
        # Fill bucket 2: 100 Buy -> Imbalance 100. Toxic? Yes.
        vpin.update(100, 'BUY')
        # Bucket 2 closed. Imbalance=100. Total=100.
        
        # Window: [B1(0), B2(100)]
        # Total Imbalance = 100
        # Total Volume = 200
        # VPIN = 0.5
        
        self.assertAlmostEqual(vpin.get_value(), 0.5)
        
    def test_ofi_calculation(self):
        ofi = OFICalculator(window_seconds=10)
        
        # Initial State: Bid 100x10, Ask 101x10
        ofi.update(100, 10, 101, 10, timestamp=1)
        
        # Update 1: Bid Size Increases to 15 (Buy Pressure +5)
        ofi.update(100, 15, 101, 10, timestamp=2)
        
        self.assertEqual(ofi.get_value(), 5.0)
        
        # Update 2: Ask Price Moves Up (Supply removed at 101 -> Bullish)
        # Prev Ask: 101x10. New Ask: 102x10.
        # OFI += Size at 101 (10)
        ofi.update(100, 15, 102, 10, timestamp=3)
        
        # Total = 5 + 10 = 15
        self.assertEqual(ofi.get_value(), 15.0)

class TestAlphaFactors(unittest.TestCase):
    
    def test_cascade_prediction(self):
        vpin = VPINCalculator(bucket_volume=100, window_size=1)
        # Create TOXIC flow (100% Sell)
        vpin.update(100, 'SELL') 
        # VPIN should be 1.0
        
        factor = CascadePredictionFactor(vpin, depth_threshold_usd=1000, vpin_threshold=0.5)
        
        # Input thin book
        data = {
            'type': 'ORDERBOOK_SNAPSHOT',
            'bid_depth_1pct': 500, # Thin!
            'price': 100
        }
        
        signal = factor.update(data)
        self.assertIsNotNone(signal)
        self.assertEqual(signal['signal_type'], 'MARKET_CRASH_RISK')
        
    def test_absoption_reversal(self):
        ofi = OFICalculator()
        
        # Mock OFI to be POSITIVE (Buying)
        # We manually inject state if possible, or just mock the object
        # Let's just use updates
        ofi.update(100, 10, 102, 10, timestamp=1)
        ofi.update(100, 1000, 102, 10, timestamp=2) # Massive bid add -> High OFI
        
        factor = LiquidationAbsorptionFactor(ofi, min_liq_vol=500)
        
        # Input Large SELL Liquidation
        data = {
            'type': 'LIQUIDATION',
            'side': 'SELL', # Forced Sell
            'value_usd': 1000,
            'price': 100
        }
        
        signal = factor.update(data)
        self.assertIsNotNone(signal)
        self.assertEqual(signal['signal_type'], 'ABSORPTION_REVERSAL')
        self.assertEqual(signal['direction'], 'LONG')

if __name__ == '__main__':
    unittest.main()
