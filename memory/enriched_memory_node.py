"""
Enriched Liquidity Memory Node

Extends basic node with dense factual evidence across 4 dimensions:
- Interaction frequency & diversity
- Flow imbalance (non-directional)
- Temporal stability
- Stress proximity history

NO signals, NO predictions, NO strategy logic.
"""

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple, Dict
from collections import deque
import statistics


@dataclass
class EnrichedLiquidityMemoryNode:
    """
    Information-dense factual record of historically significant price level.
    All fields are directly observable facts from market data.
    """
    
    # IDENTITY
    id: str
    symbol: str  # Partitioning key for multi-symbol support
    price_center: float
    price_band: float
    side: Literal["bid", "ask", "both"]
    
    # TEMPORAL TRACKING
    first_seen_ts: float
    last_interaction_ts: float
    
    # MEMORY STATE
    strength: float
    confidence: float
    active: bool
    decay_rate: float
    creation_reason: str
    
    # DIMENSION 1: INTERACTION FREQUENCY & DIVERSITY
    interaction_count: int = 0
    orderbook_appearance_count: int = 0
    trade_execution_count: int = 0
    liquidation_proximity_count: int = 0
    
    volume_total: float = 0.0
    volume_largest_event: float = 0.0
    volume_concentration_ratio: float = 0.0
    
    # DIMENSION 2: FLOW EVIDENCE (NON-DIRECTIONAL)
    buyer_initiated_volume: float = 0.0
    seller_initiated_volume: float = 0.0
    passive_fill_volume: float = 0.0
    aggressive_fill_volume: float = 0.0
    
    # DIMENSION 3: TEMPORAL STABILITY
    interaction_timestamps: deque = field(default_factory=lambda: deque(maxlen=50))
    interaction_gap_median: float = 0.0
    interaction_gap_stddev: float = 0.0
    strength_history: List[float] = field(default_factory=list)
    
    # DIMENSION 4: STRESS PROXIMITY HISTORY
    liquidations_within_band: int = 0
    long_liquidations: int = 0
    short_liquidations: int = 0
    liquidation_timestamps: deque = field(default_factory=lambda: deque(maxlen=20))
    max_liquidation_cascade_size: int = 0
    
    # METADATA
    last_decay_application_ts: float = 0.0

    # ORDER BOOK STATE (Phase OB-1)
    resting_size_bid: float = 0.0
    resting_size_ask: float = 0.0
    last_orderbook_update_ts: Optional[float] = None
    orderbook_update_count: int = 0

    # M3: TEMPORAL EVIDENCE ORDERING (Phase M3 extension)
    # Sequence buffer for chronological token ordering
    sequence_buffer: 'SequenceBuffer' = None  # type: ignore
    # Motif tracking dictionaries
    motif_counts: dict = field(default_factory=dict)  # {motif_tuple: count}
    motif_last_seen: dict = field(default_factory=dict)  # {motif_tuple: timestamp}
    motif_strength: dict = field(default_factory=dict)  # {motif_tuple: strength}
    total_sequences_observed: int = 0
    
    def __post_init__(self):
        """Validate invariants."""
        assert 0.0 <= self.strength <= 1.0, f"Strength must be [0,1], got {self.strength}"
        assert 0.0 <= self.confidence <= 1.0, f"Confidence must be [0,1], got {self.confidence}"
        assert self.price_band > 0, f"Price band must be positive, got {self.price_band}"
        assert self.first_seen_ts <= self.last_interaction_ts
        
        # Initialize M3 sequence buffer if not set (backward compatibility)
        if self.sequence_buffer is None:
            from memory.m3_sequence_buffer import SequenceBuffer
            self.sequence_buffer = SequenceBuffer()
    
    def record_orderbook_appearance(self, timestamp: float):
        """Record orderbook appearance evidence."""
        self.orderbook_appearance_count += 1
        self.interaction_count += 1
        self.last_interaction_ts = timestamp
        self.interaction_timestamps.append(timestamp)
        self._update_temporal_stats()
    
    def record_trade_execution(self, timestamp: float, volume: float, is_buyer_maker: bool):
        """Record trade execution evidence."""
        self.trade_execution_count += 1
        self.interaction_count += 1
        self.last_interaction_ts = timestamp
        self.interaction_timestamps.append(timestamp)
        
        self.volume_total += volume
        if volume > self.volume_largest_event:
            self.volume_largest_event = volume
        
        if is_buyer_maker:
            self.seller_initiated_volume += volume
            self.aggressive_fill_volume += volume
        else:
            self.buyer_initiated_volume += volume
            self.passive_fill_volume += volume
        
        self._update_volume_concentration()
        self._update_temporal_stats()
    
    def record_liquidation(self, timestamp: float, side: str):
        """Record liquidation proximity evidence."""
        self.liquidation_proximity_count += 1
        self.liquidations_within_band += 1
        self.interaction_count += 1
        self.last_interaction_ts = timestamp
        self.interaction_timestamps.append(timestamp)
        self.liquidation_timestamps.append(timestamp)
        
        if side == "BUY":
            self.long_liquidations += 1
        else:
            self.short_liquidations += 1
        
        self._update_cascade_size()
        self._update_temporal_stats()
    
    def record_price_touch(self, timestamp: float):
        """Record implicit price touch."""
        self.interaction_count += 1
        self.last_interaction_ts = timestamp
        self.interaction_timestamps.append(timestamp)
        self._update_temporal_stats()
    
    def apply_decay(self, current_timestamp: float, current_price: float = None):
        """Apply time-based decay."""
        if not self.active:
            return
        
        time_elapsed = current_timestamp - self.last_interaction_ts
        decay_factor = max(0.0, 1.0 - (self.decay_rate * time_elapsed))
        self.strength *= decay_factor
        
        if self.strength < 0.01:
            self.active = False
        
        self.last_decay_application_ts = current_timestamp
    
    def apply_enhanced_decay(self, current_timestamp: float, current_price: float = None) -> dict:
        """Apply enhanced decay with invalidation detection."""
        from memory.enhanced_decay import EnhancedDecayEngine, DecayContext
        
        context = DecayContext(
            current_time=current_timestamp,
            current_price=current_price
        )
        
        return EnhancedDecayEngine.apply_decay(self, context)
    
    def checkpoint_strength(self):
        """Save current strength to history."""
        if len(self.strength_history) >= 10:
            self.strength_history.pop(0)
        self.strength_history.append(self.strength)
    
    def _update_temporal_stats(self):
        """Update temporal statistics from interaction timestamps."""
        if len(self.interaction_timestamps) < 2:
            return
        
        timestamps = list(self.interaction_timestamps)
        gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        
        if gaps:
            self.interaction_gap_median = statistics.median(gaps)
            if len(gaps) > 1:
                self.interaction_gap_stddev = statistics.stdev(gaps)
    
    def _update_volume_concentration(self):
        """Calculate volume concentration ratio (placeholder - needs full event history)."""
        if self.volume_total > 0:
            self.volume_concentration_ratio = min(1.0, self.volume_largest_event / self.volume_total)
    
    def _update_cascade_size(self):
        """Update maximum liquidation cascade size."""
        if len(self.liquidation_timestamps) < 2:
            self.max_liquidation_cascade_size = max(1, self.max_liquidation_cascade_size)
            return
        
        timestamps = list(self.liquidation_timestamps)
        max_cascade = 1
        current_cascade = 1
        
        for i in range(1, len(timestamps)):
            if timestamps[i] - timestamps[i-1] <= 10.0:
                current_cascade += 1
                max_cascade = max(max_cascade, current_cascade)
            else:
                current_cascade = 1
        
        self.max_liquidation_cascade_size = max_cascade
    
    def overlaps(self, price: float) -> bool:
        """Check if price falls within band."""
        lower = self.price_center - (self.price_band / 2)
        upper = self.price_center + (self.price_band / 2)
        return lower <= price <= upper
    
    def age_seconds(self, current_timestamp: float) -> float:
        """Get age in seconds."""
        return current_timestamp - self.first_seen_ts
    
    def time_since_interaction(self, current_timestamp: float) -> float:
        """Get time since last interaction."""
        return current_timestamp - self.last_interaction_ts
    
    def get_lifecycle_state(self, current_time: float, current_price: float = None) -> str:
        """Get implicit lifecycle state."""
        from memory.enhanced_decay import NodeLifecycleAnalyzer
        return NodeLifecycleAnalyzer.get_lifecycle_state(self, current_time, current_price)
    
    def to_dict(self) -> dict:
        """Export to dict."""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'price_center': self.price_center,
            'price_band': self.price_band,
            'side': self.side,
            'first_seen_ts': self.first_seen_ts,
            'last_interaction_ts': self.last_interaction_ts,
            'strength': self.strength,
            'confidence': self.confidence,
            'active': self.active,
            'decay_rate': self.decay_rate,
            'creation_reason': self.creation_reason,
            'interaction_count': self.interaction_count,
            'orderbook_appearance_count': self.orderbook_appearance_count,
            'trade_execution_count': self.trade_execution_count,
            'liquidation_proximity_count': self.liquidation_proximity_count,
            'volume_total': self.volume_total,
            'volume_largest_event': self.volume_largest_event,
            'buyer_initiated_volume': self.buyer_initiated_volume,
            'seller_initiated_volume': self.seller_initiated_volume,
            'interaction_gap_median': self.interaction_gap_median,
            'liquidations_within_band': self.liquidations_within_band,
            'long_liquidations': self.long_liquidations,
            'short_liquidations': self.short_liquidations,
            'max_liquidation_cascade_size': self.max_liquidation_cascade_size,
        }
    
    def __repr__(self) -> str:
        """String representation."""
        status = "ACTIVE" if self.active else "ARCHIVED"
        return (
            f"EnrichedLMN({self.symbol} {self.side} ${self.price_center:.4f}±{self.price_band:.4f} "
            f"str={self.strength:.2f} interactions={self.interaction_count} "
            f"vol=${self.volume_total:.0f} {status})"
        )
