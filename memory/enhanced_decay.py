"""
Enhanced Decay Logic for LiquidityMemoryNode

Adds invalidation detection and accelerated decay for broken levels.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DecayContext:
    """Context for applying decay to a node."""
    current_time: float
    current_price: Optional[float] = None  # For invalidation detection
    

class EnhancedDecayEngine:
    """
    Enhanced decay logic with invalidation detection.
    
    DECAY TYPES:
    1. Time-based (exponential): Normal passage of time
    2. Invalidation (accelerated): Price breaks through without reaction
    """
    
    # Invalidation thresholds
    CLEAN_BREAK_MULTIPLIER = 2.0  # Price must break by 2x band width to be "clean"
    NO_REACTION_TIME_SEC = 300.0  # 5 minutes without price returning = invalidated
    INVALIDATION_DECAY_MULTIPLIER = 10.0  # 10x faster decay when invalidated
    
    @classmethod
    def apply_decay(cls, node, context: DecayContext) -> dict:
        """
        Apply enhanced decay to node.
        
        Returns:
            Dictionary with decay details for logging
        """
        time_elapsed = context.current_time - node.last_interaction_ts
        
        # Base decay rate
        decay_rate = node.decay_rate
        decay_type = "time_based"
        
        # Check for invalidation (if current price provided)
        if context.current_price is not None:
            is_invalidated, reason = cls._check_invalidation(node, context.current_price, time_elapsed)
            
            if is_invalidated:
                # Accelerate decay
                decay_rate *= cls.INVALIDATION_DECAY_MULTIPLIER
                decay_type = f"invalidation_{reason}"
        
        # Apply exponential decay
        decay_factor = max(0.0, 1.0 - (decay_rate * time_elapsed))
        old_strength = node.strength
        node.strength *= decay_factor
        
        # Archive if below threshold
        if node.strength < 0.01:
            node.active = False
        
        return {
            'decay_type': decay_type,
            'time_elapsed': time_elapsed,
            'decay_rate': decay_rate,
            'old_strength': old_strength,
            'new_strength': node.strength,
            'archived': not node.active
        }
    
    @classmethod
    def _check_invalidation(cls, node, current_price: float, time_elapsed: float) -> tuple[bool, str]:
        """
        Check if node should be considered invalidated.
        
        Returns:
            (is_invalidated, reason)
        """
        # Calculate distance from node
        distance = abs(current_price - node.price_center)
        
        # INVALIDATION 1: Clean break through band
        if distance > node.price_band * cls.CLEAN_BREAK_MULTIPLIER:
            # Price has moved significantly away
            if time_elapsed > cls.NO_REACTION_TIME_SEC:
                # And hasn't returned in 5 minutes
                return True, "clean_break"
        
        # INVALIDATION 2: Price at node but no reaction
        if node.overlaps(current_price):
            # Price is AT the node level
            if time_elapsed > cls.NO_REACTION_TIME_SEC:
                # But node hasn't been interacted with in 5+ minutes
                # This means price is sitting at level but nothing is happening
                return True, "no_reaction"
        
        return False, ""


class NodeLifecycleAnalyzer:
    """
    Analyzes node lifecycle state based on properties.
    
    States are IMPLICIT - derived from:
    - strength (how significant)
    - recency (time since interaction)
    - distance (how far current price is)
    
    NO hardcoded enum transitions.
    """
    
    # Thresholds for state classification (soft boundaries)
    FORMING_MAX_AGE = 60.0  # Under 1 minute old = forming
    FORMING_MIN_STRENGTH = 0.3  # Needs at least 30% strength
    
    ESTABLISHED_MIN_STRENGTH = 0.5  # 50%+ strength = established
    ESTABLISHED_MIN_INTERACTIONS = 2  # Multiple interactions
    
    ACTIVE_MAX_TIME_SINCE_INTERACTION = 600.0  # Within 10 minutes = active
    ACTIVE_MIN_STRENGTH = 0.4  # 40%+ strength
    
    DORMANT_MAX_TIME = 3600.0  # Up to 1 hour idle = dormant
    DORMANT_MIN_STRENGTH = 0.1  # 10%+ strength
    
    @classmethod
    def get_lifecycle_state(cls, node, current_time: float, current_price: Optional[float] = None) -> str:
        """
        Determine implicit lifecycle state.
        
        Returns:
            State name: "forming", "established", "active", "dormant", or "archived"
        """
        if not node.active:
            return "archived"
        
        age = node.age_seconds(current_time)
        recency = node.time_since_interaction(current_time)
        
        # ARCHIVED: Strength dropped below threshold
        if node.strength < 0.01:
            return "archived"
        
        # FORMING: New node, still gathering evidence
        if age < cls.FORMING_MAX_AGE and node.strength < cls.FORMING_MIN_STRENGTH:
            return "forming"
        
        # ACTIVE: Recent interaction and decent strength (check BEFORE established)
        if (recency < cls.ACTIVE_MAX_TIME_SINCE_INTERACTION and 
            node.strength >= cls.ACTIVE_MIN_STRENGTH):
            return "active"
        
        # ESTABLISHED: Strong and proven but not recently active
        if (node.strength >= cls.ESTABLISHED_MIN_STRENGTH and 
            node.interaction_count >= cls.ESTABLISHED_MIN_INTERACTIONS):
            return "established"
        
        # DORMANT: Older but still has some strength
        if (recency < cls.DORMANT_MAX_TIME and 
            node.strength >= cls.DORMANT_MIN_STRENGTH):
            return "dormant"
        
        # Default to dormant if none of above (transitioning to archive)
        return "dormant"
    
    @classmethod
    def get_lifecycle_metadata(cls, node, current_time: float, current_price: Optional[float] = None) -> dict:
        """
        Get detailed lifecycle metadata.
        
        Returns:
            Dictionary with state and contributing factors
        """
        state = cls.get_lifecycle_state(node, current_time, current_price)
        age = node.age_seconds(current_time)
        recency = node.time_since_interaction(current_time)
        
        metadata = {
            'state': state,
            'age_seconds': age,
            'time_since_interaction': recency,
            'strength': node.strength,
            'confidence': node.confidence,
            'interaction_count': node.interaction_count,
        }
        
        # Add distance if current price provided
        if current_price is not None:
            distance = abs(current_price - node.price_center)
            distance_bps = (distance / current_price) * 10000
            metadata['distance_from_price_bps'] = distance_bps
            metadata['is_at_price'] = node.overlaps(current_price)
        
        return metadata
    
    @classmethod
    def describe_transition(cls, old_state: str, new_state: str) -> str:
        """
        Describe what transition occurred.
        
        Returns:
            Human-readable description
        """
        transitions = {
            ('forming', 'established'): "Node gained sufficient strength and interactions",
            ('forming', 'active'): "Node received recent interaction",
            ('forming', 'archived'): "Node failed to strengthen (decayed)",
            ('established', 'active'): "Price returned to established level",
            ('established', 'dormant'): "No recent interaction, strength maintained",
            ('established', 'archived'): "Level broken or forgotten",
            ('active', 'dormant'): "Activity ceased, entering quieter phase",
            ('active', 'archived'): "Rapid decay (likely invalidated)",
            ('dormant', 'active'): "Price returned, node reactivated",
            ('dormant', 'archived'): "Extended dormancy led to archival",
        }
        
        return transitions.get((old_state, new_state), f"Transitioned from {old_state} to {new_state}")
