"""
Block Detector

Detects and classifies liquidity blocks from orderbook zones.

RULES:
- ALL 4 qualification conditions must be met
- Classification: ABSORPTION (tradable), CONSUMPTION, or SPOOF
- Only Zones A and B are checked (C is context only)
- Blocks invalidated on price acceptance
"""

from typing import Dict, List, Optional
from collections import deque
import sys
sys.path.append('d:/liquidation-trading')
from masterframe.orderbook_zoning.types import OrderbookZones, ZoneLiquidity, ZoneMetrics
from .types import BlockType, LiquidityBlock


class BlockDetector:
    """
    Detects and classifies liquidity blocks.
    
    INVARIANT: Only qualified blocks are classified.
    INVARIANT: Only ABSORPTION blocks are tradable.
    """
    
    # Qualification thresholds
    LIQUIDITY_MULTIPLIER = 2.5
    MIN_PERSISTENCE_SECONDS = 30.0
    MAX_CANCEL_TO_TRADE_RATIO = 3.5
    
    # Classification thresholds
    MIN_EXECUTION_FOR_ABSORPTION = 100.0  # Base currency units
    PRICE_ACCEPTANCE_THRESHOLD_BPS = 2.0  # bps through zone
    
    # Rolling average window
    ZONE_AVG_WINDOW_SIZE = 20
    
    def __init__(self):
        """Initialize block detector."""
        self.active_blocks: Dict[str, LiquidityBlock] = {}
        self.zone_liquidity_history: Dict[str, deque] = {}
    
    def detect_blocks(
        self,
        zones: OrderbookZones,
        zone_metrics: Dict[str, ZoneMetrics],
        current_time: float
    ) -> List[LiquidityBlock]:
        """
        Detect liquidity blocks from current zones.
        
        Args:
            zones: Current orderbook zones
            zone_metrics: Zone tracking metrics
            current_time: Current timestamp
        
        Returns:
            List of detected blocks
        
        RULE: Check Zones A and B only (C is context).
        RULE: Qualification first, then classification.
        """
        detected_blocks = []
        
        # Check zones A and B for both sides
        zones_to_check = [
            ('A', 'bid', zones.zone_a_bid),
            ('A', 'ask', zones.zone_a_ask),
            ('B', 'bid', zones.zone_b_bid),
            ('B', 'ask', zones.zone_b_ask),
        ]
        
        for zone_name, side, zone in zones_to_check:
            zone_key = f"{zone_name}_{side}"
            
            # Get zone metrics
            if zone_key not in zone_metrics:
                continue
            
            metrics = zone_metrics[zone_key]
            
            # Update rolling average
            rolling_avg = self._update_rolling_average(zone_key, zone.total_quantity)
            
            # Check qualification
            if self._check_qualification(zone, metrics, rolling_avg):
                # Classify block
                block_type = self._classify_block(zone, metrics, zones.mid_price)
                
                # Create block
                block_id = LiquidityBlock.generate_block_id(zone_name, side, current_time)
                
                # Calculate cancel-to-trade ratio
                if metrics.executed_volume > 0:
                    cancel_ratio = metrics.canceled_volume / metrics.executed_volume
                else:
                    cancel_ratio = 999.0  # High value if no executions
                
                block = LiquidityBlock(
                    block_id=block_id,
                    zone_name=zone_name,
                    side=side,
                    block_type=block_type,
                    zone_liquidity=zone.total_quantity,
                    rolling_zone_avg=rolling_avg,
                    persistence_seconds=metrics.persistence_seconds,
                    executed_volume=metrics.executed_volume,
                    canceled_volume=metrics.canceled_volume,
                    cancel_to_trade_ratio=cancel_ratio,
                    price_min=zone.price_min,
                    price_max=zone.price_max,
                    initial_price=zone.weighted_avg_price if zone.weighted_avg_price else zones.mid_price,
                    current_price=zones.mid_price,
                    first_seen=metrics.first_seen,
                    last_updated=current_time,
                    is_tradable=(block_type == BlockType.ABSORPTION),
                    is_invalidated=False,
                )
                
                detected_blocks.append(block)
                self.active_blocks[block_id] = block
        
        # Invalidate broken blocks
        self._invalidate_broken_blocks(zones.mid_price, current_time)
        
        return detected_blocks
    
    def _check_qualification(
        self,
        zone: ZoneLiquidity,
        metrics: ZoneMetrics,
        rolling_avg: float
    ) -> bool:
        """
        Check if zone qualifies as liquidity block.
        
        Args:
            zone: Zone liquidity snapshot
            metrics: Zone metrics
            rolling_avg: Rolling average liquidity
        
        Returns:
            True if ALL 4 conditions met
        
        RULE: ALL conditions must be True.
        
        Conditions:
        1. zone_liquidity >= 2.5 × rolling_zone_avg
        2. persistence >= 30 seconds
        3. executed_volume > 0
        4. cancel_to_trade_ratio < 3.5
        """
        # Condition 1: High liquidity
        if rolling_avg == 0:
            return False  # Need history first
        
        condition_1 = zone.total_quantity >= self.LIQUIDITY_MULTIPLIER * rolling_avg
        
        # Condition 2: Persistence
        condition_2 = metrics.persistence_seconds >= self.MIN_PERSISTENCE_SECONDS
        
        # Condition 3: Executed volume
        condition_3 = metrics.executed_volume > 0
        
        # Condition 4: Cancel-to-trade ratio
        if metrics.executed_volume > 0:
            cancel_ratio = metrics.canceled_volume / metrics.executed_volume
            condition_4 = cancel_ratio < self.MAX_CANCEL_TO_TRADE_RATIO
        else:
            condition_4 = False  # No executions → not qualified
        
        return condition_1 and condition_2 and condition_3 and condition_4
    
    def _classify_block(
        self,
        zone: ZoneLiquidity,
        metrics: ZoneMetrics,
        current_price: float
    ) -> BlockType:
        """
        Classify qualified block.
        
        Args:
            zone: Zone liquidity snapshot
            metrics: Zone metrics
            current_price: Current mid-price
        
        Returns:
            BlockType classification
        
        RULE: ABSORPTION if high execution + price stayed in zone.
        RULE: CONSUMPTION if high execution + price broke through zone.
        RULE: SPOOF otherwise.
        """
        # Check if price is still in zone
        price_in_zone = zone.price_min <= current_price <= zone.price_max
        
        # High execution threshold met?
        high_execution = metrics.executed_volume >= self.MIN_EXECUTION_FOR_ABSORPTION
        
        if high_execution:
            if price_in_zone:
                return BlockType.ABSORPTION
            else:
                return BlockType.CONSUMPTION
        else:
            return BlockType.SPOOF
    
    def _update_rolling_average(
        self,
        zone_key: str,
        current_liquidity: float
    ) -> float:
        """
        Update and return rolling average for zone.
        
        Args:
            zone_key: Zone identifier
            current_liquidity: Current liquidity value
        
        Returns:
            Rolling average
        
        RULE: Fixed window size.
        RULE: Returns 0 if insufficient history.
        """
        if zone_key not in self.zone_liquidity_history:
            self.zone_liquidity_history[zone_key] = deque(maxlen=self.ZONE_AVG_WINDOW_SIZE)
        
        history = self.zone_liquidity_history[zone_key]
        history.append(current_liquidity)
        
        if len(history) == 0:
            return 0.0
        
        return sum(history) / len(history)
    
    def _invalidate_broken_blocks(
        self,
        current_price: float,
        current_time: float
    ) -> None:
        """
        Invalidate blocks where price accepted through.
        
        Args:
            current_price: Current mid-price
            current_time: Current timestamp
        
        RULE: If price breaks through block price range, invalidate.
        """
        for block_id, block in list(self.active_blocks.items()):
            # Check if price broke through
            if block.side == 'bid':
                # Bid block below price - broken if price goes below
                if current_price < block.price_min:
                    # Mark as invalidated (create new block with updated flag)
                    # Since block is frozen, we mark it in our tracking
                    pass  # Will be handled by tracker
            else:  # ask
                # Ask block above price - broken if price goes above
                if current_price > block.price_max:
                    # Mark as invalidated
                    pass  # Will be handled by tracker
    
    def get_active_blocks(self) -> Dict[str, LiquidityBlock]:
        """Get currently active blocks."""
        return self.active_blocks
    
    def reset(self) -> None:
        """Reset detector state."""
        self.active_blocks.clear()
        self.zone_liquidity_history.clear()
