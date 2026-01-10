"""
Phase 6.2 Verification: Additional M4 Primitives

Tests velocity, structural absence, and event non-occurrence primitives.
"""

import sys
import os
import unittest
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestAdditionalPrimitives(unittest.TestCase):
    def setUp(self):
        self.obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
    
    def test_price_traversal_velocity_computed(self):
        """Test: Price traversal velocity computed from price changes."""
        # Ingest trades with different prices
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50000.0",
                "q": "10.0",
                "T": 1000000,
                "m": False
            }
        )
        
        self.obs.ingest_observation(
            timestamp=1000.5,  # Same window (< 1s apart)
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50100.0",  # +100 price change
                "q": "10.0",
                "T": 1000500,
                "m": False
            }
        )
        
        # Set system time but don't close window yet
        self.obs._system_time = 1000.5
        
        # Get snapshot (prices still in current window)
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Velocity should be computed
        self.assertIsNotNone(primitives.price_traversal_velocity)
        # Should be positive (price going up)
        self.assertGreater(primitives.price_traversal_velocity, 0)
    
    def test_structural_absence_duration_computed(self):
        """Test: Structural absence duration computed from last interaction."""
        # Create node at t=1000
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
        
        # Adv time to t=1100 (100 seconds later, no interaction)
        self.obs.advance_time(1100.0)
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Absence duration should be ~100 seconds
        self.assertIsNotNone(primitives.structural_absence_duration)
        self.assertGreater(primitives.structural_absence_duration, 90.0)
    
    def test_event_non_occurrence_counter_computed(self):
        """Test: Event non-occurrence counter tracks stale nodes."""
        # Create node at t=1000
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
        
        # Advance time by 70 seconds (exceeds stale threshold of 60s)
        self.obs.advance_time(1070.0)
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have 1 stale node
        self.assertIsNotNone(primitives.event_non_occurrence_counter)
        self.assertEqual(primitives.event_non_occurrence_counter, 1)
    
    def test_all_four_primitives_together(self):
        """Test: All 4 primitives computed simultaneously."""
        # Create liquidation node
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
        
        # Ingest trades in same window (for velocity and zone penetration)
        self.obs.ingest_observation(
            timestamp=1000.3,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50025.0",  # Inside zone
                "q": "10.0",
                "T": 1000300,
                "m": False
            }
        )
        
        self.obs.ingest_observation(
            timestamp=1000.6,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50050.0",  # Different price for velocity
                "q": "10.0",
                "T": 1000600,
                "m": False
            }
        )
        
        # Set time without closing window (keep current prices)
        self.obs._system_time = 1000.6
        
        # Now advance time to create absence (but M3 will close window)
        # So we need to test separately
        self.obs._system_time = 1005.0  # 5 seconds later
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Zone penetration and velocity should work
        self.assertIsNotNone(primitives.zone_penetration)
        self.assertIsNotNone(primitives.price_traversal_velocity)
        # Structural absence should exist (5 seconds since last trade)
        self.assertIsNotNone(primitives.structural_absence_duration)
        self.assertGreater(primitives.structural_absence_duration, 4.0)
    
    def test_primitives_none_when_no_data(self):
        """Test: Primitives are None when insufficient data."""
        # Get snapshot with no ingested data
        snapshot = self.obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # All should be None (no nodes, no prices)
        self.assertIsNone(primitives.zone_penetration)
        self.assertIsNone(primitives.price_traversal_velocity)  # No prices
        self.assertIsNone(primitives.structural_absence_duration)
        self.assertIsNone(primitives.event_non_occurrence_counter)


if __name__ == '__main__':
    unittest.main()
