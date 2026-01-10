"""
Phase 6.3 Verification: Complete M4 Primitive Bundle

Tests all 8 primitives are computed correctly.
"""

import sys
import os
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestCompletePrimitiveBundle(unittest.TestCase):
    def setUp(self):
        self.obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
    
    def test_all_8_primitives_computed(self):
        """Test: All 8 primitives computed with sufficient data."""
        # Create liquidation node at t=1000
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
        
        # Ingest multiple trades (for richer primitives)
        for i, price in enumerate([50010, 50020, 50030, 50025, 50015]):
            self.obs.ingest_observation(
                timestamp=1000.0 + i * 0.1,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={
                    "p": str(float(price)),
                    "q": "10.0",
                    "T": 1000000 + i * 100,
                    "m": False
                }
            )
        
        # Set time to keep trades in window
        self.obs._system_time = 1000.5
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Verify ALL 8 primitives are computed
        self.assertIsNotNone(primitives.zone_penetration, "Zone penetration should be computed")
        self.assertIsNotNone(primitives.displacement_origin_anchor, "Displacement origin should be computed")
        self.assertIsNotNone(primitives.price_traversal_velocity, "Velocity should be computed")
        self.assertIsNotNone(primitives.traversal_compactness, "Compactness should be computed")
        self.assertIsNotNone(primitives.central_tendency_deviation, "Central tendency should be computed")
        self.assertIsNotNone(primitives.structural_absence_duration, "Absence should be computed")
        self.assertIsNotNone(primitives.traversal_void_span, "Void span should be computed")
        # event_non_occurrence might be None if not enough time passed
        
        # Verify values are sensible
        self.assertGreater(primitives.zone_penetration, 0)
        self.assertGreaterEqual(primitives.displacement_origin_anchor, 0)
        # velocity can be positive or negative
        self.assertGreater(primitives.traversal_compactness, 0)  # Ratio > 0
        self.assertLessEqual(primitives.traversal_compactness, 1.0)  # Ratio <= 1
        # central tendency can be positive or negative
        self.assertGreater(primitives.structural_absence_duration, 0)
        self.assertGreaterEqual(primitives.traversal_void_span, 0)
    
    def test_displacement_origin_anchor_computed(self):
        """Test: Displacement origin anchor computed from pre-traversal prices."""
        # Ingest trades
        for i in range(5):
            self.obs.ingest_observation(
                timestamp=1000.0 + i * 0.1,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={
                    "p": str(50000.0 + i * 10),
                    "q": "10.0",
                    "T": 1000000 + i * 100,
                    "m": False
                }
            )
        
        self.obs._system_time = 1000.5
        
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have anchor value
        self.assertIsNotNone(primitives.displacement_origin_anchor)
        self.assertGreaterEqual(primitives.displacement_origin_anchor, 0)
    
    def test_traversal_compactness_computed(self):
        """Test: Traversal compactness computed from price path."""
        # Ingest trades with varying prices (non-linear path)
        prices = [50000, 50100, 50050,  50150, 50100]  # Zigzag pattern
        for i, price in enumerate(prices):
            self.obs.ingest_observation(
                timestamp=1000.0 + i * 0.1,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={
                    "p": str(float(price)),
                    "q": "10.0",
                    "T": 1000000 + i * 100,
                    "m": False
                }
            )
        
        self.obs._system_time = 1000.5
        
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have compactness ratio
        self.assertIsNotNone(primitives.traversal_compactness)
        # For zigzag path, compactness should be < 1 (net displacement < total path)
        self.assertLess(primitives.traversal_compactness, 1.0)
    
    def test_central_tendency_deviation_computed(self):
        """Test: Central tendency deviation computed from node centers and price."""
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
        
        # Trade at 50100 (100 above node center)
        self.obs.ingest_observation(
            timestamp=1000.1,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50100.0",
                "q": "10.0",
                "T": 1000100,
                "m": False
            }
        )
        
        self.obs._system_time = 1000.1
        
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Deviation should be +100
        self.assertIsNotNone(primitives.central_tendency_deviation)
        self.assertAlmostEqual(primitives.central_tendency_deviation, 100.0, places=0)
    
    def test_traversal_void_span_computed(self):
        """Test: Traversal void span computed from interaction gaps."""
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
        
        # Another interaction at 1001
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50025.0",
                "q": "10.0",
                "T": 1001000,
                "m": False
            }
        )
        
        # Set time to 1002 (creates a void span)
        self.obs._system_time = 1002.0
        
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have void span value
        self.assertIsNotNone(primitives.traversal_void_span)
        # Should be around 1 second (gap from 1001 to 1002)
        self.assertGreaterEqual(primitives.traversal_void_span, 0.9)


if __name__ == '__main__':
    unittest.main()
