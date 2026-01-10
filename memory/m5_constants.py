"""
M5 Constants - Strict Prohibition Rules and Neutral Defaults.
This file defines the immutable laws of the M5 Governance Layer.
"""

from typing import List, Dict, Any

# ==============================================================================
# 1. FORBIDDEN PARAMETERS (INPUT SCAN)
# queries containing these keys anywhere will be rejected.
# ==============================================================================
GLOBAL_FORBIDDEN_PARAMS: List[str] = [
    # Evaluative Terms
    "min_strength", "max_strength", "min_score", "max_score",
    "importance", "quality", "rank", "rating",
    "significance", "weight", "priority",
    
    # Financial/Strategic Terms
    "alpha", "beta", "pnl", "profit", "loss",
    "return", "yield", "margin",
    "signal", "alert", "trigger",
    "opportunity", "edge",
    
    # Directional Terms
    "bullish", "bearish", "long", "short",
    "support", "resistance", "trend", "momentum",
    
    # Implicit/Lazy Filtering
    "top_n", "best", "worst", "limit_quality",
    "recent_best", "strongest", "weakest"
]

# ==============================================================================
# 2. FORBIDDEN OUTPUT FIELDS (OUTPUT SCAN)
# outputs containing these keys will cause an internal system error.
# ==============================================================================
GLOBAL_FORBIDDEN_OUTPUTS: List[str] = [
    "score", "rank", "rating", "quality",
    "confidence", "probability", "likelihood",
    "prediction", "forecast", "expectation",
    "bullish_intensity", "bearish_intensity",
    "buy_signal", "sell_signal", "action",
    "recommendation", "alpha", "edge"
]

# ==============================================================================
# 3. FORBIDDEN SEMANTIC PATTERNS (VALUE SCAN)
# string values matching these patterns will be rejected.
# ==============================================================================
FORBIDDEN_VALUE_PATTERNS: List[str] = [
    "STRONG_", "WEAK_", "GOOD_", "BAD_",
    "BULL_", "BEAR_",
    "ENTRY", "EXIT",
    "BUY", "SELL",  # Except as part of standard specific event types
    "POSITIVE", "NEGATIVE",
    "PROFIT", "LOSS",
    "SCORE", "RANK"
]

# ==============================================================================
# 4. NEUTRAL DEFAULTS
# These values MUST be used if the caller does not provide them.
# ==============================================================================
NEUTRAL_DEFAULTS: Dict[str, Any] = {
    # Limit=None implies "Return All", avoiding "Top 10" bias
    "limit": None,
    "max_count": None,
    
    # Sorting
    "sort_by": "time",     # Neutral chronological sort
    "sort_order": "asc",   # Standard ascending
    
    # Inclusion
    "include_archived": False,
    "include_dormant": False,
    
    # Time
    "lookback_seconds": None,  # Infinite lookback
    "max_tokens": None         # All tokens
}

# ==============================================================================
# 5. ERROR MESSAGES
# Standardized feedback for rejection.
# ==============================================================================
ERR_EVALUATIVE = "EvaluativeQueryError: Parameter '{param}' implies judgment/selection."
ERR_SEMANTIC = "EpistemicSafetyError: Value '{value}' contains forbidden semantic pattern."
ERR_DETERMINISM = "DeterminismError: Explicit time parameter required."
ERR_SCHEMA = "SchemaValidationError: {details}"
