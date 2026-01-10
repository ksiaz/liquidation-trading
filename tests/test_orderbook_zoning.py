"""
Unit Tests for Orderbook Zoning Module

Tests implement requirements from PROMPT 3:
- Mid-price calculation
- Zone boundary definitions (0-5, 5-15, 15-30 bps)
- Liquidity aggregation per zone
- Zone metrics tracking
- Immutability

RULE: All tests are deterministic.
RULE: No randomness or data mocking.
"""

import pytest
import time
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion import OrderbookSnapshot, AggressiveTrade
from masterframe.orderbook_zoning import (
    ZoneLiquidity,
    OrderbookZones,
    ZoneMetrics,
    ZoneCalculator,
    ZoneState,
)


class TestZoneCalculator:
    """Test zone calculator functionality."""
    
    def test_mid_price_calculation(self):
        """Known bid/ask → correct mid-price."""
        calc = ZoneCalculator()
        
        bids = ((100.0, 1.0), (99.0, 2.0))
        asks = ((101.0, 1.0), (102.0, 2.0))
        
        mid = calc.calculate_mid_price(bids, asks)
        
        # mid = (100 + 101) / 2 = 100.5
        assert mid == 100.5
    
    def test_calculate_bps_from_mid(self):
        """Verify basis points calculation."""
        calc = ZoneCalculator()
        
        mid_price = 100.0
        
        # 5 bps = 0.05% from mid
        price_5bps = 100.05
        bps = calc.calculate_bps_from_mid(price_5bps, mid_price)
        assert abs(bps - 5.0) < 0.01
        
        # 15 bps
        price_15bps = 100.15
        bps = calc.calculate_bps_from_mid(price_15bps, mid_price)
        assert abs(bps - 15.0) < 0.01
    
    def test_zone_boundaries(self):
        """Verify zone definitions."""
        calc = ZoneCalculator()
        
        assert calc.ZONE_A_MIN_BPS == 0.0
        assert calc.ZONE_A_MAX_BPS == 5.0
        
        assert calc.ZONE_B_MIN_BPS == 5.0
        assert calc.ZONE_B_MAX_BPS == 15.0
        
        assert calc.ZONE_C_MIN_BPS == 15.0
        assert calc.ZONE_C_MAX_BPS == 30.0
    
    def test_zone_aggregation(self):
        """Multiple levels → single zone liquidity."""
        calc = ZoneCalculator()
        
        # Mid = 100.0
        # Zone A bid: 99.95 - 100.0 (0-5 bps below mid)
        # 1 bps = 0.01%, so 5 bps = 0.05
        
        bids = (
            (100.0, 1.0),    # 0 bps - Zone A
            (99.98, 2.0),    # ~2 bps - Zone A
            (99.95, 3.0),    # ~5 bps - boundary (included in A)
            (99.90, 4.0),    # ~10 bps - Zone B
        )
        asks = ((100.01, 1.0),)
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.005  # Will be recalculated
        )
        
        zones = calc.calculate_zones(orderbook)
        
        # Zone A bid should have levels within 0-5 bps
        zone_a_bid = zones.zone_a_bid
        assert zone_a_bid.zone_name == 'A'
        assert zone_a_bid.side == 'bid'
        assert zone_a_bid.total_quantity > 0
        assert zone_a_bid.level_count >= 2  # At least first two levels
    
    def test_weighted_average_price(self):
        """Known levels → correct volume-weighted average price."""
        calc = ZoneCalculator()
        
        # Create orderbook where we control zone A exactly
        # Mid = 100.0
        bids = (
            (99.98, 1.0),  # Price * Qty = 99.98
            (99.96, 2.0),  # Price * Qty = 199.92
        )
        asks = ((100.02, 1.0),)
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.0
        )
        
        zones = calc.calculate_zones(orderbook)
        zone_a_bid = zones.zone_a_bid
        
        # VWAP = (99.98*1 + 99.96*2) / (1 + 2) = 399.88 / 3
        expected_vwap = (99.98 * 1.0 + 99.96 * 2.0) / 3.0
        assert zone_a_bid.weighted_avg_price is not None
        assert abs(zone_a_bid.weighted_avg_price - expected_vwap) < 0.01
    
    def test_empty_zone(self):
        """No levels in range → zero liquidity."""
        calc = ZoneCalculator()
        
        # Create orderbook with no levels in Zone C
        # Mid = 100.0
        # Zone C bid: 99.70 - 99.85 (15-30 bps below)
        bids = (
            (99.98, 1.0),  # Zone A
            (99.90, 2.0),  # Zone B
            # No levels in Zone C range
        )
        asks = ((100.02, 1.0),)
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.0
        )
        
        zones = calc.calculate_zones(orderbook)
        zone_c_bid = zones.zone_c_bid
        
        assert zone_c_bid.total_quantity == 0.0
        assert zone_c_bid.weighted_avg_price is None
        assert zone_c_bid.level_count == 0
    
    def test_zone_A_bid_ask(self):
        """Correct aggregation for tight zones (0-5 bps)."""
        calc = ZoneCalculator()
        
        # Mid = 100.0
        bids = ((99.97, 10.0),)  # ~3 bps
        asks = ((100.03, 15.0),)  # ~3 bps
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.0
        )
        
        zones = calc.calculate_zones(orderbook)
        
        # Both should be in Zone A
        assert zones.zone_a_bid.total_quantity == 10.0
        assert zones.zone_a_ask.total_quantity == 15.0
    
    def test_zone_B_bid_ask(self):
        """Correct aggregation for medium zones (5-15 bps)."""
        calc = ZoneCalculator()
        
        # Mid = 100.0
        bids = (
            (99.95, 5.0),   # Boundary - should be in A
            (99.90, 10.0),  # ~10 bps - Zone B
        )
        asks = (
            (100.05, 5.0),   # Boundary - should be in A
            (100.10, 15.0),  # ~10 bps - Zone B
        )
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.0
        )
        
        zones = calc.calculate_zones(orderbook)
        
        # Zone B should have the 10 bps levels
        assert zones.zone_b_bid.total_quantity >= 10.0
        assert zones.zone_b_ask.total_quantity >= 15.0
    
    def test_zone_C_context(self):
        """Non-tradable context zone still calculated."""
        calc = ZoneCalculator()
        
        # Mid = 100.0
        # Zone C: 15-30 bps
        bids = ((99.75, 20.0),)  # ~25 bps - Zone C
        asks = ((100.25, 25.0),)  # ~25 bps - Zone C
        
        orderbook = OrderbookSnapshot(
            timestamp=time.time(),
            bids=bids,
            asks=asks,
            mid_price=100.0
        )
        
        zones = calc.calculate_zones(orderbook)
        
        # Zone C should have liquidity
        assert zones.zone_c_bid.total_quantity == 20.0
        assert zones.zone_c_ask.total_quantity == 25.0


class TestZoneState:
    """Test zone state manager."""
    
    def create_orderbook(self, mid: float, timestamp: float) -> OrderbookSnapshot:
        """Helper to create test orderbook."""
        bids = (
            (mid - 0.02, 10.0),  # Zone A
            (mid - 0.10, 15.0),  # Zone B
            (mid - 0.25, 20.0),  # Zone C
        )
        asks = (
            (mid + 0.02, 10.0),  # Zone A
            (mid + 0.10, 15.0),  # Zone B
            (mid + 0.25, 20.0),  # Zone C
        )
        
        return OrderbookSnapshot(
            timestamp=timestamp,
            bids=bids,
            asks=asks,
            mid_price=mid
        )
    
    def test_persistence_tracking(self):
        """Zone persists → persistence time increases."""
        state = ZoneState()
        
        base_time = time.time()
        
        # First update
        ob1 = self.create_orderbook(100.0, base_time)
        zones1, metrics1 = state.update(ob1, (), base_time)
        
        # Second update 5 seconds later
        ob2 = self.create_orderbook(100.0, base_time + 5.0)
        zones2, metrics2 = state.update(ob2, (), base_time + 5.0)
        
        # Check Zone A bid persistence
        zone_a_bid_metrics = metrics2['A_bid']
        assert zone_a_bid_metrics.persistence_seconds >= 5.0
    
    def test_get_current_zones(self):
        """Can retrieve current zones."""
        state = ZoneState()
        
        assert state.get_current_zones() is None
        
        ob = self.create_orderbook(100.0, time.time())
        zones, _ = state.update(ob, (), time.time())
        
        current = state.get_current_zones()
        assert current is not None
        assert current == zones


class TestImmutability:
    """Test immutability of zone types."""
    
    def test_orderbook_zones_immutable(self):
        """OrderbookZones is immutable."""
        zone_liq = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=10.0,
            weighted_avg_price=100.0,
            level_count=2,
            price_min=99.95,
            price_max=100.0,
        )
        
        zones = OrderbookZones(
            timestamp=time.time(),
            mid_price=100.0,
            zone_a_bid=zone_liq,
            zone_b_bid=zone_liq,
            zone_c_bid=zone_liq,
            zone_a_ask=zone_liq,
            zone_b_ask=zone_liq,
            zone_c_ask=zone_liq,
        )
        
        # Attempting to modify should raise error
        with pytest.raises(Exception):
            zones.mid_price = 999.0
    
    def test_zone_liquidity_immutable(self):
        """ZoneLiquidity is immutable."""
        zone = ZoneLiquidity(
            zone_name='A',
            side='bid',
            total_quantity=10.0,
            weighted_avg_price=100.0,
            level_count=2,
            price_min=99.95,
            price_max=100.0,
        )
        
        with pytest.raises(Exception):
            zone.total_quantity = 999.0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
