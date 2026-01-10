"""
Zone Calculator

Converts raw L2 orderbook into zone-based representation.

RULES:
- Zones always relative to mid-price
- All levels within zone must be aggregated
- No per-level logic exposed
- Deterministic calculations
"""

from typing import Tuple, Optional
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import OrderbookSnapshot
from .types import ZoneLiquidity, OrderbookZones


class ZoneCalculator:
    """
    Converts raw orderbook to zone-based representation.
    
    INVARIANT: Zones always relative to mid-price.
    INVARIANT: No per-level logic exposed.
    """
    
    # Zone definitions in basis points (bps)
    ZONE_A_MIN_BPS = 0.0
    ZONE_A_MAX_BPS = 5.0
    
    ZONE_B_MIN_BPS = 5.0
    ZONE_B_MAX_BPS = 15.0
    
    ZONE_C_MIN_BPS = 15.0
    ZONE_C_MAX_BPS = 30.0
    
    @staticmethod
    def calculate_mid_price(
        bids: Tuple[Tuple[float, float], ...],
        asks: Tuple[Tuple[float, float], ...]
    ) -> float:
        """
        Calculate mid-price from best bid and ask.
        
        Args:
            bids: Bid levels (price, quantity)
            asks: Ask levels (price, quantity)
        
        Returns:
            Mid-price
        
        RULE: mid = (best_bid + best_ask) / 2
        
        Raises:
            ValueError: If bids or asks are empty
        """
        if not bids or not asks:
            raise ValueError("Cannot calculate mid-price: empty orderbook")
        
        best_bid = bids[0][0]  # Highest bid
        best_ask = asks[0][0]  # Lowest ask
        
        return (best_bid + best_ask) / 2.0
    
    @staticmethod
    def calculate_bps_from_mid(price: float, mid_price: float) -> float:
        """
        Calculate basis points distance from mid-price.
        
        Args:
            price: Price level
            mid_price: Mid-price
        
        Returns:
            Absolute basis points from mid
        
        RULE: bps = |price - mid| / mid * 10000
        """
        return abs(price - mid_price) / mid_price * 10000.0
    
    def calculate_zones(
        self,
        orderbook: OrderbookSnapshot
    ) -> OrderbookZones:
        """
        Convert orderbook snapshot to zoned representation.
        
        Args:
            orderbook: Raw orderbook snapshot
        
        Returns:
            OrderbookZones with all 6 zones populated
        
        RULE: Aggregate all levels within each zone's bps range.
        """
        # Calculate mid-price
        mid_price = self.calculate_mid_price(orderbook.bids, orderbook.asks)
        
        # Calculate bid zones (below mid-price)
        zone_a_bid = self._aggregate_zone(
            orderbook.bids, mid_price,
            self.ZONE_A_MIN_BPS, self.ZONE_A_MAX_BPS,
            'bid', 'A'
        )
        
        zone_b_bid = self._aggregate_zone(
            orderbook.bids, mid_price,
            self.ZONE_B_MIN_BPS, self.ZONE_B_MAX_BPS,
            'bid', 'B'
        )
        
        zone_c_bid = self._aggregate_zone(
            orderbook.bids, mid_price,
            self.ZONE_C_MIN_BPS, self.ZONE_C_MAX_BPS,
            'bid', 'C'
        )
        
        # Calculate ask zones (above mid-price)
        zone_a_ask = self._aggregate_zone(
            orderbook.asks, mid_price,
            self.ZONE_A_MIN_BPS, self.ZONE_A_MAX_BPS,
            'ask', 'A'
        )
        
        zone_b_ask = self._aggregate_zone(
            orderbook.asks, mid_price,
            self.ZONE_B_MIN_BPS, self.ZONE_B_MAX_BPS,
            'ask', 'B'
        )
        
        zone_c_ask = self._aggregate_zone(
            orderbook.asks, mid_price,
            self.ZONE_C_MIN_BPS, self.ZONE_C_MAX_BPS,
            'ask', 'C'
        )
        
        return OrderbookZones(
            timestamp=orderbook.timestamp,
            mid_price=mid_price,
            zone_a_bid=zone_a_bid,
            zone_b_bid=zone_b_bid,
            zone_c_bid=zone_c_bid,
            zone_a_ask=zone_a_ask,
            zone_b_ask=zone_b_ask,
            zone_c_ask=zone_c_ask,
        )
    
    def _aggregate_zone(
        self,
        levels: Tuple[Tuple[float, float], ...],
        mid_price: float,
        bps_min: float,
        bps_max: float,
        side: str,
        zone_name: str
    ) -> ZoneLiquidity:
        """
        Aggregate orderbook levels into single zone.
        
        Args:
            levels: Orderbook levels (price, quantity)
            mid_price: Current mid-price
            bps_min: Minimum basis points from mid
            bps_max: Maximum basis points from mid
            side: 'bid' or 'ask'
            zone_name: 'A', 'B', or 'C'
        
        Returns:
            ZoneLiquidity for this zone
        
        RULE: Include only levels within [bps_min, bps_max] range.
        RULE: Weighted avg price = Σ(price * qty) / Σ(qty)
        """
        total_quantity = 0.0
        weighted_sum = 0.0
        level_count = 0
        prices_in_zone = []
        
        for price, quantity in levels:
            bps = self.calculate_bps_from_mid(price, mid_price)
            
            # Check if level is within zone boundaries
            if bps_min <= bps < bps_max:
                total_quantity += quantity
                weighted_sum += price * quantity
                level_count += 1
                prices_in_zone.append(price)
        
        # Calculate weighted average price
        weighted_avg_price = None
        if total_quantity > 0:
            weighted_avg_price = weighted_sum / total_quantity
        
        # Determine price range
        if prices_in_zone:
            price_min = min(prices_in_zone)
            price_max = max(prices_in_zone)
        else:
            # Empty zone - set boundaries based on mid-price and bps range
            if side == 'bid':
                # Bids are below mid-price
                price_max = mid_price * (1 - bps_min / 10000.0)
                price_min = mid_price * (1 - bps_max / 10000.0)
            else:  # ask
                # Asks are above mid-price
                price_min = mid_price * (1 + bps_min / 10000.0)
                price_max = mid_price * (1 + bps_max / 10000.0)
        
        return ZoneLiquidity(
            zone_name=zone_name,
            side=side,
            total_quantity=total_quantity,
            weighted_avg_price=weighted_avg_price,
            level_count=level_count,
            price_min=price_min,
            price_max=price_max,
        )
