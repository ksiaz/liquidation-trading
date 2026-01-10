"""
Orderbook Zoning Type Definitions

Data structures for zone-based orderbook representation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ZoneLiquidity:
    """
    Liquidity snapshot for a single zone on one side.
    
    Immutable representation of zone state at a point in time.
    
    INVARIANT: All quantities are aggregated from orderbook levels.
    INVARIANT: Weighted average price is volume-weighted.
    """
    zone_name: str  # 'A', 'B', or 'C'
    side: str       # 'bid' or 'ask'
    total_quantity: float  # Sum of all quantities in zone
    weighted_avg_price: Optional[float]  # Volume-weighted average price (None if empty)
    level_count: int  # Number of orderbook levels in zone
    
    # Price range boundaries (inclusive)
    price_min: float
    price_max: float


@dataclass(frozen=True)
class OrderbookZones:
    """
    Complete zoned representation of orderbook snapshot.
    
    Contains all 6 zones (A/B/C × bid/ask).
    
    INVARIANT: Zones are relative to mid_price.
    INVARIANT: Immutable snapshot.
    """
    timestamp: float
    mid_price: float
    
    # Bid zones (below mid-price)
    zone_a_bid: ZoneLiquidity
    zone_b_bid: ZoneLiquidity
    zone_c_bid: ZoneLiquidity
    
    # Ask zones (above mid-price)
    zone_a_ask: ZoneLiquidity
    zone_b_ask: ZoneLiquidity
    zone_c_ask: ZoneLiquidity
    
    def get_zone(self, zone_name: str, side: str) -> ZoneLiquidity:
        """
        Get specific zone by name and side.
        
        Args:
            zone_name: 'A', 'B', or 'C'
            side: 'bid' or 'ask'
        
        Returns:
            ZoneLiquidity for specified zone
        """
        zone_map = {
            ('A', 'bid'): self.zone_a_bid,
            ('B', 'bid'): self.zone_b_bid,
            ('C', 'bid'): self.zone_c_bid,
            ('A', 'ask'): self.zone_a_ask,
            ('B', 'ask'): self.zone_b_ask,
            ('C', 'ask'): self.zone_c_ask,
        }
        
        key = (zone_name.upper(), side.lower())
        if key not in zone_map:
            raise ValueError(f"Invalid zone: {zone_name} {side}")
        
        return zone_map[key]


@dataclass
class ZoneMetrics:
    """
    Tracked metrics for a zone over time.
    
    Mutable - updated as zone state changes.
    
    INVARIANT: Tracks volume changes (executed vs canceled).
    INVARIANT: Persistence time updated on each snapshot.
    """
    zone_name: str
    side: str
    
    # Current state
    current_liquidity: float
    first_seen: float  # Timestamp when zone first appeared with liquidity
    last_updated: float  # Timestamp of last update
    
    # Tracking metrics
    persistence_seconds: float  # How long zone has had liquidity
    executed_volume: float  # Volume that was in zone and got filled
    canceled_volume: float  # Volume that was in zone and got removed without fill
    
    # Historical ranges
    max_liquidity_seen: float
    min_liquidity_seen: float
    
    def update_persistence(self, current_time: float) -> None:
        """
        Update persistence time.
        
        Args:
            current_time: Current timestamp
        
        RULE: persistence = current_time - first_seen
        """
        self.last_updated = current_time
        self.persistence_seconds = current_time - self.first_seen
    
    def update_liquidity(self, new_liquidity: float) -> None:
        """
        Update current liquidity and historical ranges.
        
        Args:
            new_liquidity: New liquidity value
        """
        self.current_liquidity = new_liquidity
        self.max_liquidity_seen = max(self.max_liquidity_seen, new_liquidity)
        if new_liquidity > 0:  # Only track non-zero minimums
            if self.min_liquidity_seen == 0:
                self.min_liquidity_seen = new_liquidity
            else:
                self.min_liquidity_seen = min(self.min_liquidity_seen, new_liquidity)
