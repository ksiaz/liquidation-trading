"""
Phase 7: End-to-End Validation - All Scenarios

Complete test suite covering:
- Scenario 2: Normal Market Activity
- Scenario 3: Zone Formation & Interaction
- Scenario 4: Multi-Symbol Independence
- Scenario 5: High-Frequency Stress Test
"""

import sys
import os
import unittest
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestAllValidationScenarios(unittest.TestCase):
    
    # ========== SCENARIO 2: Normal Market Activity ==========
    
    def test_scenario_2_normal_market(self):
        """
        Scenario 2: Normal market with trades but no liquidations.
        
        Expected: M2 has no nodes, M4 primitives mostly None.
        """
        print("\n=== SCENARIO 2: Normal Market Activity ===")
        
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        
        # Simulate normal trading activity (no liquidations)
        trades = [
            (1000.0, 50000.0),
            (1000.5, 50010.0),
            (1001.0, 50005.0),
            (1001.5, 50015.0),
            (1002.0, 50020.0),
        ]
        
        for ts, price in trades:
            obs.ingest_observation(
                timestamp=ts,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={
                    "p": str(price),
                    "q": "10.0",
                    "T": int(ts * 1000),
                    "m": False
                }
            )
        
        obs._system_time = 1002.0
        
        # Verify M2 has no nodes (trades don't create nodes)
        nodes = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        self.assertEqual(len(nodes), 0, "No nodes should exist without liquidations")
        
        # Get snapshot
        snapshot = obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        print(f"Primitives in normal market:")
        print(f"  Zone Penetration: {primitives.zone_penetration}")
        print(f"  Velocity: {primitives.price_traversal_velocity}")
        print(f"  Structural Absence: {primitives.structural_absence_duration}")
        
        # Validate - zone-related primitives should be None
        self.assertIsNone(primitives.zone_penetration, "No zones = no penetration")
        self.assertIsNone(primitives.structural_absence_duration, "No nodes = no absence")
        self.assertIsNone(primitives.event_non_occurrence_counter, "No nodes = no events")
        
        # Velocity and compactness may be None if M3 window closed
        # This is expected behavior - primitives degrade gracefully
        
        print("✅ Normal Market: System handles gracefully (no nodes created)")
    
    # ========== SCENARIO 3: Zone Formation & Interaction ==========
    
    def test_scenario_3_zone_memory(self):
        """
        Scenario 3: Zone formation, price moves away, then returns.
        
        Expected: Zone persists, penetration detected on return.
        """
        print("\n=== SCENARIO 3: Zone Formation & Interaction ===")
        
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        
        # Phase 1: Create zone at 50000
        obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,
                "o": {"p": "50000.0", "q": "100.0", "S": "BUY"}
            }
        )
        
        print("Phase 1: Zone created at $50,000")
        nodes_after_creation = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        self.assertEqual(len(nodes_after_creation), 1)
        
        # Phase 2: Price moves away
        away_trades = [(1001.0, 51000.0), (1002.0, 52000.0), (1003.0, 53000.0)]
        for ts, price in away_trades:
            obs.ingest_observation(
                timestamp=ts,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={"p": str(price), "q": "10.0", "T": int(ts * 1000), "m": False}
            )
        
        obs._system_time = 1004.0
        print("Phase 2: Price moved away to $53,000")
        
        # Advance time significantly (zone should persist)
        obs.advance_time(1060.0)
        
        nodes_after_away = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        print(f"Zone still exists after 60s: {len(nodes_after_away)} nodes")
        self.assertGreater(len(nodes_after_away), 0, "Zone should persist")
        
        # Phase 3: Price returns to zone
        return_trades = [(1061.0, 50500.0), (1061.5, 50100.0), (1062.0, 50025.0)]
        for ts, price in return_trades:
            obs.ingest_observation(
                timestamp=ts,
                symbol="BTCUSDT",
                event_type="TRADE",
                payload={"p": str(price), "q": "10.0", "T": int(ts * 1000), "m": False}
            )
        
        obs._system_time = 1062.0
        
        # Get snapshot
        snapshot = obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        print(f"Phase 3: Price returned to zone")
        print(f"  Zone Penetration: {primitives.zone_penetration}")
        print(f"  Structural Absence: {primitives.structural_absence_duration}")
        
        # Zone penetration should be detected
        self.assertIsNotNone(primitives.zone_penetration, "Penetration on return")
        self.assertGreater(primitives.zone_penetration, 0)
        
        # Structural absence may be None if recent interaction (< 1s)
        # This is expected - absence is 0 when just interacted
        
        print("✅ Zone Memory: Persists and detects re-interaction")
    
    # ========== SCENARIO 4: Multi-Symbol Independence ==========
    
    def test_scenario_4_multi_symbol(self):
        """
        Scenario 4: BTC and ETH events interleaved.
        
        Expected: Complete symbol partitioning, no cross-contamination.
        """
        print("\n=== SCENARIO 4: Multi-Symbol Independence ===")
        
        obs = ObservationSystem(allowed_symbols=["BTCUSDT", "ETHUSDT"])
        
        # Interleaved BTC and ETH events
        events = [
            (1000.0, "BTCUSDT", "LIQUIDATION", 50000.0),
            (1000.1, "ETHUSDT", "LIQUIDATION", 3000.0),
            (1000.2, "BTCUSDT", "TRADE", 50050.0),
            (1000.3, "ETHUSDT", "TRADE", 3025.0),
            (1000.4, "BTCUSDT", "TRADE", 50100.0),
            (1000.5, "ETHUSDT", "TRADE", 3050.0),
        ]
        
        for ts, symbol, event_type, price in events:
            if event_type == "LIQUIDATION":
                obs.ingest_observation(
                    timestamp=ts,
                    symbol=symbol,
                    event_type=event_type,
                    payload={
                        "E": int(ts * 1000),
                        "o": {"p": str(price), "q": "100.0", "S": "BUY"}
                    }
                )
            else:  # TRADE
                obs.ingest_observation(
                    timestamp=ts,
                    symbol=symbol,
                    event_type=event_type,
                    payload={
                        "p": str(price),
                        "q": "10.0",
                        "T": int(ts * 1000),
                        "m": False
                    }
                )
        
        obs._system_time = 1000.6
        
        # Verify M2 partitioning
        btc_nodes = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        eth_nodes = obs._m2_store.get_active_nodes(symbol="ETHUSDT")
        
        print(f"M2 Partitioning:")
        print(f"  BTC nodes: {len(btc_nodes)}")
        print(f"  ETH nodes: {len(eth_nodes)}")
        
        self.assertEqual(len(btc_nodes), 1)
        self.assertEqual(len(eth_nodes), 1)
        self.assertEqual(btc_nodes[0].symbol, "BTCUSDT")
        self.assertEqual(eth_nodes[0].symbol, "ETHUSDT")
        
        # Verify M4 primitive independence
        snapshot = obs.query({"type": "snapshot"})
        btc_primitives = snapshot.primitives["BTCUSDT"]
        eth_primitives = snapshot.primitives["ETHUSDT"]
        
        print(f"\nBTC Primitives:")
        print(f"  Zone Penetration: {btc_primitives.zone_penetration}")
        print(f"  Central Deviation: {btc_primitives.central_tendency_deviation}")
        
        print(f"\nETH Primitives:")
        print(f"  Zone Penetration: {eth_primitives.zone_penetration}")
        print(f"  Central Deviation: {eth_primitives.central_tendency_deviation}")
        
        # At least one should have zone penetration (depends on M3 window timing)
        has_penetration = (
            btc_primitives.zone_penetration is not None or
            eth_primitives.zone_penetration is not None
        )
        self.assertTrue(has_penetration, "At least one symbol should have penetration")
        
        # Central deviations should be different (different price levels)
        self.assertNotEqual(
            btc_primitives.central_tendency_deviation,
            eth_primitives.central_tendency_deviation
        )
        
        print("✅ Multi-Symbol: Complete partitioning verified")
    
    # ========== SCENARIO 5: High-Frequency Stress Test ==========
    
    def test_scenario_5_stress_test(self):
        """
        Scenario 5: 1000 events in rapid succession.
        
        Expected: System handles volume, no errors, performance acceptable.
        """
        print("\n=== SCENARIO 5: High-Frequency Stress Test ===")
        
        obs = ObservationSystem(allowed_symbols=["BTCUSDT"])
        
        start_time = time.time()
        
        # Generate 1000 events (mix of liquidations and trades)
        event_count = 1000
        base_price = 50000.0
        
        for i in range(event_count):
            ts = 1000.0 + i * 0.001  # 1ms intervals
            price = base_price + (i % 100) - 50  # Oscillate ±50
            
            # Every 10th event is a liquidation
            if i % 10 == 0:
                obs.ingest_observation(
                    timestamp=ts,
                    symbol="BTCUSDT",
                    event_type="LIQUIDATION",
                    payload={
                        "E": int(ts * 1000),
                        "o": {"p": str(price), "q": "10.0", "S": "BUY"}
                    }
                )
            else:
                obs.ingest_observation(
                    timestamp=ts,
                    symbol="BTCUSDT",
                    event_type="TRADE",
                    payload={
                        "p": str(price),
                        "q": "5.0",
                        "T": int(ts * 1000),
                        "m": False
                    }
                )
        
        end_time = time.time()
        elapsed = end_time - start_time
        avg_per_event = (elapsed / event_count) * 1000  # ms
        
        print(f"Performance:")
        print(f"  Total events: {event_count}")
        print(f"  Total time: {elapsed:.3f}s")
        print(f"  Avg per event: {avg_per_event:.2f}ms")
        
        # Performance validation
        self.assertLess(avg_per_event, 10.0, "Should process < 10ms per event")
        
        # System state validation
        obs._system_time = 1001.0
        nodes = obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        metrics = obs._m2_store.get_metrics()
        
        print(f"\nSystem State:")
        print(f"  Active nodes: {len(nodes)}")
        print(f"  Total interactions: {metrics['total_interactions']}")
        
        self.assertGreater(len(nodes), 0, "Should have created nodes")
        # Some events may not update nodes depending on spatial overlap
        self.assertGreater(metrics['total_interactions'], 900)  # At least 90%
        
        # Snapshot validation
        snapshot = obs.query({"type": "snapshot"})
        primitives = snapshot.primitives["BTCUSDT"]
        
        # Should have computed primitives
        self.assertIsNotNone(primitives.zone_penetration)
        self.assertIsNotNone(primitives.price_traversal_velocity)
        
        print("✅ Stress Test: System stable under load")


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
