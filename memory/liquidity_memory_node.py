"""
Liquidity Memory Node (LMN) — Phase M1

Represents a price band that historically mattered.

CONSTRAINTS:
- NO signal generation
- NO strategy-specific fields
- Purely observational
- Deterministic on replay
"""

from dataclasses import dataclass, field
from typing import Literal
from enum import Enum


class CreationReason(Enum):
    """Why this memory node was created."""
    ORDERBOOK_PERSISTENCE = "orderbook_persistence"  # Zone persisted for significant time
    EXECUTED_LIQUIDITY = "executed_liquidity"        # Significant volume executed
    LIQUIDATION_INTERACTION = "liquidation_interaction"  # Liquidations occurred near level
    PRICE_REJECTION = "price_rejection"              # Price repeatedly rejected at level


@dataclass
class LiquidityMemoryNode:
    """
    Represents a price band with historical significance.
    
    Memory is built from evidence, strengthened by interaction,
    decayed by time, and archived when irrelevant.
    
    This is OBSERVATION, not DETECTION.
    """
    
    # Identity
    id: str  # Unique identifier (e.g., "bid_2.01_1767446412")
    
    # Price characteristics
    price_center: float  # Center of price band (e.g., 2.0100)
    price_band: float    # Width of band in absolute terms (e.g., 0.0010 = ±0.05%)
    side: Literal["bid", "ask", "both"]  # Which side(s) this memory represents
    
    # Temporal tracking
    first_seen_ts: float      # Timestamp when node was created
    last_interaction_ts: float  # Timestamp of most recent meaningful interaction
    
    # Memory strength
    strength: float     # Current strength of this memory (0.0 to 1.0)
    confidence: float   # Confidence in this memory's relevance (0.0 to 1.0)
    
    # Metadata
    creation_reason: CreationReason  # Why this node was created
    decay_rate: float   # Rate at which strength decays per second (e.g., 0.001)
    active: bool        # Whether this node is currently active (not archived)
    
    # Interaction counters (observational only)
    interaction_count: int = 0  # Number of times price interacted with this band
    volume_observed: float = 0.0  # Total volume observed at this level
    
    def __post_init__(self):
        """Validate node parameters."""
        assert 0.0 <= self.strength <= 1.0, f"Strength must be [0,1], got {self.strength}"
        assert 0.0 <= self.confidence <= 1.0, f"Confidence must be [0,1], got {self.confidence}"
        assert self.price_band > 0, f"Price band must be positive, got {self.price_band}"
        assert self.decay_rate >= 0, f"Decay rate must be non-negative, got {self.decay_rate}"
        assert self.first_seen_ts <= self.last_interaction_ts, \
            "last_interaction_ts cannot be before first_seen_ts"
    
    def update_interaction(self, timestamp: float, volume: float = 0.0):
        """
        Record an interaction with this price level.
        
        Args:
            timestamp: When the interaction occurred
            volume: Optional volume associated with interaction
        """
        self.last_interaction_ts = max(self.last_interaction_ts, timestamp)
        self.interaction_count += 1
        self.volume_observed += volume
    
    def apply_decay(self, current_timestamp: float, current_price: float = None):
        """
        Apply time-based decay to strength.
        
        Args:
            current_timestamp: Current time for decay calculation
            current_price: Optional current price for invalidation detection
        """
        if not self.active:
            return
        
        time_elapsed = current_timestamp - self.last_interaction_ts
        decay_factor = max(0.0, 1.0 - (self.decay_rate * time_elapsed))
        self.strength *= decay_factor
        
        # Archive if strength drops below threshold
        if self.strength < 0.01:
            self.active = False
    
    def apply_enhanced_decay(self, current_timestamp: float, current_price: float = None) -> dict:
        """
        Apply enhanced decay with invalidation detection.
        
        Args:
            current_timestamp: Current time
            current_price: Optional current price for invalidation detection
        
        Returns:
            Decay details dictionary
        """
        from memory.enhanced_decay import EnhancedDecayEngine, DecayContext
        
        context = DecayContext(
            current_time=current_timestamp,
            current_price=current_price
        )
        
        return EnhancedDecayEngine.apply_decay(self, context)
    
    def get_lifecycle_state(self, current_time: float, current_price: float = None) -> str:
        """
        Get implicit lifecycle state.
        
        Returns:
            State: "forming", "established", "active", "dormant", or "archived"
        """
        from memory.enhanced_decay import NodeLifecycleAnalyzer
        return NodeLifecycleAnalyzer.get_lifecycle_state(self, current_time, current_price)
    
    def get_lifecycle_metadata(self, current_time: float, current_price: float = None) -> dict:
        """Get detailed lifecycle metadata."""
        from memory.enhanced_decay import NodeLifecycleAnalyzer
        return NodeLifecycleAnalyzer.get_lifecycle_metadata(self, current_time, current_price)
    
    def age_seconds(self, current_timestamp: float) -> float:
        """Get age of this node in seconds."""
        return current_timestamp - self.first_seen_ts
    
    def time_since_interaction(self, current_timestamp: float) -> float:
        """Get time since last interaction in seconds."""
        return current_timestamp - self.last_interaction_ts
    
    def overlaps(self, price: float) -> bool:
        """Check if a price falls within this node's band."""
        lower = self.price_center - (self.price_band / 2)
        upper = self.price_center + (self.price_band / 2)
        return lower <= price <= upper
    
    def to_dict(self) -> dict:
        """Export node to dictionary for serialization."""
        return {
            'id': self.id,
            'price_center': self.price_center,
            'price_band': self.price_band,
            'side': self.side,
            'first_seen_ts': self.first_seen_ts,
            'last_interaction_ts': self.last_interaction_ts,
            'strength': self.strength,
            'confidence': self.confidence,
            'creation_reason': self.creation_reason.value,
            'decay_rate': self.decay_rate,
            'active': self.active,
            'interaction_count': self.interaction_count,
            'volume_observed': self.volume_observed,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LiquidityMemoryNode':
        """Create node from dictionary."""
        data['creation_reason'] = CreationReason(data['creation_reason'])
        return cls(**data)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "ACTIVE" if self.active else "ARCHIVED"
        return (
            f"LMN({self.side} ${self.price_center:.4f}±{self.price_band:.4f} "
            f"str={self.strength:.2f} conf={self.confidence:.2f} "
            f"age={self.age_seconds(self.last_interaction_ts):.0f}s {status})"
        )
