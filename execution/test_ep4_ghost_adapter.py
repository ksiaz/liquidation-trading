"""
Ghost Exchange Adapter Tests

Validates ghost execution with real Binance APIs.
Tests LIVE and SNAPSHOT modes.

NOTE: These tests may make real API calls to Binance (read-only).
Set BINANCE_API_KEY environment variable for authenticated tests.
"""

import pytest
import os
from execution.ep4_ghost_adapter import (
    GhostExchangeAdapter,
    ExecutionMode,
    FillEstimate,
    BinanceAPIClient,
    OrderBookSnapshot
)


# ==============================================================================
# Test Configuration
# ==============================================================================

# Get API key from environment (optional, read-only)
API_KEY = os.environ.get("BINANCE_API_KEY")

# Skip tests requiring live API if no connectivity
SKIP_LIVE = os.environ.get("SKIP_LIVE_TESTS", "false").lower() == "true"


# ==============================================================================
# Binance API Client Tests
# ==============================================================================

@pytest.mark.skipif(SKIP_LIVE, reason="Live API tests disabled")
def test_binance_client_get_exchange_info():
    """Binance client fetches exchange info correctly."""
    client = BinanceAPIClient(api_key=API_KEY)
    info = client.get_exchange_info(symbol="BTCUSDT")
    
    assert info["symbol"] == "BTCUSDT"
    assert "filters" in info


@pytest.mark.skipif(SKIP_LIVE, reason="Live API tests disabled")
def test_binance_client_get_order_book():
    """Binance client fetches order book correctly."""
    client = BinanceAPIClient(api_key=API_KEY)
    ob = client.get_order_book(symbol="BTCUSDT", limit=20)
    
    assert "bids" in ob
    assert "asks" in ob
    assert len(ob["bids"]) > 0
    assert len(ob["asks"]) > 0


@pytest.mark.skipif(SKIP_LIVE, reason="Live API tests disabled")
def test_binance_client_get_ticker_price():
    """Binance client fetches ticker price correctly."""
    client = BinanceAPIClient(api_key=API_KEY)
    price = client.get_ticker_price(symbol="BTCUSDT")
    
    assert price > 0
    assert isinstance(price, float)


# ==============================================================================
# Ghost Adapter Tests - Snapshot Capture
# ==============================================================================

@pytest.mark.skipif(SKIP_LIVE, reason="Live API tests disabled")
def test_ghost_adapter_captures_snapshot():
    """Ghost adapter captures order book snapshot."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_LIVE
    )
    
    snapshot = adapter.capture_snapshot()
    
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.best_bid > 0
    assert snapshot.best_ask > 0
    assert snapshot.spread > 0
    assert len(snapshot.bids) > 0
    assert len(snapshot.asks) > 0


def test_ghost_adapter_snapshot_repr():
    """OrderBookSnapshot is properly frozen."""
    snapshot = OrderBookSnapshot(
        snapshot_id="TEST_1",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 1.0),),
        asks=((60001.0, 1.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    
    # Should be immutable
    with pytest.raises(Exception):  # FrozenInstanceError
        snapshot.best_bid = 99999.0


# ==============================================================================
# Ghost Execution Tests - Validation
# ==============================================================================

def test_ghost_execution_validates_min_quantity():
    """Ghost execution rejects quantity below minimum."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_SNAPSHOT
    )
    
    # Use mocked snapshot for determinism
    adapter._current_snapshot = OrderBookSnapshot(
        snapshot_id="TEST",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 1.0),),
        asks=((60001.0, 1.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    
    result = adapter.execute_ghost_order(
        side="BUY",
        order_type="MARKET",
        quantity=0.00001  # Too small
    )
    
    assert not result.would_execute
    assert result.reject_reason is not None
    assert "minimum" in result.reject_reason.lower()


# ==============================================================================
# Ghost Execution Tests - Matching Simulation
# ==============================================================================

def test_ghost_market_order_crosses_spread():
    """Ghost market order simulates immediate execution."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_SNAPSHOT
    )
    
    # Mock snapshot
    adapter._current_snapshot = OrderBookSnapshot(
        snapshot_id="TEST",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 10.0),),
        asks=((60001.0, 10.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    
    result = adapter.execute_ghost_order(
        side="BUY",
        order_type="MARKET",
        quantity=0.01  # Small quantity
    )
    
    assert result.would_execute
    assert result.fill_estimate == FillEstimate.FULL


def test_ghost_limit_order_crosses_spread():
    """Ghost limit buy at/above ask crosses spread."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_SNAPSHOT
    )
    
    adapter._current_snapshot = OrderBookSnapshot(
        snapshot_id="TEST",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 10.0),),
        asks=((60001.0, 10.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    
    result = adapter.execute_ghost_order(
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60001.5  # Above ask
    )
    
    assert result.would_execute


def test_ghost_limit_order_rests_in_book():
    """Ghost limit buy below ask rests in book."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_SNAPSHOT
    )
    
    adapter._current_snapshot = OrderBookSnapshot(
        snapshot_id="TEST",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 10.0),),
        asks=((60001.0, 10.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    
    result = adapter.execute_ghost_order(
        side="BUY",
        order_type="LIMIT",
        quantity=0.01,
        price=60000.5  # Between bid and ask
    )
    
    assert not result.would_execute  # Would rest
    assert result.fill_estimate == FillEstimate.NONE


# ==============================================================================
# Determinism Tests
# ==============================================================================

def test_snapshot_mode_determinism():
    """Snapshot mode produces deterministic results."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY,
        execution_mode=ExecutionMode.GHOST_SNAPSHOT
    )
    
    # Set snapshot
    snapshot = OrderBookSnapshot(
        snapshot_id="TEST",
        timestamp=1000.0,
        symbol="BTCUSDT",
        bids=((60000.0, 1.0),),
        asks=((60001.0, 1.0),),
        best_bid=60000.0,
        best_ask=60001.0,
        spread=1.0
    )
    adapter._current_snapshot = snapshot
    
    # Execute same order twice
    result1 = adapter.execute_ghost_order(
        side="BUY",
        order_type="MARKET",
        quantity=0.01
    )
    
    result2 = adapter.execute_ghost_order(
        side="BUY",
        order_type="MARKET",
        quantity=0.01
    )
    
    # Should be identical
    assert result1.would_execute == result2.would_execute
    assert result1.fill_estimate == result2.fill_estimate
    assert result1.orderbook_snapshot_id == result2.orderbook_snapshot_id


# ==============================================================================
# Safety Tests - Zero Actual Orders
# ==============================================================================

def test_ghost_adapter_never_places_orders():
    """Ghost adapter has no order placement methods."""
    adapter = GhostExchangeAdapter(
        symbol="BTCUSDT",
        api_key=API_KEY
    )
    
    # Should not have any order-placing methods
    assert not hasattr(adapter, 'place_order')
    assert not hasattr(adapter, 'submit_order')
    assert not hasattr(adapter, 'create_order')


def test_binance_client_has_no_write_methods():
    """Binance client only has read-only methods."""
    client = BinanceAPIClient(api_key=API_KEY)
    
    # Should not have write methods
    assert not hasattr(client, 'place_order')
    assert not hasattr(client, 'cancel_order')
    assert not hasattr(client, 'modify_order')
