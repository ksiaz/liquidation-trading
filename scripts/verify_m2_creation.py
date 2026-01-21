"""
Phase 5.2 Verification: Node Creation Logic

Tests constitutional constraints:
1. Nodes created ONLY on liquidations
2. Trades DO NOT create nodes
3. Spatial matching enforced
4. Symbol partitioning enforced
5. Decay and lifecycle transitions
"""

import sys
import os
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory.m2_continuity_store import ContinuityMemoryStore


class TestNodeCreationLogic(unittest.TestCase):
    def setUp(self):
        self.store = ContinuityMemoryStore()
    
    def test_liquidation_creates_node(self):
        """Test: Liquidation event creates new node."""
        node = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        self.assertIsNotNone(node)
        self.assertEqual(node.symbol, "BTCUSDT")
        self.assertEqual(node.price_center, 50000.0)
        self.assertEqual(node.creation_reason, "liquidation_BUY")
        
        # Verify node is in active store
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 1)
        self.assertEqual(metrics['total_nodes_created'], 1)
    
    def test_trade_does_not_create_node(self):
        """Test: Trade event without existing node does NOT create node."""
        node = self.store.ingest_trade(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            is_buyer_maker=False,
            timestamp=1000.0
        )
        
        self.assertIsNone(node)
        
        # Verify no nodes created
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 0)
        self.assertEqual(metrics['total_nodes_created'], 0)
    
    def test_trade_updates_existing_node(self):
        """Test: Trade updates existing node (spatial overlap)."""
        # Create node via liquidation
        liq_node = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        initial_volume = liq_node.volume_total
        
        # Trade at overlapping price (within band)
        trade_node = self.store.ingest_trade(
            symbol="BTCUSDT",
            price=50050.0,  # Within 100.0 band
            side="SELL",
            volume=50.0,
            is_buyer_maker=True,
            timestamp=1001.0
        )
        
        self.assertIsNotNone(trade_node)
        self.assertEqual(trade_node.id, liq_node.id)  # Same node
        self.assertGreater(trade_node.volume_total, initial_volume)
        
        # Still only 1 node
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 1)
    
    def test_trade_ignores_non_overlapping_price(self):
        """Test: Trade at distant price is ignored (no spatial match)."""
        # Create node at 50k
        self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        # Trade at 60k (far from 50k ± 50 band)
        result = self.store.ingest_trade(
            symbol="BTCUSDT",
            price=60000.0,
            side="SELL",
            volume=50.0,
            is_buyer_maker=False,
            timestamp=1001.0
        )
        
        self.assertIsNone(result)
    
    def test_symbol_partitioning(self):
        """Test: BTC liquidation does not match ETH trades."""
        # Create BTC node
        btc_node = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        # ETH trade at same price (different symbol)
        eth_result = self.store.ingest_trade(
            symbol="ETHUSDT",
            price=50000.0,  # Same price as BTC node
            side="SELL",
            volume=50.0,
            is_buyer_maker=False,
            timestamp=1001.0
        )
        
        self.assertIsNone(eth_result)  # No match due to symbol mismatch
        
        # Still only 1 node (BTC)
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 1)
    
    def test_liquidation_overlap_reinforces_node(self):
        """Test: Second liquidation at overlapping price reinforces existing node."""
        # First liquidation
        node1 = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        initial_strength = node1.strength
        
        # Second liquidation at nearby price
        node2 = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50030.0,  # Within band
            side="SELL",
            volume=150.0,
            timestamp=1001.0
        )
        
        # Should return same node (reinforced)
        self.assertEqual(node1.id, node2.id)
        self.assertGreater(node2.strength, initial_strength)
        
        # Still only 1 node
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 1)
    
    def test_liquidation_non_overlap_creates_second_node(self):
        """Test: Liquidation at distant price creates separate node."""
        # First liquidation at 50k
        node1 = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        # Second liquidation at 52k (outside 50k ± 50 band)
        node2 = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=52000.0,
            side="SELL",
            volume=150.0,
            timestamp=1001.0
        )
        
        self.assertNotEqual(node1.id, node2.id)
        
        # Now have 2 nodes
        metrics = self.store.get_metrics()
        self.assertEqual(metrics['active_nodes'], 2)
    
    def test_decay_reduces_strength(self):
        """Test: advance_time applies decay."""
        node = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        initial_strength = node.strength
        
        # Advance time by 100 seconds (no interaction)
        self.store.advance_time(1100.0)
        
        # Strength should decrease
        self.assertLess(node.strength, initial_strength)
    
    def test_lifecycle_transition_to_dormant(self):
        """Test: Low strength transitions node to DORMANT."""
        node = self.store.ingest_liquidation(
            symbol="BTCUSDT",
            price=50000.0,
            side="BUY",
            volume=100.0,
            timestamp=1000.0
        )
        
        # Force decay by advancing time significantly
        for _ in range(20):
            self.store.advance_time(1000.0 + (_ * 100))
        
        # Check metrics
        metrics = self.store.get_metrics()
        # Node should transition to dormant or archived
        self.assertLessEqual(metrics['active_nodes'], 0)


if __name__ == '__main__':
    unittest.main()
