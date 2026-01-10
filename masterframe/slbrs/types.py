"""
Liquidity Block Type Definitions

Data structures for liquidity block representation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import uuid


class BlockType(Enum):
    """
    Liquidity block classification.
    
    ABSORPTION: High execution, price stayed (tradable)
    CONSUMPTION: High execution, price broke through (non-tradable)
    SPOOF: Low execution or high cancellations (non-tradable)
    """
    ABSORPTION = "ABSORPTION"
    CONSUMPTION = "CONSUMPTION"
    SPOOF = "SPOOF"


@dataclass(frozen=True)
class LiquidityBlock:
    """
    Detected liquidity block.
    
    INVARIANT: Immutable snapshot of block state.
    INVARIANT: Only ABSORPTION blocks have is_tradable = True.
    """
    block_id: str  # Unique identifier
    zone_name: str  # 'A' or 'B'
    side: str  # 'bid' or 'ask'
    block_type: BlockType
    
    # Qualification metrics
    zone_liquidity: float
    rolling_zone_avg: float
    persistence_seconds: float
    executed_volume: float
    canceled_volume: float
    cancel_to_trade_ratio: float
    
    # Price tracking
    price_min: float
    price_max: float
    initial_price: float  # Price when block first detected
    current_price: float  # Current mid-price
    
    # Timestamps
    first_seen: float
    last_updated: float
    
    # Status flags
    is_tradable: bool  # True only for ABSORPTION
    is_invalidated: bool  # True if price accepted through
    
    def is_qualified(self) -> bool:
        """
        Check if block meets ALL qualification criteria.
        
        Returns:
            True if all 4 conditions met
        
        Conditions:
        1. zone_liquidity >= 2.5 × rolling_zone_avg
        2. persistence >= 30 seconds
        3. executed_volume > 0
        4. cancel_to_trade_ratio < 3.5
        """
        return (
            self.zone_liquidity >= 2.5 * self.rolling_zone_avg and
            self.persistence_seconds >= 30.0 and
            self.executed_volume > 0 and
            self.cancel_to_trade_ratio < 3.5
        )
    
    @staticmethod
    def generate_block_id(zone_name: str, side: str, timestamp: float) -> str:
        """
        Generate unique block ID.
        
        Args:
            zone_name: Zone name
            side: Side (bid/ask)
            timestamp: Current timestamp
        
        Returns:
            Unique block ID
        """
        # Use short UUID for uniqueness
        unique_id = str(uuid.uuid4())[:8]
        return f"{zone_name}_{side}_{int(timestamp)}_{unique_id}"
