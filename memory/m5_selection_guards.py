"""
M5 Selection Guards - The Police of the Firewall.
Enforces strict neutrality and prohibits evaluative language.
"""

from typing import Dict, Any, Optional
from memory.m5_constants import (
    GLOBAL_FORBIDDEN_PARAMS,
    FORBIDDEN_VALUE_PATTERNS,
    NEUTRAL_DEFAULTS,
    ERR_EVALUATIVE,
    ERR_SEMANTIC,
    ERR_DETERMINISM
)

class EpistemicSafetyError(Exception):
    """Raised when a query violates M5 safety protocols."""
    pass

class DeterminismError(Exception):
    """Raised when a query violates determinism rules (e.g. implicit time)."""
    pass

def validate_keys(params: Dict[str, Any]) -> None:
    """
    Scan all keys in the params dict against forbidden list.
    Raises EpistemicSafetyError if violation found.
    """
    for key in params.keys():
        if key in GLOBAL_FORBIDDEN_PARAMS:
            raise EpistemicSafetyError(ERR_EVALUATIVE.format(param=key))

def validate_values(params: Dict[str, Any]) -> None:
    """
    Scan all string values for forbidden semantic patterns.
    Raises EpistemicSafetyError if violation found.
    """
    for value in params.values():
        if isinstance(value, str):
            upper_val = value.upper()
            for pattern in FORBIDDEN_VALUE_PATTERNS:
                if pattern in upper_val:
                    # Explicitly reject any forbidden pattern match
                    raise EpistemicSafetyError(ERR_SEMANTIC.format(value=value))

def enforce_determinism(params: Dict[str, Any]) -> None:
    """
    Ensure clear time handling.
    """
    # Check 1: No "now" or "latest" strings in values
    for val in params.values():
        if val in ["now", "latest", "current", "realtime"]:
            raise DeterminismError(ERR_DETERMINISM)

def inject_neutral_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a NEW dict with neutral defaults injected for missing keys.
    Does not modify input.
    """
    cleaned = params.copy()
    
    for key, default_val in NEUTRAL_DEFAULTS.items():
        if key not in cleaned:
            cleaned[key] = default_val
            
    return cleaned

def run_guards(params: Dict[str, Any]) -> None:
    """
    Master Guard Function. Runs all checks.
    """
    # 1. Validate Keys
    validate_keys(params)
    
    # 2. Inject Defaults (conceptually happens here, but we usually validate raw input first)
    # The guards usually run on the raw input or the defaulted input.
    # We should validate values on the input AS IS.
    
    # 3. Validate Values
    validate_values(params)
    
    # 4. Enforce Determinism
    enforce_determinism(params)
