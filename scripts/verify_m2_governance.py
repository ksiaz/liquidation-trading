"""
Phase 5.4 Verification: M2-Governance Integration

Tests that M2 Store is populated from live observation stream.
"""

import sys
import os
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from observation.governance import ObservationSystem


class TestM2GovernanceIntegration(unittest.TestCase):
    def setUp(self):
        self.obs = ObservationSystem(allowed_symbols=["BTCUSDT", "ETHUSDT"])
    
    def test_liquidation_populates_m2(self):
        """Test: Liquidation event creates node in M2."""
        # Ingest liquidation (Binance ForceOrder format)
        self.obs.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1000000,  # Event time in ms
                "o": {
                    "p": "50000.0",
                    "q": "100.0",
                    "S": "BUY"
                }
            }
        )
        
        # Verify M2 has node
        metrics = self.obs._m2_store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 1)
        self.assertEqual(metrics['total_nodes_created'], 1)
    
    def test_trade_without_node_ignored(self):
        """Test: Trade without existing node does not create M2 node."""
        # Ingest trade (no liquidation first) - Binance AggTrade format
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
        
        # Verify M2 is empty
        metrics = self.obs._m2_store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 0)
    
    def test_trade_updates_existing_node(self):
        """Test: Trade updates existing M2 node."""
        # Create node via liquidation (Binance format)
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
        
        # Get initial trade count
        nodes = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        initial_trade_count = nodes[0].trade_execution_count
        
        # Ingest trade at overlapping price (Binance AggTrade format)
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="TRADE",
            payload={
                "p": "50020.0",  # Price
                "q": "50.0",     # Quantity
                "T": 1001000,    # Trade time in ms
                "m": True        # is_buyer_maker
            }
        )
        
        # Verify node updated
        nodes_after = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        self.assertEqual(len(nodes_after), 1)
        self.assertGreater(nodes_after[0].trade_execution_count, initial_trade_count)
        self.assertGreater(nodes_after[0].volume_total, 0.0)  # Volume should be set
    
    def test_advance_time_triggers_decay(self):
        """Test: advance_time drives M2 decay."""
        # Create node (Binance format)
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
        
        nodes = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        initial_strength = nodes[0].strength
        
        # Advance time (triggers decay)
        self.obs.advance_time(1100.0)
        
        # Verify decay applied
        nodes_after = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        self.assertLess(nodes_after[0].strength, initial_strength)
    
    def test_symbol_partitioning_via_governance(self):
        """Test: Symbol filtering respected in M2 via governance."""
        # Create BTC node (Binance format)
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
        
        # Create ETH node (Binance format)
        self.obs.ingest_observation(
            timestamp=1001.0,
            symbol="ETHUSDT",
            event_type="LIQUIDATION",
            payload={
                "E": 1001000,
                "o": {
                    "p": "3000.0",
                    "q": "50.0",
                    "S": "SELL"
                }
            }
        )
        
        # Verify partitioning
        btc_nodes = self.obs._m2_store.get_active_nodes(symbol="BTCUSDT")
        eth_nodes = self.obs._m2_store.get_active_nodes(symbol="ETHUSDT")
        
        self.assertEqual(len(btc_nodes), 1)
        self.assertEqual(len(eth_nodes), 1)
        self.assertEqual(btc_nodes[0].symbol, "BTCUSDT")
        self.assertEqual(eth_nodes[0].symbol, "ETHUSDT")
    
    def test_snapshot_includes_m2_primitives(self):
        """Test: ObservationSnapshot includes M2 primitive bundles."""
        # Create node (Binance format)
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
        
        # Get snapshot
        snapshot = self.obs.query({"type": "snapshot"})
        
        # Verify primitives dict exists
        self.assertIn("primitives", snapshot.__dict__)
        self.assertIsInstance(snapshot.primitives, dict)
        
        # For now, primitives should be None (M4 computation not fully wired)
        # But structure is present
        self.assertIn("BTCUSDT", snapshot.primitives)


if __name__ == '__main__':
    unittest.main()
