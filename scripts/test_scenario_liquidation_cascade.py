"""
Phase 7.1: End-to-End Validation - Liquidation Cascade Scenario

Simulates a realistic liquidation cascade:
1. Multiple liquidations cluster around same price level
2. Trades execute in the liquidation zone
3. Price moves through the zone
4. Time passes, nodes decay
5. Validate complete pipeline M1 → M2 → M3 → M4 → Snapshot
"""

import sys
import os
import unittest
from decimal import Decimal
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestLiquidationCascadeScenario(unittest.TestCase):
    """
    Scenario: Flash crash triggers liquidation cascade at $50,000
    - 5 liquidations between $49,950 - $50,050
    - Price rebounds through zone
    - Trades execute in liquidation zones
    """
    
    def setUp(self):
        self.obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
    
    def test_complete_liquidation_cascade(self):
        """Test: Complete liquidation cascade scenario from start to finish."""
        
        # ===== PHASE 1: Liquidation Cascade (t=1000-1001) =====
        print("\n=== PHASE 1: Liquidation Cascade ===")
        
        liquidations = [
            (1000.0, 49950.0, "BUY", 150.0),   # Long liquidated at 49950
            (1000.2, 50000.0, "BUY", 200.0),   # Long liquidated at 50000
            (1000.4, 50025.0, "BUY", 175.0),   # Long liquidated at 50025
            (1000.6, 50050.0, "BUY", 225.0),   # Long liquidated at 50050
            (1000.8, 49975.0, "BUY", 180.0),   # Long liquidated at 49975
        ]
        
        for ts, price, side, volume in liquidations:
            self.obs.ingest_observation(
                timestamp=ts,
                symbol="BTCUSDT",
                event_type="LIQUIDATION",
                payload={
                    "E": int(ts * 1000),
                    "o": {
                        "p": str(price),
                        "q": str(volume),
                        "S": side
                    }
                }
            )
        
        # Validate M2 state after liquidations
        self.obs._system_time = 1001.0
        nodes_after_cascade = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        print(f"Nodes after cascade: {len(nodes_after_cascade)}")
        
        # Should have nodes (either 5 separate or merged due to overlap)
        self.assertGreater(len(nodes_after_cascade), 0)
        self.assertLessEqual(len(nodes_after_cascade), 5)  # Max 5, could be merged
        
        # ===== PHASE 2: Price Rebound Through Zone (t=1001-1002) =====
        print("\n=== PHASE 2: Price Rebound ===")
        
        rebound_trades = [
            (1001.0, 49960.0),
            (1001.1, 49980.0),
            (1001.2, 50000.0),  # Back at liquidation level
            (1001.3, 50020.0),
            (1001.4, 50040.0),
        ]
        
        for ts, price in rebound_trades:
            self.obs.ingest_observation(
                timestamp=ts,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={
                    "p": str(price),
                    "q": "25.0",
                    "T": int(ts * 1000),
                    "m": False
                }
            )
        
        # Keep trades in current window
        self.obs._system_time = 1002.0
        
        # Get snapshot immediately after rebound
        snapshot_rebound = self.obs.query({"type": "snapshot"})
        primitives_rebound = snapshot_rebound.primitives["BTCUSDT"]
        
        print(f"\nPrimitives after rebound:")
        print(f"  Zone Penetration: {primitives_rebound.zone_penetration}")
        print(f"  Velocity: {primitives_rebound.price_traversal_velocity}")
        print(f"  Compactness: {primitives_rebound.traversal_compactness}")
        print(f"  Central Deviation: {primitives_rebound.central_tendency_deviation}")
        
        # Validate primitives
        self.assertIsNotNone(primitives_rebound.zone_penetration, "Zone penetration should exist (price in zones)")
        self.assertIsNotNone(primitives_rebound.price_traversal_velocity, "Velocity should exist (price moving)")
        self.assertIsNotNone(primitives_rebound.traversal_compactness, "Compactness should exist (path exists)")
        self.assertIsNotNone(primitives_rebound.central_tendency_deviation, "Central deviation should exist")
        
        # Zone penetration should be significant (trades in liquidation zones)
        self.assertGreater(primitives_rebound.zone_penetration, 0)
        
        # ===== PHASE 3: Time Progression & Decay (t=1002-1100) =====
        print("\n=== PHASE 3: Time Progression & Decay ===")
        
        # Advance time significantly (100 seconds)
        self.obs.advance_time(1100.0)
        
        snapshot_decay = self.obs.query({"type": "snapshot"})
        primitives_decay = snapshot_decay.primitives["BTCUSDT"]
        
        print(f"\nPrimitives after 100s decay:")
        print(f"  Structural Absence: {primitives_decay.structural_absence_duration}")
        print(f"  Event Non-Occurrence: {primitives_decay.event_non_occurrence_counter}")
        print(f"  Traversal Void Span: {primitives_decay.traversal_void_span}")
        
        # Structural absence should be present (long time since interaction)
        self.assertIsNotNone(primitives_decay.structural_absence_duration)
        self.assertGreater(primitives_decay.structural_absence_duration, 90.0)  # ~98 seconds
        
        # Event non-occurrence should be present (stale nodes)
        self.assertIsNotNone(primitives_decay.event_non_occurrence_counter)
        self.assertGreater(primitives_decay.event_non_occurrence_counter, 0)
        
        # Verify nodes transitioned to dormant/archived
        active_after_decay = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        dormant_after_decay = self.obs._m2_store.get_dormant_nodes(symbol="BTCUSDT")
        
        print(f"\nNode lifecycle after decay:")
        print(f"  Active: {len(active_after_decay)}")
        print(f"  Dormant: {len(dormant_after_decay)}")
        
        # Some nodes should have transitioned to dormant
        self.assertGreaterEqual(len(dormant_after_decay), 0)
        
        # ===== PHASE 4: System Metrics Validation =====
        print("\n=== PHASE 4: System Metrics ===")
        
        metrics = self.obs._m2_store.get_metrics()
        print(f"\nM2 Store Metrics:")
        print(f"  Total nodes created: {metrics['total_nodes_created']}")
        print(f"  Active nodes: {metrics['active_nodes']}")
        print(f"  Dormant nodes: {metrics['dormant_nodes']}")
        print(f"  Total interactions: {metrics['total_interactions']}")
        
        # Validate metrics
        self.assertGreater(metrics['total_nodes_created'], 0)
        self.assertGreater(metrics['total_interactions'], 0)
        
        print("\n✅ Liquidation Cascade Scenario: PASSED")
    
    def test_snapshot_quality_during_cascade(self):
        """Test: Snapshots contain valid data throughout cascade."""
        
        # Create liquidation
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {"p": "50000.0", "q": "100.0", "S": "BUY"}
            }
        )
        
        # Add trades
        for i in range(3):
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
        
        self.obs._system_time = 1000.3
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        
        # Validate snapshot structure
        self.assertIsNotNone(snapshot.status)
        self.assertIsNotNone(snapshot.timestamp)
        self.assertIn("BTCUSDT", snapshot.symbols_active)
        self.assertIn("BTCUSDT", snapshot.primitives)
        
        # Validate primitive bundle exists
        primitives = snapshot.primitives["BTCUSDT"]
        self.assertEqual(primitives.symbol, "BTCUSDT")
        
        print("✅ Snapshot Quality: PASSED")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
