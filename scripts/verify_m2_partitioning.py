
import sys
import unittest
# Add parent dir to path to allow imports
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory.m2_continuity_store import ContinuityMemoryStore
from memory.m5_access import MemoryAccess, AccessDeniedError
from memory.m5_query_schemas import QUERY_TYPES, LifecycleState

class TestM2Partitioning(unittest.TestCase):
    def setUp(self):
        self.store = ContinuityMemoryStore()
        self.m5 = MemoryAccess(self.store)
        
        # Seed nodes
        # BTC Nodes at 50k, 51k
        self.store.add_or_update_node("BTC_50K", "BTCUSDT", 50000.0, 100.0, "bid", 1000.0, "manual")
        self.store.add_or_update_node("BTC_51K", "BTCUSDT", 51000.0, 100.0, "ask", 1000.0, "manual")
        
        # ETH Nodes at 3000, 3100
        self.store.add_or_update_node("ETH_3K", "ETHUSDT", 3000.0, 10.0, "bid", 1000.0, "manual")
        self.store.add_or_update_node("ETH_3100", "ETHUSDT", 3100.0, 10.0, "ask", 1000.0, "manual")
        
        # Add a Rogue BTC node at 3000 to test strict partitioning even with price overlap
        self.store.add_or_update_node("BTC_ROGUE_3K", "BTCUSDT", 3000.0, 100.0, "bid", 1000.0, "manual")

    def test_state_distribution_partitioning(self):
        # Result: {'ACTIVE': 5, 'DORMANT': 0, 'ARCHIVED': 0, 'total_count': 5}
        global_stats = self.m5.execute_query("STATE_DISTRIBUTION", {"query_ts": 1005.0})
        self.assertEqual(global_stats['ACTIVE'], 5)
        
        # BTC Stats
        btc_stats = self.m5.execute_query("STATE_DISTRIBUTION", {"query_ts": 1005.0, "symbol": "BTCUSDT"})
        self.assertEqual(btc_stats['ACTIVE'], 3)
        
        # ETH Stats
        eth_stats = self.m5.execute_query("STATE_DISTRIBUTION", {"query_ts": 1005.0, "symbol": "ETHUSDT"})
        self.assertEqual(eth_stats['ACTIVE'], 2)

    def test_spatial_group_partitioning(self):
        # Query generic price range 0-60000 (covers all)
        # Without symbol filter
        all_nodes = self.m5.execute_query("SPATIAL_GROUP", {
            "min_price": 0.0,
            "max_price": 60000.0,
            "current_ts": 1005.0
        })
        self.assertEqual(len(all_nodes), 5)
        
        # With BTC filter
        btc_nodes = self.m5.execute_query("SPATIAL_GROUP", {
            "min_price": 0.0,
            "max_price": 60000.0,
            "current_ts": 1005.0,
            "symbol": "BTCUSDT"
        })
        self.assertEqual(len(btc_nodes), 3)
        self.assertTrue(all(n['node_id'].startswith("BTC") for n in btc_nodes))
        
        # With ETH filter
        eth_nodes = self.m5.execute_query("SPATIAL_GROUP", {
            "min_price": 0.0,
            "max_price": 60000.0,
            "current_ts": 1005.0,
            "symbol": "ETHUSDT"
        })
        self.assertEqual(len(eth_nodes), 2)
        self.assertTrue(all(n['node_id'].startswith("ETH") for n in eth_nodes))

    def test_proximity_partitioning(self):
        # Query near 3000. 
        # Candidates: ETH_3K (3000), ETH_3100 (3100), BTC_ROGUE_3K (3000)
        
        # ETH filter near 3000 with radius 500 -> Should find 2 ETH nodes (3000, 3100)
        # BUT MUST NOT find BTC_ROGUE_3K (3000)
        eth_near = self.m5.execute_query("PROXIMITY", {
            "center_price": 3000.0,
            "search_radius": 500.0,
            "current_ts": 1005.0,
            "symbol": "ETHUSDT"
        })
        self.assertEqual(len(eth_near), 2)
        node_ids = sorted([n['node_id'] for n in eth_near])
        self.assertEqual(node_ids, ["ETH_3100", "ETH_3K"])
        
        # BTC filter near 3000 -> Should find only the Rogue BTC node
        btc_near_3k = self.m5.execute_query("PROXIMITY", {
            "center_price": 3000.0,
            "search_radius": 500.0,
            "current_ts": 1005.0,
            "symbol": "BTCUSDT"
        })
        self.assertEqual(len(btc_near_3k), 1)
        self.assertEqual(btc_near_3k[0]['node_id'], "BTC_ROGUE_3K")

if __name__ == '__main__':
    unittest.main()
