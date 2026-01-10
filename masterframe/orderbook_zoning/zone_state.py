"""
Zone State Manager

Maintains current orderbook zone state and integrates calculator + tracker.

RULES:
- Orchestrates zone calculation and tracking
- Maintains current/previous zones
- Provides clean interface for strategies
"""

from typing import Optional, Dict, Tuple
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.data_ingestion.types import OrderbookSnapshot, AggressiveTrade
from .types import OrderbookZones, ZoneMetrics
from .zone_calculator import ZoneCalculator
from .zone_tracker import ZoneTracker


class ZoneState:
    """
    Maintains current orderbook zone state.
    
    Integrates ZoneCalculator and ZoneTracker to provide complete
    zone-based orderbook representation.
    
    INVARIANT: Strategies access zones only through this interface.
    INVARIANT: No raw orderbook access exposed.
    """
    
    def __init__(self):
        """Initialize zone state manager."""
        self.calculator = ZoneCalculator()
        self.tracker = ZoneTracker()
        self.current_zones: Optional[OrderbookZones] = None
        self.previous_zones: Optional[OrderbookZones] = None
    
    def update(
        self,
        orderbook: OrderbookSnapshot,
        recent_trades: Tuple[AggressiveTrade, ...],
        current_time: float
    ) -> Tuple[OrderbookZones, Dict[str, ZoneMetrics]]:
        """
        Update zone state with new orderbook.
        
        Args:
            orderbook: Raw orderbook snapshot
            recent_trades: Recent trades (for execution detection)
            current_time: Current timestamp
        
        Returns:
            (current_zones, zone_metrics)
        
        RULE: Calculates zones, updates tracking, returns both.
        RULE: Previous zones stored for next iteration.
        """
        # Shift current to previous
        self.previous_zones = self.current_zones
        
        # Calculate new zones
        self.current_zones = self.calculator.calculate_zones(orderbook)
        
        # Update tracking
        zone_metrics = self.tracker.update(
            current_zones=self.current_zones,
            previous_zones=self.previous_zones,
            executed_trades=recent_trades,
            current_time=current_time
        )
        
        return self.current_zones, zone_metrics
    
    def get_current_zones(self) -> Optional[OrderbookZones]:
        """
        Get latest zoned orderbook.
        
        Returns:
            Current OrderbookZones or None if not yet initialized
        """
        return self.current_zones
    
    def get_zone_metrics(self) -> Dict[str, ZoneMetrics]:
        """
        Get current zone tracking metrics.
        
        Returns:
            Dict of zone metrics by zone key
        """
        return self.tracker.get_metrics()
    
    def reset(self) -> None:
        """
        Reset zone state.
        
        Clears all zones and metrics.
        """
        self.current_zones = None
        self.previous_zones = None
        self.tracker.reset()
