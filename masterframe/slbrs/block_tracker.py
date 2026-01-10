"""
Block Tracker

Tracks active liquidity blocks over time.

RULES:
- Maintains block history
- Removes invalidated blocks
- Removes stale blocks (older than max age)
- Filters tradable (ABSORPTION) blocks
"""

from typing import Dict, List
import sys
sys.path.append('d:/liquidation-trading')
from .types import LiquidityBlock, BlockType


class BlockTracker:
    """
    Tracks active liquidity blocks over time.
    
    INVARIANT: Maintains block history.
    INVARIANT: Removes invalidated/stale blocks.
    """
    
    MAX_BLOCK_AGE_SECONDS = 300.0  # 5 minutes
    
    def __init__(self):
        """Initialize block tracker."""
        self.active_blocks: Dict[str, LiquidityBlock] = {}
        self.block_history: List[LiquidityBlock] = []
    
    def update(
        self,
        detected_blocks: List[LiquidityBlock],
        current_price: float,
        current_time: float
    ) -> Dict[str, LiquidityBlock]:
        """
        Update tracked blocks.
        
        Args:
            detected_blocks: Newly detected blocks
            current_price: Current mid-price
            current_time: Current timestamp
        
        Returns:
            Active blocks dict
        
        RULE: Remove invalidated blocks.
        RULE: Remove blocks older than MAX_AGE.
        """
        # Add new blocks
        for block in detected_blocks:
            self.active_blocks[block.block_id] = block
            
            # Add to history if not already there
            if not any(b.block_id == block.block_id for b in self.block_history):
                self.block_history.append(block)
        
        # Remove invalidated blocks (price broke through)
        blocks_to_remove = []
        for block_id, block in self.active_blocks.items():
            # Check if price broke through block
            if self._is_invalidated(block, current_price):
                blocks_to_remove.append(block_id)
            
            # Check if block is too old
            elif (current_time - block.first_seen) > self.MAX_BLOCK_AGE_SECONDS:
                blocks_to_remove.append(block_id)
            
            # Check if block no longer qualified
            elif not block.is_qualified():
                blocks_to_remove.append(block_id)
        
        for block_id in blocks_to_remove:
            del self.active_blocks[block_id]
        
        return self.active_blocks
    
    def _is_invalidated(self, block: LiquidityBlock, current_price: float) -> bool:
        """
        Check if block is invalidated by price acceptance.
        
        Args:
            block: Liquidity block
            current_price: Current mid-price
        
        Returns:
            True if price broke through block
        
        RULE: Bid blocks invalidated if price goes below.
        RULE: Ask blocks invalidated if price goes above.
        """
        if block.side == 'bid':
            # Bid block - invalidated if price breaks below
            return current_price < block.price_min
        else:  # ask
            # Ask block - invalidated if price breaks above
            return current_price > block.price_max
    
    def get_tradable_blocks(self) -> List[LiquidityBlock]:
        """
        Get only tradable (ABSORPTION) blocks.
        
        Returns:
            List of ABSORPTION blocks
        
        RULE: Filter for is_tradable = True.
        RULE: Only ABSORPTION blocks are tradable.
        """
        return [
            block for block in self.active_blocks.values()
            if block.is_tradable and block.block_type == BlockType.ABSORPTION
        ]
    
    def get_active_blocks(self) -> Dict[str, LiquidityBlock]:
        """Get all active blocks."""
        return self.active_blocks
    
    def get_block_history(self) -> List[LiquidityBlock]:
        """Get block history."""
        return self.block_history
    
    def reset(self) -> None:
        """Reset tracker state."""
        self.active_blocks.clear()
        self.block_history.clear()
