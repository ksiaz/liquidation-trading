"""
M3 Evidence Token System

Neutral, atomic event tokens for temporal evidence ordering.
NO directional inference, NO semantic interpretation.

Each token represents a single, observable, factual event type.
"""

from enum import Enum
from typing import Optional


class EvidenceToken(Enum):
    """
    Closed set of neutral evidence tokens for M3 temporal ordering.
    
    Each token represents a single, observable event with factual trigger conditions.
    NO directional bias (no BUY/SELL, LONG/SHORT, UP/DOWN).
    NO semantic meaning (no BREAKOUT, DEFEND, ABSORPTION).
    
    Token set is CLOSED - no additions without violating neutrality principle.
    """
    
    # ==================== ORDERBOOK EVENTS ====================
    
    OB_APPEAR = "ob_appear"
    # Trigger: Orderbook level appears within node's price band
    # Factual condition: level exists now, didn't exist before
    # NOT interpretive: does not imply "support building"
    
    OB_PERSIST = "ob_persist"
    # Trigger: Orderbook level remains present ≥N seconds
    # Factual condition: level existed continuously for threshold duration
    # NOT interpretive: does not imply "strong level"
    
    OB_VANISH = "ob_vanish"
    # Trigger: Orderbook level disappears from node's price band
    # Factual condition: level existed, now doesn't exist
    # NOT interpretive: does not imply "broken" or "swept"
    
    # ==================== TRADE EVENTS ====================
    
    TRADE_EXEC = "trade_exec"
    # Trigger: Trade executed at price within node's band
    # Factual condition: trade.price within [center - band, center + band]
    # NOT interpretive: does not imply direction or aggression
    
    TRADE_VOLUME_HIGH = "trade_vol_high"
    # Trigger: Single trade volume exceeds configured threshold
    # Factual condition: trade.price * trade.quantity > volume_threshold
    # NOT interpretive: does not imply "important" or "institutional"
    
    # ==================== LIQUIDATION EVENTS ====================
    
    LIQ_OCCUR = "liq_occur"
    # Trigger: Liquidation occurred within proximity to node price
    # Factual condition: abs(liq.price - node.price) / current_price < proximity_bps
    # NOT interpretive: does not imply "stop hunt" or "cascade trigger"
    
    LIQ_CASCADE = "liq_cascade"
    # Trigger: Multiple liquidations (≥N) within short time window (≤T seconds)
    # Factual condition: count(liquidations in [t-T, t]) >= cascade_threshold
    # NOT interpretive: does not imply "forced selling" or "panic"
    
    # ==================== PRICE EVENTS ====================
    
    PRICE_TOUCH = "price_touch"
    # Trigger: Market price moved into node's price band from outside
    # Factual condition: price_previous outside band AND price_current inside band
    # NOT interpretive: does not imply "test" or "probe"
    
    PRICE_EXIT = "price_exit"
    # Trigger: Market price moved out of node's price band
    # Factual condition: price_previous inside band AND price_current outside band
    # NOT interpretive: does not imply "rejection" or "breakthrough"
    
    PRICE_DWELL = "price_dwell"
    # Trigger: Market price remained within node's band for threshold duration
    # Factual condition: price stayed within band continuously for ≥dwell_seconds
    # NOT interpretive: does not imply "consolidation" or "accumulation"


# Tokenization configuration (factual detection thresholds)
class TokenizationConfig:
    """
    Configuration for evidence token detection.
    
    These are DETECTION THRESHOLDS, NOT importance scores.
    They define when factual events trigger tokens.
    """
    
    # Orderbook persistence threshold
    PERSISTENCE_SECONDS: float = 30.0  # OB_PERSIST trigger
    
    # Trade volume threshold (USD)
    VOLUME_THRESHOLD_USD: float = 50000.0  # TRADE_VOLUME_HIGH trigger
    
    # Liquidation proximity (basis points)
    LIQ_PROXIMITY_BPS: float = 10.0  # LIQ_OCCUR trigger
    
    # Liquidation cascade parameters
    CASCADE_COUNT: int = 3  # Minimum liquidations for cascade
    CASCADE_WINDOW_SEC: float = 5.0  # Time window for cascade
    
    # Price dwell threshold
    DWELL_SECONDS: float = 60.0  # PRICE_DWELL trigger


def tokenize_orderbook_event(
    event_type: str,
    level_exists_now: bool,
    level_existed_before: bool,
    persistence_duration: Optional[float] = None
) -> Optional[EvidenceToken]:
    """
    Tokenize an orderbook event.
    
    Stateless, deterministic, rule-based.
    NO interpretation or prediction.
    
    Args:
        event_type: Type of orderbook event
        level_exists_now: Whether level currently exists in orderbook
        level_existed_before: Whether level existed in previous snapshot
        persistence_duration: How long level has been present (seconds)
    
    Returns:
        EvidenceToken or None if no token applies
    """
    # Level appeared
    if not level_existed_before and level_exists_now:
        return EvidenceToken.OB_APPEAR
    
    # Level vanished
    if level_existed_before and not level_exists_now:
        return EvidenceToken.OB_VANISH
    
    # Level persisted
    if (level_exists_now and level_existed_before and 
        persistence_duration is not None and 
        persistence_duration >= TokenizationConfig.PERSISTENCE_SECONDS):
        return EvidenceToken.OB_PERSIST
    
    return None


def tokenize_trade_event(
    trade_value_usd: float,
    price_in_node_band: bool
) -> Optional[EvidenceToken]:
    """
    Tokenize a trade event.
    
    Stateless, deterministic, rule-based.
    NO directional inference.
    
    Args:
        trade_value_usd: Trade value in USD (price * quantity)
        price_in_node_band: Whether trade price is within node's band
    
    Returns:
        EvidenceToken or None if trade not in band
    """
    if not price_in_node_band:
        return None
    
    # Always emit TRADE_EXEC for any trade in band
    # Optionally also emit TRADE_VOLUME_HIGH if threshold exceeded
    if trade_value_usd >= TokenizationConfig.VOLUME_THRESHOLD_USD:
        # NOTE: Both TRADE_EXEC and TRADE_VOLUME_HIGH should be emitted
        # Return TRADE_VOLUME_HIGH here; caller should also emit TRADE_EXEC
        return EvidenceToken.TRADE_VOLUME_HIGH
    
    return EvidenceToken.TRADE_EXEC


def tokenize_liquidation_event(
    distance_bps: float,
    recent_liquidation_count: int,
    time_window_sec: float
) -> Optional[EvidenceToken]:
    """
    Tokenize a liquidation event.
    
    Stateless, deterministic, rule-based.
    NO directional inference (no LONG/SHORT distinction).
    
    Args:
        distance_bps: Distance from node price in basis points
        recent_liquidation_count: Number of liquidations in recent window
        time_window_sec: Time window for cascade detection
    
    Returns:
        EvidenceToken or None if liquidation not in proximity
    """
    if distance_bps > TokenizationConfig.LIQ_PROXIMITY_BPS:
        return None
    
    # Check for cascade
    if (recent_liquidation_count >= TokenizationConfig.CASCADE_COUNT and
        time_window_sec <= TokenizationConfig.CASCADE_WINDOW_SEC):
        return EvidenceToken.LIQ_CASCADE
    
    return EvidenceToken.LIQ_OCCUR


def tokenize_price_event(
    price_in_band_now: bool,
    price_in_band_before: bool,
    dwell_duration: Optional[float] = None
) -> Optional[EvidenceToken]:
    """
    Tokenize a price movement event.
    
    Stateless, deterministic, rule-based.
    NO outcome interpretation (no rejection/breakthrough semantics).
    
    Args:
        price_in_band_now: Whether price is currently in node's band
        price_in_band_before: Whether price was in band before
        dwell_duration: How long price has been in band (seconds)
    
    Returns:
        EvidenceToken or None if no transition
    """
    # Price entered band
    if not price_in_band_before and price_in_band_now:
        return EvidenceToken.PRICE_TOUCH
    
    # Price exited band
    if price_in_band_before and not price_in_band_now:
        return EvidenceToken.PRICE_EXIT
    
    # Price dwelling in band
    if (price_in_band_now and price_in_band_before and
        dwell_duration is not None and
        dwell_duration >= TokenizationConfig.DWELL_SECONDS):
        return EvidenceToken.PRICE_DWELL
    
    return None


# Tokenization validation
def is_valid_token(token: EvidenceToken) -> bool:
    """
    Validate that token is in the approved set.
    
    Always returns True for EvidenceToken enum members.
    Provided for explicit validation in critical paths.
    """
    return isinstance(token, EvidenceToken)


def get_token_source_type(token: EvidenceToken) -> str:
    """
    Get the source type for a token (orderbook/trade/liquidation/price).
    
    Factual categorization, NOT importance weighting.
    """
    if token in (EvidenceToken.OB_APPEAR, EvidenceToken.OB_PERSIST, EvidenceToken.OB_VANISH):
        return "orderbook"
    elif token in (EvidenceToken.TRADE_EXEC, EvidenceToken.TRADE_VOLUME_HIGH):
        return "trade"
    elif token in (EvidenceToken.LIQ_OCCUR, EvidenceToken.LIQ_CASCADE):
        return "liquidation"
    elif token in (EvidenceToken.PRICE_TOUCH, EvidenceToken.PRICE_EXIT, EvidenceToken.PRICE_DWELL):
        return "price"
    else:
        return "unknown"
