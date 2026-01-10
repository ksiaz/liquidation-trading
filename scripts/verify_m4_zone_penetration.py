"""
Phase 6.1 Verification: Zone Penetration Primitive

Tests that M4 zone penetration is computed from M2 nodes and M3 price data.
"""

import sys
import os
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestZonePenetrationPrimitive(unittest.TestCase):
    def setUp(self):
        self.obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
    
    def test_zone_penetration_computed_when_data_present(self):
        """Test: Zone penetration is computed when M2 has nodes and M3 has prices."""
        # Step 1: Create a liquidation node (zone) at 50000
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {
                    "p": "50000.0",
                    "q": "100.0",
                    "S": "BUY"
                }
            }
        )
        
        # Step 2: Ingest trades that penetrate the zone
        # Zone is at 50000 ± 50 (49950 to 50050)
        # Trade at 50025 should penetrate
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50025.0",  # Inside zone
                "q": "10.0",
                "T": 1001000,
                "m": False
            }
        )
        
        # Step 3: Get snapshot and check primitives
        snapshot = self.obs.query({"type": "snapshot"})
        
        # Verify primitives structure
        self.assertIn("BTCUSDT", snapshot.primitives)
        btc_primitives = snapshot.primitives["BTCUSDT"]
        
        # Zone penetration should NOT be None
        self.assertIsNotNone(btc_primitives.zone_penetration)
        self.assertGreater(btc_primitives.zone_penetration, 0.0)
    
    def test_zone_penetration_none_when_no_penetration(self):
        """Test: Zone penetration is None when trades don't penetrate zone."""
        # Create node at 50000
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {
                    "p": "50000.0",
                    "q": "100.0",
                    "S": "BUY"
                }
            }
        )
        
        # Trade far from zone (60000, outside 50000 ± 50)
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "60000.0",  # Far from zone
                "q": "10.0",
                "T": 1001000,
                "m": False
            }
        )
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        btc_primitives = snapshot.primitives["BTCUSDT"]
        
        # Zone penetration should be None (no penetration detected)
        self.assertIsNone(btc_primitives.zone_penetration)
    
    def test_zone_penetration_none_when_no_nodes(self):
        """Test: Zone penetration is None when M2 has no nodes."""
        # No liquidations, only trade
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50000.0",
                "q": "10.0",
                "T": 1001000,
                "m": False
            }
        )
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        btc_primitives = snapshot.primitives["BTCUSDT"]
        
        # Zone penetration should be None (no zones to penetrate)
        self.assertIsNone(btc_primitives.zone_penetration)
    
    def test_zone_penetration_none_when_no_trades(self):
        """Test: Zone penetration is None when M3 has no price data."""
        # Create node
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {
                    "p": "50000.0",
                    "q": "100.0",
                    "S": "BUY"
                }
            }
        )
        
        # No trades - get snapshot immediately
        snapshot = self.obs.query({"type": "snapshot"})
        btc_primitives = snapshot.primitives["BTCUSDT"]
        
        # Zone penetration should be None (no price history)
        self.assertIsNone(btc_primitives.zone_penetration)
    
    def test_max_penetration_across_multiple_zones(self):
        """Test: Computes maximum penetration across multiple zones."""
        # Create two zones
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {
                    "p": "50000.0",
                    "q": "100.0",
                    "S": "BUY"
                }
            }
        )
        
        self.obs.ingest_observation(
            timestamp=1002.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1002000,
                "o": {
                    "p": "51000.0",
                    "q": "100.0",
                    "S": "SELL"
                }
            }
        )
        
        # Trade that penetrates first zone deeply
        self.obs.ingest_observation(
            timestamp=1003.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50000.0",  # Center of first zone (max penetration = 50)
                "q": "10.0",
                "T": 1003000,
                "m": False
            }
        )
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        btc_primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have penetration value
        self.assertIsNotNone(btc_primitives.zone_penetration)
        # Max penetration should be 50 (half of band width of 100)
        self.assertAlmostEqual(btc_primitives.zone_penetration, 50.0, places=1)


if __name__ == '__main__':
    unittest.main()
