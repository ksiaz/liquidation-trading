"""
Test Order Book Integration

Verifies order book ingestion flow from M1 → M2 → M4 → Snapshot.
"""

import pytest
from observation.governance import ObservationSystem
from observation.types import ObservationStatus


class TestOrderBookIngestion:
    """Test M1 order book normalization."""

    def test_m1_normalizes_depth_update(self):
        """M1 normalizes Binance @depth format correctly."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Simulate Binance @depth payload
        depth_payload = {
            "e": "depthUpdate",
            "E": 1000000,
            "s": "BTCUSDT",
            "U": 157,
            "u": 160,
            "b": [
                ["50000.00", "1.5"],
                ["49999.00", "2.0"]
            ],
            "a": [
                ["50001.00", "1.0"],
                ["50002.00", "0.5"]
            ]
        }

        # Ingest depth update
        obs_system.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="DEPTH",
            payload=depth_payload
        )

        # Check M1 counter
        assert obs_system._m1.counters['depth'] == 1

    def test_m1_handles_empty_orderbook(self):
        """M1 handles empty bids/asks gracefully."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        depth_payload = {
            "e": "depthUpdate",
            "E": 1000000,
            "s": "BTCUSDT",
            "b": [],
            "a": []
        }

        obs_system.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="DEPTH",
            payload=depth_payload
        )

        assert obs_system._m1.counters['depth'] == 1


class TestOrderBookStateUpdate:
    """Test M2 order book state updates."""

    def test_m2_updates_orderbook_state(self):
        """M2 updates node resting size from order book data."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Create a node via liquidation
        liq_payload = {
            "E": 1000000,
            "o": {
                "p": "50000.00",
                "q": "10.0",
                "S": "BUY"
            }
        }

        obs_system.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload=liq_payload
        )

        # Verify node created
        active_nodes = obs_system._m2_store.get_active_nodes(symbol="BTCUSDT")
        assert len(active_nodes) == 1

        # Update order book state
        depth_payload = {
            "e": "depthUpdate",
            "E": 1001000,
            "s": "BTCUSDT",
            "b": [["50000.00", "5.0"]],
            "a": [["50001.00", "3.0"]]
        }

        obs_system.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="DEPTH",
            payload=depth_payload
        )

        # Verify node updated with order book state
        node = active_nodes[0]
        assert node.last_observed_bid_size == 5.0
        assert node.last_observed_ask_size == 3.0
        assert node.last_orderbook_update_ts == 1001.0

    def test_m2_updates_multiple_price_levels(self):
        """M2 updates nodes that overlap with best bid/ask price."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Create multiple nodes at different prices
        for price in [50000.0, 49900.0, 50100.0]:
            liq_payload = {
                "E": 1000000,
                "o": {
                    "p": str(price),
                    "q": "10.0",
                    "S": "BUY"
                }
            }
            obs_system.ingest_observation(
                timestamp=1000.0,
                symbol="BTCUSDT",
                event_type="LIQUIDATION",
                payload=liq_payload
            )

        # Verify 3 nodes created
        active_nodes = obs_system._m2_store.get_active_nodes(symbol="BTCUSDT")
        assert len(active_nodes) == 3

        # Update order book - only best_bid_price (50000) is used for overlap check
        # The depth update aggregates sizes but only the best price level is checked
        depth_payload = {
            "e": "depthUpdate",
            "E": 1001000,
            "s": "BTCUSDT",
            "b": [
                ["50000.00", "5.0"],
                ["49900.00", "3.0"],
                ["50100.00", "7.0"]
            ],
            "a": []
        }

        obs_system.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="DEPTH",
            payload=depth_payload
        )

        # Only the node overlapping with best_bid_price (50000) should be updated
        nodes_with_ob = [n for n in active_nodes if n.last_orderbook_update_ts is not None]
        assert len(nodes_with_ob) == 1

        # Verify the correct node was updated
        updated_node = nodes_with_ob[0]
        assert updated_node.price_center == 50000.0
        # bid_size is sum of top 5 levels = 5.0 + 3.0 + 7.0 = 15.0
        assert updated_node.last_observed_bid_size == 15.0


class TestOrderBookPrimitives:
    """Test M4 order book primitive computation."""

    def test_snapshot_includes_resting_size(self):
        """Snapshot includes resting size primitive."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Create node
        liq_payload = {
            "E": 1000000,
            "o": {"p": "50000.00", "q": "10.0", "S": "BUY"}
        }
        obs_system.ingest_observation(
            timestamp=1000.0,
            symbol="BTCUSDT",
            event_type="LIQUIDATION",
            payload=liq_payload
        )

        # Update order book
        depth_payload = {
            "e": "depthUpdate",
            "E": 1001000,
            "s": "BTCUSDT",
            "b": [["50000.00", "5.0"]],
            "a": [["50001.00", "3.0"]]
        }
        obs_system.ingest_observation(
            timestamp=1001.0,
            symbol="BTCUSDT",
            event_type="DEPTH",
            payload=depth_payload
        )

        # Advance time and get snapshot
        obs_system.advance_time(1002.0)
        snapshot = obs_system.query({"type": "snapshot"})

        # Verify resting size primitive exists
        primitives = snapshot.primitives["BTCUSDT"]
        assert primitives.resting_size is not None
        assert primitives.resting_size.best_bid_price == 50000.0
        assert primitives.resting_size.bid_size == 5.0
        # Note: ask_size is 3.0 because the ask price 50001 falls within
        # the node's price band (50000 ± 50), so both bid and ask matched the node
        assert primitives.resting_size.ask_size == 3.0

    def test_empty_orderbook_returns_none(self):
        """Empty order book data returns None primitive gracefully."""
        obs_system = ObservationSystem(allowed_symbols=["BTCUSDT"])

        # Advance time without any order book data
        obs_system.advance_time(1000.0)
        snapshot = obs_system.query({"type": "snapshot"})

        # Verify resting size is None (no data)
        primitives = snapshot.primitives["BTCUSDT"]
        assert primitives.resting_size is None
        assert primitives.order_consumption is None


class TestOrderBookConstitutionalCompliance:
    """Test constitutional compliance of order book implementation."""

    def test_no_semantic_interpretation(self):
        """Order book primitives are factual, not interpretive."""
        from memory.m4_orderbook_primitives import RestingSizeAtPrice

        # Create primitive
        resting_size = RestingSizeAtPrice(
            bid_size=5.0,
            ask_size=3.0,
            best_bid_price=50000.0,
            best_ask_price=50001.0,
            timestamp=1000.0
        )

        # Verify fields are purely factual
        assert hasattr(resting_size, 'best_bid_price')
        assert hasattr(resting_size, 'bid_size')
        assert hasattr(resting_size, 'ask_size')
        assert hasattr(resting_size, 'timestamp')

        # Verify NO semantic fields
        assert not hasattr(resting_size, 'support')
        assert not hasattr(resting_size, 'resistance')
        assert not hasattr(resting_size, 'strength')
        assert not hasattr(resting_size, 'importance')

    def test_primitives_are_frozen(self):
        """Order book primitives are immutable."""
        from memory.m4_orderbook_primitives import RestingSizeAtPrice

        resting_size = RestingSizeAtPrice(
            bid_size=5.0,
            ask_size=3.0,
            best_bid_price=50000.0,
            best_ask_price=50001.0,
            timestamp=1000.0
        )

        # Attempt to modify (should raise)
        with pytest.raises(Exception):
            resting_size.bid_size = 10.0
