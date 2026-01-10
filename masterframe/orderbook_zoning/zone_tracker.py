"""
Zone Tracker

Tracks zone metrics across orderbook updates.

RULES:
- Detects executed volume (liquidity removed + trade occurred)
- Detects canceled volume (liquidity removed without trade)
- Updates persistence time on each snapshot
- Maintains historical ranges
"""

from typing import Dict, Optional, Tuple
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import AggressiveTrade
from .types import OrderbookZones, ZoneLiquidity, ZoneMetrics


class ZoneTracker:
    """
    Tracks zone metrics across orderbook updates.
    
    INVARIANT: Maintains history for executed/canceled volume.
    INVARIANT: Updates persistence time on each snapshot.
    """
    
    def __init__(self):
        """Initialize zone tracker."""
        self._zone_metrics: Dict[str, ZoneMetrics] = {}
    
    def update(
        self,
        current_zones: OrderbookZones,
        previous_zones: Optional[OrderbookZones],
        executed_trades: Tuple[AggressiveTrade, ...],
        current_time: float
    ) -> Dict[str, ZoneMetrics]:
        """
        Update zone metrics with new orderbook snapshot.
        
        Args:
            current_zones: Latest zoned orderbook
            previous_zones: Previous zoned orderbook (for delta calc)
            executed_trades: Recent trades (for executed volume detection)
            current_time: Current timestamp
        
        Returns:
            Updated zone metrics dict
        
        RULE: executed_volume increases when liquidity removed + trade occurred.
        RULE: canceled_volume increases when liquidity removed without trade.
        """
        # Define all zone keys
        zone_keys = [
            ('A', 'bid'), ('B', 'bid'), ('C', 'bid'),
            ('A', 'ask'), ('B', 'ask'), ('C', 'ask'),
        ]
        
        for zone_name, side in zone_keys:
            zone_key = f"{zone_name}_{side}"
            current_zone = current_zones.get_zone(zone_name, side)
            
            # Initialize metrics if first time seeing this zone
            if zone_key not in self._zone_metrics:
                self._zone_metrics[zone_key] = ZoneMetrics(
                    zone_name=zone_name,
                    side=side,
                    current_liquidity=current_zone.total_quantity,
                    first_seen=current_time,
                    last_updated=current_time,
                    persistence_seconds=0.0,
                    executed_volume=0.0,
                    canceled_volume=0.0,
                    max_liquidity_seen=current_zone.total_quantity,
                    min_liquidity_seen=current_zone.total_quantity if current_zone.total_quantity > 0 else 0.0,
                )
                continue
            
            metrics = self._zone_metrics[zone_key]
            
            # Get previous zone liquidity
            prev_liquidity = 0.0
            if previous_zones is not None:
                prev_zone = previous_zones.get_zone(zone_name, side)
                prev_liquidity = prev_zone.total_quantity
            
            curr_liquidity = current_zone.total_quantity
            
            # Detect volume changes
            if curr_liquidity < prev_liquidity:
                # Liquidity decreased - could be execution or cancellation
                liquidity_removed = prev_liquidity - curr_liquidity
                
                # Check if trades occurred in this zone's price range
                executed = self._detect_executed_volume(
                    zone_key,
                    prev_liquidity,
                    curr_liquidity,
                    executed_trades,
                    current_zone
                )
                
                # Remainder is canceled
                canceled = self._detect_canceled_volume(
                    prev_liquidity,
                    curr_liquidity,
                    executed
                )
                
                metrics.executed_volume += executed
                metrics.canceled_volume += canceled
            
            # Update metrics
            metrics.update_liquidity(curr_liquidity)
            metrics.update_persistence(current_time)
        
        return self._zone_metrics
    
    def _detect_executed_volume(
        self,
        zone_key: str,
        prev_liquidity: float,
        curr_liquidity: float,
        trades: Tuple[AggressiveTrade, ...],
        zone: ZoneLiquidity
    ) -> float:
        """
        Estimate volume that was executed from zone.
        
        Args:
            zone_key: Zone identifier
            prev_liquidity: Previous liquidity
            curr_liquidity: Current liquidity
            trades: Recent trades
            zone: Current zone state
        
        Returns:
            Estimated executed volume
        
        RULE: If liquidity decreased AND trades occurred in zone price range,
              attribute decrease to execution.
        """
        if prev_liquidity <= curr_liquidity:
            return 0.0
        
        if not trades:
            return 0.0
        
        # Filter trades in zone's price range
        trades_in_zone = [
            trade for trade in trades
            if zone.price_min <= trade.price <= zone.price_max
        ]
        
        if not trades_in_zone:
            return 0.0
        
        # Sum trade volumes in zone
        trade_volume = sum(trade.quantity for trade in trades_in_zone)
        
        # Executed volume is min of liquidity removed and trade volume
        # (conservative estimate to avoid over-counting)
        liquidity_removed = prev_liquidity - curr_liquidity
        return min(liquidity_removed, trade_volume)
    
    def _detect_canceled_volume(
        self,
        prev_liquidity: float,
        curr_liquidity: float,
        executed: float
    ) -> float:
        """
        Estimate volume that was canceled from zone.
        
        Args:
            prev_liquidity: Previous liquidity
            curr_liquidity: Current liquidity
            executed: Already detected executed volume
        
        Returns:
            Estimated canceled volume
        
        RULE: canceled = (prev - curr) - executed
        """
        if prev_liquidity <= curr_liquidity:
            return 0.0
        
        liquidity_removed = prev_liquidity - curr_liquidity
        canceled = liquidity_removed - executed
        
        # Ensure non-negative
        return max(0.0, canceled)
    
    def get_metrics(self) -> Dict[str, ZoneMetrics]:
        """Get current zone metrics."""
        return self._zone_metrics
    
    def reset(self) -> None:
        """Reset all zone metrics."""
        self._zone_metrics.clear()
